"""Regras de negocio da biblioteca.

Os estados que dependem da passagem do tempo (emprestimo atrasado, multa
acumulando, suspensao automatica, expiracao de reserva) sao atualizados por
`processar_pendencias`, executado no inicio de cada requisicao. Assim o banco
fica sempre consistente com o relogio sem depender de um agendador externo.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import clock
from .models import Emprestimo, Exemplar, Livro, Multa, Reserva, Usuario
from .regras import (
    DIAS_ATRASO_BAIXA, DIAS_ATRASO_SUSPENSAO, DIAS_PERDAO_PROFESSOR, FATOR_SUSPENSAO,
    HORAS_RETIRADA_RESERVA, regra,
)

EMPRESTIMO_ABERTO = ("ativo", "atrasado")
RESERVA_NA_FILA = ("aguardando", "disponivel")
EXEMPLAR_CIRCULANTE = ("disponivel", "emprestado", "reservado")
CENTAVO = Decimal("0.01")


# ------------------------------------------------------------------ erros
def conflito(codigo: str, mensagem: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail={"codigo": codigo, "mensagem": mensagem})


def nao_encontrado(entidade: str, id_: int) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{entidade} {id_} nao encontrado(a)")


def obter(db: Session, modelo, id_: int, nome: str):
    obj = db.get(modelo, id_)
    if obj is None:
        raise nao_encontrado(nome, id_)
    return obj


# ------------------------------------------------------------------ calculos
def dias_atraso(emp: Emprestimo, hoje: date | None = None) -> int:
    """Dias corridos entre a data prevista e a devolucao (ou hoje, se em aberto)."""
    fim = emp.data_devolucao.date() if emp.data_devolucao else (hoje or clock.agora().date())
    return max(0, (fim - emp.data_prevista).days)


def valor_multa(categoria: str, dias: int) -> Decimal:
    r = regra(categoria)
    return min(r.multa_diaria * dias, r.teto_multa).quantize(CENTAVO)


# ------------------------------------------------------------------ fila de reservas
def fila_reservas(db: Session, livro_id: int) -> list[Reserva]:
    """Reservas ativas do livro em ordem de atendimento (disponiveis primeiro, depois FIFO)."""
    reservas = db.scalars(
        select(Reserva)
        .where(Reserva.livro_id == livro_id, Reserva.estado.in_(RESERVA_NA_FILA))
        .order_by(Reserva.data, Reserva.id)
    ).all()
    return sorted(reservas, key=lambda r: r.estado != "disponivel")


def posicao_na_fila(db: Session, reserva: Reserva) -> int | None:
    if reserva.estado not in RESERVA_NA_FILA:
        return None
    for i, r in enumerate(fila_reservas(db, reserva.livro_id), start=1):
        if r.id == reserva.id:
            return i
    return None


def liberar_exemplar(db: Session, exemplar: Exemplar, inicio: datetime) -> None:
    """Regra 4: exemplar que volta a circular atende o primeiro da fila, se houver."""
    proxima = db.scalars(
        select(Reserva)
        .where(Reserva.livro_id == exemplar.livro_id, Reserva.estado == "aguardando")
        .order_by(Reserva.data, Reserva.id)
        .limit(1)
    ).first()
    if proxima is None:
        exemplar.estado = "disponivel"
        return
    proxima.estado = "disponivel"
    proxima.exemplar_id = exemplar.id
    proxima.disponivel_em = inicio
    proxima.expira_em = inicio + timedelta(hours=HORAS_RETIRADA_RESERVA)
    exemplar.estado = "reservado"


def devolver_reserva_para_fila(db: Session, exemplar: Exemplar) -> None:
    """Exemplar separado para uma reserva saiu de circulacao: a reserva volta a aguardar."""
    reserva = db.scalars(
        select(Reserva).where(Reserva.exemplar_id == exemplar.id, Reserva.estado == "disponivel")
    ).first()
    if reserva:
        reserva.estado = "aguardando"
        reserva.exemplar_id = None
        reserva.disponivel_em = None
        reserva.expira_em = None


def cancelar_reservas_se_sem_exemplares(db: Session, livro_id: int) -> None:
    """Regra 6: baixado o ultimo exemplar apto a circular, as reservas do livro sao canceladas."""
    db.flush()
    restantes = db.scalar(
        select(func.count()).select_from(Exemplar)
        .where(Exemplar.livro_id == livro_id, Exemplar.estado.in_(EXEMPLAR_CIRCULANTE))
    )
    if restantes:
        return
    for r in db.scalars(
        select(Reserva).where(Reserva.livro_id == livro_id, Reserva.estado.in_(RESERVA_NA_FILA))
    ):
        r.estado = "cancelada"
        r.exemplar_id = None
        r.expira_em = None


# ------------------------------------------------------------------ suspensao e multa
def suspender(usuario: Usuario, ate: date) -> None:
    """Regra 2: suspensao automatica; prevalece a data final mais distante."""
    usuario.situacao = "suspenso"
    usuario.suspensao_automatica = True
    if usuario.suspenso_ate is None or ate > usuario.suspenso_ate:
        usuario.suspenso_ate = ate


def registrar_multa(db: Session, emp: Emprestimo, valor: Decimal, estado: str = "aberta") -> Multa:
    multa = emp.multa
    if multa is None:
        multa = Multa(emprestimo=emp, valor=valor, estado=estado)
        db.add(multa)
    elif multa.estado == "aberta":
        multa.valor = valor
        multa.estado = estado
    return multa


# ------------------------------------------------------------------ processamento temporal
def processar_pendencias(db: Session) -> None:
    agora = clock.agora()
    hoje = agora.date()

    # Regra 4: reserva disponivel nao retirada em 48h expira e a vez passa ao proximo.
    # O prazo do proximo conta a partir da expiracao do anterior.
    while True:
        vencida = db.scalars(
            select(Reserva)
            .where(Reserva.estado == "disponivel", Reserva.expira_em <= agora)
            .order_by(Reserva.expira_em, Reserva.id)
            .limit(1)
        ).first()
        if vencida is None:
            break
        exemplar = vencida.exemplar
        vencida.estado = "expirada"
        db.flush()
        if exemplar is not None and exemplar.estado == "reservado":
            liberar_exemplar(db, exemplar, vencida.expira_em)
        db.flush()

    # Regras 2 e 5: atraso, multa acumulada e suspensao de emprestimos em aberto.
    for emp in db.scalars(
        select(Emprestimo).where(Emprestimo.estado.in_(EMPRESTIMO_ABERTO), Emprestimo.data_prevista < hoje)
    ):
        dias = dias_atraso(emp, hoje)
        emp.estado = "atrasado"
        registrar_multa(db, emp, valor_multa(emp.usuario.categoria, dias))
        if dias > DIAS_ATRASO_SUSPENSAO:
            suspender(emp.usuario, hoje + timedelta(days=FATOR_SUSPENSAO * dias))

    # Fim da suspensao automatica.
    db.flush()
    for u in db.scalars(
        select(Usuario).where(
            Usuario.situacao == "suspenso",
            Usuario.suspensao_automatica.is_(True),
            Usuario.suspenso_ate <= hoje,
        )
    ):
        ainda_grave = any(
            e.estado in EMPRESTIMO_ABERTO and dias_atraso(e, hoje) > DIAS_ATRASO_SUSPENSAO
            for e in u.emprestimos
        )
        if not ainda_grave:
            u.situacao = "ativo"
            u.suspensao_automatica = False
            u.suspenso_ate = None


# ------------------------------------------------------------------ emprestimos
def emprestimos_abertos(db: Session, usuario_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(Emprestimo)
        .where(Emprestimo.usuario_id == usuario_id, Emprestimo.estado.in_(EMPRESTIMO_ABERTO))
    )


def possui_multa_aberta(db: Session, usuario_id: int) -> bool:
    return db.scalar(
        select(func.count()).select_from(Multa).join(Emprestimo)
        .where(Emprestimo.usuario_id == usuario_id, Multa.estado == "aberta")
    ) > 0


def criar_emprestimo(db: Session, usuario_id: int, exemplar_id: int) -> Emprestimo:
    usuario = obter(db, Usuario, usuario_id, "Usuario")
    exemplar = obter(db, Exemplar, exemplar_id, "Exemplar")
    r = regra(usuario.categoria)

    # Regra 1
    if usuario.situacao != "ativo":
        raise conflito("USUARIO_SUSPENSO", "Usuario suspenso nao pode realizar emprestimos")
    if possui_multa_aberta(db, usuario.id):
        raise conflito("MULTA_ABERTA", "Usuario possui multa em aberto")
    if emprestimos_abertos(db, usuario.id) >= r.limite_exemplares:
        raise conflito(
            "LIMITE_EXEMPLARES",
            f"Limite de {r.limite_exemplares} exemplar(es) da categoria {usuario.categoria} atingido",
        )

    # Regra 6 e disponibilidade do exemplar
    if exemplar.estado in ("em_reparo", "baixado"):
        raise conflito("EXEMPLAR_INDISPONIVEL", f"Exemplar {exemplar.estado} nao pode ser emprestado")
    if exemplar.estado == "emprestado":
        raise conflito("EXEMPLAR_EMPRESTADO", "Exemplar ja esta emprestado")

    reserva_do_usuario = db.scalars(
        select(Reserva).where(
            Reserva.livro_id == exemplar.livro_id,
            Reserva.usuario_id == usuario.id,
            Reserva.estado.in_(RESERVA_NA_FILA),
        )
    ).first()
    if exemplar.estado == "reservado" and not (
        reserva_do_usuario is not None
        and reserva_do_usuario.estado == "disponivel"
        and reserva_do_usuario.exemplar_id == exemplar.id
    ):
        raise conflito("EXEMPLAR_RESERVADO", "Exemplar esta separado para outro usuario da fila de reserva")

    agora = clock.agora()
    emp = Emprestimo(
        exemplar=exemplar,
        usuario=usuario,
        data_retirada=agora,
        data_prevista=agora.date() + timedelta(days=r.prazo_dias),
        estado="ativo",
        numero_renovacoes=0,
    )
    db.add(emp)
    exemplar.estado = "emprestado"
    if reserva_do_usuario is not None:
        separado = (
            reserva_do_usuario.exemplar
            if reserva_do_usuario.estado == "disponivel" and reserva_do_usuario.exemplar_id != exemplar.id
            else None
        )
        reserva_do_usuario.estado = "atendida"
        db.flush()
        if separado is not None:
            # Usuario levou outro exemplar: o que estava separado segue para o proximo da fila.
            liberar_exemplar(db, separado, agora)
    db.flush()
    return emp


def renovar_emprestimo(db: Session, emprestimo_id: int) -> Emprestimo:
    emp = obter(db, Emprestimo, emprestimo_id, "Emprestimo")
    if emp.estado == "devolvido":
        raise conflito("EMPRESTIMO_ENCERRADO", "Emprestimo ja foi devolvido")
    # Regra 3
    if emp.estado == "atrasado" or dias_atraso(emp) > 0:
        raise conflito("EMPRESTIMO_ATRASADO", "Emprestimo atrasado nao pode ser renovado")
    r = regra(emp.usuario.categoria)
    if emp.numero_renovacoes >= r.max_renovacoes:
        raise conflito(
            "LIMITE_RENOVACOES",
            f"Limite de {r.max_renovacoes} renovacao(oes) da categoria {emp.usuario.categoria} atingido",
        )
    if fila_reservas(db, emp.exemplar.livro_id):
        raise conflito("FILA_RESERVA", "Ha fila de reserva para este livro")

    emp.numero_renovacoes += 1
    emp.data_prevista = clock.agora().date() + timedelta(days=r.prazo_dias)
    db.flush()
    return emp


def devolver_emprestimo(db: Session, emprestimo_id: int) -> Emprestimo:
    emp = obter(db, Emprestimo, emprestimo_id, "Emprestimo")
    if emp.estado == "devolvido":
        raise conflito("EMPRESTIMO_ENCERRADO", "Emprestimo ja foi devolvido")

    agora = clock.agora()
    usuario, exemplar = emp.usuario, emp.exemplar
    r = regra(usuario.categoria)

    emp.data_devolucao = agora
    emp.estado = "devolvido"
    dias = dias_atraso(emp)
    baixar = dias > DIAS_ATRASO_BAIXA

    if dias > 0:
        if baixar:
            # Regra 7: multa no valor do teto da categoria.
            registrar_multa(db, emp, r.teto_multa.quantize(CENTAVO))
        elif usuario.categoria == "professor" and dias <= DIAS_PERDAO_PROFESSOR:
            # Regra 5: perdao automatico para professor.
            registrar_multa(db, emp, valor_multa(usuario.categoria, dias), "perdoada")
        else:
            registrar_multa(db, emp, valor_multa(usuario.categoria, dias))
        if dias > DIAS_ATRASO_SUSPENSAO:
            # Regra 2: suspensao pelo dobro dos dias de atraso, contada da devolucao.
            suspender(usuario, agora.date() + timedelta(days=FATOR_SUSPENSAO * dias))

    if baixar:
        exemplar.estado = "baixado"
        cancelar_reservas_se_sem_exemplares(db, exemplar.livro_id)
    else:
        liberar_exemplar(db, exemplar, agora)
    db.flush()
    return emp


# ------------------------------------------------------------------ exemplares
def alterar_estado_exemplar(db: Session, exemplar: Exemplar, novo: str) -> None:
    atual = exemplar.estado
    if novo == atual:
        return
    if atual == "emprestado":
        raise conflito("EXEMPLAR_EMPRESTADO", "Exemplar emprestado so muda de estado pela devolucao")
    if atual == "baixado":
        raise conflito("EXEMPLAR_BAIXADO", "Exemplar baixado nao pode voltar a circular")
    if atual == "reservado":
        devolver_reserva_para_fila(db, exemplar)
        db.flush()

    if novo == "disponivel":
        liberar_exemplar(db, exemplar, clock.agora())
    else:
        exemplar.estado = novo
        if novo == "baixado":
            cancelar_reservas_se_sem_exemplares(db, exemplar.livro_id)
    db.flush()


# ------------------------------------------------------------------ reservas
def criar_reserva(db: Session, usuario_id: int, livro_id: int) -> Reserva:
    usuario = obter(db, Usuario, usuario_id, "Usuario")
    livro = obter(db, Livro, livro_id, "Livro")

    if usuario.situacao != "ativo":
        raise conflito("USUARIO_SUSPENSO", "Usuario suspenso nao pode fazer reservas")
    if db.scalar(
        select(func.count()).select_from(Reserva).where(
            Reserva.livro_id == livro.id, Reserva.usuario_id == usuario.id,
            Reserva.estado.in_(RESERVA_NA_FILA),
        )
    ):
        raise conflito("RESERVA_DUPLICADA", "Usuario ja possui reserva ativa para este livro")
    if db.scalar(
        select(func.count()).select_from(Emprestimo).join(Exemplar).where(
            Exemplar.livro_id == livro.id, Emprestimo.usuario_id == usuario.id,
            Emprestimo.estado.in_(EMPRESTIMO_ABERTO),
        )
    ):
        raise conflito("LIVRO_JA_EMPRESTADO", "Usuario ja esta com um exemplar deste livro")

    estados = db.scalars(select(Exemplar.estado).where(Exemplar.livro_id == livro.id)).all()
    if "disponivel" in estados:
        raise conflito("EXEMPLAR_DISPONIVEL", "Ha exemplar disponivel; realize o emprestimo diretamente")
    if not any(e in EXEMPLAR_CIRCULANTE for e in estados):
        # Regra 6: exemplares em reparo ou baixados nao podem ser reservados.
        raise conflito("SEM_EXEMPLAR_RESERVAVEL", "Livro nao possui exemplar em circulacao para reserva")

    reserva = Reserva(livro=livro, usuario=usuario, data=clock.agora(), estado="aguardando")
    db.add(reserva)
    db.flush()
    return reserva


def cancelar_reserva(db: Session, reserva_id: int) -> Reserva:
    reserva = obter(db, Reserva, reserva_id, "Reserva")
    if reserva.estado not in RESERVA_NA_FILA:
        raise conflito("RESERVA_ENCERRADA", f"Reserva ja esta {reserva.estado}")
    exemplar = reserva.exemplar if reserva.estado == "disponivel" else None
    reserva.estado = "cancelada"
    db.flush()
    if exemplar is not None and exemplar.estado == "reservado":
        liberar_exemplar(db, exemplar, clock.agora())
    db.flush()
    return reserva


# ------------------------------------------------------------------ multas
def pagar_multa(db: Session, multa_id: int, valor: Decimal | None) -> Multa:
    multa = obter(db, Multa, multa_id, "Multa")
    if multa.estado != "aberta":
        raise conflito("MULTA_NAO_ABERTA", f"Multa ja esta {multa.estado}")
    if multa.emprestimo.estado != "devolvido":
        raise conflito(
            "MULTA_EM_APURACAO",
            "Multa ainda acumula; o exemplar precisa ser devolvido antes do pagamento",
        )
    if valor is not None and valor.quantize(CENTAVO) != Decimal(multa.valor).quantize(CENTAVO):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Valor informado difere do valor da multa (R$ {multa.valor:.2f}); nao ha pagamento parcial",
        )
    multa.estado = "paga"
    multa.data_pagamento = clock.agora()
    db.flush()
    return multa

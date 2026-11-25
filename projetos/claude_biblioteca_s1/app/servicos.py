"""Regras de negocio da biblioteca.

Os eventos dependentes do tempo (atraso, multa acumulada, suspensao, expiracao de reserva)
sao processados de forma preguicosa por `sincronizar`, executada no inicio de cada requisicao.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app import relogio
from app.erros import Conflito, NaoEncontrado
from app.models import (Categoria, Emprestimo, EstadoEmprestimo, EstadoExemplar, EstadoMulta,
                        EstadoReserva, Exemplar, Livro, Multa, Reserva, SituacaoUsuario, Usuario)
from app.regras import (ATRASO_PARA_BAIXA_DIAS, ATRASO_PARA_SUSPENSAO_DIAS, FATOR_DURACAO_SUSPENSAO,
                        PRAZO_RETIRADA_RESERVA, REGRAS, TOLERANCIA_PERDAO_PROFESSOR_DIAS)

EMPRESTIMO_EM_ABERTO = (EstadoEmprestimo.ATIVO, EstadoEmprestimo.ATRASADO)
RESERVA_ATIVA = (EstadoReserva.AGUARDANDO, EstadoReserva.DISPONIVEL)
# Exemplares que ainda podem atender uma reserva (regra 6: em reparo/baixado nao podem ser reservados)
EXEMPLAR_RESERVAVEL = (EstadoExemplar.DISPONIVEL, EstadoExemplar.EMPRESTADO, EstadoExemplar.RESERVADO)


def obter(db: Session, modelo, id_: int, nome: str):
    obj = db.get(modelo, id_)
    if obj is None:
        raise NaoEncontrado(f"{nome} {id_} nao encontrado(a)")
    return obj


# ======================================================================
# Calculos
# ======================================================================
def dias_atraso(emp: Emprestimo, referencia: date) -> int:
    return max(0, (referencia - emp.data_prevista).days)


def calcular_multa_centavos(categoria: Categoria, dias: int) -> int:
    regra = REGRAS[categoria]
    return min(dias * regra.multa_diaria_centavos, regra.teto_multa_centavos)


def _suspender(usuario: Usuario, ate: date) -> None:
    """Regra 2. Uma suspensao manual (sem data de fim) nao e convertida em suspensao temporaria."""
    if usuario.situacao == SituacaoUsuario.SUSPENSO and usuario.suspenso_ate is None:
        return
    usuario.situacao = SituacaoUsuario.SUSPENSO
    if usuario.suspenso_ate is None or ate > usuario.suspenso_ate:
        usuario.suspenso_ate = ate


def _aplicar_suspensao_por_atraso(usuario: Usuario, dias: int, referencia: date) -> None:
    if dias > ATRASO_PARA_SUSPENSAO_DIAS:
        _suspender(usuario, referencia + timedelta(days=FATOR_DURACAO_SUSPENSAO * dias))


def _registrar_multa(db: Session, emp: Emprestimo, dias: int, final: bool) -> Multa:
    """Regra 5 (e 7 quando final e atraso > 60 dias)."""
    categoria = emp.usuario.categoria
    if final and dias > ATRASO_PARA_BAIXA_DIAS:
        valor = REGRAS[categoria].teto_multa_centavos
    else:
        valor = calcular_multa_centavos(categoria, dias)

    multa = emp.multa
    if multa is None:
        multa = Multa(emprestimo=emp, valor_centavos=valor, dias_atraso=dias, estado=EstadoMulta.ABERTA)
        db.add(multa)
    elif multa.estado == EstadoMulta.ABERTA:
        multa.valor_centavos = valor
        multa.dias_atraso = dias

    if (final and multa.estado == EstadoMulta.ABERTA and categoria == Categoria.PROFESSOR
            and dias <= TOLERANCIA_PERDAO_PROFESSOR_DIAS):
        multa.estado = EstadoMulta.PERDOADA
    return multa


# ======================================================================
# Fila de reservas
# ======================================================================
def _reservas_ativas(db: Session, livro_id: int) -> list[Reserva]:
    ordem_estado = case((Reserva.estado == EstadoReserva.DISPONIVEL, 0), else_=1)
    return list(db.scalars(
        select(Reserva)
        .where(Reserva.livro_id == livro_id, Reserva.estado.in_(RESERVA_ATIVA))
        .order_by(ordem_estado, Reserva.data, Reserva.id)
    ))


def recalcular_fila(db: Session, livro_id: int) -> None:
    db.flush()
    for i, r in enumerate(_reservas_ativas(db, livro_id), start=1):
        r.posicao = i


def _encerrar_reserva(r: Reserva, estado: EstadoReserva) -> None:
    r.estado = estado
    r.posicao = None
    r.expira_em = None if estado == EstadoReserva.CANCELADA else r.expira_em


def encaminhar_exemplar(db: Session, exemplar: Exemplar, agora: datetime) -> None:
    """Regra 4: exemplar liberado vai para o primeiro da fila (48h para retirada) ou fica disponivel."""
    db.flush()
    proxima = db.scalars(
        select(Reserva)
        .where(Reserva.livro_id == exemplar.livro_id, Reserva.estado == EstadoReserva.AGUARDANDO)
        .order_by(Reserva.data, Reserva.id)
        .limit(1)
    ).first()
    if proxima:
        proxima.estado = EstadoReserva.DISPONIVEL
        proxima.exemplar_id = exemplar.id
        proxima.expira_em = agora + PRAZO_RETIRADA_RESERVA
        exemplar.estado = EstadoExemplar.RESERVADO
    else:
        exemplar.estado = EstadoExemplar.DISPONIVEL
    recalcular_fila(db, exemplar.livro_id)


def _devolver_reserva_a_fila(db: Session, exemplar: Exemplar) -> None:
    """Exemplar separado para uma reserva saiu de circulacao: a reserva volta a aguardar (mantendo a ordem)."""
    reserva = db.scalars(select(Reserva).where(
        Reserva.exemplar_id == exemplar.id, Reserva.estado == EstadoReserva.DISPONIVEL)).first()
    if reserva:
        reserva.estado = EstadoReserva.AGUARDANDO
        reserva.exemplar_id = None
        reserva.expira_em = None


def verificar_cancelamento_reservas(db: Session, livro_id: int) -> None:
    """Regra 6: sem exemplar que possa atender reservas, todas as reservas do livro sao canceladas."""
    db.flush()
    restantes = db.scalar(select(func.count(Exemplar.id)).where(
        Exemplar.livro_id == livro_id, Exemplar.estado.in_(EXEMPLAR_RESERVAVEL)))
    if restantes == 0:
        for r in _reservas_ativas(db, livro_id):
            _encerrar_reserva(r, EstadoReserva.CANCELADA)
            r.exemplar_id = None


# ======================================================================
# Sincronizacao temporal
# ======================================================================
def sincronizar(db: Session) -> None:
    agora = relogio.agora()
    hoje = agora.date()

    # Regra 4: reservas disponiveis nao retiradas em 48h expiram e a vez passa ao proximo
    expiradas = db.scalars(select(Reserva).where(
        Reserva.estado == EstadoReserva.DISPONIVEL, Reserva.expira_em <= agora
    ).order_by(Reserva.expira_em, Reserva.id)).all()
    for r in expiradas:
        _encerrar_reserva(r, EstadoReserva.EXPIRADA)
        exemplar = r.exemplar
        if exemplar is not None and exemplar.estado == EstadoExemplar.RESERVADO:
            encaminhar_exemplar(db, exemplar, agora)

    # Regras 2 e 5: atraso, multa acumulada e suspensao
    abertos = db.scalars(select(Emprestimo).where(Emprestimo.estado.in_(EMPRESTIMO_EM_ABERTO))).all()
    for emp in abertos:
        dias = dias_atraso(emp, hoje)
        if dias > 0:
            emp.estado = EstadoEmprestimo.ATRASADO
            _registrar_multa(db, emp, dias, final=False)
            _aplicar_suspensao_por_atraso(emp.usuario, dias, hoje)

    # Fim de suspensoes automaticas
    db.flush()
    for u in db.scalars(select(Usuario).where(
            Usuario.situacao == SituacaoUsuario.SUSPENSO, Usuario.suspenso_ate.is_not(None),
            Usuario.suspenso_ate <= hoje)):
        u.situacao = SituacaoUsuario.ATIVO
        u.suspenso_ate = None

    db.commit()


# ======================================================================
# Usuarios / Livros / Exemplares
# ======================================================================
def _checar_unico(db: Session, modelo, campo: str, valor, ignorar_id: int | None = None) -> None:
    coluna = getattr(modelo, campo)
    existente = db.scalars(select(modelo).where(coluna == valor)).first()
    if existente is not None and existente.id != ignorar_id:
        raise Conflito(f"Ja existe registro com {campo} = '{valor}'")


def salvar_usuario(db: Session, dados: dict, usuario: Usuario | None = None) -> Usuario:
    if "email" in dados:
        dados["email"] = dados["email"].lower()
        _checar_unico(db, Usuario, "email", dados["email"], usuario and usuario.id)
    if "matricula" in dados:
        _checar_unico(db, Usuario, "matricula", dados["matricula"], usuario and usuario.id)
    if usuario is None:
        usuario = Usuario()
        db.add(usuario)
    for k, v in dados.items():
        setattr(usuario, k, v)
    if "situacao" in dados:
        # alteracao manual: ativar encerra a suspensao; suspender manualmente e por tempo indeterminado
        usuario.suspenso_ate = None
    db.commit()
    return usuario


def excluir_usuario(db: Session, usuario: Usuario) -> None:
    if usuario.emprestimos or usuario.reservas:
        raise Conflito("Usuario possui historico de emprestimos/reservas e nao pode ser excluido")
    db.delete(usuario)
    db.commit()


def salvar_livro(db: Session, dados: dict, livro: Livro | None = None) -> Livro:
    if "isbn" in dados:
        _checar_unico(db, Livro, "isbn", dados["isbn"], livro and livro.id)
    if livro is None:
        livro = Livro()
        db.add(livro)
    for k, v in dados.items():
        setattr(livro, k, v)
    db.commit()
    return livro


def excluir_livro(db: Session, livro: Livro) -> None:
    if livro.exemplares:
        raise Conflito("Livro possui exemplares cadastrados e nao pode ser excluido")
    if db.scalar(select(func.count(Reserva.id)).where(Reserva.livro_id == livro.id)):
        raise Conflito("Livro possui historico de reservas e nao pode ser excluido")
    db.delete(livro)
    db.commit()


def criar_exemplar(db: Session, dados: dict) -> Exemplar:
    obter(db, Livro, dados["livro_id"], "Livro")
    _checar_unico(db, Exemplar, "codigo_tombo", dados["codigo_tombo"])
    exemplar = Exemplar(livro_id=dados["livro_id"], codigo_tombo=dados["codigo_tombo"],
                        estado=EstadoExemplar(dados.get("estado", EstadoExemplar.DISPONIVEL)))
    db.add(exemplar)
    if exemplar.estado == EstadoExemplar.DISPONIVEL:
        encaminhar_exemplar(db, exemplar, relogio.agora())  # atende fila de reservas, se houver
    db.commit()
    return exemplar


def atualizar_exemplar(db: Session, exemplar: Exemplar, dados: dict) -> Exemplar:
    if "codigo_tombo" in dados and dados["codigo_tombo"] != exemplar.codigo_tombo:
        _checar_unico(db, Exemplar, "codigo_tombo", dados["codigo_tombo"], exemplar.id)
        exemplar.codigo_tombo = dados["codigo_tombo"]

    novo = dados.get("estado")
    if novo is not None and novo != exemplar.estado:
        novo = EstadoExemplar(novo)
        atual = exemplar.estado
        if atual == EstadoExemplar.BAIXADO:
            raise Conflito("Exemplar baixado nao pode mudar de estado")
        if atual == EstadoExemplar.EMPRESTADO:
            raise Conflito("Exemplar emprestado deve ser devolvido antes de mudar de estado")
        if atual == EstadoExemplar.RESERVADO:
            if novo == EstadoExemplar.DISPONIVEL:
                raise Conflito("Exemplar esta separado para uma reserva")
            _devolver_reserva_a_fila(db, exemplar)

        if novo == EstadoExemplar.DISPONIVEL:
            encaminhar_exemplar(db, exemplar, relogio.agora())
        else:
            exemplar.estado = novo
            recalcular_fila(db, exemplar.livro_id)
            if novo == EstadoExemplar.BAIXADO:
                verificar_cancelamento_reservas(db, exemplar.livro_id)
    db.commit()
    return exemplar


def excluir_exemplar(db: Session, exemplar: Exemplar) -> None:
    if exemplar.emprestimos:
        raise Conflito("Exemplar possui historico de emprestimos; utilize a baixa (estado 'baixado')")
    if exemplar.estado == EstadoExemplar.RESERVADO:
        raise Conflito("Exemplar esta separado para uma reserva")
    livro_id = exemplar.livro_id
    db.delete(exemplar)
    verificar_cancelamento_reservas(db, livro_id)
    db.commit()


# ======================================================================
# Emprestimos
# ======================================================================
def criar_emprestimo(db: Session, usuario_id: int, exemplar_id: int) -> Emprestimo:
    usuario = obter(db, Usuario, usuario_id, "Usuario")
    exemplar = obter(db, Exemplar, exemplar_id, "Exemplar")
    agora = relogio.agora()
    hoje = agora.date()

    # Regra 1
    if usuario.situacao != SituacaoUsuario.ATIVO:
        raise Conflito("Usuario suspenso nao pode realizar emprestimos")
    multas_abertas = db.scalar(select(func.count(Multa.id)).join(Emprestimo).where(
        Emprestimo.usuario_id == usuario.id, Multa.estado == EstadoMulta.ABERTA))
    if multas_abertas:
        raise Conflito("Usuario possui multa em aberto")
    regra = REGRAS[usuario.categoria]
    em_aberto = db.scalar(select(func.count(Emprestimo.id)).where(
        Emprestimo.usuario_id == usuario.id, Emprestimo.estado.in_(EMPRESTIMO_EM_ABERTO)))
    if em_aberto >= regra.limite_exemplares:
        raise Conflito(f"Limite de {regra.limite_exemplares} exemplar(es) da categoria "
                       f"'{usuario.categoria}' atingido")

    # Regra 6 e reservas
    reserva_do_usuario = None
    if exemplar.estado == EstadoExemplar.RESERVADO:
        reserva_do_usuario = db.scalars(select(Reserva).where(
            Reserva.exemplar_id == exemplar.id, Reserva.estado == EstadoReserva.DISPONIVEL)).first()
        if reserva_do_usuario is None or reserva_do_usuario.usuario_id != usuario.id:
            raise Conflito("Exemplar reservado para outro usuario")
    elif exemplar.estado != EstadoExemplar.DISPONIVEL:
        raise Conflito(f"Exemplar indisponivel para emprestimo (estado: {exemplar.estado})")
    else:
        # usuario com reserva aguardando para o mesmo livro: a reserva e atendida
        reserva_do_usuario = db.scalars(select(Reserva).where(
            Reserva.livro_id == exemplar.livro_id, Reserva.usuario_id == usuario.id,
            Reserva.estado.in_(RESERVA_ATIVA))).first()

    if reserva_do_usuario is not None:
        separado = reserva_do_usuario.exemplar
        _encerrar_reserva(reserva_do_usuario, EstadoReserva.ATENDIDA)
        if separado is not None and separado.id != exemplar.id and separado.estado == EstadoExemplar.RESERVADO:
            encaminhar_exemplar(db, separado, agora)  # libera o outro exemplar separado ao usuario

    emp = Emprestimo(exemplar=exemplar, usuario=usuario, data_retirada=hoje,
                     data_prevista=hoje + timedelta(days=regra.prazo_dias),
                     estado=EstadoEmprestimo.ATIVO, renovacoes=0)
    db.add(emp)
    exemplar.estado = EstadoExemplar.EMPRESTADO
    recalcular_fila(db, exemplar.livro_id)
    db.commit()
    return emp


def renovar_emprestimo(db: Session, emp: Emprestimo) -> Emprestimo:
    hoje = relogio.agora().date()
    if emp.estado == EstadoEmprestimo.DEVOLVIDO:
        raise Conflito("Emprestimo ja devolvido")
    # Regra 3
    if emp.estado == EstadoEmprestimo.ATRASADO or dias_atraso(emp, hoje) > 0:
        raise Conflito("Emprestimo atrasado nao pode ser renovado")
    regra = REGRAS[emp.usuario.categoria]
    if emp.renovacoes >= regra.max_renovacoes:
        raise Conflito(f"Limite de {regra.max_renovacoes} renovacao(oes) da categoria "
                       f"'{emp.usuario.categoria}' atingido")
    fila = db.scalar(select(func.count(Reserva.id)).where(
        Reserva.livro_id == emp.exemplar.livro_id, Reserva.estado.in_(RESERVA_ATIVA)))
    if fila:
        raise Conflito("Ha fila de reserva para este livro")

    emp.renovacoes += 1
    emp.data_prevista = hoje + timedelta(days=regra.prazo_dias)
    db.commit()
    return emp


def devolver_emprestimo(db: Session, emp: Emprestimo) -> Emprestimo:
    if emp.estado == EstadoEmprestimo.DEVOLVIDO:
        raise Conflito("Emprestimo ja devolvido")
    agora = relogio.agora()
    hoje = agora.date()
    dias = dias_atraso(emp, hoje)

    emp.data_devolucao = hoje
    emp.estado = EstadoEmprestimo.DEVOLVIDO
    if dias > 0:
        _registrar_multa(db, emp, dias, final=True)          # regras 5 e 7
        _aplicar_suspensao_por_atraso(emp.usuario, dias, hoje)  # regra 2

    exemplar = emp.exemplar
    if dias > ATRASO_PARA_BAIXA_DIAS:                         # regra 7
        exemplar.estado = EstadoExemplar.BAIXADO
        verificar_cancelamento_reservas(db, exemplar.livro_id)  # regra 6
    else:
        encaminhar_exemplar(db, exemplar, agora)              # regra 4
    db.commit()
    return emp


# ======================================================================
# Reservas
# ======================================================================
def criar_reserva(db: Session, usuario_id: int, livro_id: int) -> Reserva:
    usuario = obter(db, Usuario, usuario_id, "Usuario")
    livro = obter(db, Livro, livro_id, "Livro")
    if usuario.situacao != SituacaoUsuario.ATIVO:
        raise Conflito("Usuario suspenso nao pode realizar reservas")

    contagem = dict(db.execute(select(Exemplar.estado, func.count(Exemplar.id))
                               .where(Exemplar.livro_id == livro.id).group_by(Exemplar.estado)).all())
    if contagem.get(EstadoExemplar.DISPONIVEL, 0):
        raise Conflito("Ha exemplar disponivel deste livro; realize o emprestimo diretamente")
    if not any(contagem.get(e, 0) for e in EXEMPLAR_RESERVAVEL):
        raise Conflito("Livro nao possui exemplares que possam ser reservados (em reparo, baixados ou inexistentes)")

    duplicada = db.scalar(select(func.count(Reserva.id)).where(
        Reserva.livro_id == livro.id, Reserva.usuario_id == usuario.id, Reserva.estado.in_(RESERVA_ATIVA)))
    if duplicada:
        raise Conflito("Usuario ja possui reserva ativa para este livro")
    com_usuario = db.scalar(select(func.count(Emprestimo.id)).join(Exemplar).where(
        Exemplar.livro_id == livro.id, Emprestimo.usuario_id == usuario.id,
        Emprestimo.estado.in_(EMPRESTIMO_EM_ABERTO)))
    if com_usuario:
        raise Conflito("Usuario ja esta com um exemplar deste livro emprestado")

    reserva = Reserva(livro_id=livro.id, usuario_id=usuario.id, data=relogio.agora(),
                      estado=EstadoReserva.AGUARDANDO)
    db.add(reserva)
    recalcular_fila(db, livro.id)
    db.commit()
    return reserva


def cancelar_reserva(db: Session, reserva: Reserva) -> Reserva:
    if reserva.estado not in RESERVA_ATIVA:
        raise Conflito(f"Reserva no estado '{reserva.estado}' nao pode ser cancelada")
    exemplar = reserva.exemplar if reserva.estado == EstadoReserva.DISPONIVEL else None
    _encerrar_reserva(reserva, EstadoReserva.CANCELADA)
    if exemplar is not None and exemplar.estado == EstadoExemplar.RESERVADO:
        encaminhar_exemplar(db, exemplar, relogio.agora())
    recalcular_fila(db, reserva.livro_id)
    db.commit()
    return reserva


def fila_do_livro(db: Session, livro_id: int, incluir_encerradas: bool) -> list[Reserva]:
    obter(db, Livro, livro_id, "Livro")
    if not incluir_encerradas:
        return _reservas_ativas(db, livro_id)
    return list(db.scalars(select(Reserva).where(Reserva.livro_id == livro_id)
                           .order_by(Reserva.data, Reserva.id)))


# ======================================================================
# Multas
# ======================================================================
def pagar_multa(db: Session, multa: Multa) -> Multa:
    if multa.estado != EstadoMulta.ABERTA:
        raise Conflito(f"Multa no estado '{multa.estado}' nao pode ser paga")
    if multa.emprestimo.estado != EstadoEmprestimo.DEVOLVIDO:
        raise Conflito("Multa ainda em acumulo: devolva o exemplar antes de registrar o pagamento")
    multa.estado = EstadoMulta.PAGA
    multa.data_pagamento = relogio.agora()
    db.commit()
    return multa


# ======================================================================
# Relatorios
# ======================================================================
def relatorio_mais_emprestados(db: Session, inicio: date, fim: date, limite: int) -> list[dict]:
    total = func.count(Emprestimo.id).label("total")
    linhas = db.execute(
        select(Livro.id, Livro.titulo, Livro.autor, total)
        .join(Exemplar, Exemplar.livro_id == Livro.id)
        .join(Emprestimo, Emprestimo.exemplar_id == Exemplar.id)
        .where(Emprestimo.data_retirada >= inicio, Emprestimo.data_retirada <= fim)
        .group_by(Livro.id, Livro.titulo, Livro.autor)
        .order_by(total.desc(), Livro.titulo)
        .limit(limite)
    ).all()
    return [dict(livro_id=i, titulo=t, autor=a, total_emprestimos=n) for i, t, a, n in linhas]


def relatorio_usuarios_atrasos(db: Session, limite: int) -> list[dict]:
    hoje = relogio.agora().date()
    por_usuario: dict[int, dict] = {}
    for emp in db.scalars(select(Emprestimo)):
        referencia = emp.data_devolucao or hoje
        dias = dias_atraso(emp, referencia)
        if dias <= 0:
            continue
        u = emp.usuario
        item = por_usuario.setdefault(u.id, dict(usuario_id=u.id, nome=u.nome, categoria=u.categoria,
                                                 emprestimos_atrasados=0, total_dias_atraso=0))
        item["emprestimos_atrasados"] += 1
        item["total_dias_atraso"] += dias
    ordenado = sorted(por_usuario.values(),
                      key=lambda x: (-x["emprestimos_atrasados"], -x["total_dias_atraso"], x["nome"]))
    return ordenado[:limite]


def relatorio_ocupacao(db: Session) -> list[dict]:
    linhas = db.execute(
        select(Livro.area, Exemplar.estado, func.count(Exemplar.id))
        .join(Exemplar, Exemplar.livro_id == Livro.id)
        .group_by(Livro.area, Exemplar.estado)
    ).all()
    areas: dict[str, dict[EstadoExemplar, int]] = {}
    for area, estado, n in linhas:
        areas.setdefault(area, {})[EstadoExemplar(estado)] = n
    resultado = []
    for area in sorted(areas):
        c = areas[area]
        total = sum(n for e, n in c.items() if e != EstadoExemplar.BAIXADO)
        emprestados = c.get(EstadoExemplar.EMPRESTADO, 0)
        resultado.append(dict(
            area=area, total_exemplares=total,
            disponiveis=c.get(EstadoExemplar.DISPONIVEL, 0), emprestados=emprestados,
            reservados=c.get(EstadoExemplar.RESERVADO, 0), em_reparo=c.get(EstadoExemplar.EM_REPARO, 0),
            taxa_ocupacao=round(100 * emprestados / total, 2) if total else 0.0,
        ))
    return resultado

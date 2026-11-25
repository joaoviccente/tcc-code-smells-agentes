from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
from fastapi import HTTPException, status

from app.models import (
    Usuario,
    Livro,
    Exemplar,
    Emprestimo,
    Reserva,
    Multa,
    CategoriaUsuario,
    SituacaoUsuario,
    EstadoExemplar,
    EstadoEmprestimo,
    EstadoReserva,
    EstadoMulta,
)
from app.rules import (
    get_regras_categoria,
    calcular_dias_atraso,
    DIAS_ATRASO_SUSPENSAO,
    FATOR_SUSPENSAO,
    HORAS_LIMITE_RETIRADA_RESERVA,
    DIAS_TOLERANCIA_PROFESSOR,
    DIAS_ATRASO_BAIXA,
)

def now_datetime() -> datetime:
    """Retorna datetime UTC sem timezone (compatível com SQLite)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

# ----------------- REGRAS & UTILITÁRIOS -----------------

def atualizar_status_atrasos_usuario(db: Session, usuario_id: int, now: Optional[datetime] = None) -> None:
    """Atualiza o estado de empréstimos em atraso e aplica suspensão caso atraso > 15 dias."""
    if now is None:
        now = now_datetime()
    
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        return

    # Verificar se a suspensão atual já expirou
    if usuario.situacao == SituacaoUsuario.suspenso:
        if usuario.data_fim_suspensao and usuario.data_fim_suspensao <= now:
            usuario.situacao = SituacaoUsuario.ativo
            usuario.data_fim_suspensao = None
            db.add(usuario)

    # Verificar empréstimos ativos com data prevista vencida
    emprestimos_vencidos = db.query(Emprestimo).filter(
        Emprestimo.usuario_id == usuario_id,
        Emprestimo.estado.in_([EstadoEmprestimo.ativo, EstadoEmprestimo.atrasado]),
        Emprestimo.data_prevista < now
    ).all()

    maior_suspensao_dias = 0
    for emp in emprestimos_vencidos:
        emp.estado = EstadoEmprestimo.atrasado
        dias_atraso = calcular_dias_atraso(emp.data_prevista, now)
        if dias_atraso > DIAS_ATRASO_SUSPENSAO:
            dias_suspensao = dias_atraso * FATOR_SUSPENSAO
            if dias_suspensao > maior_suspensao_dias:
                maior_suspensao_dias = dias_suspensao

    if maior_suspensao_dias > 0:
        usuario.situacao = SituacaoUsuario.suspenso
        fim_suspensao = now + timedelta(days=maior_suspensao_dias)
        if not usuario.data_fim_suspensao or usuario.data_fim_suspensao < fim_suspensao:
            usuario.data_fim_suspensao = fim_suspensao
        db.add(usuario)

    db.commit()

def verificar_reservas_expiradas(db: Session, livro_id: Optional[int] = None, now: Optional[datetime] = None) -> None:
    """Verifica e expira reservas com prazo de 48h esgotado, passando a vez ao próximo da fila."""
    if now is None:
        now = now_datetime()

    query = db.query(Reserva).filter(
        Reserva.estado == EstadoReserva.disponivel,
        Reserva.data_limite_retirada.isnot(None),
        Reserva.data_limite_retirada <= now
    )
    if livro_id:
        query = query.filter(Reserva.livro_id == livro_id)

    reservas_expiradas = query.all()
    for res in reservas_expiradas:
        res.estado = EstadoReserva.expirada
        res.posicao_fila = None
        exemplar = res.exemplar
        res.exemplar_id = None
        db.add(res)

        # Passar a vez ao próximo da fila
        proxima = db.query(Reserva).filter(
            Reserva.livro_id == res.livro_id,
            Reserva.estado == EstadoReserva.aguardando
        ).order_by(Reserva.posicao_fila.asc(), Reserva.data.asc()).first()

        if proxima and exemplar and exemplar.estado != EstadoExemplar.baixado:
            proxima.estado = EstadoReserva.disponivel
            proxima.data_limite_retirada = now + timedelta(hours=HORAS_LIMITE_RETIRADA_RESERVA)
            proxima.exemplar_id = exemplar.id
            proxima.posicao_fila = 1
            exemplar.estado = EstadoExemplar.reservado
            db.add(proxima)
            db.add(exemplar)
            reordenar_fila_reservas(db, res.livro_id, exclude_id=proxima.id)
        elif exemplar and exemplar.estado != EstadoExemplar.baixado:
            exemplar.estado = EstadoExemplar.disponivel
            db.add(exemplar)

    db.commit()

def reordenar_fila_reservas(db: Session, livro_id: int, exclude_id: Optional[int] = None) -> None:
    """Reordena posições das reservas aguardando fila."""
    # Verificar se existe alguma disponível ocupando a posição 1
    disp = db.query(Reserva).filter(
        Reserva.livro_id == livro_id,
        Reserva.estado == EstadoReserva.disponivel
    ).first()

    inicio = 2 if disp else 1

    query = db.query(Reserva).filter(
        Reserva.livro_id == livro_id,
        Reserva.estado == EstadoReserva.aguardando
    )
    if exclude_id:
        query = query.filter(Reserva.id != exclude_id)

    reservas = query.order_by(Reserva.posicao_fila.asc(), Reserva.data.asc()).all()
    pos = inicio
    for r in reservas:
        r.posicao_fila = pos
        db.add(r)
        pos += 1

def verificar_e_cancelar_reservas_se_sem_exemplares(db: Session, livro_id: int) -> None:
    """Regra 6: se o último exemplar disponível de um livro for baixado, todas as reservas são canceladas."""
    validos = db.query(Exemplar).filter(
        Exemplar.livro_id == livro_id,
        ~Exemplar.estado.in_([EstadoExemplar.baixado, EstadoExemplar.em_reparo])
    ).count()

    if validos == 0:
        reservas_ativas = db.query(Reserva).filter(
            Reserva.livro_id == livro_id,
            Reserva.estado.in_([EstadoReserva.aguardando, EstadoReserva.disponivel])
        ).all()
        for r in reservas_ativas:
            r.estado = EstadoReserva.cancelada
            r.posicao_fila = None
            r.exemplar_id = None
            db.add(r)
        db.commit()

# ----------------- USUÁRIOS -----------------

def get_usuarios(db: Session, categoria: Optional[CategoriaUsuario] = None, situacao: Optional[SituacaoUsuario] = None) -> List[Usuario]:
    query = db.query(Usuario)
    if categoria:
        query = query.filter(Usuario.categoria == categoria)
    if situacao:
        query = query.filter(Usuario.situacao == situacao)
    return query.all()

def get_usuario(db: Session, usuario_id: int) -> Usuario:
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    atualizar_status_atrasos_usuario(db, usuario.id)
    return usuario

def criar_usuario(db: Session, dados: Any) -> Usuario:
    # Checar duplicidade de e-mail e matrícula
    if db.query(Usuario).filter(Usuario.email == dados.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="E-mail já cadastrado.")
    if db.query(Usuario).filter(Usuario.matricula == dados.matricula).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matrícula já cadastrada.")

    usuario = Usuario(
        nome=dados.nome,
        email=dados.email,
        matricula=dados.matricula,
        categoria=dados.categoria,
        situacao=SituacaoUsuario.ativo,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario

def atualizar_usuario(db: Session, usuario_id: int, dados: Any) -> Usuario:
    usuario = get_usuario(db, usuario_id)
    if dados.email and dados.email != usuario.email:
        if db.query(Usuario).filter(Usuario.email == dados.email).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="E-mail já em uso.")
        usuario.email = dados.email
    if dados.matricula and dados.matricula != usuario.matricula:
        if db.query(Usuario).filter(Usuario.matricula == dados.matricula).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Matrícula já em uso.")
        usuario.matricula = dados.matricula
    if dados.nome is not None:
        usuario.nome = dados.nome
    if dados.categoria is not None:
        usuario.categoria = dados.categoria
    if dados.situacao is not None:
        usuario.situacao = dados.situacao
    if dados.data_fim_suspensao is not None:
        usuario.data_fim_suspensao = dados.data_fim_suspensao

    db.commit()
    db.refresh(usuario)
    return usuario

def deletar_usuario(db: Session, usuario_id: int) -> None:
    usuario = get_usuario(db, usuario_id)
    # Não deletar se tiver histórico de empréstimos
    tem_emprestimos = db.query(Emprestimo).filter(Emprestimo.usuario_id == usuario.id).count()
    if tem_emprestimos > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não é possível excluir usuário com histórico de empréstimos.")
    db.delete(usuario)
    db.commit()

# ----------------- LIVROS -----------------

def get_livros(db: Session, area_conhecimento: Optional[str] = None) -> List[Livro]:
    query = db.query(Livro)
    if area_conhecimento:
        query = query.filter(Livro.area_conhecimento == area_conhecimento)
    return query.all()

def get_livro(db: Session, livro_id: int) -> Livro:
    livro = db.query(Livro).filter(Livro.id == livro_id).first()
    if not livro:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Livro não encontrado.")
    return livro

def criar_livro(db: Session, dados: Any) -> Livro:
    if db.query(Livro).filter(Livro.isbn == dados.isbn).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ISBN já cadastrado.")

    livro = Livro(
        titulo=dados.titulo,
        autor=dados.autor,
        isbn=dados.isbn,
        ano=dados.ano,
        area_conhecimento=dados.area_conhecimento,
    )
    db.add(livro)
    db.commit()
    db.refresh(livro)
    return livro

def atualizar_livro(db: Session, livro_id: int, dados: Any) -> Livro:
    livro = get_livro(db, livro_id)
    if dados.isbn and dados.isbn != livro.isbn:
        if db.query(Livro).filter(Livro.isbn == dados.isbn).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ISBN já cadastrado.")
        livro.isbn = dados.isbn
    if dados.titulo is not None:
        livro.titulo = dados.titulo
    if dados.autor is not None:
        livro.autor = dados.autor
    if dados.ano is not None:
        livro.ano = dados.ano
    if dados.area_conhecimento is not None:
        livro.area_conhecimento = dados.area_conhecimento

    db.commit()
    db.refresh(livro)
    return livro

def deletar_livro(db: Session, livro_id: int) -> None:
    livro = get_livro(db, livro_id)
    tem_emprestimos = db.query(Emprestimo).join(Exemplar).filter(Exemplar.livro_id == livro.id).count()
    if tem_emprestimos > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não é possível excluir livro com histórico de empréstimos.")
    db.delete(livro)
    db.commit()

# ----------------- EXEMPLARES -----------------

def get_exemplares(db: Session, livro_id: Optional[int] = None, estado: Optional[EstadoExemplar] = None) -> List[Exemplar]:
    query = db.query(Exemplar)
    if livro_id:
        query = query.filter(Exemplar.livro_id == livro_id)
    if estado:
        query = query.filter(Exemplar.estado == estado)
    return query.all()

def get_exemplar(db: Session, exemplar_id: int) -> Exemplar:
    exemplar = db.query(Exemplar).filter(Exemplar.id == exemplar_id).first()
    if not exemplar:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exemplar não encontrado.")
    return exemplar

def criar_exemplar(db: Session, dados: Any) -> Exemplar:
    # Checar existência do livro
    get_livro(db, dados.livro_id)
    if db.query(Exemplar).filter(Exemplar.codigo_tombo == dados.codigo_tombo).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código de tombo já cadastrado.")

    exemplar = Exemplar(
        livro_id=dados.livro_id,
        codigo_tombo=dados.codigo_tombo,
        estado=dados.estado or EstadoExemplar.disponivel,
    )
    db.add(exemplar)
    db.commit()
    db.refresh(exemplar)
    return exemplar

def atualizar_exemplar(db: Session, exemplar_id: int, dados: Any) -> Exemplar:
    exemplar = get_exemplar(db, exemplar_id)
    if dados.codigo_tombo and dados.codigo_tombo != exemplar.codigo_tombo:
        if db.query(Exemplar).filter(Exemplar.codigo_tombo == dados.codigo_tombo).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Código de tombo já cadastrado.")
        exemplar.codigo_tombo = dados.codigo_tombo

    estado_anterior = exemplar.estado
    if dados.estado is not None:
        exemplar.estado = dados.estado

    db.commit()
    db.refresh(exemplar)

    # Se foi baixado ou colocado em reparo, verificar regra 6
    if dados.estado in [EstadoExemplar.baixado, EstadoExemplar.em_reparo]:
        verificar_e_cancelar_reservas_se_sem_exemplares(db, exemplar.livro_id)

    return exemplar

def deletar_exemplar(db: Session, exemplar_id: int) -> None:
    exemplar = get_exemplar(db, exemplar_id)
    tem_emprestimos = db.query(Emprestimo).filter(Emprestimo.exemplar_id == exemplar.id).count()
    if tem_emprestimos > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não é possível excluir exemplar com histórico de empréstimos.")
    livro_id = exemplar.livro_id
    db.delete(exemplar)
    db.commit()
    verificar_e_cancelar_reservas_se_sem_exemplares(db, livro_id)

# ----------------- EMPRÉSTIMOS -----------------

def get_emprestimos(db: Session, usuario_id: Optional[int] = None, estado: Optional[EstadoEmprestimo] = None) -> List[Emprestimo]:
    query = db.query(Emprestimo)
    if usuario_id:
        atualizar_status_atrasos_usuario(db, usuario_id)
        query = query.filter(Emprestimo.usuario_id == usuario_id)
    if estado:
        query = query.filter(Emprestimo.estado == estado)
    return query.all()

def get_emprestimo(db: Session, emprestimo_id: int) -> Emprestimo:
    emp = db.query(Emprestimo).filter(Emprestimo.id == emprestimo_id).first()
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empréstimo não encontrado.")
    return emp

def criar_emprestimo(db: Session, usuario_id: int, exemplar_id: int, data_retirada: Optional[datetime] = None) -> Emprestimo:
    now = data_retirada or now_datetime()
    usuario = get_usuario(db, usuario_id)
    exemplar = get_exemplar(db, exemplar_id)

    # Atualiza atrasos do usuário e eventuais suspensões
    atualizar_status_atrasos_usuario(db, usuario.id, now=now)
    db.refresh(usuario)

    # Regra 1: Usuário ativo
    if usuario.situacao == SituacaoUsuario.suspenso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Usuário está suspenso até {usuario.data_fim_suspensao}."
        )

    # Regra 1: Sem multa aberta
    multas_abertas = db.query(Multa).join(Emprestimo).filter(
        Emprestimo.usuario_id == usuario.id,
        Multa.estado == EstadoMulta.aberta
    ).count()
    if multas_abertas > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empréstimo negado: usuário possui multas em aberto."
        )

    # Regra 1: Abaixo do limite de exemplares
    regras = get_regras_categoria(usuario.categoria)
    emprestimos_ativos = db.query(Emprestimo).filter(
        Emprestimo.usuario_id == usuario.id,
        Emprestimo.estado.in_([EstadoEmprestimo.ativo, EstadoEmprestimo.atrasado])
    ).count()
    if emprestimos_ativos >= regras.limite_exemplares:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Empréstimo negado: limite de {regras.limite_exemplares} exemplares atingido para a categoria {usuario.categoria.value}."
        )

    # Regra 6: Exemplar em reparo ou baixado não pode ser emprestado
    if exemplar.estado in [EstadoExemplar.em_reparo, EstadoExemplar.baixado]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Exemplar não pode ser emprestado pois está no estado '{exemplar.estado.value}'."
        )

    if exemplar.estado == EstadoExemplar.emprestado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exemplar já está emprestado."
        )

    # Verificar expiração de reservas deste livro
    verificar_reservas_expiradas(db, livro_id=exemplar.livro_id, now=now)
    db.refresh(exemplar)

    # Checar se exemplar está reservado
    if exemplar.estado == EstadoExemplar.reservado:
        reserva_deste_usuario = db.query(Reserva).filter(
            Reserva.livro_id == exemplar.livro_id,
            Reserva.usuario_id == usuario.id,
            Reserva.estado == EstadoReserva.disponivel
        ).first()
        if not reserva_deste_usuario:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Exemplar está reservado para outro usuário."
            )
        # Finaliza a reserva atendida
        reserva_deste_usuario.estado = EstadoReserva.concluida
        reserva_deste_usuario.posicao_fila = None
        reserva_deste_usuario.exemplar_id = None
        db.add(reserva_deste_usuario)
    else:
        # Se exemplar estava 'disponivel', verificar se há reserva disponivel aguardando outro usuario
        reserva_outro = db.query(Reserva).filter(
            Reserva.livro_id == exemplar.livro_id,
            Reserva.estado == EstadoReserva.disponivel,
            Reserva.usuario_id != usuario.id
        ).first()
        if reserva_outro:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Exemplar aguarda retirada de reserva de outro usuário."
            )

        # Se o próprio usuário tinha reserva aguardando ou disponível, dar baixa nela
        reserva_propria = db.query(Reserva).filter(
            Reserva.livro_id == exemplar.livro_id,
            Reserva.usuario_id == usuario.id,
            Reserva.estado.in_([EstadoReserva.aguardando, EstadoReserva.disponivel])
        ).first()
        if reserva_propria:
            reserva_propria.estado = EstadoReserva.concluida
            reserva_propria.posicao_fila = None
            reserva_propria.exemplar_id = None
            db.add(reserva_propria)
            reordenar_fila_reservas(db, exemplar.livro_id)

    # Criar empréstimo
    prazo = regras.prazo_dias
    data_prevista = now + timedelta(days=prazo)

    exemplar.estado = EstadoExemplar.emprestado
    db.add(exemplar)

    emprestimo = Emprestimo(
        exemplar_id=exemplar.id,
        usuario_id=usuario.id,
        data_retirada=now,
        data_prevista=data_prevista,
        estado=EstadoEmprestimo.ativo,
        numero_renovacoes=0,
    )
    db.add(emprestimo)
    db.commit()
    db.refresh(emprestimo)
    return emprestimo

def renovar_emprestimo(db: Session, emprestimo_id: int) -> Emprestimo:
    emp = get_emprestimo(db, emprestimo_id)
    now = now_datetime()

    if emp.estado not in [EstadoEmprestimo.ativo, EstadoEmprestimo.atrasado]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas empréstimos ativos podem ser renovados."
        )

    # Regra 3: se o empréstimo estiver atrasado
    if emp.estado == EstadoEmprestimo.atrasado or now > emp.data_prevista:
        emp.estado = EstadoEmprestimo.atrasado
        db.add(emp)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Renovação negada: empréstimo em atraso."
        )

    # Regra 3: se o limite de renovações da categoria já tiver sido atingido
    regras = get_regras_categoria(emp.usuario.categoria)
    if emp.numero_renovacoes >= regras.max_renovacoes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Renovação negada: limite de {regras.max_renovacoes} renovações atingido para a categoria {emp.usuario.categoria.value}."
        )

    # Regra 3: se houver fila de reserva para aquele livro
    verificar_reservas_expiradas(db, livro_id=emp.exemplar.livro_id, now=now)
    reservas_fila = db.query(Reserva).filter(
        Reserva.livro_id == emp.exemplar.livro_id,
        Reserva.estado.in_([EstadoReserva.aguardando, EstadoReserva.disponivel])
    ).count()
    if reservas_fila > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Renovação negada: há fila de reserva para este livro."
        )

    # Efetuar renovação
    emp.numero_renovacoes += 1
    emp.data_prevista = emp.data_prevista + timedelta(days=regras.prazo_dias)
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp

def devolver_emprestimo(db: Session, emprestimo_id: int, data_devolucao: Optional[datetime] = None) -> Emprestimo:
    emp = get_emprestimo(db, emprestimo_id)
    if emp.estado == EstadoEmprestimo.devolvido:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empréstimo já foi devolvido anteriormente."
        )

    devolucao_dt = data_devolucao or now_datetime()
    emp.data_devolucao = devolucao_dt
    emp.estado = EstadoEmprestimo.devolvido

    usuario = emp.usuario
    exemplar = emp.exemplar
    regras = get_regras_categoria(usuario.categoria)

    dias_atraso = calcular_dias_atraso(emp.data_prevista, devolucao_dt)

    # Regra 2: Usuário com atraso superior a 15 dias é automaticamente suspenso
    if dias_atraso > DIAS_ATRASO_SUSPENSAO:
        usuario.situacao = SituacaoUsuario.suspenso
        dias_suspensao = dias_atraso * FATOR_SUSPENSAO
        nova_data_fim = devolucao_dt + timedelta(days=dias_suspensao)
        if not usuario.data_fim_suspensao or usuario.data_fim_suspensao < nova_data_fim:
            usuario.data_fim_suspensao = nova_data_fim
        db.add(usuario)

    # Regra 7: Devolução com mais de 60 dias de atraso marca o exemplar como baixado e gera multa no teto
    if dias_atraso > DIAS_ATRASO_BAIXA:
        exemplar.estado = EstadoExemplar.baixado
        db.add(exemplar)

        multa = Multa(
            emprestimo_id=emp.id,
            valor=regras.teto_multa,
            estado=EstadoMulta.aberta,
            data_geracao=devolucao_dt,
        )
        db.add(multa)
        # Regra 6: se o último exemplar foi baixado, cancela reservas
        verificar_e_cancelar_reservas_se_sem_exemplares(db, exemplar.livro_id)

    elif dias_atraso > 0:
        # Regra 5: Multa acumula por dia corrido de atraso limitada ao teto
        valor_calculado = Decimal(str(dias_atraso)) * regras.valor_multa_dia
        valor_final = min(valor_calculado, regras.teto_multa)

        # Regra 5: Multa de professor é perdoada automaticamente se o atraso for de até 2 dias
        if usuario.categoria == CategoriaUsuario.professor and dias_atraso <= DIAS_TOLERANCIA_PROFESSOR:
            estado_multa = EstadoMulta.perdoada
        else:
            estado_multa = EstadoMulta.aberta

        multa = Multa(
            emprestimo_id=emp.id,
            valor=valor_final,
            estado=estado_multa,
            data_geracao=devolucao_dt,
        )
        db.add(multa)

    # Se exemplar não foi baixado, gerenciar fila de reservas (Regra 4)
    if exemplar.estado != EstadoExemplar.baixado:
        verificar_reservas_expiradas(db, livro_id=exemplar.livro_id, now=devolucao_dt)
        primeira_reserva = db.query(Reserva).filter(
            Reserva.livro_id == exemplar.livro_id,
            Reserva.estado == EstadoReserva.aguardando
        ).order_by(Reserva.posicao_fila.asc(), Reserva.data.asc()).first()

        if primeira_reserva:
            primeira_reserva.estado = EstadoReserva.disponivel
            primeira_reserva.data_limite_retirada = devolucao_dt + timedelta(hours=HORAS_LIMITE_RETIRADA_RESERVA)
            primeira_reserva.exemplar_id = exemplar.id
            primeira_reserva.posicao_fila = 1
            exemplar.estado = EstadoExemplar.reservado
            db.add(primeira_reserva)
            db.add(exemplar)
            reordenar_fila_reservas(db, exemplar.livro_id, exclude_id=primeira_reserva.id)
        else:
            exemplar.estado = EstadoExemplar.disponivel
            db.add(exemplar)

    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp

# ----------------- RESERVAS -----------------

def get_reservas_livro(db: Session, livro_id: int) -> List[Reserva]:
    get_livro(db, livro_id)
    verificar_reservas_expiradas(db, livro_id)
    # Retorna a fila do livro (reservas ativas)
    return db.query(Reserva).filter(
        Reserva.livro_id == livro_id,
        Reserva.estado.in_([EstadoReserva.aguardando, EstadoReserva.disponivel])
    ).order_by(Reserva.posicao_fila.asc(), Reserva.data.asc()).all()

def get_reservas(db: Session, livro_id: Optional[int] = None, usuario_id: Optional[int] = None, estado: Optional[EstadoReserva] = None) -> List[Reserva]:
    if livro_id:
        verificar_reservas_expiradas(db, livro_id)
    query = db.query(Reserva)
    if livro_id:
        query = query.filter(Reserva.livro_id == livro_id)
    if usuario_id:
        query = query.filter(Reserva.usuario_id == usuario_id)
    if estado:
        query = query.filter(Reserva.estado == estado)
    return query.order_by(Reserva.posicao_fila.asc(), Reserva.data.asc()).all()

def get_reserva(db: Session, reserva_id: int) -> Reserva:
    res = db.query(Reserva).filter(Reserva.id == reserva_id).first()
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva não encontrada.")
    return res

def criar_reserva(db: Session, usuario_id: int, livro_id: int) -> Reserva:
    usuario = get_usuario(db, usuario_id)
    livro = get_livro(db, livro_id)

    # Regra 6: Exemplar em reparo ou baixado não pode ser reservado; verificar se o livro tem exemplares válidos
    exemplares_validos = db.query(Exemplar).filter(
        Exemplar.livro_id == livro.id,
        ~Exemplar.estado.in_([EstadoExemplar.em_reparo, EstadoExemplar.baixado])
    ).count()
    if exemplares_validos == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível reservar: todos os exemplares deste livro estão em reparo ou baixados."
        )

    # Verificar se usuário já possui reserva ativa para este livro
    reserva_existente = db.query(Reserva).filter(
        Reserva.usuario_id == usuario.id,
        Reserva.livro_id == livro.id,
        Reserva.estado.in_([EstadoReserva.aguardando, EstadoReserva.disponivel])
    ).first()
    if reserva_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já possui reserva ativa para este livro."
        )

    verificar_reservas_expiradas(db, livro.id)

    # Determinar posição na fila (ordem de chegada - Regra 4)
    # Contar total de reservas ativas na fila
    reservas_ativas_count = db.query(Reserva).filter(
        Reserva.livro_id == livro.id,
        Reserva.estado.in_([EstadoReserva.aguardando, EstadoReserva.disponivel])
    ).count()

    posicao = reservas_ativas_count + 1

    reserva = Reserva(
        livro_id=livro.id,
        usuario_id=usuario.id,
        data=now_datetime(),
        posicao_fila=posicao,
        estado=EstadoReserva.aguardando,
    )
    db.add(reserva)
    db.commit()
    db.refresh(reserva)
    return reserva

def cancelar_reserva(db: Session, reserva_id: int) -> Reserva:
    res = get_reserva(db, reserva_id)
    if res.estado in [EstadoReserva.cancelada, EstadoReserva.expirada, EstadoReserva.concluida]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Reserva já está no estado '{res.estado.value}' e não pode ser cancelada."
        )

    estado_anterior = res.estado
    exemplar = res.exemplar
    livro_id = res.livro_id

    res.estado = EstadoReserva.cancelada
    res.posicao_fila = None
    res.exemplar_id = None
    db.add(res)

    # Se a reserva estava no estado 'disponivel', repassar exemplar ao próximo
    if estado_anterior == EstadoReserva.disponivel and exemplar and exemplar.estado != EstadoExemplar.baixado:
        proxima = db.query(Reserva).filter(
            Reserva.livro_id == livro_id,
            Reserva.estado == EstadoReserva.aguardando,
            Reserva.id != res.id
        ).order_by(Reserva.posicao_fila.asc(), Reserva.data.asc()).first()

        if proxima:
            proxima.estado = EstadoReserva.disponivel
            proxima.data_limite_retirada = now_datetime() + timedelta(hours=HORAS_LIMITE_RETIRADA_RESERVA)
            proxima.exemplar_id = exemplar.id
            proxima.posicao_fila = 1
            exemplar.estado = EstadoExemplar.reservado
            db.add(proxima)
            db.add(exemplar)
            reordenar_fila_reservas(db, livro_id, exclude_id=proxima.id)
        else:
            exemplar.estado = EstadoExemplar.disponivel
            db.add(exemplar)
    else:
        reordenar_fila_reservas(db, livro_id, exclude_id=res.id)

    db.commit()
    db.refresh(res)
    return res

# ----------------- MULTAS -----------------

def get_multas(db: Session, usuario_id: Optional[int] = None, estado: Optional[EstadoMulta] = None) -> List[Multa]:
    query = db.query(Multa)
    if usuario_id:
        query = query.join(Emprestimo).filter(Emprestimo.usuario_id == usuario_id)
    if estado:
        query = query.filter(Multa.estado == estado)
    return query.all()

def get_multa(db: Session, multa_id: int) -> Multa:
    multa = db.query(Multa).filter(Multa.id == multa_id).first()
    if not multa:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Multa não encontrada.")
    return multa

def pagar_multa(db: Session, multa_id: int) -> Multa:
    multa = get_multa(db, multa_id)
    if multa.estado == EstadoMulta.paga:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Multa já está paga.")
    if multa.estado == EstadoMulta.perdoada:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Multa já foi perdoada.")

    multa.estado = EstadoMulta.paga
    multa.data_pagamento = now_datetime()
    db.add(multa)
    db.commit()
    db.refresh(multa)
    return multa

# ----------------- RELATÓRIOS -----------------

def relatorio_livros_mais_emprestados(
    db: Session,
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    query = db.query(
        Livro.id.label("livro_id"),
        Livro.titulo,
        Livro.autor,
        Livro.isbn,
        Livro.area_conhecimento,
        func.count(Emprestimo.id).label("total_emprestimos")
    ).join(Exemplar, Exemplar.livro_id == Livro.id).join(Emprestimo, Emprestimo.exemplar_id == Exemplar.id)

    if data_inicio:
        query = query.filter(Emprestimo.data_retirada >= data_inicio)
    if data_fim:
        query = query.filter(Emprestimo.data_retirada <= data_fim)

    results = query.group_by(Livro.id).order_by(desc("total_emprestimos")).all()

    return [
        {
            "livro_id": r.livro_id,
            "titulo": r.titulo,
            "autor": r.autor,
            "isbn": r.isbn,
            "area_conhecimento": r.area_conhecimento,
            "total_emprestimos": r.total_emprestimos,
        }
        for r in results
    ]

def relatorio_usuarios_mais_atrasos(db: Session) -> List[Dict[str, Any]]:
    # Considera empréstimos que tiveram data_devolucao > data_prevista OU que estão atualmente atrasados
    # OU empréstimos que geraram multa
    atrasados_subquery = db.query(
        Emprestimo.usuario_id.label("uid"),
        func.count(Emprestimo.id).label("total_atrasos")
    ).outerjoin(Multa, Multa.emprestimo_id == Emprestimo.id).filter(
        or_(
            Emprestimo.data_devolucao > Emprestimo.data_prevista,
            Emprestimo.estado == EstadoEmprestimo.atrasado,
            Multa.id.isnot(None)
        )
    ).group_by(Emprestimo.usuario_id).subquery()

    results = db.query(
        Usuario.id.label("usuario_id"),
        Usuario.nome,
        Usuario.matricula,
        Usuario.categoria,
        atrasados_subquery.c.total_atrasos
    ).join(atrasados_subquery, Usuario.id == atrasados_subquery.c.uid).order_by(
        desc(atrasados_subquery.c.total_atrasos)
    ).all()

    return [
        {
            "usuario_id": r.usuario_id,
            "nome": r.nome,
            "matricula": r.matricula,
            "categoria": r.categoria,
            "total_atrasos": r.total_atrasos,
        }
        for r in results
    ]

def relatorio_taxa_ocupacao_acervo(db: Session) -> List[Dict[str, Any]]:
    # Por área de conhecimento do livro
    areas = db.query(Livro.area_conhecimento).distinct().all()
    relatorio = []

    for (area,) in areas:
        # Total de exemplares ativos do acervo nesta área (não baixados)
        total_exemplares = db.query(Exemplar).join(Livro).filter(
            Livro.area_conhecimento == area,
            Exemplar.estado != EstadoExemplar.baixado
        ).count()

        emprestados = db.query(Exemplar).join(Livro).filter(
            Livro.area_conhecimento == area,
            Exemplar.estado == EstadoExemplar.emprestado
        ).count()

        taxa = round((emprestados / total_exemplares * 100), 2) if total_exemplares > 0 else 0.0

        relatorio.append({
            "area_conhecimento": area,
            "total_exemplares": total_exemplares,
            "exemplares_emprestados": emprestados,
            "taxa_ocupacao": taxa,
        })

    return relatorio

from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.turma import Turma
from app.models.disciplina import Disciplina
from app.models.matricula import Matricula
from app.config import EstadoTurma, EstadoMatricula, MINIMO_MATRICULAS_TURMA
from app.schemas.turma import TurmaCreate, TurmaUpdate
from app.services.schedule_parser import parse_schedule


def count_vagas_ocupadas(db: Session, turma_id: int) -> int:
    """
    Conta matrículas que ocupam ou estão reservando vaga:
    - CONFIRMADA
    - SOLICITADA (que possui data_oferta_vaga preenchida, ou seja, vaga reservada aguardando confirmação dentro de 48h)
    """
    return db.query(Matricula).filter(
        Matricula.turma_id == turma_id,
        Matricula.estado.in_([EstadoMatricula.CONFIRMADA, EstadoMatricula.SOLICITADA])
    ).count()


def count_matriculas_confirmadas(db: Session, turma_id: int) -> int:
    return db.query(Matricula).filter(
        Matricula.turma_id == turma_id,
        Matricula.estado == EstadoMatricula.CONFIRMADA
    ).count()


def get_turma_by_id(db: Session, turma_id: int) -> Turma:
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turma com ID {turma_id} não encontrada."
        )
    return turma


def list_turmas(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    semestre: Optional[str] = None,
    disciplina_id: Optional[int] = None,
    estado: Optional[str] = None
) -> List[Turma]:
    query = db.query(Turma)
    if semestre:
        query = query.filter(Turma.semestre == semestre)
    if disciplina_id:
        query = query.filter(Turma.disciplina_id == disciplina_id)
    if estado:
        query = query.filter(Turma.estado == estado)
    return query.offset(skip).limit(limit).all()


def create_turma(db: Session, data: TurmaCreate) -> Turma:
    # Validar se disciplina existe
    disciplina = db.query(Disciplina).filter(Disciplina.id == data.disciplina_id).first()
    if not disciplina:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disciplina com ID {data.disciplina_id} não encontrada."
        )

    # Validar formato de horário
    parse_schedule(data.horario)

    turma = Turma(
        disciplina_id=data.disciplina_id,
        semestre=data.semestre,
        professor=data.professor,
        numero_vagas=data.numero_vagas,
        horario=data.horario,
        estado=data.estado,
    )
    db.add(turma)
    db.commit()
    db.refresh(turma)
    return turma


def update_turma(db: Session, turma_id: int, data: TurmaUpdate) -> Turma:
    turma = get_turma_by_id(db, turma_id)

    if data.disciplina_id is not None and data.disciplina_id != turma.disciplina_id:
        disciplina = db.query(Disciplina).filter(Disciplina.id == data.disciplina_id).first()
        if not disciplina:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Disciplina com ID {data.disciplina_id} não encontrada."
            )
        turma.disciplina_id = data.disciplina_id

    if data.horario is not None:
        parse_schedule(data.horario)
        turma.horario = data.horario

    if data.semestre is not None:
        turma.semestre = data.semestre
    if data.professor is not None:
        turma.professor = data.professor
    if data.numero_vagas is not None:
        turma.numero_vagas = data.numero_vagas
    if data.estado is not None:
        turma.estado = data.estado

    db.commit()
    db.refresh(turma)
    return turma


def delete_turma(db: Session, turma_id: int) -> None:
    turma = get_turma_by_id(db, turma_id)
    db.delete(turma)
    db.commit()


def encerrar_periodo_turma(db: Session, turma_id: int) -> Tuple[Turma, bool, int]:
    """
    Regra 5: Turma com menos de 5 matriculas confirmadas ao fim do periodo de matricula
    e cancelada, e todas as suas matriculas passam ao estado cancelada.
    Retorna (turma, foi_cancelada, total_confirmadas).
    """
    turma = get_turma_by_id(db, turma_id)
    total_confirmadas = count_matriculas_confirmadas(db, turma_id)

    if total_confirmadas < MINIMO_MATRICULAS_TURMA:
        turma.estado = EstadoTurma.CANCELADA
        # Todas as suas matrículas passam ao estado cancelada
        matriculas = db.query(Matricula).filter(
            Matricula.turma_id == turma_id,
            Matricula.estado != EstadoMatricula.CANCELADA
        ).all()
        for m in matriculas:
            m.estado = EstadoMatricula.CANCELADA
        db.commit()
        db.refresh(turma)
        return turma, True, total_confirmadas
    else:
        # Se tem 5 ou mais, permanece aberta ou se estiver cheia fica lotada
        vagas_ocupadas = count_vagas_ocupadas(db, turma_id)
        if vagas_ocupadas >= turma.numero_vagas:
            turma.estado = EstadoTurma.LOTADA
        db.commit()
        db.refresh(turma)
        return turma, False, total_confirmadas


def encerrar_periodo_semestre(db: Session, semestre: str) -> List[dict]:
    """
    Aplica a Regra 5 para todas as turmas ativas do semestre especificado.
    """
    turmas = db.query(Turma).filter(
        Turma.semestre == semestre,
        Turma.estado.in_([EstadoTurma.ABERTA, EstadoTurma.LOTADA])
    ).all()

    resultados = []
    for t in turmas:
        turma, cancelada, confirmadas = encerrar_periodo_turma(db, t.id)
        resultados.append({
            "turma_id": turma.id,
            "disciplina_id": turma.disciplina_id,
            "semestre": turma.semestre,
            "total_confirmadas": confirmadas,
            "cancelada_por_baixa_adesao": cancelada,
            "estado_final": turma.estado.value,
        })
    return resultados

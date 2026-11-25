from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.turma import Turma
from app.models.disciplina import Disciplina
from app.models.matricula import Matricula
from app.models.enums import EstadoTurma, EstadoMatricula
from app.schemas.turma import TurmaCreate, TurmaUpdate, TurmaResponse
from app.schemas.matricula import FilaEsperaResponse
from app.services.schedule_service import parse_schedule
from app.services.turma_service import (
    get_turma_with_details,
    encerrar_periodo_matricula,
    consultar_fila_turma,
)
from app.services.matricula_service import processar_fila_espera

router = APIRouter(prefix="/turmas", tags=["Turmas"])


@router.post("", response_model=TurmaResponse, status_code=status.HTTP_201_CREATED)
def criar_turma(payload: TurmaCreate, db: Session = Depends(get_db)):
    """Cria uma nova turma vinculada a uma disciplina."""
    disciplina = db.query(Disciplina).filter(Disciplina.id == payload.disciplina_id).first()
    if not disciplina:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disciplina com ID {payload.disciplina_id} não encontrada."
        )

    # Validar formato do horário
    try:
        parse_schedule(payload.horario)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    nova_turma = Turma(
        disciplina_id=payload.disciplina_id,
        semestre=payload.semestre,
        professor=payload.professor,
        numero_vagas=payload.numero_vagas,
        horario=payload.horario,
        estado=payload.estado,
    )
    db.add(nova_turma)
    db.commit()
    db.refresh(nova_turma)

    nova_turma.vagas_ocupadas = 0
    nova_turma.vagas_restantes = nova_turma.numero_vagas
    return nova_turma


@router.get("", response_model=List[TurmaResponse])
def listar_turmas(
    semestre: Optional[str] = None,
    disciplina_id: Optional[int] = None,
    estado: Optional[EstadoTurma] = None,
    db: Session = Depends(get_db)
):
    """Lista turmas com filtros opcionais por semestre, disciplina e estado."""
    query = db.query(Turma)
    if semestre:
        query = query.filter(Turma.semestre == semestre)
    if disciplina_id:
        query = query.filter(Turma.disciplina_id == disciplina_id)
    if estado:
        query = query.filter(Turma.estado == estado)

    turmas = query.all()
    resultado = []
    for t in turmas:
        ocupadas = (
            db.query(Matricula)
            .filter(
                Matricula.turma_id == t.id,
                Matricula.estado == EstadoMatricula.CONFIRMADA
            )
            .count()
        )
        t.vagas_ocupadas = ocupadas
        t.vagas_restantes = max(0, t.numero_vagas - ocupadas)
        resultado.append(t)

    return resultado


@router.get("/{turma_id}", response_model=TurmaResponse)
def obter_turma(turma_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de uma turma específica com cálculo de vagas restantes."""
    return get_turma_with_details(db, turma_id)


@router.put("/{turma_id}", response_model=TurmaResponse)
def atualizar_turma(
    turma_id: int,
    payload: TurmaUpdate,
    db: Session = Depends(get_db)
):
    """Atualiza dados de uma turma."""
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turma com ID {turma_id} não encontrada."
        )

    update_data = payload.model_dump(exclude_unset=True)

    if "disciplina_id" in update_data:
        disc = db.query(Disciplina).filter(Disciplina.id == update_data["disciplina_id"]).first()
        if not disc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Disciplina {update_data['disciplina_id']} não encontrada."
            )

    if "horario" in update_data:
        try:
            parse_schedule(update_data["horario"])
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

    for field, value in update_data.items():
        setattr(turma, field, value)

    db.commit()
    db.refresh(turma)

    # Processar fila caso vagas tenham sido aumentadas
    processar_fila_espera(db, turma.id)

    return get_turma_with_details(db, turma.id)


@router.delete("/{turma_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_turma(turma_id: int, db: Session = Depends(get_db)):
    """Remove uma turma do sistema."""
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turma com ID {turma_id} não encontrada."
        )
    db.delete(turma)
    db.commit()
    return None


@router.get("/{turma_id}/fila", response_model=FilaEsperaResponse)
def consultar_fila_espera(turma_id: int, db: Session = Depends(get_db)):
    """
    REGRA 2: Consulta a fila de espera de uma turma.
    Ordenada por prioridade da categoria (Pós > Graduação > Especial) e data da solicitação.
    Informa também status de convocação com janela de 48 horas.
    """
    return consultar_fila_turma(db, turma_id)


@router.post("/{turma_id}/processar-fila")
def acao_processar_fila(turma_id: int, db: Session = Depends(get_db)):
    """
    Processa a fila de espera da turma: expira prazos de 48h vencidos e chama novos candidatos.
    """
    notificados = processar_fila_espera(db, turma_id)
    return {
        "turma_id": turma_id,
        "novos_convocados_48h": len(notificados),
        "mensagem": f"Fila processada. {len(notificados)} aluno(s) convocado(s) para confirmação em até 48 horas."
    }


@router.post("/{turma_id}/encerrar-periodo-matricula")
def acao_encerrar_periodo(turma_id: int, db: Session = Depends(get_db)):
    """
    REGRA 5: Encerra o período de matrícula da turma.
    Se a turma possuir menos de 5 matrículas confirmadas, ela é cancelada
    e todas as suas matrículas passam para o estado cancelada.
    """
    return encerrar_periodo_matricula(db, turma_id)

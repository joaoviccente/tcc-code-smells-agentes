from typing import List, Optional
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.turma import TurmaCreate, TurmaUpdate, TurmaResponse, DisciplinaSimples
from app.schemas.matricula import FilaEsperaResponse, FilaEsperaItemResponse
from app.services import turma_service, matricula_service

router = APIRouter(prefix="/turmas", tags=["Turmas"])


def format_turma_response(db: Session, t) -> TurmaResponse:
    ocupadas = turma_service.count_vagas_ocupadas(db, t.id)
    disponiveis = max(0, t.numero_vagas - ocupadas)
    disciplina_info = None
    if t.disciplina:
        disciplina_info = DisciplinaSimples(
            id=t.disciplina.id,
            codigo=t.disciplina.codigo,
            nome=t.disciplina.nome,
            numero_creditos=t.disciplina.numero_creditos,
            departamento=t.disciplina.departamento,
        )
    return TurmaResponse(
        id=t.id,
        disciplina_id=t.disciplina_id,
        semestre=t.semestre,
        professor=t.professor,
        numero_vagas=t.numero_vagas,
        horario=t.horario,
        estado=t.estado,
        vagas_ocupadas=ocupadas,
        vagas_disponiveis=disponiveis,
        disciplina=disciplina_info,
    )


@router.post("", response_model=TurmaResponse, status_code=status.HTTP_201_CREATED)
def criar_turma(data: TurmaCreate, db: Session = Depends(get_db)):
    turma = turma_service.create_turma(db, data)
    return format_turma_response(db, turma)


@router.get("", response_model=List[TurmaResponse])
def listar_turmas(
    skip: int = 0,
    limit: int = 100,
    semestre: Optional[str] = None,
    disciplina_id: Optional[int] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db)
):
    turmas = turma_service.list_turmas(
        db, skip=skip, limit=limit, semestre=semestre, disciplina_id=disciplina_id, estado=estado
    )
    return [format_turma_response(db, t) for t in turmas]


@router.get("/{turma_id}", response_model=TurmaResponse)
def obter_turma(turma_id: int, db: Session = Depends(get_db)):
    turma = turma_service.get_turma_by_id(db, turma_id)
    return format_turma_response(db, turma)


@router.put("/{turma_id}", response_model=TurmaResponse)
def atualizar_turma(turma_id: int, data: TurmaUpdate, db: Session = Depends(get_db)):
    turma = turma_service.update_turma(db, turma_id, data)
    return format_turma_response(db, turma)


@router.delete("/{turma_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_turma(turma_id: int, db: Session = Depends(get_db)):
    turma_service.delete_turma(db, turma_id)
    return None


@router.get("/{turma_id}/fila", response_model=FilaEsperaResponse)
@router.get("/{turma_id}/lista-espera", response_model=FilaEsperaResponse)
def consultar_fila_espera(turma_id: int, db: Session = Depends(get_db)):
    """
    Lista de espera: consultar a fila de uma turma.
    Ordenada por prioridade da categoria (Pós > Graduação > Especial)
    e data de solicitação.
    """
    turma = turma_service.get_turma_by_id(db, turma_id)
    fila_itens = matricula_service.obter_fila_espera(db, turma_id)
    ocupadas = turma_service.count_vagas_ocupadas(db, turma_id)

    itens = [FilaEsperaItemResponse(**item) for item in fila_itens]

    return FilaEsperaResponse(
        turma_id=turma.id,
        disciplina_codigo=turma.disciplina.codigo,
        disciplina_nome=turma.disciplina.nome,
        semestre=turma.semestre,
        total_na_fila=len(itens),
        vagas_totais=turma.numero_vagas,
        vagas_ocupadas=ocupadas,
        fila=itens,
    )


@router.post("/{turma_id}/encerrar-periodo", response_model=TurmaResponse)
def encerrar_periodo_turma_endpoint(turma_id: int, db: Session = Depends(get_db)):
    """
    Regra 5: Turma com menos de 5 matrículas confirmadas ao fim do período de matrícula
    é cancelada, e todas as suas matrículas passam ao estado cancelada.
    """
    turma, _, _ = turma_service.encerrar_periodo_turma(db, turma_id)
    return format_turma_response(db, turma)


@router.post("/encerrar-periodo-semestre")
def encerrar_periodo_semestre_endpoint(
    semestre: str = Query(..., description="Semestre letivo (ex: '2026.1')"),
    db: Session = Depends(get_db)
):
    """
    Aplica a Regra 5 para todas as turmas de um semestre.
    """
    return turma_service.encerrar_periodo_semestre(db, semestre)

from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.aluno import AlunoCreate, AlunoUpdate, AlunoResponse
from app.schemas.matricula import MatriculaResponse
from app.schemas.historico import HistoricoResponse, HistoricoCreate
from app.services import aluno_service, matricula_service, historico_service

router = APIRouter(prefix="/alunos", tags=["Alunos"])


@router.post("", response_model=AlunoResponse, status_code=status.HTTP_201_CREATED)
def criar_aluno(data: AlunoCreate, db: Session = Depends(get_db)):
    return aluno_service.create_aluno(db, data)


@router.get("", response_model=List[AlunoResponse])
def listar_alunos(
    skip: int = 0,
    limit: int = 100,
    categoria: Optional[str] = None,
    situacao: Optional[str] = None,
    db: Session = Depends(get_db)
):
    return aluno_service.list_alunos(db, skip=skip, limit=limit, categoria=categoria, situacao=situacao)


@router.get("/{aluno_id}", response_model=AlunoResponse)
def obter_aluno(aluno_id: int, db: Session = Depends(get_db)):
    return aluno_service.get_aluno_by_id(db, aluno_id)


@router.put("/{aluno_id}", response_model=AlunoResponse)
def atualizar_aluno(aluno_id: int, data: AlunoUpdate, db: Session = Depends(get_db)):
    return aluno_service.update_aluno(db, aluno_id, data)


@router.delete("/{aluno_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_aluno(aluno_id: int, db: Session = Depends(get_db)):
    aluno_service.delete_aluno(db, aluno_id)
    return None


@router.get("/{aluno_id}/matriculas", response_model=List[MatriculaResponse])
def listar_matriculas_aluno(aluno_id: int, db: Session = Depends(get_db)):
    """
    Lista todas as matrículas de um aluno.
    """
    matriculas = matricula_service.list_matriculas_por_aluno(db, aluno_id)
    resultado = []
    for m in matriculas:
        resultado.append(
            MatriculaResponse(
                id=m.id,
                aluno_id=m.aluno_id,
                turma_id=m.turma_id,
                data=m.data,
                estado=m.estado,
                data_oferta_vaga=m.data_oferta_vaga,
                aluno_nome=m.aluno.nome,
                aluno_categoria=m.aluno.categoria,
                disciplina_codigo=m.turma.disciplina.codigo,
                disciplina_nome=m.turma.disciplina.nome,
                semestre=m.turma.semestre,
            )
        )
    return resultado


@router.get("/{aluno_id}/historico", response_model=List[HistoricoResponse])
def obter_historico_aluno(aluno_id: int, db: Session = Depends(get_db)):
    """
    Consulta o histórico acadêmico completo do aluno.
    """
    historicos = historico_service.get_historico_by_aluno(db, aluno_id)
    resultado = []
    for h in historicos:
        resultado.append(
            HistoricoResponse(
                id=h.id,
                aluno_id=h.aluno_id,
                disciplina_id=h.disciplina_id,
                disciplina_codigo=h.disciplina.codigo if h.disciplina else None,
                disciplina_nome=h.disciplina.nome if h.disciplina else None,
                semestre=h.semestre,
                nota=h.nota,
                situacao=h.situacao,
            )
        )
    return resultado


@router.post("/{aluno_id}/historico", response_model=HistoricoResponse, status_code=status.HTTP_201_CREATED)
def adicionar_historico_aluno(aluno_id: int, data: HistoricoCreate, db: Session = Depends(get_db)):
    """
    Registra uma disciplina cursada previamente no histórico do aluno.
    """
    data.aluno_id = aluno_id
    h = historico_service.create_historico(db, data)
    return HistoricoResponse(
        id=h.id,
        aluno_id=h.aluno_id,
        disciplina_id=h.disciplina_id,
        disciplina_codigo=h.disciplina.codigo if h.disciplina else None,
        disciplina_nome=h.disciplina.nome if h.disciplina else None,
        semestre=h.semestre,
        nota=h.nota,
        situacao=h.situacao,
    )

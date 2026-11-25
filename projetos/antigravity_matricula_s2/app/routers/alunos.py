"""Rotas REST para gerenciamento de Alunos."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.aluno import Aluno
from app.models.enums import CategoriaAluno, SituacaoAluno
from app.models.matricula import Matricula
from app.models.historico import Historico
from app.schemas.aluno import AlunoCreate, AlunoUpdate, AlunoResponse
from app.schemas.matricula import MatriculaResponse
from app.schemas.historico import HistoricoResponse
from app.config import REGRAS_POR_CATEGORIA

router = APIRouter(prefix="/alunos", tags=["Alunos"])


def formatar_aluno_response(aluno: Aluno) -> AlunoResponse:
    cat_str = aluno.categoria.value if hasattr(aluno.categoria, "value") else str(aluno.categoria)
    regra = REGRAS_POR_CATEGORIA.get(cat_str)
    return AlunoResponse(
        id=aluno.id,
        nome=aluno.nome,
        matricula=aluno.matricula,
        email=aluno.email,
        categoria=aluno.categoria,
        situacao=aluno.situacao,
        max_creditos=regra.max_creditos_semestre if regra else None,
        limite_trancamentos=regra.max_trancamentos_disciplina if regra else None,
        prazo_cancelamento_dias=regra.prazo_cancelamento_dias if regra else None,
        prioridade_espera=regra.nome_prioridade if regra else None,
    )


@router.post("", response_model=AlunoResponse, status_code=status.HTTP_201_CREATED)
def criar_aluno(payload: AlunoCreate, db: Session = Depends(get_db)):
    """Cadastra um novo aluno no sistema."""
    if db.query(Aluno).filter(Aluno.matricula == payload.matricula).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Aluno com matrícula '{payload.matricula}' já existe",
        )
    if db.query(Aluno).filter(Aluno.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Aluno com e-mail '{payload.email}' já existe",
        )

    novo_aluno = Aluno(
        nome=payload.nome.strip(),
        matricula=payload.matricula.strip(),
        email=payload.email.strip().lower(),
        categoria=payload.categoria,
        situacao=payload.situacao,
    )
    db.add(novo_aluno)
    db.commit()
    db.refresh(novo_aluno)
    return formatar_aluno_response(novo_aluno)


@router.get("", response_model=List[AlunoResponse])
def listar_alunos(
    categoria: Optional[CategoriaAluno] = None,
    situacao: Optional[SituacaoAluno] = None,
    termo: Optional[str] = Query(None, description="Busca por nome ou matrícula"),
    db: Session = Depends(get_db)
):
    """Lista alunos com filtros opcionais."""
    query = db.query(Aluno)
    if categoria:
        query = query.filter(Aluno.categoria == categoria)
    if situacao:
        query = query.filter(Aluno.situacao == situacao)
    if termo:
        like_termo = f"%{termo.strip()}%"
        query = query.filter((Aluno.nome.ilike(like_termo)) | (Aluno.matricula.ilike(like_termo)))

    alunos = query.all()
    return [formatar_aluno_response(a) for a in alunos]


@router.get("/{id}", response_model=AlunoResponse)
def obter_aluno(id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de um aluno por ID."""
    aluno = db.query(Aluno).filter(Aluno.id == id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aluno não encontrado")
    return formatar_aluno_response(aluno)


@router.put("/{id}", response_model=AlunoResponse)
def atualizar_aluno(id: int, payload: AlunoUpdate, db: Session = Depends(get_db)):
    """Atualiza dados cadastrais de um aluno."""
    aluno = db.query(Aluno).filter(Aluno.id == id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aluno não encontrado")

    if payload.matricula and payload.matricula != aluno.matricula:
        if db.query(Aluno).filter(Aluno.matricula == payload.matricula).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Matrícula já cadastrada")
        aluno.matricula = payload.matricula.strip()

    if payload.email and payload.email != aluno.email:
        if db.query(Aluno).filter(Aluno.email == payload.email).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado")
        aluno.email = payload.email.strip().lower()

    if payload.nome is not None:
        aluno.nome = payload.nome.strip()
    if payload.categoria is not None:
        aluno.categoria = payload.categoria
    if payload.situacao is not None:
        aluno.situacao = payload.situacao

    db.commit()
    db.refresh(aluno)
    return formatar_aluno_response(aluno)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_aluno(id: int, db: Session = Depends(get_db)):
    """Remove um aluno do sistema."""
    aluno = db.query(Aluno).filter(Aluno.id == id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aluno não encontrado")
    db.delete(aluno)
    db.commit()
    return None


@router.get("/{id}/matriculas", response_model=List[MatriculaResponse])
def listar_matriculas_do_aluno(id: int, db: Session = Depends(get_db)):
    """Endpoint alternativo para listar matrículas por aluno."""
    aluno = db.query(Aluno).filter(Aluno.id == id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aluno não encontrado")

    from app.routers.matriculas import formatar_matricula_response
    matriculas = db.query(Matricula).filter(Matricula.aluno_id == id).all()
    return [formatar_matricula_response(m) for m in matriculas]


@router.get("/{id}/historico", response_model=List[HistoricoResponse])
def obter_historico_do_aluno(id: int, db: Session = Depends(get_db)):
    """Endpoint alternativo para consultar histórico de um aluno."""
    aluno = db.query(Aluno).filter(Aluno.id == id).first()
    if not aluno:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aluno não encontrado")

    from app.routers.historico import formatar_historico_response
    registros = db.query(Historico).filter(Historico.aluno_id == id).order_by(Historico.semestre).all()
    return [formatar_historico_response(r) for r in registros]

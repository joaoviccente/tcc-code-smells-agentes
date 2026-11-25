"""Rotas REST para consulta e processamento da lista de espera."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.turma import Turma
from app.schemas.matricula import FilaEsperaItemResponse
from app.services.matricula_service import (
    obter_fila_espera_ordenada,
    processar_expiracoes_48h,
    processar_proximo_fila_espera,
)
from app.config import REGRAS_POR_CATEGORIA

router = APIRouter(prefix="/lista-de-espera", tags=["Lista de Espera"])


@router.get("/{turma_id}", response_model=List[FilaEsperaItemResponse])
@router.get("/turma/{turma_id}", response_model=List[FilaEsperaItemResponse])
def consultar_fila_espera(turma_id: int, db: Session = Depends(get_db)):
    """
    Consulta a fila de espera de uma turma.
    Ordenada por:
    1. Prioridade da categoria (Pós: alta, Graduação: média, Especial: baixa)
    2. Data da solicitação ASC
    """
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turma não encontrada")

    # Atualiza expirações caso haja alguma de 48h vencida
    processar_expiracoes_48h(db, turma_id)

    fila = obter_fila_espera_ordenada(db, turma_id)
    resultado = []
    for pos, m in enumerate(fila, start=1):
        cat_str = m.aluno.categoria.value if hasattr(m.aluno.categoria, "value") else str(m.aluno.categoria)
        regra = REGRAS_POR_CATEGORIA.get(cat_str)
        resultado.append(
            FilaEsperaItemResponse(
                posicao=pos,
                matricula_id=m.id,
                aluno_id=m.aluno_id,
                aluno_nome=m.aluno.nome,
                aluno_categoria=cat_str,
                prioridade=regra.nome_prioridade if regra else "desconhecida",
                prioridade_num=regra.prioridade_espera if regra else 99,
                data_solicitacao=m.data,
                data_limite_confirmacao=m.data_limite_confirmacao,
                estado=m.estado.value,
            )
        )
    return resultado


@router.post("/{turma_id}/processar")
def processar_fila(turma_id: int, db: Session = Depends(get_db)):
    """
    Processa expirações de 48h e avança a fila de espera se houver vaga.
    """
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turma não encontrada")

    expirados = processar_expiracoes_48h(db, turma_id)
    promovido = processar_proximo_fila_espera(db, turma_id)

    return {
        "turma_id": turma_id,
        "matriculas_expiradas_canceladas": expirados,
        "novo_promovido_matricula_id": promovido.id if promovido else None,
    }

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..enums import SituacaoHistorico
from ..errors import Conflito
from ..models import Aluno, Disciplina, Historico
from ..schemas import HistoricoCreate, HistoricoOut
from ..servicos import obter_ou_404

router = APIRouter(prefix="/historico", tags=["Historico"])


@router.post("", response_model=HistoricoOut, status_code=201, summary="Registrar resultado no historico")
def registrar(dados: HistoricoCreate, db: Session = Depends(get_db)):
    obter_ou_404(db, Aluno, dados.aluno_id, "Aluno")
    obter_ou_404(db, Disciplina, dados.disciplina_id, "Disciplina")
    if dados.situacao != SituacaoHistorico.TRANCADO:
        existente = db.scalar(
            select(Historico.id).where(
                Historico.aluno_id == dados.aluno_id,
                Historico.disciplina_id == dados.disciplina_id,
                Historico.semestre == dados.semestre,
                Historico.situacao.in_((SituacaoHistorico.APROVADO, SituacaoHistorico.REPROVADO)),
            )
        )
        if existente:
            raise Conflito(
                "RESULTADO_DUPLICADO",
                "Ja existe resultado final para este aluno, disciplina e semestre.",
            )
    h = Historico(**dados.model_dump(), por_falta=False)
    db.add(h)
    db.commit()
    return h

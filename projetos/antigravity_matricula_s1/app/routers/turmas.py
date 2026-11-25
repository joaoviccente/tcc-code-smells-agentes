from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.turma import Turma
from app.models.disciplina import Disciplina
from app.models.matricula import Matricula
from app.models.enums import EstadoTurma, EstadoMatricula
from app.schemas.turma import TurmaCreate, TurmaUpdate, TurmaResponse
from app.schemas.matricula import FilaEsperaItemResponse
from app.services.matricula_service import (
    obter_fila_espera_ordenada,
    encerrar_periodo_matricula_turma,
    atualizar_estado_turma,
    processar_proximo_fila_espera,
)
from app.config import REGRAS_POR_CATEGORIA

router = APIRouter(prefix="/turmas", tags=["Turmas"])


def formatar_turma_response(t: Turma, db: Session) -> TurmaResponse:
    ocupadas = db.query(Matricula).filter(
        Matricula.turma_id == t.id,
        Matricula.estado == EstadoMatricula.CONFIRMADA
    ).count()

    espera = db.query(Matricula).filter(
        Matricula.turma_id == t.id,
        Matricula.estado == EstadoMatricula.LISTA_DE_ESPERA
    ).count()

    disponiveis = max(0, t.numero_vagas - ocupadas)

    return TurmaResponse(
        id=t.id,
        disciplina_id=t.disciplina_id,
        semestre=t.semestre,
        professor=t.professor,
        numero_vagas=t.numero_vagas,
        horario=t.horario,
        estado=t.estado,
        disciplina_codigo=t.disciplina.codigo if t.disciplina else None,
        disciplina_nome=t.disciplina.nome if t.disciplina else None,
        vagas_ocupadas=ocupadas,
        vagas_disponiveis=disponiveis,
        total_espera=espera,
    )


@router.post("", response_model=TurmaResponse, status_code=status.HTTP_201_CREATED)
def criar_turma(payload: TurmaCreate, db: Session = Depends(get_db)):
    disciplina = db.query(Disciplina).filter(Disciplina.id == payload.disciplina_id).first()
    if not disciplina:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disciplina não encontrada")

    nova_turma = Turma(
        disciplina_id=payload.disciplina_id,
        semestre=payload.semestre.strip(),
        professor=payload.professor.strip(),
        numero_vagas=payload.numero_vagas,
        horario=payload.horario.strip(),
        estado=payload.estado,
    )
    db.add(nova_turma)
    db.commit()
    db.refresh(nova_turma)
    return formatar_turma_response(nova_turma, db)


@router.get("", response_model=List[TurmaResponse])
def listar_turmas(
    semestre: Optional[str] = None,
    disciplina_id: Optional[int] = None,
    estado: Optional[EstadoTurma] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Turma)
    if semestre:
        query = query.filter(Turma.semestre == semestre.strip())
    if disciplina_id:
        query = query.filter(Turma.disciplina_id == disciplina_id)
    if estado:
        query = query.filter(Turma.estado == estado)

    turmas = query.all()
    return [formatar_turma_response(t, db) for t in turmas]


@router.get("/{id}", response_model=TurmaResponse)
def obter_turma(id: int, db: Session = Depends(get_db)):
    turma = db.query(Turma).filter(Turma.id == id).first()
    if not turma:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turma não encontrada")
    return formatar_turma_response(turma, db)


@router.put("/{id}", response_model=TurmaResponse)
def atualizar_turma(id: int, payload: TurmaUpdate, db: Session = Depends(get_db)):
    turma = db.query(Turma).filter(Turma.id == id).first()
    if not turma:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turma não encontrada")

    vagas_anteriores = turma.numero_vagas

    if payload.disciplina_id is not None:
        if not db.query(Disciplina).filter(Disciplina.id == payload.disciplina_id).first():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disciplina não encontrada")
        turma.disciplina_id = payload.disciplina_id

    if payload.semestre is not None:
        turma.semestre = payload.semestre.strip()
    if payload.professor is not None:
        turma.professor = payload.professor.strip()
    if payload.numero_vagas is not None:
        turma.numero_vagas = payload.numero_vagas
    if payload.horario is not None:
        turma.horario = payload.horario.strip()
    if payload.estado is not None:
        turma.estado = payload.estado

    db.commit()
    db.refresh(turma)

    # Se aumentou o número de vagas, processa fila de espera
    if payload.numero_vagas is not None and payload.numero_vagas > vagas_anteriores:
        processar_proximo_fila_espera(db, turma.id)

    atualizar_estado_turma(db, turma.id)
    return formatar_turma_response(turma, db)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_turma(id: int, db: Session = Depends(get_db)):
    turma = db.query(Turma).filter(Turma.id == id).first()
    if not turma:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turma não encontrada")
    db.delete(turma)
    db.commit()
    return None


@router.post("/{id}/finalizar-periodo-matricula", response_model=TurmaResponse)
@router.post("/{id}/encerrar-matriculas", response_model=TurmaResponse)
def finalizar_periodo_matricula(id: int, db: Session = Depends(get_db)):
    """
    Regra 5: Turma com menos de 5 matrículas confirmadas ao fim do período de matrícula
    é cancelada, e todas as suas matrículas passam ao estado cancelada.
    """
    turma = encerrar_periodo_matricula_turma(db, id)
    return formatar_turma_response(turma, db)


@router.get("/{id}/lista-de-espera", response_model=List[FilaEsperaItemResponse])
def consultar_lista_espera_turma(id: int, db: Session = Depends(get_db)):
    """
    Retorna a fila de espera da turma ordenada pela prioridade da categoria
    (Pós > Graduação > Especial) e, em caso de empate, pela data da solicitação.
    """
    turma = db.query(Turma).filter(Turma.id == id).first()
    if not turma:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turma não encontrada")

    fila = obter_fila_espera_ordenada(db, id)
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

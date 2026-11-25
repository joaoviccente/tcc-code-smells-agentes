from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from .. import errors, schemas
from ..deps import db_sincronizado, obter_agora, paginacao
from ..models import Disciplina, EstadoTurma, HorarioTurma, Matricula, Turma
from ..regras import regra_do_aluno
from ..services import matriculas as svc

router = APIRouter(prefix="/turmas", tags=["Turmas"])


def obter_turma(db: Session, turma_id: int) -> Turma:
    t = db.get(Turma, turma_id)
    if t is None:
        raise errors.nao_encontrado("Turma", turma_id)
    return t


def saida_turma(db: Session, t: Turma) -> schemas.TurmaOut:
    ocupadas = svc.contar_ocupadas(db, t.id)
    return schemas.TurmaOut(
        id=t.id,
        disciplina=schemas.DisciplinaResumo.model_validate(t.disciplina),
        semestre=t.semestre,
        professor=t.professor,
        vagas=t.vagas,
        estado=t.estado,
        horarios=[schemas.HorarioOut.model_validate(h) for h in t.horarios],
        matriculas_confirmadas=svc.contar_confirmadas(db, t.id),
        vagas_ocupadas=ocupadas,
        vagas_disponiveis=max(t.vagas - ocupadas, 0)
        if t.estado in svc.TURMA_EM_ANDAMENTO
        else 0,
        tamanho_lista_espera=len(svc.fila_de_espera(db, t.id)),
    )


def _horarios(itens: list[schemas.HorarioIn]) -> list[HorarioTurma]:
    return [HorarioTurma(dia=h.dia, inicio=h.inicio, fim=h.fim) for h in itens]


@router.post("", response_model=schemas.TurmaOut, status_code=status.HTTP_201_CREATED)
def criar_turma(dados: schemas.TurmaCreate, db: Session = Depends(db_sincronizado)):
    if db.get(Disciplina, dados.disciplina_id) is None:
        raise errors.nao_encontrado("Disciplina", dados.disciplina_id)
    t = Turma(
        disciplina_id=dados.disciplina_id,
        semestre=dados.semestre,
        professor=dados.professor,
        vagas=dados.vagas,
        estado=EstadoTurma.aberta,
        horarios=_horarios(dados.horarios),
    )
    db.add(t)
    db.commit()
    return saida_turma(db, t)


@router.get("", response_model=list[schemas.TurmaOut])
def listar_turmas(
    semestre: Optional[str] = Query(default=None, pattern=schemas.SEMESTRE_REGEX),
    disciplina_id: Optional[int] = None,
    estado: Optional[EstadoTurma] = None,
    pag: tuple[int, int] = Depends(paginacao),
    db: Session = Depends(db_sincronizado),
):
    q = select(Turma).order_by(Turma.id)
    if semestre:
        q = q.where(Turma.semestre == semestre)
    if disciplina_id:
        q = q.where(Turma.disciplina_id == disciplina_id)
    if estado:
        q = q.where(Turma.estado == estado)
    return [saida_turma(db, t) for t in db.scalars(q.offset(pag[0]).limit(pag[1])).all()]


@router.get("/{turma_id}", response_model=schemas.TurmaOut)
def obter(turma_id: int, db: Session = Depends(db_sincronizado)):
    return saida_turma(db, obter_turma(db, turma_id))


@router.patch("/{turma_id}", response_model=schemas.TurmaOut)
def atualizar_turma(
    turma_id: int,
    dados: schemas.TurmaUpdate,
    db: Session = Depends(db_sincronizado),
    agora: datetime = Depends(obter_agora),
):
    t = obter_turma(db, turma_id)
    if t.estado not in svc.TURMA_EM_ANDAMENTO:
        raise errors.conflito("TURMA_INDISPONIVEL", f"Turma {t.estado.value} não pode ser alterada.")
    valores = dados.model_dump(exclude_unset=True)
    if "vagas" in valores:
        ocupadas = svc.contar_ocupadas(db, t.id)
        if valores["vagas"] < ocupadas:
            raise errors.conflito(
                "VAGAS_INSUFICIENTES",
                f"A turma já possui {ocupadas} vagas ocupadas; não é possível reduzir para "
                f"{valores['vagas']}.",
            )
        t.vagas = valores["vagas"]
    if "horarios" in valores:
        tem_matriculas = db.scalar(
            select(exists().where(Matricula.turma_id == t.id, Matricula.estado.in_(svc.ESTADOS_ATIVOS)))
        )
        if tem_matriculas:
            raise errors.conflito(
                "TURMA_COM_MATRICULAS",
                "Não é possível alterar o horário de turma com matrículas ativas.",
            )
        t.horarios = _horarios(dados.horarios)
    if "professor" in valores:
        t.professor = valores["professor"]
    svc.ofertar_vagas_liberadas(db, t, agora)
    db.commit()
    return saida_turma(db, t)


@router.delete("/{turma_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_turma(turma_id: int, db: Session = Depends(db_sincronizado)):
    t = obter_turma(db, turma_id)
    if db.scalar(select(exists().where(Matricula.turma_id == t.id))):
        raise errors.conflito(
            "TURMA_COM_MATRICULAS",
            "Turma possui matrículas e não pode ser removida; utilize o cancelamento da turma.",
        )
    db.delete(t)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{turma_id}/cancelar", response_model=schemas.TurmaOut)
def cancelar_turma(
    turma_id: int, db: Session = Depends(db_sincronizado), agora: datetime = Depends(obter_agora)
):
    t = obter_turma(db, turma_id)
    if t.estado not in svc.TURMA_EM_ANDAMENTO:
        raise errors.conflito("TURMA_INDISPONIVEL", f"A turma já está {t.estado.value}.")
    svc.cancelar_turma(db, t, agora, "Turma cancelada pela coordenação.")
    db.commit()
    return saida_turma(db, t)


@router.post("/{turma_id}/encerrar", response_model=schemas.TurmaOut)
def encerrar_turma(
    turma_id: int, db: Session = Depends(db_sincronizado), agora: datetime = Depends(obter_agora)
):
    t = obter_turma(db, turma_id)
    svc.encerrar_turma(db, t, agora)
    db.commit()
    return saida_turma(db, t)


@router.get("/{turma_id}/lista-espera", response_model=schemas.ListaEsperaOut)
def consultar_lista_espera(turma_id: int, db: Session = Depends(db_sincronizado)):
    t = obter_turma(db, turma_id)
    fila = []
    for i, m in enumerate(svc.fila_de_espera(db, t.id), start=1):
        fila.append(
            schemas.ItemListaEspera(
                posicao=i,
                matricula_id=m.id,
                aluno_id=m.aluno_id,
                aluno_nome=m.aluno.nome,
                categoria=m.aluno.categoria,
                prioridade=regra_do_aluno(m.aluno.categoria).rotulo_prioridade,
                data=m.data,
                vaga_ofertada=m.prazo_confirmacao is not None,
                prazo_confirmacao=m.prazo_confirmacao,
            )
        )
    return schemas.ListaEsperaOut(
        turma_id=t.id,
        estado_turma=t.estado,
        vagas=t.vagas,
        vagas_ocupadas=svc.contar_ocupadas(db, t.id),
        fila=fila,
    )

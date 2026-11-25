from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.database import get_db
from app.errors import Conflito
from app.models import Disciplina, EstadoTurma, Matricula, Turma
from app.regras import REGRAS
from app.schemas import FilaItem, FilaOut, Semestre, TurmaCreate, TurmaOut, TurmaUpdate

router = APIRouter(prefix="/turmas", tags=["Turmas"])


def turma_out(db: Session, t: Turma) -> TurmaOut:
    out = TurmaOut.model_validate(t)
    out.vagas_ocupadas = services.vagas_ocupadas(db, t)
    out.vagas_disponiveis = max(t.vagas - out.vagas_ocupadas, 0)
    return out


@router.post("", response_model=TurmaOut, status_code=status.HTTP_201_CREATED)
def criar(dados: TurmaCreate, db: Session = Depends(get_db)):
    services.obter(db, Disciplina, dados.disciplina_id, "disciplina")
    t = Turma(**dados.model_dump(mode="json"), estado=EstadoTurma.ABERTA)
    db.add(t)
    db.commit()
    db.refresh(t)
    return turma_out(db, t)


@router.get("", response_model=list[TurmaOut])
def listar(
    semestre: Semestre | None = None,
    disciplina_id: int | None = None,
    estado: EstadoTurma | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = select(Turma).order_by(Turma.id)
    if semestre:
        q = q.where(Turma.semestre == semestre)
    if disciplina_id:
        q = q.where(Turma.disciplina_id == disciplina_id)
    if estado:
        q = q.where(Turma.estado == estado)
    return [turma_out(db, t) for t in db.scalars(q.offset(skip).limit(limit)).all()]


@router.get("/{turma_id}", response_model=TurmaOut)
def obter(turma_id: int, db: Session = Depends(get_db)):
    t = services.obter(db, Turma, turma_id, "turma")
    if services.processar_expiracoes(db, t):
        db.commit()
    return turma_out(db, t)


@router.patch("/{turma_id}", response_model=TurmaOut)
def atualizar(turma_id: int, dados: TurmaUpdate, db: Session = Depends(get_db)):
    t = services.obter(db, Turma, turma_id, "turma")
    campos = dados.model_dump(exclude_unset=True, exclude_none=True, mode="json")
    if t.estado in (EstadoTurma.CANCELADA, EstadoTurma.ENCERRADA):
        raise Conflito(f"turma {t.estado.value} nao pode ser alterada")
    services.processar_expiracoes(db, t)

    if "vagas" in campos:
        ocupadas = services.vagas_ocupadas(db, t)
        if campos["vagas"] < ocupadas:
            raise Conflito(f"turma ja possui {ocupadas} vagas ocupadas; nao e possivel reduzir para {campos['vagas']}")
    if "horario" in campos:
        confirmadas = db.scalar(select(Matricula.id).where(
            Matricula.turma_id == t.id, Matricula.estado.in_(services.ATIVAS)))
        if confirmadas:
            raise Conflito("horario nao pode ser alterado em turma com matriculas ativas")

    novo_estado = campos.pop("estado", None)
    for k, v in campos.items():
        setattr(t, k, v)
    if novo_estado == EstadoTurma.CANCELADA.value:
        services.cancelar_turma(t, "turma cancelada pela coordenacao")
    elif novo_estado == EstadoTurma.ENCERRADA.value:
        t.estado = EstadoTurma.ENCERRADA
    else:
        services.preencher_vagas(db, t)
    db.commit()
    db.refresh(t)
    return turma_out(db, t)


@router.delete("/{turma_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(turma_id: int, db: Session = Depends(get_db)):
    t = services.obter(db, Turma, turma_id, "turma")
    if db.scalar(select(Matricula.id).where(Matricula.turma_id == turma_id)):
        raise Conflito("turma possui matriculas; cancele-a em vez de remover")
    db.delete(t)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{turma_id}/lista-espera", response_model=FilaOut, tags=["Lista de espera"])
def lista_espera(turma_id: int, db: Session = Depends(get_db)):
    t = services.obter(db, Turma, turma_id, "turma")
    if services.processar_expiracoes(db, t):
        db.commit()
    fila = [
        FilaItem(
            posicao=i, matricula_id=m.id, aluno_id=m.aluno_id, aluno_nome=m.aluno.nome,
            categoria=m.aluno.categoria, prioridade=REGRAS[m.aluno.categoria].prioridade_nome,
            data_solicitacao=m.data, vaga_oferecida=m.prazo_confirmacao is not None,
            prazo_confirmacao=m.prazo_confirmacao,
        )
        for i, m in enumerate(services.fila_ordenada(db, t), start=1)
    ]
    return FilaOut(turma_id=t.id, estado_turma=t.estado, vagas=t.vagas,
                   vagas_ocupadas=services.vagas_ocupadas(db, t), fila=fila)

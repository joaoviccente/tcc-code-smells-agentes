from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, services
from app.database import get_db
from app.enums import EstadoTurma
from app.errors import ErroNegocio
from app.models import Disciplina, HorarioTurma, Turma
from app.schemas import ItemListaEspera, ListaEsperaOut, TurmaCreate, TurmaOut, TurmaUpdate

router = APIRouter(prefix="/turmas", tags=["turmas"])


@router.post("", response_model=TurmaOut, status_code=status.HTTP_201_CREATED)
def criar(dados: TurmaCreate, db: Session = Depends(get_db)):
    services.obter(db, Disciplina, dados.disciplina_id, "disciplina")
    t = Turma(disciplina_id=dados.disciplina_id, semestre=dados.semestre, professor=dados.professor,
              vagas=dados.vagas, estado=EstadoTurma.ABERTA,
              horarios=[HorarioTurma(**h.model_dump()) for h in dados.horarios])
    db.add(t)
    db.commit()
    return t


@router.get("", response_model=list[TurmaOut])
def listar(semestre: str | None = Query(None, pattern=r"^\d{4}\.[12]$"), disciplina_id: int | None = None,
           estado: EstadoTurma | None = None, offset: int = Query(0, ge=0),
           limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    services.processar_prazos(db)
    db.commit()
    q = select(Turma).order_by(Turma.id)
    if semestre:
        q = q.where(Turma.semestre == semestre)
    if disciplina_id:
        q = q.where(Turma.disciplina_id == disciplina_id)
    if estado:
        q = q.where(Turma.estado == estado)
    return db.scalars(q.offset(offset).limit(limit)).all()


@router.get("/{turma_id}", response_model=TurmaOut)
def obter(turma_id: int, db: Session = Depends(get_db)):
    services.processar_prazos(db)
    db.commit()
    return services.obter(db, Turma, turma_id, "turma")


@router.patch("/{turma_id}", response_model=TurmaOut)
@router.put("/{turma_id}", response_model=TurmaOut, include_in_schema=False)
def atualizar(turma_id: int, dados: TurmaUpdate, db: Session = Depends(get_db)):
    services.processar_prazos(db)
    t = services.obter(db, Turma, turma_id, "turma")
    if t.estado in services.TURMA_FECHADA:
        raise ErroNegocio(409, "turma_indisponivel", f"Turma em estado '{t.estado.value}' nao pode ser alterada")
    valores = dados.model_dump(exclude_unset=True)
    for campo, valor in valores.items():
        if valor is None:
            raise ErroNegocio(422, "valor_nulo", f"Campo '{campo}' nao pode ser nulo")
    if "vagas" in valores and valores["vagas"] < services.ocupacao(db, t):
        raise ErroNegocio(409, "vagas_insuficientes",
                          f"Turma ja possui {services.ocupacao(db, t)} vagas ocupadas")
    if "horarios" in valores:
        if t.confirmadas or t.vagas_ocupadas:
            raise ErroNegocio(409, "turma_com_matriculas", "Horario nao pode ser alterado com matriculas ativas")
        t.horarios = [HorarioTurma(**h) for h in valores.pop("horarios")]
    for campo, valor in valores.items():
        setattr(t, campo, valor)
    db.flush()
    services.preencher_vagas(db, t)  # aumento de vagas libera a fila
    services.atualizar_estado_turma(db, t)
    db.commit()
    return t


@router.delete("/{turma_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(turma_id: int, db: Session = Depends(get_db)):
    t = services.obter(db, Turma, turma_id, "turma")
    if t.matriculas:
        raise ErroNegocio(409, "turma_com_matriculas",
                          "Turma possui matriculas; use POST /turmas/{id}/cancelar")
    db.delete(t)
    db.commit()
    return Response(status_code=204)


@router.post("/{turma_id}/cancelar", response_model=TurmaOut)
def cancelar(turma_id: int, db: Session = Depends(get_db)):
    t = services.obter(db, Turma, turma_id, "turma")
    if t.estado in services.TURMA_FECHADA:
        raise ErroNegocio(409, "turma_indisponivel", f"Turma ja esta '{t.estado.value}'")
    services.cancelar_turma(db, t, "Turma cancelada pela coordenacao")
    db.commit()
    return t


@router.post("/{turma_id}/encerrar", response_model=TurmaOut)
def encerrar(turma_id: int, db: Session = Depends(get_db)):
    t = services.obter(db, Turma, turma_id, "turma")
    if t.estado in services.TURMA_FECHADA:
        raise ErroNegocio(409, "turma_indisponivel", f"Turma ja esta '{t.estado.value}'")
    t.estado = EstadoTurma.ENCERRADA
    db.commit()
    return t


@router.get("/{turma_id}/lista-espera", response_model=ListaEsperaOut)
def lista_espera(turma_id: int, db: Session = Depends(get_db)):
    services.processar_prazos(db)
    db.commit()
    t = services.obter(db, Turma, turma_id, "turma")
    fila = services.fila_espera(db, t)
    return ListaEsperaOut(
        turma_id=t.id, estado_turma=t.estado, vagas=t.vagas, vagas_ocupadas=t.vagas_ocupadas,
        fila=[ItemListaEspera(posicao=i, matricula_id=m.id, aluno_id=m.aluno_id, aluno_nome=m.aluno.nome,
                              categoria=m.aluno.categoria,
                              prioridade=config.regras(m.aluno.categoria).rotulo_prioridade,
                              data_solicitacao=m.data)
              for i, m in enumerate(fila, start=1)],
    )

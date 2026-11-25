from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import servicos as sv
from app.database import get_db
from app.errors import Conflito, RegraViolada
from app.models import (Disciplina, EstadoMatricula as EM, EstadoTurma as ET,
                        Matricula, Turma)
from app.regras import REGRAS_CATEGORIA
from app.routers.comum import turma_saida
from app.schemas import (ItemListaEspera, ListaEsperaSaida, Semestre, TurmaAtualizar,
                         TurmaCriar, TurmaSaida)

router = APIRouter(prefix="/turmas", tags=["Turmas"])


@router.post("", response_model=TurmaSaida, status_code=status.HTTP_201_CREATED)
def criar(dados: TurmaCriar, db: Session = Depends(get_db)):
    sv.obter(db, Disciplina, dados.disciplina_id, "Disciplina")
    t = Turma(**dados.model_dump(), estado=ET.aberta)
    db.add(t)
    db.commit()
    return turma_saida(db, t)


@router.get("", response_model=list[TurmaSaida])
def listar(semestre: Optional[Semestre] = None, disciplina_id: Optional[int] = None,
           estado: Optional[ET] = None, skip: int = Query(0, ge=0),
           limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    stmt = select(Turma).order_by(Turma.id)
    if semestre:
        stmt = stmt.where(Turma.semestre == semestre)
    if disciplina_id:
        stmt = stmt.where(Turma.disciplina_id == disciplina_id)
    if estado:
        stmt = stmt.where(Turma.estado == estado)
    return [turma_saida(db, t) for t in db.scalars(stmt.offset(skip).limit(limit)).all()]


@router.get("/{turma_id}", response_model=TurmaSaida)
def obter(turma_id: int, db: Session = Depends(get_db)):
    t = sv.obter(db, Turma, turma_id, "Turma")
    sv.processar_expiracoes(db, t)
    db.commit()
    return turma_saida(db, t)


@router.patch("/{turma_id}", response_model=TurmaSaida)
@router.put("/{turma_id}", response_model=TurmaSaida, include_in_schema=False)
def atualizar(turma_id: int, dados: TurmaAtualizar, db: Session = Depends(get_db)):
    t = sv.obter(db, Turma, turma_id, "Turma", travar=True)
    sv.processar_expiracoes(db, t)
    campos = dados.model_dump(exclude_unset=True, exclude_none=True)
    if t.estado in (ET.cancelada, ET.encerrada) and campos:
        raise Conflito("TURMA_FINALIZADA", f"Turma '{t.estado.value}' nao pode ser alterada")

    if "vagas" in campos:
        confirmadas = db.scalar(select(func.count(Matricula.id)).where(
            Matricula.turma_id == t.id, Matricula.estado == EM.confirmada)) or 0
        if campos["vagas"] < confirmadas:
            raise RegraViolada("VAGAS_INSUFICIENTES",
                               f"Turma ja possui {confirmadas} matriculas confirmadas")
        t.vagas = campos["vagas"]
    if "professor" in campos:
        t.professor = campos["professor"]
    if "horario" in campos:
        t.horario = [h.model_dump() for h in dados.horario]

    novo_estado = campos.get("estado")
    if novo_estado == "cancelada":
        sv.cancelar_turma(db, t, "turma cancelada pela coordenacao")
    elif novo_estado == "encerrada":
        t.estado = ET.encerrada
        for m in t.matriculas:
            if m.estado in (EM.solicitada, EM.lista_de_espera):
                sv._encerrar(m, EM.cancelada, "turma encerrada")
    else:
        sv.liberar_vagas(db, t)  # aumento de vagas atende a lista de espera
    db.commit()
    return turma_saida(db, t)


@router.delete("/{turma_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(turma_id: int, db: Session = Depends(get_db)):
    t = sv.obter(db, Turma, turma_id, "Turma")
    if db.scalar(select(Matricula.id).where(Matricula.turma_id == t.id).limit(1)):
        raise Conflito("TURMA_COM_MATRICULAS",
                       "Turma possui matriculas; altere o estado para 'cancelada'")
    db.delete(t)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{turma_id}/lista-espera", response_model=ListaEsperaSaida, tags=["Lista de espera"])
def lista_espera(turma_id: int, db: Session = Depends(get_db)):
    t = sv.obter(db, Turma, turma_id, "Turma", travar=True)
    sv.processar_expiracoes(db, t)
    db.commit()
    fila = [
        ItemListaEspera(
            posicao=i, matricula_id=m.id, aluno_id=m.aluno_id,
            categoria=m.aluno.categoria,
            prioridade=REGRAS_CATEGORIA[m.aluno.categoria].prioridade_espera.name.lower(),
            data_solicitacao=m.data, vaga_oferecida=m.prazo_confirmacao is not None,
            prazo_confirmacao=m.prazo_confirmacao)
        for i, m in enumerate(sv.fila_espera(db, t), start=1)
    ]
    return ListaEsperaSaida(turma_id=t.id, vagas=t.vagas,
                            vagas_ocupadas=sv.vagas_ocupadas(db, t), fila=fila)

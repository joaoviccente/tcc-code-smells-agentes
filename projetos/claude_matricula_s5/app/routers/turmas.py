from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..enums import EstadoMatricula, EstadoTurma
from ..errors import Conflito
from ..models import Disciplina, Matricula, Turma
from ..regras import REGRAS_CATEGORIA
from ..schemas import (
    SEMESTRE_PATTERN,
    AguardandoConfirmacao,
    EncerramentoPeriodoOut,
    ItemFila,
    ListaEsperaOut,
    MatriculaOut,
    TurmaCreate,
    TurmaOut,
    TurmaUpdate,
)
from ..servicos import (
    OCUPAM_VAGA,
    TURMA_FECHADA,
    cancelar_turma,
    contar_matriculas,
    encerrar_periodo_matricula,
    encerrar_turma,
    fila_de_espera,
    obter_ou_404,
    preencher_posicao,
    preencher_vagas,
)

router = APIRouter(tags=["Turmas"])


def _horario_json(slots) -> list[dict]:
    return [s.model_dump(mode="json") for s in slots]


@router.post("/turmas", response_model=TurmaOut, status_code=201)
def criar_turma(dados: TurmaCreate, db: Session = Depends(get_db)):
    obter_ou_404(db, Disciplina, dados.disciplina_id, "Disciplina")
    valores = dados.model_dump()
    valores["horario"] = _horario_json(dados.horario)
    turma = Turma(**valores, estado=EstadoTurma.ABERTA)
    db.add(turma)
    db.commit()
    return turma


@router.get("/turmas", response_model=list[TurmaOut])
def listar_turmas(
    semestre: str | None = Query(None, pattern=SEMESTRE_PATTERN),
    disciplina_id: int | None = None,
    estado: EstadoTurma | None = None,
    departamento: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = select(Turma).join(Disciplina, Turma.disciplina_id == Disciplina.id).order_by(Turma.id)
    if semestre:
        q = q.where(Turma.semestre == semestre)
    if disciplina_id:
        q = q.where(Turma.disciplina_id == disciplina_id)
    if estado:
        q = q.where(Turma.estado == estado)
    if departamento:
        q = q.where(Disciplina.departamento == departamento)
    return db.scalars(q.offset(skip).limit(limit)).all()


@router.get("/turmas/{turma_id}", response_model=TurmaOut)
def obter_turma(turma_id: int, db: Session = Depends(get_db)):
    return obter_ou_404(db, Turma, turma_id, "Turma")


def _atualizar(db: Session, turma_id: int, valores: dict) -> Turma:
    turma = obter_ou_404(db, Turma, turma_id, "Turma")
    if turma.estado in TURMA_FECHADA:
        raise Conflito("TURMA_INDISPONIVEL", f"Turma {turma.estado.value} nao pode ser alterada.")
    tem_matriculas = bool(turma.matriculas)
    for campo in ("disciplina_id", "semestre"):
        if campo in valores and valores[campo] != getattr(turma, campo) and tem_matriculas:
            raise Conflito(
                "TURMA_COM_MATRICULAS",
                f"Nao e possivel alterar '{campo}' de uma turma que ja possui matriculas.",
            )
    if "disciplina_id" in valores:
        obter_ou_404(db, Disciplina, valores["disciplina_id"], "Disciplina")
    if "vagas" in valores:
        ocupadas = contar_matriculas(db, turma.id, OCUPAM_VAGA)
        if valores["vagas"] < ocupadas:
            raise Conflito(
                "VAGAS_INSUFICIENTES",
                f"A turma ja possui {ocupadas} vagas ocupadas; nao e possivel reduzir para {valores['vagas']}.",
            )
    if "horario" in valores:
        valores["horario"] = _horario_json(valores["horario"])
    for campo, valor in valores.items():
        setattr(turma, campo, valor)
    preencher_vagas(db, turma)  # aumento de vagas libera a fila; tambem recalcula o estado
    db.commit()
    return turma


@router.put("/turmas/{turma_id}", response_model=TurmaOut)
def substituir_turma(turma_id: int, dados: TurmaCreate, db: Session = Depends(get_db)):
    valores = {k: getattr(dados, k) for k in TurmaCreate.model_fields}
    return _atualizar(db, turma_id, valores)


@router.patch("/turmas/{turma_id}", response_model=TurmaOut)
def atualizar_turma(turma_id: int, dados: TurmaUpdate, db: Session = Depends(get_db)):
    valores = {k: getattr(dados, k) for k in dados.model_fields_set}
    return _atualizar(db, turma_id, valores)


@router.delete("/turmas/{turma_id}", status_code=204)
def remover_turma(turma_id: int, db: Session = Depends(get_db)):
    turma = obter_ou_404(db, Turma, turma_id, "Turma")
    if turma.matriculas:
        raise Conflito(
            "TURMA_COM_MATRICULAS",
            "Turma possui matriculas e nao pode ser removida; utilize o cancelamento da turma.",
        )
    db.delete(turma)
    db.commit()
    return Response(status_code=204)


@router.post("/turmas/{turma_id}/cancelar", response_model=TurmaOut)
def cancelar(turma_id: int, db: Session = Depends(get_db)):
    turma = obter_ou_404(db, Turma, turma_id, "Turma")
    if turma.estado in TURMA_FECHADA:
        raise Conflito("TRANSICAO_INVALIDA", f"Turma ja esta {turma.estado.value}.")
    cancelar_turma(db, turma)
    db.commit()
    return turma


@router.post("/turmas/{turma_id}/encerrar", response_model=TurmaOut)
def encerrar(turma_id: int, db: Session = Depends(get_db)):
    turma = obter_ou_404(db, Turma, turma_id, "Turma")
    if turma.estado in TURMA_FECHADA:
        raise Conflito("TRANSICAO_INVALIDA", f"Turma ja esta {turma.estado.value}.")
    encerrar_turma(db, turma)
    db.commit()
    return turma


@router.get("/turmas/{turma_id}/matriculas", response_model=list[MatriculaOut])
def matriculas_da_turma(
    turma_id: int, estado: EstadoMatricula | None = None, db: Session = Depends(get_db)
):
    obter_ou_404(db, Turma, turma_id, "Turma")
    q = select(Matricula).where(Matricula.turma_id == turma_id).order_by(Matricula.id)
    if estado:
        q = q.where(Matricula.estado == estado)
    return preencher_posicao(db, list(db.scalars(q).all()))


@router.get("/turmas/{turma_id}/lista-espera", response_model=ListaEsperaOut)
def lista_de_espera(turma_id: int, db: Session = Depends(get_db)):
    turma = obter_ou_404(db, Turma, turma_id, "Turma")
    aguardando = db.scalars(
        select(Matricula)
        .where(
            Matricula.turma_id == turma_id,
            Matricula.estado == EstadoMatricula.SOLICITADA,
            Matricula.prazo_confirmacao.is_not(None),
        )
        .order_by(Matricula.prazo_confirmacao)
    ).all()
    return ListaEsperaOut(
        turma_id=turma.id,
        estado=turma.estado,
        vagas=turma.vagas,
        vagas_ocupadas=contar_matriculas(db, turma.id, OCUPAM_VAGA),
        aguardando_confirmacao=[
            AguardandoConfirmacao(
                matricula_id=m.id,
                aluno_id=m.aluno_id,
                aluno_nome=m.aluno.nome,
                prazo_confirmacao=m.prazo_confirmacao,
            )
            for m in aguardando
        ],
        fila=[
            ItemFila(
                posicao=i,
                matricula_id=m.id,
                aluno_id=m.aluno_id,
                aluno_nome=m.aluno.nome,
                categoria=m.aluno.categoria,
                prioridade=REGRAS_CATEGORIA[m.aluno.categoria].prioridade_lista_espera,
                data_solicitacao=m.data_solicitacao,
            )
            for i, m in enumerate(fila_de_espera(db, turma.id), start=1)
        ],
    )


@router.post(
    "/periodos/{semestre}/encerrar-matriculas",
    response_model=EncerramentoPeriodoOut,
    tags=["Periodo de matricula"],
    summary="Encerra o periodo de matricula do semestre (regra 5)",
)
def encerrar_periodo(
    semestre: str = Path(pattern=SEMESTRE_PATTERN), db: Session = Depends(get_db)
):
    canceladas, mantidas = encerrar_periodo_matricula(db, semestre)
    return EncerramentoPeriodoOut(semestre=semestre, turmas_canceladas=canceladas, turmas_mantidas=mantidas)

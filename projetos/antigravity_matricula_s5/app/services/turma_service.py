from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.config import settings
from app.models.turma import Turma
from app.models.matricula import Matricula
from app.models.enums import EstadoTurma, EstadoMatricula
from app.services.matricula_service import get_waitlist_ordered, processar_fila_espera, get_current_time

def get_turma_with_details(db: Session, turma_id: int) -> Turma:
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turma com ID {turma_id} não encontrada."
        )
    # Contar confirmadas
    vagas_ocupadas = (
        db.query(Matricula)
        .filter(
            Matricula.turma_id == turma.id,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        )
        .count()
    )
    turma.vagas_ocupadas = vagas_ocupadas
    turma.vagas_restantes = max(0, turma.numero_vagas - vagas_ocupadas)
    return turma


def encerrar_periodo_matricula(db: Session, turma_id: int) -> Dict[str, Any]:
    """
    REGRA 5: Turma com menos de 5 matrículas confirmadas ao fim do período de matrícula
    é cancelada, e todas as suas matrículas passam ao estado cancelada.
    """
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turma com ID {turma_id} não encontrada."
        )

    if turma.estado == EstadoTurma.CANCELADA:
        return {
            "turma_id": turma.id,
            "estado": turma.estado.value,
            "matriculas_confirmadas": 0,
            "mensagem": "A turma já estava cancelada."
        }

    # Contar matrículas confirmadas
    confirmadas = (
        db.query(Matricula)
        .filter(
            Matricula.turma_id == turma.id,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        )
        .all()
    )
    qtd_confirmadas = len(confirmadas)

    if qtd_confirmadas < settings.MIN_MATRICULAS_TURMA:
        # Menos de 5 matrículas confirmadas -> cancela turma e todas as matrículas
        turma.estado = EstadoTurma.CANCELADA
        todas_matriculas = db.query(Matricula).filter(Matricula.turma_id == turma.id).all()
        for mat in todas_matriculas:
            mat.estado = EstadoMatricula.CANCELADA
            mat.vaga_liberada_em = None
            mat.limite_confirmacao_em = None

        db.commit()
        return {
            "turma_id": turma.id,
            "estado": turma.estado.value,
            "matriculas_confirmadas": qtd_confirmadas,
            "minimo_exigido": settings.MIN_MATRICULAS_TURMA,
            "mensagem": (
                f"Turma cancelada por ter menos de {settings.MIN_MATRICULAS_TURMA} matrículas confirmadas "
                f"({qtd_confirmadas} confirmadas). Todas as matrículas associadas foram canceladas."
            )
        }
    else:
        # 5 ou mais matrículas confirmadas: turma mantida
        turma.estado = EstadoTurma.ENCERRADA
        db.commit()
        return {
            "turma_id": turma.id,
            "estado": turma.estado.value,
            "matriculas_confirmadas": qtd_confirmadas,
            "minimo_exigido": settings.MIN_MATRICULAS_TURMA,
            "mensagem": (
                f"Período de matrícula encerrado com sucesso. "
                f"Turma confirmada com {qtd_confirmadas} matrículas ativas."
            )
        }


def consultar_fila_turma(db: Session, turma_id: int) -> Dict[str, Any]:
    """
    Retorna a fila de espera da turma com informações detalhadas de cada aluno e posições.
    """
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Turma com ID {turma_id} não encontrada."
        )

    # Atualiza prazos da fila antes de consultar
    processar_fila_espera(db, turma_id)

    fila_matriculas = get_waitlist_ordered(db, turma_id)
    now = get_current_time()

    resultado = []
    for pos, m in enumerate(fila_matriculas, start=1):
        aguardando = False
        if m.vaga_liberada_em and m.limite_confirmacao_em:
            lim = m.limite_confirmacao_em
            if lim.tzinfo is None:
                lim = lim.replace(tzinfo=now.tzinfo)
            if now <= lim:
                aguardando = True

        resultado.append({
            "posicao": pos,
            "matricula_id": m.id,
            "aluno_id": m.aluno.id,
            "aluno_nome": m.aluno.nome,
            "aluno_matricula": m.aluno.matricula,
            "categoria": m.aluno.categoria,
            "prioridade_categoria": m.aluno.categoria.prioridade_fila,
            "data_solicitacao": m.data,
            "vaga_liberada_em": m.vaga_liberada_em,
            "limite_confirmacao_em": m.limite_confirmacao_em,
            "aguardando_confirmacao": aguardando
        })

    return {
        "turma_id": turma.id,
        "disciplina_nome": turma.disciplina.nome,
        "semestre": turma.semestre,
        "total_na_fila": len(resultado),
        "fila": resultado
    }

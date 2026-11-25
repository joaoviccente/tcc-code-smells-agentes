from datetime import datetime, timezone, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.aluno import Aluno
from app.models.disciplina import Disciplina
from app.models.turma import Turma
from app.models.matricula import Matricula
from app.models.historico import Historico
from app.models.enums import (
    CategoriaAluno,
    SituacaoAluno,
    EstadoTurma,
    EstadoMatricula,
    SituacaoHistorico,
    REGRAS_CATEGORIA
)
from app.schemas.matricula import FilaEsperaItem, FilaEsperaResponse
from app.services.schedule_service import tem_conflito_horario

def now_utc(ref: Optional[datetime] = None) -> datetime:
    if ref is None:
        return datetime.now(timezone.utc)
    if ref.tzinfo is None:
        return ref.replace(tzinfo=timezone.utc)
    return ref

class MatriculaService:

    @staticmethod
    def processar_expirados_fila(db: Session, turma_id: Optional[int] = None, ref_time: Optional[datetime] = None) -> List[Matricula]:
        """
        Regra 2: Quando uma vaga é liberada, o primeiro da fila tem 48 horas para confirmar;
        esgotado o prazo, a matrícula é cancelada e a vez passa ao próximo.
        """
        agora = now_utc(ref_time)
        query = db.query(Matricula).filter(
            Matricula.estado == EstadoMatricula.SOLICITADA,
            Matricula.data_limite_confirmacao.isnot(None),
            Matricula.data_limite_confirmacao < agora
        )
        if turma_id is not None:
            query = query.filter(Matricula.turma_id == turma_id)

        expiradas = query.all()
        for mat in expiradas:
            mat.estado = EstadoMatricula.CANCELADA
            db.commit()
            # Passa a vaga ao próximo da fila
            MatriculaService.promover_proximo_fila(db, mat.turma_id, agora)

        return expiradas

    @staticmethod
    def get_fila_ordenada(db: Session, turma_id: int, ref_time: Optional[datetime] = None) -> List[Matricula]:
        """
        Retorna a lista de espera ordenada por:
        1. Prioridade da categoria (Pós=3 > Graduação=2 > Especial=1)
        2. Data da solicitação (mais antiga primeiro)
        """
        MatriculaService.processar_expirados_fila(db, turma_id, ref_time)

        matriculas_espera = db.query(Matricula).join(Aluno).filter(
            Matricula.turma_id == turma_id,
            Matricula.estado == EstadoMatricula.LISTA_DE_ESPERA
        ).all()

        def ordenacao_chave(m: Matricula):
            prioridade = REGRAS_CATEGORIA[m.aluno.categoria]["prioridade_espera"]
            data = m.data if m.data.tzinfo else m.data.replace(tzinfo=timezone.utc)
            # -prioridade para ordem decrescente, data para ordem crescente
            return (-prioridade, data)

        return sorted(matriculas_espera, key=ordenacao_chave)

    @staticmethod
    def promover_proximo_fila(db: Session, turma_id: int, ref_time: Optional[datetime] = None) -> Optional[Matricula]:
        """
        Promove o próximo da lista de espera quando uma vaga é liberada.
        O aluno terá 48 horas para confirmar.
        """
        agora = now_utc(ref_time)
        turma = db.query(Turma).filter(Turma.id == turma_id).first()
        if not turma or turma.estado in (EstadoTurma.CANCELADA, EstadoTurma.ENCERRADA):
            return None

        # Conta ocupadas (confirmadas + solicitadas com reserva)
        confirmadas = db.query(Matricula).filter(
            Matricula.turma_id == turma_id,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        ).count()

        reservadas = db.query(Matricula).filter(
            Matricula.turma_id == turma_id,
            Matricula.estado == EstadoMatricula.SOLICITADA,
            Matricula.data_limite_confirmacao.isnot(None),
            Matricula.data_limite_confirmacao > agora
        ).count()

        vagas_ocupadas = confirmadas + reservadas
        if vagas_ocupadas >= turma.numero_vagas:
            turma.estado = EstadoTurma.LOTADA
            db.commit()
            return None

        fila = MatriculaService.get_fila_ordenada(db, turma_id, agora)
        if not fila:
            # Não há ninguém na fila, e há vagas
            if turma.estado == EstadoTurma.LOTADA:
                turma.estado = EstadoTurma.ABERTA
                db.commit()
            return None

        proximo = fila[0]
        proximo.estado = EstadoMatricula.SOLICITADA
        proximo.data_limite_confirmacao = agora + timedelta(hours=48)
        db.commit()
        db.refresh(proximo)
        return proximo

    @staticmethod
    def solicitar_matricula(db: Session, aluno_id: int, turma_id: int, ref_time: Optional[datetime] = None) -> Matricula:
        agora = now_utc(ref_time)

        # 1. Busca aluno e turma
        aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
        if not aluno:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Aluno com ID {aluno_id} não encontrado")

        turma = db.query(Turma).filter(Turma.id == turma_id).first()
        if not turma:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Turma com ID {turma_id} não encontrada")

        if turma.estado in (EstadoTurma.CANCELADA, EstadoTurma.ENCERRADA):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Não é possível solicitar matrícula em turma com estado '{turma.estado.value}'"
            )

        # 2. Regra 1: Aluno deve estar ativo
        if aluno.situacao != SituacaoAluno.ATIVO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Matrícula não permitida. Aluno está com situação '{aluno.situacao.value}' (apenas alunos ativos podem se matricular)"
            )

        # 3. Não permitir duplicidade na mesma turma ou disciplina no mesmo semestre
        matricula_existente = db.query(Matricula).filter(
            Matricula.aluno_id == aluno_id,
            Matricula.turma_id == turma_id,
            Matricula.estado.in_([EstadoMatricula.CONFIRMADA, EstadoMatricula.SOLICITADA, EstadoMatricula.LISTA_DE_ESPERA])
        ).first()
        if matricula_existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Aluno já possui matrícula ativa ou na fila para esta turma (estado: {matricula_existente.estado.value})"
            )

        matricula_mesma_disciplina = db.query(Matricula).join(Turma).filter(
            Matricula.aluno_id == aluno_id,
            Turma.disciplina_id == turma.disciplina_id,
            Turma.semestre == turma.semestre,
            Matricula.estado.in_([EstadoMatricula.CONFIRMADA, EstadoMatricula.SOLICITADA])
        ).first()
        if matricula_mesma_disciplina:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Aluno já está matriculado nesta disciplina ({turma.disciplina.codigo}) no semestre {turma.semestre}"
            )

        # 4. Regra 3: Aluno reprovado 3 vezes na mesma disciplina fica impedido
        reprovacoes = db.query(Historico).filter(
            Historico.aluno_id == aluno_id,
            Historico.disciplina_id == turma.disciplina_id,
            Historico.situacao.in_([SituacaoHistorico.REPROVADO, SituacaoHistorico.REPROVADO_POR_FALTA])
        ).count()
        if reprovacoes >= 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Aluno reprovado 3 vezes na disciplina {turma.disciplina.codigo}. Matrícula impedida por regra de negócio."
            )

        # 5. Regra 1: Aprovado em todos os pré-requisitos
        for req in turma.disciplina.pre_requisitos:
            aprovado_req = db.query(Historico).filter(
                Historico.aluno_id == aluno_id,
                Historico.disciplina_id == req.id,
                Historico.situacao == SituacaoHistorico.APROVADO
            ).first()
            if not aprovado_req:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Pré-requisito não cumprido: {req.codigo} - {req.nome}"
                )

        # 6. Regra 1: Limite de créditos da categoria no semestre
        regras = REGRAS_CATEGORIA[aluno.categoria]
        max_creditos = regras["max_creditos"]

        matriculas_semestre = db.query(Matricula).join(Turma).join(Disciplina).filter(
            Matricula.aluno_id == aluno_id,
            Turma.semestre == turma.semestre,
            Matricula.estado.in_([EstadoMatricula.CONFIRMADA, EstadoMatricula.SOLICITADA])
        ).all()

        creditos_atuais = sum(m.turma.disciplina.numero_creditos for m in matriculas_semestre)
        creditos_finais = creditos_atuais + turma.disciplina.numero_creditos
        if creditos_finais > max_creditos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Limite de créditos excedido para a categoria '{aluno.categoria.value}'. Máximo permitido: {max_creditos}, atual com a nova disciplina: {creditos_finais} (atual: {creditos_atuais} + {turma.disciplina.numero_creditos})"
            )

        # 7. Regra 6: Conflito de horários com turmas já confirmadas
        turmas_confirmadas = [m.turma for m in matriculas_semestre if m.estado == EstadoMatricula.CONFIRMADA]
        for tc in turmas_confirmadas:
            if tem_conflito_horario(turma.horario, tc.horario):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Conflito de horário com a turma {tc.id} ({tc.disciplina.codigo} - {tc.horario})"
                )

        # 8. Regra 2: Alocação ou Lista de Espera
        MatriculaService.processar_expirados_fila(db, turma.id, agora)

        confirmadas_count = db.query(Matricula).filter(
            Matricula.turma_id == turma_id,
            Matricula.estado == EstadoMatricula.CONFIRMADA
        ).count()

        reservadas_count = db.query(Matricula).filter(
            Matricula.turma_id == turma_id,
            Matricula.estado == EstadoMatricula.SOLICITADA,
            Matricula.data_limite_confirmacao.isnot(None),
            Matricula.data_limite_confirmacao > agora
        ).count()

        vagas_ocupadas = confirmadas_count + reservadas_count

        if vagas_ocupadas < turma.numero_vagas:
            # Há vaga disponível imediatamente: matricula é confirmada
            novo_estado = EstadoMatricula.CONFIRMADA
            if vagas_ocupadas + 1 >= turma.numero_vagas:
                turma.estado = EstadoTurma.LOTADA
        else:
            # Turma lotada: entra em lista de espera
            turma.estado = EstadoTurma.LOTADA
            novo_estado = EstadoMatricula.LISTA_DE_ESPERA

        nova_matricula = Matricula(
            aluno_id=aluno_id,
            turma_id=turma_id,
            data=agora,
            estado=novo_estado
        )
        db.add(nova_matricula)
        db.commit()
        db.refresh(nova_matricula)
        return nova_matricula

    @staticmethod
    def confirmar_matricula(db: Session, matricula_id: int, ref_time: Optional[datetime] = None) -> Matricula:
        """
        Confirma uma matrícula solicitada ou promovida da lista de espera dentro do prazo de 48h.
        """
        agora = now_utc(ref_time)
        matricula = db.query(Matricula).filter(Matricula.id == matricula_id).first()
        if not matricula:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Matrícula {matricula_id} não encontrada")

        if matricula.estado == EstadoMatricula.CONFIRMADA:
            return matricula

        if matricula.estado == EstadoMatricula.LISTA_DE_ESPERA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A matrícula está em lista de espera. Não é possível confirmar antes de ser promovido."
            )

        if matricula.estado in (EstadoMatricula.CANCELADA, EstadoMatricula.TRANCADA):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Não é possível confirmar uma matrícula no estado '{matricula.estado.value}'"
            )

        if matricula.estado == EstadoMatricula.SOLICITADA:
            # Verifica se o prazo de 48h expirou
            if matricula.data_limite_confirmacao:
                limite = matricula.data_limite_confirmacao if matricula.data_limite_confirmacao.tzinfo else matricula.data_limite_confirmacao.replace(tzinfo=timezone.utc)
                if agora > limite:
                    matricula.estado = EstadoMatricula.CANCELADA
                    db.commit()
                    MatriculaService.promover_proximo_fila(db, matricula.turma_id, agora)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Prazo de 48 horas para confirmação expirado. Matrícula cancelada e vaga passada ao próximo."
                    )

            # Verifica conflito de horário atualizado
            turma = matricula.turma
            matriculas_semestre = db.query(Matricula).join(Turma).filter(
                Matricula.aluno_id == matricula.aluno_id,
                Turma.semestre == turma.semestre,
                Matricula.estado == EstadoMatricula.CONFIRMADA,
                Matricula.id != matricula.id
            ).all()
            for m in matriculas_semestre:
                if tem_conflito_horario(turma.horario, m.turma.horario):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Conflito de horário com a turma {m.turma.id} ({m.turma.disciplina.codigo} - {m.turma.horario})"
                    )

            matricula.estado = EstadoMatricula.CONFIRMADA
            matricula.data_limite_confirmacao = None

            # Atualiza estado da turma
            confirmadas = db.query(Matricula).filter(
                Matricula.turma_id == matricula.turma_id,
                Matricula.estado == EstadoMatricula.CONFIRMADA
            ).count()
            if confirmadas >= matricula.turma.numero_vagas:
                matricula.turma.estado = EstadoTurma.LOTADA

            db.commit()
            db.refresh(matricula)
            return matricula

        return matricula

    @staticmethod
    def trancar_matricula(db: Session, matricula_id: int, ref_time: Optional[datetime] = None) -> Matricula:
        """
        Regra 4: O trancamento de uma disciplina só é permitido dentro do prazo de cancelamento da categoria
        e respeitando o limite de trancamentos.
        Regra 7: Aluno que acumular três trancamentos no semestre passa à situação trancado,
        e todas as suas matrículas confirmadas são canceladas.
        """
        agora = now_utc(ref_time)
        matricula = db.query(Matricula).filter(Matricula.id == matricula_id).first()
        if not matricula:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Matrícula {matricula_id} não encontrada")

        if matricula.estado != EstadoMatricula.CONFIRMADA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Apenas matrículas confirmadas podem ser trancadas (estado atual: {matricula.estado.value})"
            )

        aluno = matricula.aluno
        turma = matricula.turma
        regras = REGRAS_CATEGORIA[aluno.categoria]
        prazo_dias = regras["prazo_cancelamento_dias"]
        max_trancamentos = regras["max_trancamentos"]

        # 1. Verifica prazo de cancelamento/trancamento
        data_mat = matricula.data if matricula.data.tzinfo else matricula.data.replace(tzinfo=timezone.utc)
        dias_decorridos = (agora - data_mat).days
        if dias_decorridos > prazo_dias:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Prazo para trancamento expirado para a categoria '{aluno.categoria.value}' (máximo {prazo_dias} dias; decorridos {dias_decorridos} dias). Fora do prazo, deve ser feito o cancelamento."
            )

        # 2. Verifica limite de trancamentos por disciplina
        trancamentos_anteriores = db.query(Historico).filter(
            Historico.aluno_id == aluno.id,
            Historico.disciplina_id == turma.disciplina_id,
            Historico.situacao == SituacaoHistorico.TRANCADO
        ).count()

        if trancamentos_anteriores >= max_trancamentos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Limite de trancamentos para a disciplina excedido para a categoria '{aluno.categoria.value}' (máximo permitido: {max_trancamentos}, já realizados: {trancamentos_anteriores})"
            )

        # 3. Executa o trancamento
        matricula.estado = EstadoMatricula.TRANCADA

        # Registra no histórico
        historico_trancamento = Historico(
            aluno_id=aluno.id,
            disciplina_id=turma.disciplina_id,
            semestre=turma.semestre,
            nota=None,
            situacao=SituacaoHistorico.TRANCADO,
            observacao="Disciplina trancada pelo aluno dentro do prazo"
        )
        db.add(historico_trancamento)
        db.commit()

        # Libera a vaga e promove o próximo da fila
        MatriculaService.promover_proximo_fila(db, turma.id, agora)

        # 4. Regra 7: Aluno que acumular três trancamentos no semestre passa à situação trancado,
        # e todas as suas matrículas confirmadas são canceladas.
        trancamentos_semestre = db.query(Historico).filter(
            Historico.aluno_id == aluno.id,
            Historico.semestre == turma.semestre,
            Historico.situacao == SituacaoHistorico.TRANCADO
        ).count()

        if trancamentos_semestre >= 3:
            aluno.situacao = SituacaoAluno.TRANCADO
            # Cancela todas as matrículas confirmadas do aluno
            outras_confirmadas = db.query(Matricula).join(Turma).filter(
                Matricula.aluno_id == aluno.id,
                Turma.semestre == turma.semestre,
                Matricula.estado == EstadoMatricula.CONFIRMADA
            ).all()

            for out_mat in outras_confirmadas:
                out_mat.estado = EstadoMatricula.CANCELADA
                db.commit()
                # Libera vaga de cada turma cancelada
                MatriculaService.promover_proximo_fila(db, out_mat.turma_id, agora)

            db.commit()

        db.refresh(matricula)
        return matricula

    @staticmethod
    def cancelar_matricula(db: Session, matricula_id: int, ref_time: Optional[datetime] = None) -> Matricula:
        """
        Regra 4: Fora do prazo, o cancelamento registra reprovação por falta no histórico.
        Libera vaga e repassa ao próximo da fila.
        """
        agora = now_utc(ref_time)
        matricula = db.query(Matricula).filter(Matricula.id == matricula_id).first()
        if not matricula:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Matrícula {matricula_id} não encontrada")

        if matricula.estado in (EstadoMatricula.CANCELADA, EstadoMatricula.TRANCADA):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Matrícula já está com estado '{matricula.estado.value}'"
            )

        estado_anterior = matricula.estado
        aluno = matricula.aluno
        turma = matricula.turma
        regras = REGRAS_CATEGORIA[aluno.categoria]
        prazo_dias = regras["prazo_cancelamento_dias"]

        data_mat = matricula.data if matricula.data.tzinfo else matricula.data.replace(tzinfo=timezone.utc)
        dias_decorridos = (agora - data_mat).days

        # Regra 4: Cancelamento fora do prazo registra reprovação por falta no histórico
        if estado_anterior == EstadoMatricula.CONFIRMADA and dias_decorridos > prazo_dias:
            historico_reprovacao = Historico(
                aluno_id=aluno.id,
                disciplina_id=turma.disciplina_id,
                semestre=turma.semestre,
                nota=0.0,
                situacao=SituacaoHistorico.REPROVADO_POR_FALTA,
                observacao=f"Cancelamento fora do prazo de {prazo_dias} dias da categoria {aluno.categoria.value} (decorridos {dias_decorridos} dias)"
            )
            db.add(historico_reprovacao)

        matricula.estado = EstadoMatricula.CANCELADA
        db.commit()

        # Se a vaga estava confirmada ou reservada, repassa ao próximo da fila
        if estado_anterior in (EstadoMatricula.CONFIRMADA, EstadoMatricula.SOLICITADA):
            MatriculaService.promover_proximo_fila(db, turma.id, agora)

        db.refresh(matricula)
        return matricula

    @staticmethod
    def consultar_fila_turma(db: Session, turma_id: int, ref_time: Optional[datetime] = None) -> FilaEsperaResponse:
        agora = now_utc(ref_time)
        turma = db.query(Turma).filter(Turma.id == turma_id).first()
        if not turma:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Turma {turma_id} não encontrada")

        fila = MatriculaService.get_fila_ordenada(db, turma_id, agora)
        itens: List[FilaEsperaItem] = []
        for idx, mat in enumerate(fila, start=1):
            prioridade = REGRAS_CATEGORIA[mat.aluno.categoria]["prioridade_espera"]
            itens.append(
                FilaEsperaItem(
                    posicao=idx,
                    matricula_id=mat.id,
                    aluno_id=mat.aluno.id,
                    aluno_nome=mat.aluno.nome,
                    aluno_matricula=mat.aluno.matricula,
                    categoria=mat.aluno.categoria,
                    prioridade_categoria=prioridade,
                    data_solicitacao=mat.data,
                    data_limite_confirmacao=mat.data_limite_confirmacao
                )
            )

        return FilaEsperaResponse(turma_id=turma_id, total_na_fila=len(itens), fila=itens)

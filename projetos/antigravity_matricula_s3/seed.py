"""
Script para popular o banco de dados com dados de exemplo:
- Alunos das três categorias (Graduação, Pós, Especial)
- Disciplinas de múltiplos departamentos com pré-requisitos
- Turmas abertas e com horários variados
- Histórico acadêmico de exemplo
- Matrículas e filas de espera
"""
from app.database import SessionLocal, Base, engine
from app.models import (
    Aluno, Disciplina, Turma, Matricula, Historico,
    CategoriaAluno, SituacaoAluno, EstadoTurma, EstadoMatricula, SituacaoHistorico
)

def popular_banco():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Verifica se já há dados
        if db.query(Aluno).first():
            print("Banco de dados já contém registros. Pulando seed.")
            return

        print("Populando banco de dados...")

        # 1. Alunos
        alunos = [
            Aluno(nome="Lucas Oliveira", matricula="20261001", email="lucas.oliveira@uf.edu.br", categoria=CategoriaAluno.GRADUACAO, situacao=SituacaoAluno.ATIVO),
            Aluno(nome="Beatriz Santos", matricula="20261002", email="beatriz.santos@uf.edu.br", categoria=CategoriaAluno.GRADUACAO, situacao=SituacaoAluno.ATIVO),
            Aluno(nome="Guilherme Pereira", matricula="20261003", email="guilherme.pos@uf.edu.br", categoria=CategoriaAluno.POS, situacao=SituacaoAluno.ATIVO),
            Aluno(nome="Camila Fernandes", matricula="20261004", email="camila.esp@uf.edu.br", categoria=CategoriaAluno.ESPECIAL, situacao=SituacaoAluno.ATIVO),
            Aluno(nome="Rodrigo Jubilado", matricula="20261005", email="rodrigo.jub@uf.edu.br", categoria=CategoriaAluno.GRADUACAO, situacao=SituacaoAluno.JUBILADO),
            Aluno(nome="Ana Trancada", matricula="20261006", email="ana.trancada@uf.edu.br", categoria=CategoriaAluno.GRADUACAO, situacao=SituacaoAluno.TRANCADO),
        ]
        db.add_all(alunos)
        db.commit()

        # 2. Disciplinas
        d_calc1 = Disciplina(codigo="MAT001", nome="Cálculo Diferencial e Integral 1", numero_creditos=6, carga_horaria=90, departamento="Matemática")
        d_calc2 = Disciplina(codigo="MAT002", nome="Cálculo Diferencial e Integral 2", numero_creditos=6, carga_horaria=90, departamento="Matemática")
        d_alg1 = Disciplina(codigo="DCC001", nome="Algoritmos e Estruturas de Dados 1", numero_creditos=4, carga_horaria=60, departamento="Ciência da Computação")
        d_alg2 = Disciplina(codigo="DCC002", nome="Algoritmos e Estruturas de Dados 2", numero_creditos=4, carga_horaria=60, departamento="Ciência da Computação")
        d_bd = Disciplina(codigo="DCC003", nome="Banco de Dados", numero_creditos=4, carga_horaria=60, departamento="Ciência da Computação")
        d_ia = Disciplina(codigo="DCC004", nome="Inteligência Artificial", numero_creditos=4, carga_horaria=60, departamento="Ciência da Computação")

        # Pré-requisitos
        d_calc2.pre_requisitos.append(d_calc1)
        d_alg2.pre_requisitos.append(d_alg1)
        d_ia.pre_requisitos.append(d_alg2)

        db.add_all([d_calc1, d_calc2, d_alg1, d_alg2, d_bd, d_ia])
        db.commit()

        # 3. Turmas
        t_calc1 = Turma(disciplina_id=d_calc1.id, semestre="2026.1", professor="Prof. Gauss", numero_vagas=40, horario="SEG 08:00-10:00, QUA 08:00-10:00, SEX 08:00-10:00", estado=EstadoTurma.ABERTA)
        t_calc2 = Turma(disciplina_id=d_calc2.id, semestre="2026.1", professor="Prof. Leibniz", numero_vagas=30, horario="TER 10:00-12:00, QUI 10:00-12:00", estado=EstadoTurma.ABERTA)
        t_alg1 = Turma(disciplina_id=d_alg1.id, semestre="2026.1", professor="Prof. Knuth", numero_vagas=35, horario="SEG 14:00-16:00, QUA 14:00-16:00", estado=EstadoTurma.ABERTA)
        t_alg2 = Turma(disciplina_id=d_alg2.id, semestre="2026.1", professor="Prof. Dijkstra", numero_vagas=25, horario="TER 14:00-16:00, QUI 14:00-16:00", estado=EstadoTurma.ABERTA)
        t_bd = Turma(disciplina_id=d_bd.id, semestre="2026.1", professor="Prof. Codd", numero_vagas=2, horario="SEX 14:00-18:00", estado=EstadoTurma.ABERTA) # pequena para testar fila

        db.add_all([t_calc1, t_calc2, t_alg1, t_alg2, t_bd])
        db.commit()

        # 4. Histórico (Lucas foi aprovado em Cálculo 1 e Algoritmos 1)
        h1 = Historico(aluno_id=alunos[0].id, disciplina_id=d_calc1.id, semestre="2025.2", nota=8.5, situacao=SituacaoHistorico.APROVADO)
        h2 = Historico(aluno_id=alunos[0].id, disciplina_id=d_alg1.id, semestre="2025.2", nota=9.0, situacao=SituacaoHistorico.APROVADO)
        # Beatriz reprovou em Cálculo 1 em 2025.2
        h3 = Historico(aluno_id=alunos[1].id, disciplina_id=d_calc1.id, semestre="2025.2", nota=4.0, situacao=SituacaoHistorico.REPROVADO)

        db.add_all([h1, h2, h3])
        db.commit()

        print("Banco de dados populado com sucesso!")

    finally:
        db.close()

if __name__ == "__main__":
    popular_banco()

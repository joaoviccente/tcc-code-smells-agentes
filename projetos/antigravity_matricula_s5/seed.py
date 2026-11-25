from app.database import engine, SessionLocal, Base
from app.models.aluno import Aluno
from app.models.disciplina import Disciplina
from app.models.turma import Turma
from app.models.matricula import Matricula
from app.models.historico import Historico
from app.models.enums import CategoriaAluno, SituacaoAluno, EstadoTurma, SituacaoHistorico

def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Aluno).first():
            print("Banco de dados já possui registros.")
            return

        print("Populando banco de dados com dados iniciais...")

        # 1. Alunos
        alunos = [
            Aluno(nome="Maria Santos", matricula="GRAD202601", e_mail="maria.santos@universidade.edu.br", categoria=CategoriaAluno.GRADUACAO, situacao=SituacaoAluno.ATIVO),
            Aluno(nome="João Pereira", matricula="POS202601", e_mail="joao.pereira@universidade.edu.br", categoria=CategoriaAluno.POS, situacao=SituacaoAluno.ATIVO),
            Aluno(nome="Lucas Costa", matricula="ESP202601", e_mail="lucas.costa@universidade.edu.br", categoria=CategoriaAluno.ESPECIAL, situacao=SituacaoAluno.ATIVO),
            Aluno(nome="Beatriz Lima", matricula="GRAD202602", e_mail="beatriz.lima@universidade.edu.br", categoria=CategoriaAluno.GRADUACAO, situacao=SituacaoAluno.ATIVO),
            Aluno(nome="Pedro Souza", matricula="GRAD202603", e_mail="pedro.souza@universidade.edu.br", categoria=CategoriaAluno.GRADUACAO, situacao=SituacaoAluno.TRANCADO),
            Aluno(nome="Ana Oliveira", matricula="GRAD202604", e_mail="ana.oliveira@universidade.edu.br", categoria=CategoriaAluno.GRADUACAO, situacao=SituacaoAluno.JUBILADO),
        ]
        db.add_all(alunos)
        db.flush()

        # 2. Disciplinas
        calc1 = Disciplina(codigo="MAT101", nome="Cálculo Diferencial e Integral I", numero_creditos=4, carga_horaria=60, departamento="Matemática")
        db.add(calc1)
        db.flush()

        calc2 = Disciplina(codigo="MAT102", nome="Cálculo Diferencial e Integral II", numero_creditos=4, carga_horaria=60, departamento="Matemática", prerequisitos=[calc1])
        db.add(calc2)

        prog1 = Disciplina(codigo="INF101", nome="Algoritmos e Programação", numero_creditos=4, carga_horaria=60, departamento="Informática")
        db.add(prog1)
        db.flush()

        ed = Disciplina(codigo="INF102", nome="Estruturas de Dados", numero_creditos=4, carga_horaria=60, departamento="Informática", prerequisitos=[prog1])
        db.add(ed)

        fis1 = Disciplina(codigo="FIS101", nome="Física Geral e Experimental I", numero_creditos=4, carga_horaria=60, departamento="Física")
        db.add(fis1)
        db.flush()

        # 3. Histórico prévio (ex: Maria Santos já aprovada em Cálculo 1 e Programação 1)
        hist1 = Historico(aluno_id=alunos[0].id, disciplina_id=calc1.id, semestre="2025.2", nota=9.0, situacao=SituacaoHistorico.APROVADO)
        hist2 = Historico(aluno_id=alunos[0].id, disciplina_id=prog1.id, semestre="2025.2", nota=8.5, situacao=SituacaoHistorico.APROVADO)
        # Beatriz Lima foi reprovada em Cálculo 1 no semestre anterior
        hist3 = Historico(aluno_id=alunos[3].id, disciplina_id=calc1.id, semestre="2025.2", nota=3.5, situacao=SituacaoHistorico.REPROVADO)
        db.add_all([hist1, hist2, hist3])

        # 4. Turmas do Semestre 2026.1
        turmas = [
            Turma(disciplina_id=calc1.id, semestre="2026.1", professor="Prof. Gauss", numero_vagas=30, horario="SEG 08:00-10:00, QUA 08:00-10:00", estado=EstadoTurma.ABERTA),
            Turma(disciplina_id=calc2.id, semestre="2026.1", professor="Prof. Newton", numero_vagas=25, horario="TER 10:00-12:00, QUI 10:00-12:00", estado=EstadoTurma.ABERTA),
            Turma(disciplina_id=prog1.id, semestre="2026.1", professor="Prof. Turing", numero_vagas=30, horario="SEG 10:00-12:00, QUA 10:00-12:00", estado=EstadoTurma.ABERTA),
            Turma(disciplina_id=ed.id, semestre="2026.1", professor="Prof. Knuth", numero_vagas=20, horario="TER 14:00-16:00, QUI 14:00-16:00", estado=EstadoTurma.ABERTA),
            Turma(disciplina_id=fis1.id, semestre="2026.1", professor="Prof. Feynman", numero_vagas=2, horario="SEX 08:00-12:00", estado=EstadoTurma.ABERTA),
        ]
        db.add_all(turmas)

        db.commit()
        print("Dados de exemplo inseridos com sucesso!")
    finally:
        db.close()

if __name__ == "__main__":
    seed()

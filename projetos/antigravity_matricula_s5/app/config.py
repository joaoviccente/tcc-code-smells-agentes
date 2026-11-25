import os

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./matriculas.db")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1")
    PROJECT_NAME: str = "API de Gestão de Matrículas Acadêmicas"
    VERSION: str = "1.0.0"

    # Regras de Negócio - Constantes Numéricas
    # Créditos máximos por semestre por categoria
    MAX_CREDITOS_GRADUACAO: int = 28
    MAX_CREDITOS_POS: int = 16
    MAX_CREDITOS_ESPECIAL: int = 8

    # Limite de trancamentos por disciplina por categoria
    MAX_TRANCAMENTOS_GRADUACAO: int = 2
    MAX_TRANCAMENTOS_POS: int = 1
    MAX_TRANCAMENTOS_ESPECIAL: int = 0

    # Prazo de cancelamento (em dias) por categoria
    PRAZO_CANCELAMENTO_GRADUACAO_DIAS: int = 15
    PRAZO_CANCELAMENTO_POS_DIAS: int = 30
    PRAZO_CANCELAMENTO_ESPECIAL_DIAS: int = 7

    # Prazo para confirmação de vaga da lista de espera (em horas)
    PRAZO_CONFIRMACAO_FILA_HORAS: int = 48

    # Máximo de reprovações permitidas na mesma disciplina
    MAX_REPROVACOES_DISCIPLINA: int = 3

    # Mínimo de matrículas confirmadas para manter a turma aberta ao fim do período
    MIN_MATRICULAS_TURMA: int = 5

    # Máximo de trancamentos no semestre antes de trancar o aluno
    MAX_TRANCAMENTOS_SEMESTRE_ALUNO: int = 3

settings = Settings()

import os

class Settings:
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "API de Gestão de Matrículas Acadêmicas")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./matriculas.db")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

settings = Settings()

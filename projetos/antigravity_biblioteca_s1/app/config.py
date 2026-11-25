import os
from pydantic import BaseModel

class Settings(BaseModel):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./biblioteca.db")
    APP_NAME: str = "API de Gestão de Biblioteca Universitária"
    APP_VERSION: str = "1.0.0"

settings = Settings()

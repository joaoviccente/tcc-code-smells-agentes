from pydantic import BaseModel, ConfigDict
from app.models.enums import EstadoMulta


class MultaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    emprestimo_id: int
    valor: float
    estado: EstadoMulta

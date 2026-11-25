class ErroNegocio(Exception):
    status_code = 400

    def __init__(self, detalhe: str):
        super().__init__(detalhe)
        self.detalhe = detalhe


class NaoEncontrado(ErroNegocio):
    status_code = 404


class Conflito(ErroNegocio):
    """Operacao valida sintaticamente, mas violando regra de negocio ou estado atual do recurso."""
    status_code = 409

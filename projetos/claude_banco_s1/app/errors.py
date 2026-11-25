class ErroNegocio(Exception):
    """Erro de regra de negocio, traduzido para resposta HTTP."""

    status_code = 422

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


class NaoEncontrado(ErroNegocio):
    status_code = 404


class Conflito(ErroNegocio):
    """Operacao incompativel com o estado atual do recurso."""

    status_code = 409


class RegraViolada(ErroNegocio):
    """Operacao valida sintaticamente, mas negada por regra (saldo, limites)."""

    status_code = 422

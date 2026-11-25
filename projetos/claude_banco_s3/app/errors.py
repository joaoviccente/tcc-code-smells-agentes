class ErroNegocio(Exception):
    status_code = 422

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


class NaoEncontrado(ErroNegocio):
    status_code = 404

    def __init__(self, recurso: str, ident):
        super().__init__(f"{recurso}_nao_encontrado", f"{recurso.capitalize()} {ident} nao encontrado(a).")


class Conflito(ErroNegocio):
    """Operacao incompativel com o estado atual do recurso."""
    status_code = 409


class RegraViolada(ErroNegocio):
    """Operacao viola regra de negocio (limites, saldo, prazos)."""
    status_code = 422

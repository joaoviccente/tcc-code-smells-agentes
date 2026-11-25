class ErroNegocio(Exception):
    """Violacao de regra de negocio ou de estado; vira resposta HTTP."""

    def __init__(self, mensagem: str, status_code: int = 409, codigo: str = "regra_negocio"):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status_code = status_code
        self.codigo = codigo


class NaoEncontrado(ErroNegocio):
    def __init__(self, entidade: str, ident):
        super().__init__(f"{entidade} {ident} nao encontrado(a)", 404, "nao_encontrado")

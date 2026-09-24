"""Erros das APIs que o juiz trata de um jeito especial."""


class CotaEsgotada(RuntimeError):
    """A cota DIÁRIA do tier grátis da API acabou. Tentar de novo agora não adianta."""

    MENSAGEM = (
        "A cota diária grátis da API do Google acabou. Ela volta no dia seguinte "
        "(à meia-noite no horário do Pacífico, por volta das 4h ou 5h da manhã em Brasília)."
    )

    def __init__(self, detalhe: str = ""):
        super().__init__(self.MENSAGEM + (f" [{detalhe}]" if detalhe else ""))


def cota_diaria_esgotada(erro: Exception) -> bool:
    """Erro 429 por cota POR DIA (diferente do limite por minuto, que passa em segundos)."""
    return getattr(erro, "code", None) == 429 and "PerDay" in str(erro)

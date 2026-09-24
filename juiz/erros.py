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


def explicar_erro(erro: Exception) -> str:
    """Motivo curto de uma falha, pra mostrar na tela. Nunca inclui a chave: as mensagens da API do
    Google e dos downloads não trazem o valor dela. O detalhe completo vai pro log do servidor."""
    from urllib.error import HTTPError, URLError

    from google.genai.errors import APIError

    if isinstance(erro, APIError):
        mensagem = erro.message or ""
        if erro.code in (400, 401, 403) and ("API key" in mensagem or "API_KEY" in mensagem):
            return "o Google recusou a chave da API; confira se ela foi colada inteira nos secrets"
        if erro.code == 403:
            return "o Google negou acesso à API com essa chave (403); confira o projeto da chave no AI Studio"
        if erro.code == 404:
            return f"a API do Gemini não encontrou o modelo pedido (404): {mensagem[:150]}"
        if erro.code in (500, 503):
            return f"o Gemini está instável agora (erro {erro.code})"
        return f"a API do Gemini respondeu com erro {erro.code} {erro.status or ''}: {mensagem[:150]}"
    if isinstance(erro, HTTPError):
        return f"o download de {erro.url} respondeu com erro HTTP {erro.code}"
    if isinstance(erro, URLError):
        return f"não consegui acessar a internet ({erro.reason})"
    if isinstance(erro, RuntimeError):
        return str(erro)
    return f"{type(erro).__name__}: {str(erro)[:150]}"

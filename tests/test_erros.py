"""Testes das mensagens de erro mostradas na tela (etapa 8)."""

from urllib.error import HTTPError

from google.genai.errors import ClientError, ServerError

from juiz.erros import explicar_erro


def erro_da_api(tipo, codigo, mensagem, status):
    return tipo(codigo, {"error": {"code": codigo, "message": mensagem, "status": status}})


def test_chave_recusada_pelo_google():
    erro = erro_da_api(ClientError, 400, "API key not valid. Please pass a valid API key.", "INVALID_ARGUMENT")
    assert "recusou a chave" in explicar_erro(erro)


def test_modelo_inexistente_e_instabilidade():
    assert "404" in explicar_erro(erro_da_api(ClientError, 404, "models/x is not found", "NOT_FOUND"))
    assert "instável" in explicar_erro(erro_da_api(ServerError, 503, "overloaded", "UNAVAILABLE"))


def test_download_que_falhou_diz_o_endereco():
    erro = HTTPError("https://www.riftboundfaq.com/reference/core-rules/1.4", 403, "Forbidden", {}, None)
    assert explicar_erro(erro) == "o download de https://www.riftboundfaq.com/reference/core-rules/1.4 respondeu com erro HTTP 403"


def test_outros_erros_mostram_o_tipo():
    assert explicar_erro(RuntimeError("Coloque GEMINI_API_KEY")) == "Coloque GEMINI_API_KEY"
    assert explicar_erro(FileNotFoundError("git")).startswith("FileNotFoundError")

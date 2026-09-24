"""Testes da leitura dos secrets do app publicado (etapa 8)."""

import os

import pytest
from streamlit.errors import StreamlitSecretNotFoundError

from juiz.segredos import aplicar_segredos


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch):
    # delenv também faz o monkeypatch apagar, no fim do teste, o que o código gravar no ambiente.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("SENHA_DO_APP", raising=False)


def test_secrets_certos_vao_pro_ambiente():
    assert aplicar_segredos(lambda: {"GEMINI_API_KEY": " chave ", "SENHA_DO_APP": "senha"}) is None
    assert os.environ["GEMINI_API_KEY"] == "chave" and os.environ["SENHA_DO_APP"] == "senha"


def test_aceita_minusculas_e_uma_secao():
    assert aplicar_segredos(lambda: {"geral": {"gemini_api_key": "chave"}}) is None
    assert os.environ["GEMINI_API_KEY"] == "chave"


def test_sem_secrets_e_o_normal_no_computador_local():
    def ler():
        raise StreamlitSecretNotFoundError("No secrets found. {file_paths}", file_paths="x", error_id="no-secrets-found")

    assert aplicar_segredos(ler) is None


def test_formato_invalido_explica_sem_mostrar_o_valor():
    def ler():
        raise StreamlitSecretNotFoundError("Error parsing secrets file at {path}: {error}", path="x",
                                           error="AIza-segredo", error_id="failed-parsing-secrets-file")

    aviso = aplicar_segredos(ler)
    assert "formato válido" in aviso and "aspas" in aviso
    assert "AIza" not in aviso


def test_chave_faltando_ou_vazia():
    assert "Falta GEMINI_API_KEY" in aplicar_segredos(lambda: {"SENHA_DO_APP": "x"})
    assert "SENHA_DO_APP" in aplicar_segredos(lambda: {"SENHA_DO_APP": "x"})  # só o nome, pra achar o erro
    assert "vazia" in aplicar_segredos(lambda: {"GEMINI_API_KEY": ""})


def test_chave_do_env_local_vale_mesmo_com_secrets_sem_ela(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "do-env")
    assert aplicar_segredos(lambda: {"SENHA_DO_APP": "x"}) is None
    assert os.environ["GEMINI_API_KEY"] == "do-env"

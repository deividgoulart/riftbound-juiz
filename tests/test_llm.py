"""Testes do LLM (etapa 5): troca pro modelo de reserva quando o principal está indisponível.

Não chama a API: o cliente do Gemini é substituído por um "de mentira".
"""

from types import SimpleNamespace

import pytest
from google.genai import errors

import juiz.llm as llm_mod
from juiz.llm import LLMGemini


class ClienteFalso:
    """Responde erro 503 pros modelos da lista `indisponiveis` e texto normal pros outros."""

    def __init__(self, indisponiveis=(), erro=503):
        self.indisponiveis = set(indisponiveis)
        self.erro = erro
        self.chamadas = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.chamadas.append(model)
        if model in self.indisponiveis:
            raise errors.APIError(self.erro, {"error": {"message": "indisponível", "status": "UNAVAILABLE"}})
        uso = SimpleNamespace(prompt_token_count=100, candidates_token_count=20, thoughts_token_count=5)
        return SimpleNamespace(text=f" resposta do {model} ", usage_metadata=uso)


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)


def llm_com(cliente):
    llm = LLMGemini(modelos=["principal", "reserva-1", "reserva-2"])
    llm._cliente = cliente
    return llm


def test_usa_o_modelo_principal_quando_disponivel():
    llm = llm_com(ClienteFalso())
    assert llm.gerar("instruções", "mensagem") == "resposta do principal"
    assert llm.ultimo_uso["modelo"] == "principal" and llm.ultimo_uso["tokens_entrada"] == 100


def test_passa_pra_reserva_quando_o_principal_esta_sobrecarregado():
    cliente = ClienteFalso(indisponiveis={"principal"})
    llm = llm_com(cliente)
    assert llm.gerar("i", "m") == "resposta do reserva-1"
    assert cliente.chamadas == ["principal"] * LLMGemini.TENTATIVAS_POR_MODELO + ["reserva-1"]
    assert llm.ultimo_uso["modelo"] == "reserva-1"


def test_erro_que_nao_e_temporario_nao_tenta_de_novo():
    cliente = ClienteFalso(indisponiveis={"principal"}, erro=400)  # 400 = pedido errado
    with pytest.raises(errors.APIError):
        llm_com(cliente).gerar("i", "m")
    assert cliente.chamadas == ["principal"]


def test_todos_indisponiveis_levanta_o_ultimo_erro():
    cliente = ClienteFalso(indisponiveis={"principal", "reserva-1", "reserva-2"})
    with pytest.raises(errors.APIError):
        llm_com(cliente).gerar("i", "m")
    assert len(cliente.chamadas) == 3 * LLMGemini.TENTATIVAS_POR_MODELO


def test_modelo_sobrecarregado_fica_de_fora_nas_proximas_perguntas(monkeypatch):
    relogio = [1000.0]
    monkeypatch.setattr(llm_mod.time, "monotonic", lambda: relogio[0])
    cliente = ClienteFalso(indisponiveis={"principal"})
    llm = llm_com(cliente)
    llm.gerar("i", "m")  # 1ª pergunta: tenta o principal, falha e vai pra reserva
    cliente.chamadas.clear()
    llm.gerar("i", "m")  # 2ª pergunta: nem tenta o principal
    assert cliente.chamadas == ["reserva-1"]
    relogio[0] += LLMGemini.PAUSA_SEGUNDOS + 1  # passou o tempo: o principal volta pra lista
    cliente.indisponiveis.clear()
    cliente.chamadas.clear()
    assert llm.gerar("i", "m") == "resposta do principal"


def test_cota_diaria_esgotada_pula_direto_pro_proximo_modelo():
    from juiz.erros import CotaEsgotada

    class ClienteSemCota(ClienteFalso):
        def generate_content(self, model, contents, config):
            if model in self.indisponiveis:
                self.chamadas.append(model)
                raise errors.APIError(429, {"error": {"message": "Quota exceeded ... PerDay ...", "status": "RESOURCE_EXHAUSTED"}})
            return super().generate_content(model, contents, config)  # a classe mãe registra a chamada

    cliente = ClienteSemCota(indisponiveis={"principal"})
    llm = llm_com(cliente)
    assert llm.gerar("i", "m") == "resposta do reserva-1"
    assert cliente.chamadas == ["principal", "reserva-1"]  # não insiste no modelo sem cota

    todos = ClienteSemCota(indisponiveis={"principal", "reserva-1", "reserva-2"})
    with pytest.raises(CotaEsgotada):
        llm_com(todos).gerar("i", "m")

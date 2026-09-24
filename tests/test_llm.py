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


# --- Groq como reserva de outra empresa (etapa 8) ---

class RespostaHttp:
    def __init__(self, status, corpo, cabecalhos=None):
        self.status_code, self._corpo, self.headers, self.text = status, corpo, cabecalhos or {}, str(corpo)

    def json(self):
        return self._corpo


def groq_que_responde(monkeypatch, respostas):
    """Troca o httpx.post por uma fila de respostas prontas; devolve a lista dos corpos enviados."""
    import httpx

    enviados = []

    def post(url, json, headers, timeout):
        enviados.append(json)
        return respostas.pop(0)

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setenv("GROQ_API_KEY", "chave-de-teste")
    return enviados


OK_GROQ = RespostaHttp(200, {"choices": [{"message": {"content": " Não. [F1] "}}],
                             "usage": {"prompt_tokens": 900, "completion_tokens": 40}})


def test_groq_responde_e_esconde_o_raciocinio(monkeypatch):
    from juiz.llm import LLMGroq

    enviados = groq_que_responde(monkeypatch, [OK_GROQ])
    llm = LLMGroq("openai/gpt-oss-120b")
    assert llm.gerar("instruções", "pergunta") == "Não. [F1]"
    assert enviados[0]["messages"][0] == {"role": "system", "content": "instruções"}
    assert enviados[0]["include_reasoning"] is False
    assert llm.ultimo_uso == {"modelo": "groq/openai/gpt-oss-120b", "tokens_entrada": 900, "tokens_saida": 40}


def test_groq_tenta_de_novo_na_sobrecarga_e_para_na_cota_do_dia(monkeypatch):
    from juiz.llm import ErroGroq, LLMGroq

    sobrecarga = RespostaHttp(503, {"error": {"message": "over capacity"}})
    groq_que_responde(monkeypatch, [sobrecarga, OK_GROQ])
    assert LLMGroq().gerar("i", "m") == "Não. [F1]"

    groq_que_responde(monkeypatch, [sobrecarga, sobrecarga])
    with pytest.raises(ErroGroq, match="503"):
        LLMGroq().gerar("i", "m")

    por_dia = RespostaHttp(429, {"error": {"message": "Rate limit reached on tokens per day (TPD): Limit 200000"}})
    groq_que_responde(monkeypatch, [por_dia])
    with pytest.raises(llm_mod.CotaEsgotada):
        LLMGroq().gerar("i", "m")


def test_cadeia_passa_pro_groq_quando_os_gemini_falham(monkeypatch):
    from juiz.llm import LLMComReservas, LLMGroq

    groq_que_responde(monkeypatch, [OK_GROQ])
    cadeia = LLMComReservas([llm_com(ClienteFalso(indisponiveis={"principal", "reserva-1", "reserva-2"})), LLMGroq()])
    assert cadeia.gerar("i", "m") == "Não. [F1]"
    assert cadeia.ultimo_uso["modelo"].startswith("groq/")


def test_cadeia_pula_o_groq_sem_chave_e_prefere_o_erro_passageiro(monkeypatch):
    from juiz.llm import LLMComReservas, LLMGroq

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    gemini = llm_com(ClienteFalso(indisponiveis={"principal", "reserva-1", "reserva-2"}))
    with pytest.raises(errors.APIError):  # o 503 do Gemini, e não "falta a chave do Groq"
        LLMComReservas([gemini, LLMGroq()]).gerar("i", "m")

    class SemCota:
        nome = "sem-cota"

        def gerar(self, *a, **k):
            raise llm_mod.CotaEsgotada("x")

    with pytest.raises(errors.APIError):  # sobrecarga (passageira) vence "cota do dia"
        LLMComReservas([SemCota(), llm_com(ClienteFalso(indisponiveis={"principal", "reserva-1", "reserva-2"}))]).gerar("i", "m")


def test_resposta_vazia_conta_como_falha_e_passa_pra_proxima_reserva():
    from juiz.llm import LLMComReservas

    class Vazio:
        nome = "vazio"
        ultimo_uso = {}

        def gerar(self, *a, **k):
            return "   "

    cadeia = LLMComReservas([Vazio(), llm_com(ClienteFalso())])
    assert cadeia.gerar("i", "m") == "resposta do principal"
    with pytest.raises(RuntimeError, match="resposta vazia"):
        LLMComReservas([Vazio()]).gerar("i", "m")

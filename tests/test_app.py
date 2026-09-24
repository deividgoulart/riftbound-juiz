"""Testes da interface (etapa 6), com o AppTest do Streamlit.

O AppTest roda o app.py "sem navegador" e deixa inspecionar o que apareceria na tela.
O juiz de verdade é trocado por um "de mentira" (via session_state), então nada chama a API.
"""

import json

import pytest
from streamlit.testing.v1 import AppTest

from juiz import config
from juiz.responder import NAO_ENCONTREI, Fonte, Resposta


class JuizFalso:
    def __init__(self, resposta=None, erro=None):
        self.resposta, self.erro = resposta, erro
        self.historicos = []

    def responder(self, pergunta, historico=None):
        self.historicos.append(list(historico or []))
        if self.erro:
            raise self.erro
        self.resposta.pergunta = pergunta
        return self.resposta


def resposta_com_fontes():
    fontes = [
        Fonte(1, "faq", "FAQ: Can I use Ambush to play a unit to my base?", "https://faq/ambush", "x", 0.84,
              citacao_pendente=True, citada=True),
        Fonte(2, "crd", "Core Rules: regra 822", "https://crd#R822", "x", 0.71),
    ]
    return Resposta("?", "Não. O Ambush só vale em battlefields [F1] (CRD 822.1.b).", True, fontes,
                    regras={"822.1.b": "https://crd#R822.1.b"}, termos=[("emboscada", "Ambush")],
                    nota_busca=0.84, uso={"modelo": "modelo-falso", "tokens_entrada": 10, "tokens_saida": 5})


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.delenv("SENHA_DO_APP", raising=False)  # sem senha = rodando no seu computador, sem limites

    def criar(juiz):
        at = AppTest.from_file(str(config.RAIZ / "app.py"), default_timeout=30)
        at.session_state["juiz_de_teste"] = juiz
        return at.run()

    return criar


def eventos(tmp_path):
    arquivo = tmp_path / "conversas.jsonl"
    return [json.loads(l) for l in arquivo.open(encoding="utf-8")] if arquivo.exists() else []


def test_tela_inicial_tem_titulo_exemplos_e_creditos(app):
    at = app(JuizFalso(resposta_com_fontes()))
    assert not at.exception
    assert at.title[0].value == "⚖️ Juiz Riftbound"
    assert len(at.pills[0].options) == 4
    assert any("CC BY-SA 4.0" in m.value for m in at.sidebar.markdown)
    assert any("não oficial" in m.value for m in at.sidebar.markdown)


def test_pergunta_mostra_resposta_com_links_fontes_e_aviso(app, tmp_path):
    at = app(JuizFalso(resposta_com_fontes()))
    at.chat_input[0].set_value("posso usar emboscada na base?").run()
    assert not at.exception
    resposta = at.chat_message[1]
    assert '<a href="https://faq/ambush" target="_blank">F1</a>' in resposta.markdown[0].value
    assert '<a href="https://crd#R822.1.b" target="_blank">822.1.b</a>' in resposta.markdown[0].value
    assert [e.label for e in at.expander if e.label.startswith("Fontes")] == ["Fontes (1 citada, 1 também consultada)"]
    assert "Core Rules ainda não confirma" in at.info[0].value  # citação pendente
    assert len(at.get("feedback")) == 1
    registro = eventos(tmp_path)
    assert registro[-1]["tipo"] == "resposta" and registro[-1]["pergunta"] == "posso usar emboscada na base?"


def test_nao_encontrei_nao_mostra_fontes_nem_avaliacao(app):
    at = app(JuizFalso(Resposta("?", NAO_ENCONTREI, False, nota_busca=0.6)))
    at.chat_input[0].set_value("qual o melhor deck?").run()
    assert "Não encontrei" in at.chat_message[1].markdown[0].value
    assert len(at.get("feedback")) == 0
    assert not [e for e in at.expander if e.label.startswith("Fontes")]


def test_erro_na_api_mostra_mensagem_amigavel_e_registra(app, tmp_path):
    at = app(JuizFalso(erro=RuntimeError("Coloque GEMINI_API_KEY no arquivo .env")))
    at.chat_input[0].set_value("pergunta").run()
    assert "Não consegui responder agora" in at.error[0].value
    assert "GEMINI_API_KEY" in at.error[0].value
    assert eventos(tmp_path)[-1]["tipo"] == "erro"


def test_detalhes_da_busca_aparecem_quando_ligados(app):
    at = app(JuizFalso(resposta_com_fontes()))
    at.sidebar.toggle[0].set_value(True).run()
    at.chat_input[0].set_value("posso usar emboscada na base?").run()
    legenda = " ".join(c.value for c in at.chat_message[1].caption)
    assert "modelo-falso" in legenda and "emboscada → Ambush" in legenda


def test_cota_esgotada_mostra_aviso_especifico(app, tmp_path):
    from juiz.erros import CotaEsgotada

    at = app(JuizFalso(erro=CotaEsgotada("gemini-embedding-2")))
    at.chat_input[0].set_value("o que é open state?").run()
    assert "cota diária grátis" in at.warning[0].value
    assert not at.error
    assert eventos(tmp_path)[-1]["tipo"] == "erro"



def test_resposta_da_busca_reserva_avisa_na_tela(app):
    resposta = resposta_com_fontes()
    resposta.modelo_busca = "e5-small"
    at = app(JuizFalso(resposta))
    at.chat_input[0].set_value("posso usar emboscada na base?").run()
    legendas = " ".join(c.value for c in at.chat_message[1].caption)
    assert "modelo reserva (e5-small)" in legendas


def test_resposta_da_busca_principal_nao_mostra_aviso_de_reserva(app):
    resposta = resposta_com_fontes()
    resposta.modelo_busca = config.MODELO_EMBEDDINGS
    at = app(JuizFalso(resposta))
    at.chat_input[0].set_value("posso usar emboscada na base?").run()
    assert "modelo reserva" not in " ".join(c.value for c in at.chat_message[1].caption)



def test_segunda_pergunta_leva_a_conversa_anterior(app):
    juiz = JuizFalso(resposta_com_fontes())
    at = app(juiz)
    at.chat_input[0].set_value("como funciona a Chain?").run()
    at.chat_input[0].set_value("e se for durante um showdown?").run()
    assert juiz.historicos[0] == []
    assert juiz.historicos[1] == [("como funciona a Chain?", resposta_com_fontes().texto)]


# ---------------------------------------------------------------------------
# App publicado (etapa 8): modo convidado com limites e senha
# ---------------------------------------------------------------------------

@pytest.fixture
def app_publico(app, monkeypatch):
    import streamlit as st

    monkeypatch.setenv("SENHA_DO_APP", "segredo")
    monkeypatch.setattr(config, "LIMITE_POR_VISITA", 2)
    st.cache_resource.clear()  # o contador do dia é compartilhado entre sessões: cada teste começa do zero
    return app


def perguntar(at, texto="posso usar emboscada na base?"):
    return at.chat_input[0].set_value(texto).run()


def avisos_de_limite(at):
    return [i.value for i in at.info if "limite" in i.value or "Você usou" in i.value]


def test_publicado_mostra_modo_convidado_privacidade_e_nao_registra(app_publico, tmp_path):
    at = app_publico(JuizFalso(resposta_com_fontes()))
    assert "Modo convidado: 2 perguntas restantes" in at.caption[1].value
    assert "Não escreva dados pessoais" in at.caption[1].value
    perguntar(at)
    assert not at.exception
    assert len(at.get("feedback")) == 0  # sem registro local, sem 👍/👎
    assert eventos(tmp_path) == []
    assert "Modo convidado: 1 pergunta restante" in at.caption[1].value


def test_convidado_fica_bloqueado_depois_do_limite_da_visita(app_publico):
    juiz = JuizFalso(resposta_com_fontes())
    at = app_publico(juiz)
    perguntar(perguntar(at))
    assert "Você usou as 2 perguntas desta visita" in avisos_de_limite(at)[0]
    assert at.chat_input[0].disabled
    assert len(juiz.historicos) == 2


def test_limite_do_dia_vale_pra_todos_os_visitantes(app_publico, monkeypatch):
    monkeypatch.setattr(config, "LIMITE_DIARIO", 1)
    perguntar(app_publico(JuizFalso(resposta_com_fontes())))  # 1º visitante gasta a única pergunta do dia
    outro_visitante = app_publico(JuizFalso(resposta_com_fontes()))
    assert "limite de perguntas de convidados de hoje" in avisos_de_limite(outro_visitante)[0]
    assert outro_visitante.chat_input[0].disabled


def test_erro_devolve_a_pergunta_ao_limite_do_dia(app_publico, monkeypatch):
    monkeypatch.setattr(config, "LIMITE_DIARIO", 1)
    at = app_publico(JuizFalso(erro=RuntimeError("503")))
    perguntar(at)
    assert "Não consegui responder agora" in at.error[0].value
    assert not at.chat_input[0].disabled  # a pergunta que deu erro não contou


def test_senha_certa_libera_uso_sem_limite(app_publico):
    at = app_publico(JuizFalso(resposta_com_fontes()))
    at.sidebar.text_input[0].input("segredo")
    [b for b in at.sidebar.button if b.label == "Entrar"][0].click().run()
    assert "Uso sem limite liberado" in at.sidebar.success[0].value
    for _ in range(3):  # passa do limite de 2 da visita
        perguntar(at)
    assert not avisos_de_limite(at) and not at.chat_input[0].disabled
    assert not any("Modo convidado" in c.value for c in at.caption)


def test_senha_errada_nao_libera(app_publico):
    at = app_publico(JuizFalso(resposta_com_fontes()))
    at.sidebar.text_input[0].input("chute")
    [b for b in at.sidebar.button if b.label == "Entrar"][0].click().run()
    assert "Senha incorreta" in at.sidebar.error[0].value
    assert not at.sidebar.success


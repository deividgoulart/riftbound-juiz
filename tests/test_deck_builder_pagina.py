"""Testes da página do deck builder (fase 2), com o AppTest do Streamlit e um banco em memória."""

import pytest
from streamlit.testing.v1 import AppTest

from decks import colecao
from decks.importar import ler_lista
from decks.meus_decks import listar_decks, salvar_deck
from juiz import config

LISTA = "Legend:\n1 Jinx, Loose Cannon\nMain Deck:\n3 Jinx, Rebel\n2 Abandon\nRunes:\n6 Fury Rune\n6 Chaos Rune"


@pytest.fixture
def pagina(monkeypatch, banco, catalogo):
    monkeypatch.delenv("SENHA_DO_APP", raising=False)
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)

    def abrir(senha=None):
        if senha:
            monkeypatch.setenv("SENHA_DO_APP", senha)
        at = AppTest.from_file(str(config.RAIZ / "paginas" / "deck_builder.py"), default_timeout=30)
        at.session_state["deck_builder_de_teste"] = (banco, catalogo)
        return at.run()

    return abrir


def botao(at, rotulo):
    return next(b for b in at.button if b.label == rotulo)


def progresso(at) -> list[str]:
    return [p.proto.text for p in at.get("progress")]


def test_tela_local_mostra_colecao_editavel_e_decks(pagina, banco):
    colecao.salvar_alteracoes(banco, {"Abandon": 2, "Jinx, Rebel": 1})
    at = pagina()
    assert not at.exception
    assert at.title[0].value == "🃏 Deck builder"
    assert [m.value for m in at.metric] == ["2", "3"]  # cartas diferentes, cópias
    assert botao(at, "Salvar alterações")
    assert "Nenhum deck ainda." in at.info[0].value


def test_importar_deck_mostra_porcentagem_e_o_que_falta(pagina, banco):
    colecao.salvar_alteracoes(banco, {"Abandon": 2, "Jinx, Rebel": 1})
    at = pagina()
    next(t for t in at.text_input if t.label == "Nome do deck").input("Jinx de teste")
    at.text_area[0].input(LISTA)
    at = botao(at, "Importar deck").click().run()

    assert not at.exception
    assert [d["nome"] for d in listar_decks(banco)] == ["Jinx de teste"]
    assert any("importado" in s.value for s in at.success)
    assert any("mínimo é 40" in i.value for i in at.info)  # aviso das regras de construção
    # runas básicas contam como "tenho" (padrão): Abandon 2 + Jinx 1 + 12 runas de 18 cópias
    assert progresso(at) == ["83% · tenho 15 de 18 cópias"]
    assert any(e.label == "Faltam 3 cópias de 2 cartas" for e in at.expander)


def test_carta_nao_reconhecida_nao_salva_e_sugere(pagina, banco):
    at = pagina()
    at.text_area[0].input("3 Jinks Rebel\n2 Abandon")
    at = botao(at, "Importar deck").click().run()
    assert listar_decks(banco) == []
    assert "\"Jinks Rebel\" (quis dizer Jinx, Rebel?)" in at.error[0].value


def test_apagar_deck(pagina, banco, catalogo):
    salvar_deck(banco, "Velho", ler_lista("2 Abandon", catalogo))
    at = pagina()
    at = botao(at, "Apagar deck").click().run()
    assert listar_decks(banco) == []
    assert any("apagado" in s.value for s in at.success)


def test_publicado_sem_senha_e_so_leitura(pagina, banco, catalogo):
    salvar_deck(banco, "Jinx", ler_lista(LISTA, catalogo))
    at = pagina(senha="segredo")
    assert not at.exception
    rotulos = {b.label for b in at.button}
    assert not rotulos & {"Salvar alterações", "Importar deck", "Apagar deck", "Importar CSV"}
    assert any("Modo leitura" in c.value for c in at.caption)
    assert any("Turso" in w.value for w in at.warning)  # publicado sem banco na nuvem: avisa
    assert progresso(at)  # os decks continuam visíveis


def test_publicado_com_senha_libera_a_edicao(pagina):
    at = pagina(senha="segredo")
    at.sidebar.text_input[0].input("segredo")
    at = at.sidebar.button[0].click().run()
    assert at.session_state["dono"] is True
    assert botao(at, "Salvar alterações")

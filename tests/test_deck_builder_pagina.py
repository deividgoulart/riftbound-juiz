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
    monkeypatch.delenv("TOPDECK_API_KEY", raising=False)

    def abrir(senha=None, topdeck=None):
        if senha:
            monkeypatch.setenv("SENHA_DO_APP", senha)
        if topdeck:
            monkeypatch.setenv("TOPDECK_API_KEY", topdeck)
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


# --- Decks do meta ---

def coletar_meta(banco, catalogo):
    from tests.test_decks_meta import AGORA, cliente_falso, deck_obj, torneio
    from decks.meta import atualizar_meta

    decks = {2: deck_obj(lenda="Kennen, Heart of the Tempest")}
    atualizar_meta(banco, catalogo, "k", cliente=cliente_falso([torneio(decks=decks)], []), agora=AGORA)


def test_sem_chave_do_topdeck_explica_como_ligar(pagina):
    at = pagina()
    assert any("TOPDECK_API_KEY" in i.value for i in at.info)
    assert "Atualizar agora" not in {b.label for b in at.button}


def test_decks_do_meta_ficam_separados_dos_meus(pagina, banco, catalogo):
    salvar_deck(banco, "Meu deck", ler_lista("2 Abandon", catalogo))
    coletar_meta(banco, catalogo)
    at = pagina(topdeck="k")
    assert not at.exception
    assert any("Última coleta: 24/09/2026" in c.value for c in at.caption)
    assert botao(at, "Atualizar agora")
    textos = [m.value for m in at.markdown]
    assert sum("º em Liga de Sábado" in t for t in textos) == 8
    assert any(t.startswith("**Meu deck**") for t in textos)
    assert sum(b.label == "Apagar deck" for b in at.button) == 1  # só o manual pode ser apagado

    filtro = next(m for m in at.multiselect if m.label == "Lenda")
    assert "Kennen, Heart of the Tempest" in filtro.options  # com o campeão na frente
    at = filtro.select("Heart of the Tempest").run()
    textos = [m.value for m in at.markdown]
    assert [t for t in textos if "º em" in t] == ["**Kennen, Heart of the Tempest · 2º em Liga de Sábado** · "
                                                   "[lista original](https://topdeck.gg/bracket/t1) · 20/09/2026"]


def test_modo_leitura_nao_tem_atualizar_agora(pagina, banco, catalogo):
    coletar_meta(banco, catalogo)
    at = pagina(senha="segredo", topdeck="k")
    assert "Atualizar agora" not in {b.label for b in at.button}
    assert sum("º em Liga de Sábado" in m.value for m in at.markdown) == 8

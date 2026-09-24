"""Testes da conclusão dos decks (fase 2): porcentagem, cartas que faltam e ranking."""

import pytest

from decks import colecao
from decks.conclusao import calcular, ranking
from decks.importar import ler_lista
from decks.meus_decks import apagar_deck, cartas_dos_decks, listar_decks, salvar_deck

LISTA = "Loose Cannon\n3 Jinx, Rebel\n2 Abandon\n6 Fury Rune\n6 Chaos Rune\nSideboard:\n2 Void Seeker"


@pytest.fixture
def deck(banco, catalogo):
    id_ = salvar_deck(banco, "Jinx", ler_lista(LISTA, catalogo), url="https://exemplo/deck")
    return next(d for d in listar_decks(banco) if d["id"] == id_)


def test_sem_colecao_tem_zero(banco, deck):
    c = calcular(banco, deck)
    assert (c.tenho, c.total, c.porcentagem) == (0, 18, 0)
    assert len(c.faltando) == 5 and c.copias_faltando == 18


def test_parcial_e_copias_a_mais_nao_passam_de_100(banco, deck):
    colecao.salvar_alteracoes(banco, {"Jinx, Rebel": 1, "Abandon": 7, "Loose Cannon": 1})
    c = calcular(banco, deck)
    assert c.tenho == 1 + 2 + 1
    assert {x.carta: x.falta for x in c.faltando} == {"Jinx, Rebel": 2, "Fury Rune": 6, "Chaos Rune": 6}


def test_runas_garantidas_e_sideboard(banco, deck):
    colecao.salvar_alteracoes(banco, {"Jinx, Rebel": 3, "Abandon": 2, "Loose Cannon": 1})
    assert calcular(banco, deck, runas_garantidas=True).porcentagem == 100
    com_side = calcular(banco, deck, runas_garantidas=True, incluir_sideboard=True)
    assert (com_side.tenho, com_side.total) == (18, 20)


def test_ranking_do_mais_facil_pro_mais_dificil(banco, catalogo, deck):
    salvar_deck(banco, "Só um Abandon", ler_lista("1 Abandon", catalogo))
    salvar_deck(banco, "Void", ler_lista("3 Void Seeker", catalogo))
    colecao.definir(banco, "Abandon", 1)
    assert [c.deck["nome"] for c in ranking(banco)] == ["Só um Abandon", "Jinx", "Void"]


def test_salvar_listar_e_apagar(banco, catalogo, deck):
    assert deck["url"] == "https://exemplo/deck" and deck["origem"] == "manual"
    assert {l["carta"] for l in cartas_dos_decks(banco)[deck["id"]]} >= {"Loose Cannon", "Void Seeker"}
    apagar_deck(banco, deck["id"])
    assert listar_decks(banco) == [] and cartas_dos_decks(banco) == {}


def test_lista_vazia_nao_e_salva(banco, catalogo):
    with pytest.raises(ValueError):
        salvar_deck(banco, "Vazio", ler_lista("3 Carta Inventada", catalogo))

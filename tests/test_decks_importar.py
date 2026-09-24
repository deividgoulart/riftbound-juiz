"""Testes da importação de listas de deck (fase 2)."""

from decks.importar import ler_lista

LISTA = """Legend:
1 Jinx - Loose Cannon
Champion:
1 Jinx, Demolitionist
Main Deck (40):
3x Jinx, Rebel
Super Mega Death Rocket! x2
# comentário
2 Abandon
1 Abandon
Battlefields:
1 Altar of Blood
Runes:
6 Fury Rune
6 Chaos Rune
Sideboard:
2 Void Seeker
"""


def test_formatos_de_linha_secoes_e_repetidas_somam(catalogo):
    lista = ler_lista(LISTA, catalogo)
    assert lista.cartas == {
        ("lenda", "Loose Cannon"): 1,
        ("campeao", "Jinx, Demolitionist"): 1,
        ("principal", "Jinx, Rebel"): 3,
        ("principal", "Super Mega Death Rocket!"): 2,
        ("principal", "Abandon"): 3,
        ("battlefields", "Altar of Blood"): 1,
        ("runas", "Fury Rune"): 6,
        ("runas", "Chaos Rune"): 6,
        ("sideboard", "Void Seeker"): 2,
    }
    assert lista.nao_reconhecidas == []


def test_sem_cabecalho_a_secao_vem_do_tipo_da_carta(catalogo):
    lista = ler_lista("Loose Cannon\n3 Abandon\n1 Altar of Blood\n12 Order Rune", catalogo)
    assert lista.cartas == {("lenda", "Loose Cannon"): 1, ("principal", "Abandon"): 3,
                            ("battlefields", "Altar of Blood"): 1, ("runas", "Order Rune"): 12}


def test_cabecalhos_em_portugues(catalogo):
    lista = ler_lista("Lenda:\nLoose Cannon\nDeck principal:\n2 Abandon\nRunas:\n12 Fury Rune", catalogo)
    assert lista.total("principal") == 2 and lista.total("runas") == 12


def test_carta_nao_reconhecida_vem_com_sugestao(catalogo):
    lista = ler_lista("3 Jinks Rebel\n2 Abandon", catalogo)
    assert lista.nao_reconhecidas == [("Jinks Rebel", ["Jinx, Rebel"])]
    assert lista.cartas == {("principal", "Abandon"): 2}


def test_avisos_das_regras_de_construcao(catalogo):
    avisos = ler_lista(LISTA, catalogo).avisos
    assert any("mínimo é 40" in a for a in avisos)  # só 9 cartas no principal
    assert not any("lenda" in a for a in avisos)
    assert not any("runas" in a for a in avisos)

    avisos = ler_lista("4 Abandon\n3 Fury Rune", catalogo).avisos
    assert any("Abandon: 4 cópias" in a for a in avisos)
    assert any("1 lenda" in a for a in avisos)
    assert any("3 runas" in a for a in avisos)


def test_lenda_runas_e_copias_certas_nao_geram_aviso(catalogo):
    # O catálogo de teste é pequeno demais pra 40 cartas: sobra só o aviso do mínimo.
    principal = "\n".join(f"3 {c}" for c in ["Jinx, Rebel", "Abandon", "Void Seeker", "Super Mega Death Rocket!"])
    avisos = ler_lista(f"Loose Cannon\n{principal}\n6 Fury Rune\n6 Chaos Rune", catalogo).avisos
    assert avisos == ["O deck principal tem 12 cartas; o mínimo é 40, contando o campeão escolhido."]

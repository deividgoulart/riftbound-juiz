"""Testes do catálogo do deck builder (fase 2): sincronização com o banco e reconhecimento de nomes."""

from decks.catalogo import Catalogo, chave, sincronizar
from tests.conftest import CARTAS


def test_catalogo_vai_pro_banco_com_as_runas(banco, catalogo):
    nomes = {l["nome"] for l in banco.consultar("SELECT nome FROM cartas")}
    assert len(nomes) == len(CARTAS)
    assert {"Fury Rune", "Order Rune", "Loose Cannon"} <= nomes


def test_sincronizar_so_grava_quando_o_catalogo_muda(banco, catalogo):
    assert sincronizar(banco, CARTAS) is False  # mesmo catálogo: não reescreve
    menor = CARTAS[1:]
    assert sincronizar(banco, menor) is True
    assert banco.consultar("SELECT COUNT(*) AS n FROM cartas")[0]["n"] == len(menor)


def test_chave_ignora_caixa_acento_apostrofo_e_separador():
    assert chave("Jinx - Loose Cannon") == chave("jinx,loose  cannon") == "jinx, loose cannon"
    assert chave("Kai’Sa") == chave("kai'sa")


def test_resolver_nomes(catalogo):
    assert catalogo.resolver("Jinx, Rebel") == "Jinx, Rebel"
    assert catalogo.resolver("  jinx, rebel ") == "Jinx, Rebel"
    assert catalogo.resolver("Jinx - Rebel") == "Jinx, Rebel"
    assert catalogo.resolver("Jinx, Rebel (OGN-202)") == "Jinx, Rebel"  # código de coleção no fim
    # Lenda: o catálogo usa só o título; as listas escrevem com o campeão na frente
    assert catalogo.resolver("Loose Cannon") == "Loose Cannon"
    assert catalogo.resolver("Jinx, Loose Cannon") == "Loose Cannon"
    assert catalogo.resolver("Jinx - Loose Cannon") == "Loose Cannon"
    assert catalogo.resolver("Kennen, Heart of the Tempest") == "Heart of the Tempest"
    assert catalogo.resolver("Dark Child - Starter") == "Dark Child - Starter"
    assert catalogo.resolver("fury rune") == "Fury Rune"


def test_nome_desconhecido_nao_e_adivinhado_mas_tem_sugestao(catalogo):
    assert catalogo.resolver("Jinks Rebel") is None
    assert catalogo.sugestoes("Jinks Rebel")[0] == "Jinx, Rebel"
    assert catalogo.sugestoes("Teemo, Scout") == []


def test_nome_de_verdade_ganha_de_apelido_igual():
    lenda = CARTAS[0]  # "Loose Cannon", tag Jinx -> apelido "Jinx, Loose Cannon"
    carta_com_o_mesmo_nome = type(lenda)("Jinx, Loose Cannon", "Unit", "", "Fury", "", 1, None, None)
    catalogo = Catalogo([lenda, carta_com_o_mesmo_nome])
    assert catalogo.resolver("Jinx, Loose Cannon") == "Jinx, Loose Cannon"

"""Testes das compras (fase 2, etapa 3): links e lista da Liga Riftbound, e preços."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from decks import precos
from decks.catalogo import Catalogo
from decks.compras import link_da_carta, lista_de_compra, nome_na_liga
from decks.precos import Preco, atualizar_precos, custo_pra_completar, ler_precos, precos_guardados
from tests.conftest import CARTAS

PAGINA_DA_LIGA = (Path(__file__).parent / "dados" / "liga_precos.html").read_text(encoding="utf-8")
AGORA = datetime(2026, 9, 25, tzinfo=timezone.utc)
GALERIA = [{"codigo": "OGN-251/298", "nome": "Loose Cannon", "texto": "Riftbound Legend: Loose Cannon. X"},
           {"codigo": "OGN-202/298", "nome": "Jinx", "texto": "Riftbound Unit: Jinx, Rebel. X"},
           {"codigo": "OGN-202a/298", "nome": "Jinx", "texto": "Riftbound Unit: Jinx, Rebel. X"},
           {"codigo": "VEN-R01", "nome": "Fury Rune", "texto": "Riftbound Rune: Fury Rune."}]


@pytest.fixture
def com_codigos():
    return Catalogo(CARTAS, GALERIA)


def parametros(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_lenda_vai_com_o_campeao_na_frente_como_na_liga(catalogo):
    assert nome_na_liga("Loose Cannon", catalogo) == "Jinx - Loose Cannon"
    assert nome_na_liga("Heart of the Tempest", catalogo) == "Kennen - Heart of the Tempest"
    assert nome_na_liga("Jinx, Rebel", catalogo) == "Jinx, Rebel"


def test_link_com_codigo_vai_na_impressao_certa(com_codigos):
    assert parametros(link_da_carta("Loose Cannon", com_codigos)) == {
        "view": "cards/card", "card": "Jinx - Loose Cannon (251)", "ed": "OGN", "num": "251"}
    assert parametros(link_da_carta("Jinx, Rebel", com_codigos))["num"] == "202"  # a normal, não a "202a"
    assert parametros(link_da_carta("Fury Rune", com_codigos))["num"] == "R01"  # a Liga numera as runas assim


def test_link_sem_codigo_vai_pelo_nome(catalogo):
    url = link_da_carta("Loose Cannon", catalogo)
    assert url.startswith("https://www.ligariftbound.com.br/?")
    assert parametros(url) == {"view": "cards/card", "card": "Jinx - Loose Cannon"}


def test_lista_de_compra_no_formato_da_liga(catalogo):
    assert lista_de_compra([("Jinx, Rebel", 2), ("Loose Cannon", 1), ("Abandon", 0)], catalogo) == \
        "2 Jinx, Rebel\n1 Jinx - Loose Cannon"


# --- preços ---

def test_le_o_resumo_de_precos_da_pagina_real_da_liga():
    assert ler_precos(PAGINA_DA_LIGA) == Preco(menor=4.0, medio=4.33, maior=4.99, menor_foil=2.0)


def test_pagina_sem_precos_devolve_none():
    assert ler_precos("<html><body>Carta sem ofertas</body></html>") is None


def test_valor_com_milhar():
    assert precos._reais("R$ 1.234,50") == 1234.5


def cliente_da_liga(pedidos, status=200, html=PAGINA_DA_LIGA):
    def atender(request):
        pedidos.append(request)
        return httpx.Response(status, text=html)
    return httpx.Client(transport=httpx.MockTransport(atender))


def test_atualizar_precos_guarda_e_reaproveita_por_uma_semana(banco, catalogo):
    pedidos, esperas = [], []
    atualizar_precos(banco, catalogo, ["Jinx, Rebel", "Abandon", "Jinx, Rebel"], cliente_da_liga(pedidos),
                     agora=AGORA, esperar=esperas.append)
    assert len(pedidos) == 2 and esperas == [1.0]  # sem repetir carta, com pausa entre os pedidos
    assert precos_guardados(banco)["Abandon"]["menor"] == 4.0
    atualizar_precos(banco, catalogo, ["Abandon"], cliente_da_liga(pedidos), agora=AGORA + timedelta(days=6),
                     esperar=esperas.append)
    assert len(pedidos) == 2  # ainda vale
    atualizar_precos(banco, catalogo, ["Abandon"], cliente_da_liga(pedidos), agora=AGORA + timedelta(days=8),
                     esperar=esperas.append)
    assert len(pedidos) == 3


def test_liga_recusando_interrompe_a_busca(banco, catalogo):
    pedidos = []
    problemas = atualizar_precos(banco, catalogo, ["Abandon", "Jinx, Rebel", "Void Seeker"],
                                 cliente_da_liga(pedidos, status=429), agora=AGORA, esperar=lambda s: None)
    assert len(pedidos) == 1 and set(problemas) == {"Abandon", "Jinx, Rebel", "Void Seeker"}
    assert precos_guardados(banco) == {}


def test_carta_sem_preco_aparece_nos_problemas(banco, catalogo):
    problemas = atualizar_precos(banco, catalogo, ["Abandon"], cliente_da_liga([], html="<html></html>"),
                                 agora=AGORA, esperar=lambda s: None)
    assert problemas == {"Abandon": "a página da carta não tem preço"}


def test_custo_pra_completar_usa_a_mais_barata_entre_normal_e_foil():
    guardados = {"Jinx, Rebel": {"menor": 4.0, "menor_foil": 2.0}, "Abandon": {"menor": 1.5, "menor_foil": None}}
    assert custo_pra_completar([("Jinx, Rebel", 2), ("Abandon", 3), ("Void Seeker", 1)], guardados) == \
        (8.5, ["Void Seeker"])

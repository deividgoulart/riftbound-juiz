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
from juiz import config
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


def test_campeoes_vao_com_hifen_como_na_liga(catalogo):
    assert nome_na_liga("Loose Cannon", catalogo) == "Jinx - Loose Cannon"
    assert nome_na_liga("Heart of the Tempest", catalogo) == "Kennen - Heart of the Tempest"
    assert nome_na_liga("Jinx, Rebel", catalogo) == "Jinx - Rebel"  # com vírgula, a página da Liga não abre
    assert nome_na_liga("Abandon", catalogo) == "Abandon"


def test_link_usa_a_impressao_normal_e_nao_a_overnumbered_nem_a_promo():
    galeria = [{"codigo": "UNL-229/219", "nome": "Loose Cannon", "texto": "Riftbound Legend: Loose Cannon. X"},
               {"codigo": "UNL-187/219", "nome": "Loose Cannon", "texto": "Riftbound Legend: Loose Cannon. X"},
               {"codigo": "VEN-SP5/006", "nome": "Jinx", "texto": "Riftbound Unit: Jinx, Rebel. X"},
               {"codigo": "SFD-149/221", "nome": "Jinx", "texto": "Riftbound Unit: Jinx, Rebel. X"}]
    c = Catalogo(CARTAS, galeria)
    assert parametros(link_da_carta("Loose Cannon", c))["num"] == "187"
    assert parametros(link_da_carta("Jinx, Rebel", c)) == {"view": "cards/card", "card": "Jinx - Rebel (149)",
                                                           "ed": "SFD", "num": "149"}


def test_link_com_codigo_vai_na_impressao_certa(com_codigos):
    assert parametros(link_da_carta("Loose Cannon", com_codigos)) == {
        "view": "cards/card", "card": "Jinx - Loose Cannon (251)", "ed": "OGN", "num": "251"}
    assert parametros(link_da_carta("Jinx, Rebel", com_codigos))["num"] == "202"  # a normal, não a "202a"
    assert parametros(link_da_carta("Fury Rune", com_codigos))["num"] == "R01"  # a Liga numera as runas assim


def test_link_sem_codigo_vai_pelo_nome(catalogo):
    url = link_da_carta("Loose Cannon", catalogo)
    assert url.startswith("https://www.ligariftbound.com.br/?")
    assert parametros(url) == {"view": "cards/card", "card": "Jinx - Loose Cannon"}
    assert parametros(link_da_carta("Jinx, Rebel", catalogo))["card"] == "Jinx - Rebel"


def test_lista_de_compra_no_formato_da_liga(catalogo):
    assert lista_de_compra([("Jinx, Rebel", 2), ("Loose Cannon", 1), ("Abandon", 0)], catalogo) == \
        "2 Jinx - Rebel\n1 Jinx - Loose Cannon"


# --- preços ---

def test_le_o_resumo_de_precos_da_pagina_real_da_liga():
    assert ler_precos(PAGINA_DA_LIGA) == Preco(menor=4.0, medio=4.33, maior=4.99, menor_foil=2.0)


def test_pagina_sem_precos_devolve_none():
    assert ler_precos("<html><body>Carta sem ofertas</body></html>") is None


def test_valor_com_milhar():
    assert precos._reais("R$ 1.234,50") == 1234.5


def test_codigo_da_pagina_salva():
    trecho = 'onclick="mpcard.priceAlertInit(19, 251, &#39;OGN&#39;, &#39;251&#39;);"'
    assert precos.codigo_da_pagina(trecho) == "OGN-251"
    assert precos.codigo_da_pagina("<html></html>") is None


COPIA_TCG = {"updated": "2026-09-24", "prices": {
    "OGN-251": 0.23, "OGN-202": 0.50, "OGN-202a": 12.0,  # a arte alternativa é mais cara: vale a mais barata
    "VEN-R01": 0.07, "XYZ-001": 3.0, "OGN-999": None}}


def cliente_tcg(pedidos, dados=COPIA_TCG):
    def atender(request):
        pedidos.append(str(request.url))
        return httpx.Response(200, json=dados)
    return httpx.Client(transport=httpx.MockTransport(atender))


def test_precos_do_tcgplayer_por_codigo(com_codigos):
    pedidos = []
    precos_usd, data = precos.baixar_precos_tcg(com_codigos, cliente_tcg(pedidos))
    assert pedidos == [config.PRECOS_TCG_URL] and data == "2026-09-24"
    assert precos_usd == {"Loose Cannon": 0.23, "Jinx, Rebel": 0.50, "Fury Rune": 0.07}


def test_atualizar_precos_guarda_e_respeita_a_semana(banco, catalogo, com_codigos):  # catalogo: cria as tabelas
    assert precos.precisa_atualizar_precos(banco, AGORA)
    assert atualizar_precos(banco, com_codigos, cliente_tcg([]), agora=AGORA) == 3
    assert precos_guardados(banco) == {"Loose Cannon": 0.23, "Jinx, Rebel": 0.50, "Fury Rune": 0.07}
    assert precos.data_dos_precos(banco) == "2026-09-24"
    assert not precos.precisa_atualizar_precos(banco, AGORA + timedelta(days=6))
    assert precos.precisa_atualizar_precos(banco, AGORA + timedelta(days=8))


def test_copia_sem_cartas_reconhecidas_nao_apaga_os_precos(banco, com_codigos, catalogo):
    atualizar_precos(banco, com_codigos, cliente_tcg([]), agora=AGORA)
    assert atualizar_precos(banco, catalogo, cliente_tcg([]), agora=AGORA) == 0  # catálogo sem códigos
    assert len(precos_guardados(banco)) == 3


def test_estimativa_segue_as_duas_faixas_sem_salto():
    assert precos.estimar_reais(0.10) == round(0.10 * config.REAIS_POR_DOLAR_BARATAS, 2)
    assert precos.estimar_reais(10.0) == round(10.0 * config.REAIS_POR_DOLAR_CARAS, 2)
    assert precos.estimar_reais(None) is None
    # entre as faixas, a razão sobe aos poucos: sem salto de preço de um centavo de dólar pro outro
    razoes = [precos.reais_por_dolar(u / 100) for u in range(40, 300)]
    assert razoes == sorted(razoes)
    assert max(b / a for a, b in zip(razoes, razoes[1:])) < 1.03


def test_custo_pra_completar():
    custo, sem_preco = custo_pra_completar([("Jinx, Rebel", 2), ("Loose Cannon", 1), ("Void Seeker", 1)],
                                           {"Jinx, Rebel": 0.5, "Loose Cannon": 20.0})
    assert custo == round(2 * precos.estimar_reais(0.5) + precos.estimar_reais(20.0), 2)
    assert sem_preco == ["Void Seeker"]


def test_calibracao_mede_as_duas_faixas_e_o_erro():
    from decks.calibrar_precos import erros, razoes

    linhas = [{"usd": u, "liga_menor": u * 2} for u in (0.05, 0.1, 0.2, 0.3)] + \
             [{"usd": u, "liga_menor": u * 10} for u in (3, 5, 20, 40)]
    assert razoes(linhas) == (2, 10)
    assert erros(linhas, tamanho_da_soma=3) == (0, 0)  # razão constante em cada faixa: erro zero

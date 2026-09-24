"""Testes dos códigos das cartas (fase 2): galeria oficial da Riot com respostas falsas (sem rede)."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from decks import codigos
from decks.catalogo import Catalogo
from decks.codigos import codigo_base, mapa_de_codigos, normalizar_codigo
from decks.meta import RelatorioMeta, ler_deck
from decks import colecao
from juiz import config
from tests.conftest import CARTAS, carta

AGORA = datetime(2026, 9, 24, tzinfo=timezone.utc)


def impressao(codigo, nome, texto):
    """Uma carta como vem no JSON da galeria (só os campos que usamos)."""
    return {"name": nome, "publicCode": codigo, "cardImage": {"accessibilityText": texto, "url": "x"}}


# A galeria dá só o nome do campeão em "name"; o nome completo vem no texto da imagem.
PAGINA = {"pageProps": {"page": {"blades": [{"type": "x"}, {"cards": {"items": [
    impressao("OGN-202/298", "Jinx", "Riftbound Unit: Jinx, Rebel. When you discard one or more cards..."),
    impressao("OGN-202a/298", "Jinx", "Riftbound Unit: Jinx, Rebel. When you discard one or more cards..."),
    impressao("OGN-251/298", "Loose Cannon", "Riftbound Legend: Loose Cannon. At the start of your turn..."),
    impressao("UNL-131/219", "Abandon", "Riftbound Spell: Abandon. [Reaction] Counter a spell."),
    impressao("VEN-R01", "Fury Rune", "Riftbound Rune: Fury Rune."),
    impressao("OGN-099/298", "Dr. Mundo", "Riftbound Unit: Dr. Mundo, Expert. My Might is increased..."),
    impressao("XYZ-001/010", "Carta Nova", "Riftbound Spell: Carta Nova. Algo."),  # não está no catálogo
]}}]}}}


@pytest.fixture
def galeria():
    return codigos.ler_pagina(PAGINA)


@pytest.fixture
def catalogo_com_codigos(galeria):
    return Catalogo(CARTAS + [carta("Dr. Mundo, Expert", supertipos="Champion", tags="Dr. Mundo")], galeria)


@pytest.mark.parametrize("texto, esperado", [
    ("OGN-042/298", "OGN-42"), ("OGN-042", "OGN-42"), ("ogn-42", "OGN-42"),
    ("OGN-042a/298", "OGN-42a"), ("SFD-227*/221", "SFD-227*"), ("VEN-R04", "VEN-R4"), ("VEN-R4", "VEN-R4"),
])
def test_normalizar_codigo_das_tres_fontes(texto, esperado):
    assert normalizar_codigo(texto) == esperado


def test_codigo_base_tira_a_variante():
    assert codigo_base("OGN-42a") == "OGN-42" and codigo_base("SFD-227*") == "SFD-227" and codigo_base("VEN-R4") == "VEN-R4"


def test_ler_pagina_acha_a_lista_de_cartas(galeria):
    assert len(galeria) == 7
    assert galeria[0] == {"codigo": "OGN-202/298", "nome": "Jinx",
                          "texto": "Riftbound Unit: Jinx, Rebel. When you discard one or more cards..."}


def test_mapa_usa_o_nome_completo_do_texto_da_imagem(catalogo_com_codigos):
    c = catalogo_com_codigos
    assert c.codigos == {"OGN-202": "Jinx, Rebel", "OGN-202a": "Jinx, Rebel", "OGN-251": "Loose Cannon",
                         "UNL-131": "Abandon", "VEN-R1": "Fury Rune", "OGN-99": "Dr. Mundo, Expert"}
    assert c.por_codigo("OGN-202") == "Jinx, Rebel"
    assert c.por_codigo("OGN-202b") == "Jinx, Rebel"  # variante sem código próprio cai na carta normal
    assert c.por_codigo("XYZ-1") is None and c.por_codigo(None) is None


def test_sem_galeria_o_catalogo_funciona_pelo_nome():
    c = Catalogo(CARTAS)
    assert c.codigos == {} and c.por_codigo("OGN-202") is None and c.resolver("jinx - rebel") == "Jinx, Rebel"


def test_topdeck_usa_o_codigo_antes_do_nome(catalogo_com_codigos):
    deck = {"Legend": {"Nome Estranho da Lenda": {"id": "OGN-251", "count": 1}},
            "Mainboard": {"Jinks Rebel": {"id": "OGN-202", "count": 3}}}
    lista = ler_deck(deck, catalogo_com_codigos, RelatorioMeta())
    assert lista.cartas == {("lenda", "Loose Cannon"): 1, ("principal", "Jinx, Rebel"): 3}


def test_csv_da_liga_usa_o_codigo(banco, catalogo_com_codigos):
    texto = ('"Edicao (Sigla)","Card (PT)","Card (EN)",Quantidade,"Card #"\n'
             'OGN,,"Nome que não bate",2,202\n'
             'VEN,,"Fury Rune",6,R01\n')
    relatorio = colecao.ler_csv(texto, catalogo_com_codigos)
    assert relatorio.importadas == {"Jinx, Rebel": 2, "Fury Rune": 6}
    assert relatorio.desconhecidas == []


# --- download e cache ---

def test_baixar_galeria_pega_o_build_id_e_o_json():
    pedidos = []

    def atender(request):
        pedidos.append(str(request.url))
        if request.url.path.endswith("/card-gallery/"):
            return httpx.Response(200, text='<script id="__NEXT_DATA__">{"buildId":"abc123","x":1}</script>')
        return httpx.Response(200, json=PAGINA)

    cartas = codigos.baixar_galeria(httpx.Client(transport=httpx.MockTransport(atender)))
    assert len(cartas) == 7
    assert pedidos[1] == "https://riftbound.leagueoflegends.com/_next/data/abc123/en-us/card-gallery.json"


def test_galeria_sem_formato_conhecido_da_erro():
    cliente = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>sem build</html>")))
    with pytest.raises(RuntimeError, match="buildId"):
        codigos.baixar_galeria(cliente)


def test_carregar_galeria_guarda_e_reaproveita_por_uma_semana(tmp_path, monkeypatch, galeria):
    monkeypatch.setattr(config, "GALERIA_CARTAS", tmp_path / "galeria.json")
    baixadas = []

    def baixar():
        baixadas.append(1)
        return galeria

    assert codigos.carregar_galeria(AGORA, baixar) == galeria
    assert codigos.carregar_galeria(AGORA + timedelta(days=6), baixar) == galeria
    assert len(baixadas) == 1  # a segunda veio do arquivo
    codigos.carregar_galeria(AGORA + timedelta(days=8), baixar)
    assert len(baixadas) == 2


def test_carregar_galeria_com_falha_usa_a_salva_ou_nada(tmp_path, monkeypatch, galeria):
    monkeypatch.setattr(config, "GALERIA_CARTAS", tmp_path / "galeria.json")

    def falha():
        raise httpx.ConnectError("sem internet")

    assert codigos.carregar_galeria(AGORA, falha) == []
    (tmp_path / "galeria.json").write_text(json.dumps({"baixada_em": "2026-01-01T00:00:00+00:00", "cartas": galeria}))
    assert codigos.carregar_galeria(AGORA, falha) == galeria

"""Testes dos decks do meta (fase 2, etapa 2): API do TopDeck.gg com um servidor falso (sem rede)."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from decks import meta
from decks.importar import ler_lista
from decks.meta import ErroNoMeta, atualizar_meta, buscar_torneios, precisa_atualizar_meta
from decks.meus_decks import cartas_dos_decks, listar_decks, salvar_deck

AGORA = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)


def deck_obj(principal=None, lenda="Jinx, Loose Cannon"):
    return {
        "metadata": {"game": "Riftbound", "format": "Constructed", "importedFrom": "x"},  # não é carta
        "Legend": {lenda: {"id": "OGN-251", "count": 1}},
        "Champion": {"Jinx, Demolitionist": {"id": "OGN-030", "count": 1}},
        "Mainboard": principal or {"Jinx, Rebel": {"id": "OGN-202", "count": 3}, "Abandon": {"id": "OGN-100", "count": 2}},
        "Runes": {"Fury Rune": {"id": "OGN-R01", "count": 6}, "Chaos Rune": {"id": "OGN-R05", "count": 6}},
        "Battlefields": {"Altar of Blood": {"id": "OGN-280", "count": 1}},
        "Sideboard": {"Void Seeker": {"id": "OGN-150", "count": 2}},
    }


def torneio(tid="t1", jogadores=10, nome="Liga de Sábado", decks=None):
    decks = decks or {}
    return {"TID": tid, "tournamentName": nome, "game": "Riftbound", "format": "Constructed",
            "startDate": int(datetime(2026, 9, 20, tzinfo=timezone.utc).timestamp()),
            "standings": [{"name": f"Jogador {i}", "standing": i, "decklist": "x", "deckObj": decks.get(i, deck_obj())}
                          for i in range(1, jogadores + 1)]}


def cliente_falso(resposta, pedidos, status=200):
    def atender(request):
        pedidos.append(request)
        return httpx.Response(status, json=resposta)
    return httpx.Client(transport=httpx.MockTransport(atender))


def test_pedido_no_formato_da_api():
    pedidos = []
    buscar_torneios("minha-chave", dias=30, cliente=cliente_falso([], pedidos), agora=AGORA)
    pedido = pedidos[0]
    assert pedido.method == "POST" and str(pedido.url) == "https://topdeck.gg/api/v2/tournaments"
    assert pedido.headers["Authorization"] == "minha-chave"  # sem "Bearer": a API responde 401 com ele
    assert json.loads(pedido.content) == {"game": "Riftbound", "format": "Constructed",
                                          "start": int((AGORA - timedelta(days=30)).timestamp())}


@pytest.mark.parametrize("status, trecho", [(401, "TOPDECK_API_KEY"), (429, "limite"), (500, "HTTP 500")])
def test_erros_da_api_sem_mostrar_a_chave(status, trecho):
    with pytest.raises(ErroNoMeta) as erro:
        buscar_torneios("chave-secreta", cliente=cliente_falso({}, [], status=status))
    assert trecho in str(erro.value) and "chave-secreta" not in str(erro.value)


def test_coleta_guarda_so_o_top_8_de_torneios_com_8_jogadores(banco, catalogo):
    torneios = [torneio("grande", jogadores=12), torneio("pequeno", jogadores=5)]
    relatorio = atualizar_meta(banco, catalogo, "k", cliente=cliente_falso(torneios, []), agora=AGORA)
    assert (relatorio.torneios, relatorio.torneios_usados, relatorio.decks) == (2, 1, 8)

    decks = listar_decks(banco)
    assert len(decks) == 8 and {d["origem"] for d in decks} == {"topdeck"}
    primeiro = next(d for d in decks if d["colocacao"] == "1")
    assert primeiro["nome"] == "Jinx, Loose Cannon · 1º em Liga de Sábado"
    assert primeiro["url"] == "https://topdeck.gg/bracket/grande"
    assert primeiro["data"] == "2026-09-20" and primeiro["torneio"] == "Liga de Sábado"
    assert not any("Jogador" in str(v) for d in decks for v in d.values())  # nome do jogador não é guardado

    cartas = {(l["secao"], l["carta"]): l["quantidade"] for l in cartas_dos_decks(banco)[primeiro["id"]]}
    assert cartas == {("lenda", "Loose Cannon"): 1, ("campeao", "Jinx, Demolitionist"): 1,
                      ("principal", "Jinx, Rebel"): 3, ("principal", "Abandon"): 2, ("runas", "Fury Rune"): 6,
                      ("runas", "Chaos Rune"): 6, ("battlefields", "Altar of Blood"): 1, ("sideboard", "Void Seeker"): 2}


def test_deck_com_carta_desconhecida_fica_de_fora(banco, catalogo):
    decks = {1: deck_obj({"Carta Inventada": {"id": "X-1", "count": 3}}),
             2: dict(deck_obj(), Sideboard={"Outra Inventada": {"id": "X-2", "count": 1}})}
    relatorio = atualizar_meta(banco, catalogo, "k", cliente=cliente_falso([torneio(decks=decks)], []), agora=AGORA)
    assert relatorio.decks == 7 and relatorio.decks_ignorados == 1
    assert relatorio.desconhecidas == {"Carta Inventada": 1, "Outra Inventada": 1}
    # carta desconhecida só no sideboard: o deck entra, sem ela
    segundo = next(d for d in listar_decks(banco) if d["colocacao"] == "2")
    assert all(l["secao"] != "sideboard" for l in cartas_dos_decks(banco)[segundo["id"]])


def test_nova_coleta_troca_os_decks_do_meta_e_mantem_os_manuais(banco, catalogo):
    salvar_deck(banco, "Meu deck", ler_lista("2 Abandon", catalogo))
    atualizar_meta(banco, catalogo, "k", cliente=cliente_falso([torneio("a")], []), agora=AGORA)
    atualizar_meta(banco, catalogo, "k", cliente=cliente_falso([torneio("b", jogadores=8)], []), agora=AGORA)
    decks = listar_decks(banco)
    assert {d["url"] for d in decks if d["origem"] == "topdeck"} == {"https://topdeck.gg/bracket/b"}
    assert [d["nome"] for d in decks if d["origem"] == "manual"] == ["Meu deck"]
    ids = {d["id"] for d in decks}
    assert set(cartas_dos_decks(banco)) == ids  # as cartas dos decks antigos saíram junto


def test_coleta_vazia_nao_apaga_os_decks(banco, catalogo):
    atualizar_meta(banco, catalogo, "k", cliente=cliente_falso([torneio()], []), agora=AGORA)
    atualizar_meta(banco, catalogo, "k", cliente=cliente_falso([], []), agora=AGORA)
    assert len(listar_decks(banco)) == 8


def test_precisa_atualizar_a_cada_7_dias(banco, catalogo):
    assert precisa_atualizar_meta(banco, AGORA)
    atualizar_meta(banco, catalogo, "k", cliente=cliente_falso([], []), agora=AGORA)
    assert meta.ultima_coleta(banco) == AGORA
    assert not precisa_atualizar_meta(banco, AGORA + timedelta(days=6))
    assert precisa_atualizar_meta(banco, AGORA + timedelta(days=8))


def test_agrupar_insere_varias_linhas_por_comando():
    comandos = [("INSERT INTO t (a, b) VALUES (?, ?)", (i, i)) for i in range(250)] + [("DELETE FROM t", ())]
    agrupados = meta._agrupar(comandos, por_insert=100)
    assert agrupados[0] == ("DELETE FROM t", ())
    assert [len(p) for _, p in agrupados[1:]] == [200, 200, 100]

"""Preço das cartas que faltam (fase 2, etapa 3): resumo do marketplace da Liga Riftbound.

A página de cada carta na Liga mostra o "Preço Médio de Venda no Marketplace": menor, médio e maior
preço, separados em Normal e Foil, em texto. É isso que lemos. Os preços de cada loja aparecem como
imagens embaralhadas (a Liga não quer que sejam lidos automaticamente), então ficam de fora.

Cuidados pra não sobrecarregar o site:
- só busca as cartas que faltam, e só quando alguém com a senha clica em "Buscar preços";
- um pedido por segundo (config.PRECOS_INTERVALO_SEGUNDOS);
- o preço fica guardado no banco (tabela precos) e vale uma semana (config.PRECOS_VALIDOS_POR_DIAS).

O formato foi conferido numa página real salva em 25/09/2026 (tests/dados/liga_precos.html, só o
trecho dos preços). Se a Liga mudar o site, o leitor devolve None e a página avisa que não achou.
"""

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from bs4 import BeautifulSoup

from decks.banco import Banco
from decks.catalogo import Catalogo
from decks.compras import link_da_carta
from juiz import config

CABECALHOS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0 Safari/537.36"}

@dataclass
class Preco:
    menor: float | None
    medio: float | None
    maior: float | None
    menor_foil: float | None = None


def _reais(texto: str) -> float | None:
    """ "R$ 1.234,50" -> 1234.5"""
    achado = re.search(r"R\$\s*([\d.]+,\d{2})", texto or "")
    return float(achado.group(1).replace(".", "").replace(",", ".")) if achado else None


def ler_precos(html: str) -> Preco | None:
    """Resumo de preços da página da carta. None se a página não tiver (carta sem oferta ou site mudou)."""
    sopa = BeautifulSoup(html, "html.parser")
    por_tipo: dict[str, dict[str, float | None]] = {}
    for bloco in sopa.select("#container-show-price .container-price-mkp"):
        tipo = (bloco.select_one(".container-extras span") or bloco).get_text(" ", strip=True).lower()
        valores = {nome: _reais(el.get_text(" ", strip=True)) if (el := bloco.select_one(f".price-mkp .{nome} .price")) else None
                   for nome in ("min", "medium", "max")}
        por_tipo["foil" if "foil" in tipo else "normal"] = valores
    if not por_tipo:
        return None
    normal = por_tipo.get("normal") or por_tipo["foil"]  # carta que só existe em foil
    return Preco(normal["min"], normal["medium"], normal["max"], (por_tipo.get("foil") or {}).get("min"))


def buscar_preco(carta: str, catalogo: Catalogo, cliente: httpx.Client) -> Preco | None:
    resposta = cliente.get(link_da_carta(carta, catalogo))
    resposta.raise_for_status()
    return ler_precos(resposta.text)


def precos_guardados(banco: Banco) -> dict[str, dict]:
    return {l["carta"]: l for l in banco.consultar("SELECT * FROM precos")}


def atualizar_precos(banco: Banco, catalogo: Catalogo, cartas: list[str], cliente: httpx.Client | None = None,
                     agora: datetime | None = None, esperar=time.sleep) -> dict[str, str]:
    """Busca o preço das `cartas` que não têm um preço recente. Devolve {carta: problema} das que falharam.
    Grava cada preço assim que chega, então uma falha no meio não perde os anteriores."""
    agora = agora or datetime.now(timezone.utc)
    guardados = precos_guardados(banco)
    validade = timedelta(days=config.PRECOS_VALIDOS_POR_DIAS)
    pendentes = [c for c in dict.fromkeys(cartas)
                 if c not in guardados or agora - datetime.fromisoformat(guardados[c]["atualizado_em"]) > validade]
    cliente = cliente or httpx.Client(timeout=30, headers=CABECALHOS, follow_redirects=True)
    problemas = {}
    for i, carta in enumerate(pendentes):
        if i:
            esperar(config.PRECOS_INTERVALO_SEGUNDOS)
        try:
            preco = buscar_preco(carta, catalogo, cliente)
        except httpx.HTTPError as erro:
            problemas[carta] = f"a Liga não respondeu ({type(erro).__name__})"
            if isinstance(erro, httpx.HTTPStatusError) and erro.response.status_code in (403, 429):
                problemas.update({c: "busca interrompida: a Liga recusou os pedidos" for c in pendentes[i + 1:]})
                break
            continue
        if preco is None:
            problemas[carta] = "a página da carta não tem preço"
            continue
        banco.executar("INSERT OR REPLACE INTO precos (carta, menor, medio, maior, menor_foil, atualizado_em) "
                       "VALUES (?, ?, ?, ?, ?, ?)", (carta, preco.menor, preco.medio, preco.maior, preco.menor_foil,
                                                    agora.isoformat(timespec="seconds")))
    return problemas


def custo_pra_completar(faltando: list[tuple[str, int]], precos: dict[str, dict]) -> tuple[float, list[str]]:
    """(soma de cópias que faltam × menor preço, cartas sem preço). A foil também serve pro deck, então
    vale a mais barata entre normal e foil."""
    total, sem_preco = 0.0, []
    for carta, qtd in faltando:
        guardado = precos.get(carta) or {}
        opcoes = [v for v in (guardado.get("menor"), guardado.get("menor_foil")) if v is not None]
        menor = min(opcoes) if opcoes else None
        if menor is None:
            sem_preco.append(carta)
        else:
            total += menor * qtd
    return round(total, 2), sem_preco

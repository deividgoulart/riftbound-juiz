"""Preço estimado das cartas que faltam (fase 2, etapa 3).

Por que estimado: a Liga Riftbound tem o preço de verdade no Brasil, mas barra programas (a primeira
tentativa de ler as páginas dela foi recusada já na 1ª carta) e mostra os preços de cada loja como
imagens embaralhadas. Não contornamos isso: o preço real continua a um clique, no link da carta e na
Compra por Lista.

Como estima:
1. Preço de mercado do TCGplayer (EUA), numa cópia diária e pública no GitHub (config.PRECOS_TCG_URL,
   que lê o tcgcsv.com). Vem por código de carta ("VEN-021", "VEN-021a"...), que vira nome pela galeria
   oficial (decks/codigos.py). Das várias impressões, vale a mais barata: qualquer uma serve pro deck.
2. Reais = dólares × config.REAIS_POR_DOLAR_TCG, calibrado com preços reais da Liga
   (decks/calibrar_precos.py). O erro medido fica em config e aparece na tela.

A leitura da página da Liga (ler_precos) continua aqui, mas só pra calibrar: com páginas salvas à mão.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from bs4 import BeautifulSoup

from decks.banco import Banco, agrupar_inserts
from decks.catalogo import Catalogo
from juiz import config


# --- preço do TCGplayer ---

def baixar_precos_tcg(catalogo: Catalogo, cliente: httpx.Client | None = None) -> tuple[dict[str, float], str | None]:
    """({carta: menor preço em US$ entre as impressões}, data da cópia)."""
    cliente = cliente or httpx.Client(timeout=60, follow_redirects=True)
    resposta = cliente.get(config.PRECOS_TCG_URL)
    resposta.raise_for_status()
    dados = resposta.json()
    precos: dict[str, float] = {}
    for codigo, usd in (dados.get("prices") or {}).items():
        carta = catalogo.por_codigo(codigo)
        if carta and isinstance(usd, (int, float)) and usd > 0:
            precos[carta] = min(usd, precos.get(carta, usd))
    return precos, dados.get("updated")


def atualizar_precos(banco: Banco, catalogo: Catalogo, cliente: httpx.Client | None = None,
                     agora: datetime | None = None) -> int:
    """Troca os preços guardados pelos da cópia mais recente (numa transação só). Devolve quantas cartas
    têm preço. Uma cópia vazia (ex.: galeria de códigos indisponível) não apaga os preços que já existem."""
    agora = agora or datetime.now(timezone.utc)
    precos, data = baixar_precos_tcg(catalogo, cliente)
    comandos: list[tuple[str, tuple]] = []
    if precos:
        comandos.append(("DELETE FROM precos_tcg", ()))
        comandos += agrupar_inserts([("INSERT INTO precos_tcg (carta, usd) VALUES (?, ?)", (c, u)) for c, u in precos.items()])
        comandos.append(("INSERT OR REPLACE INTO meta (chave, valor) VALUES ('precos_data_tcg', ?)", (data,)))
    comandos.append(("INSERT OR REPLACE INTO meta (chave, valor) VALUES ('precos_em', ?)", (agora.isoformat(timespec="seconds"),)))
    banco.lote(comandos)
    return len(precos)


def precos_guardados(banco: Banco) -> dict[str, float]:
    return {l["carta"]: l["usd"] for l in banco.consultar("SELECT carta, usd FROM precos_tcg")}


def data_dos_precos(banco: Banco) -> str | None:
    linha = banco.consultar("SELECT valor FROM meta WHERE chave = 'precos_data_tcg'")
    return linha[0]["valor"] if linha else None


def precisa_atualizar_precos(banco: Banco, agora: datetime | None = None) -> bool:
    linha = banco.consultar("SELECT valor FROM meta WHERE chave = 'precos_em'")
    agora = agora or datetime.now(timezone.utc)
    return not linha or agora - datetime.fromisoformat(linha[0]["valor"]) > timedelta(days=config.PRECOS_ATUALIZAR_A_CADA_DIAS)


# --- estimativa em reais ---

def estimar_reais(usd: float | None) -> float | None:
    return round(usd * config.REAIS_POR_DOLAR_TCG, 2) if usd is not None else None


def custo_pra_completar(faltando: list[tuple[str, int]], precos_usd: dict[str, float]) -> tuple[float, list[str]]:
    """(custo estimado em reais das cópias que faltam, cartas sem preço)."""
    total, sem_preco = 0.0, []
    for carta, qtd in faltando:
        if carta in precos_usd:
            total += estimar_reais(precos_usd[carta]) * qtd
        else:
            sem_preco.append(carta)
    return round(total, 2), sem_preco


# --- página salva da Liga (só pra calibrar) ---

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
    """Resumo "Preço Médio de Venda no Marketplace" da página da carta (normal e foil). None se não houver."""
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


def codigo_da_pagina(html: str) -> str | None:
    """Coleção e número da impressão, como a própria página informa: priceAlertInit(19, 251, 'OGN', '251')."""
    achado = re.search(r"priceAlertInit\(\d+,\s*\d+,\s*'([A-Z0-9]+)',\s*'([^']+)'\)", html.replace("&#39;", "'"))
    return f"{achado.group(1)}-{achado.group(2)}" if achado else None

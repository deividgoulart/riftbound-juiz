"""Calibra a conversão do preço do TCGplayer pro MENOR preço da Liga Riftbound, com páginas salvas.

Uso (a partir da raiz do projeto):
    python -m decks.calibrar_precos pasta_com_paginas/

Pra cada página salva (Ctrl+S na página da carta na Liga), lê o menor preço do marketplace (versão
normal) e a coleção/número da impressão, busca o preço do TCGplayer da mesma impressão e calcula quantos
reais o menor anúncio da Liga cobra por dólar do TCGplayer, em duas faixas (config.FAIXA_BARATA_ATE_USD e
FAIXA_CARA_DESDE_USD): carta barata e carta cara seguem razões bem diferentes. Mede o erro deixando cada
carta de fora do ajuste (pra não medir com a própria carta): por carta e na soma de 10 cartas.
Grava a tabela em avaliacao/precos_liga_calibracao.csv e mostra os valores pra copiar em juiz/config.py.
Salve as páginas no mesmo dia (ou perto) da cópia do TCGplayer, que muda todo dia. Páginas de cartas
entre as duas faixas ajudam: sem elas, a razão ali é só interpolada.
"""

import argparse
import csv
import random
import statistics
import sys
from pathlib import Path

import httpx

from decks.codigos import normalizar_codigo
from decks.precos import codigo_da_pagina, ler_precos, reais_por_dolar
from juiz import config

SAIDA = config.RAIZ / "avaliacao" / "precos_liga_calibracao.csv"


def ler_pasta(pasta: Path) -> list[dict]:
    linhas = []
    for arquivo in sorted(pasta.glob("*.htm*")):
        html = arquivo.read_text(encoding="utf-8", errors="replace")
        preco, codigo = ler_precos(html), codigo_da_pagina(html)
        if preco and preco.medio and codigo:
            linhas.append({"pagina": arquivo.stem.split(" _ ")[0], "codigo": normalizar_codigo(codigo),
                           "liga_menor": preco.menor, "liga_medio": preco.medio, "liga_maior": preco.maior})
    return linhas


def razoes(linhas: list[dict]) -> tuple[float, float]:
    """(reais por dólar na faixa barata, na faixa cara): mediana das razões de cada faixa."""
    def mediana(faixa):
        return statistics.median(l["liga_menor"] / l["usd"] for l in faixa) if faixa else None
    baratas = mediana([l for l in linhas if l["usd"] <= config.FAIXA_BARATA_ATE_USD])
    caras = mediana([l for l in linhas if l["usd"] >= config.FAIXA_CARA_DESDE_USD])
    return baratas or caras, caras or baratas


def estimar(l: dict, ajuste: tuple[float, float]) -> float:
    return l["usd"] * reais_por_dolar(l["usd"], *ajuste)


def erros(linhas: list[dict], tamanho_da_soma: int = 10, sorteios: int = 3000) -> tuple[float, float]:
    """(erro mediano por carta, erro mediano na soma de `tamanho_da_soma` cartas), deixando cada carta de fora."""
    estimado = [estimar(l, razoes(linhas[:i] + linhas[i + 1:])) for i, l in enumerate(linhas)]
    por_carta = statistics.median(abs(e - l["liga_menor"]) / l["liga_menor"] for e, l in zip(estimado, linhas))
    sorteio = random.Random(1)
    n = min(tamanho_da_soma, len(linhas))
    somas = []
    for _ in range(sorteios):
        idx = sorteio.sample(range(len(linhas)), n)
        real = sum(linhas[i]["liga_menor"] for i in idx)
        somas.append(abs(sum(estimado[i] for i in idx) - real) / real)
    return por_carta, statistics.median(somas)


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Calibra a conversão TCGplayer -> reais com páginas salvas da Liga.")
    parser.add_argument("pasta", type=Path)
    args = parser.parse_args()

    linhas = ler_pasta(args.pasta)
    dados = httpx.get(config.PRECOS_TCG_URL, timeout=60, follow_redirects=True).json()
    tcg = {normalizar_codigo(c): u for c, u in dados["prices"].items() if isinstance(u, (int, float)) and u > 0}
    for l in linhas:
        l["usd"] = tcg.get(l["codigo"])
    sem_tcg = [l["pagina"] for l in linhas if not l["usd"]]
    linhas = [l for l in linhas if l["usd"]]
    if len(linhas) < 5:
        sys.exit(f"Só {len(linhas)} páginas com preço nas duas fontes; salve mais páginas.")

    baratas, caras = razoes(linhas)
    por_carta, soma_10 = erros(linhas)
    with SAIDA.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, ["pagina", "codigo", "usd", "liga_menor", "liga_medio", "liga_maior"])
        escritor.writeheader()
        escritor.writerows(sorted(linhas, key=lambda l: l["usd"]))
    no_meio = sum(config.FAIXA_BARATA_ATE_USD < l["usd"] < config.FAIXA_CARA_DESDE_USD for l in linhas)
    print(f"{len(linhas)} cartas (TCGplayer de {dados.get('updated')}); sem preço no TCGplayer: {sem_tcg or 'nenhuma'}")
    print(f"Entre US$ {config.FAIXA_BARATA_ATE_USD:.2f} e US$ {config.FAIXA_CARA_DESDE_USD:.2f}: {no_meio} cartas"
          + (" (a razão nessa faixa é só interpolada)" if not no_meio else ""))
    print(f"Tabela salva em {SAIDA.relative_to(config.RAIZ)}")
    print(f"\nPra juiz/config.py:\nREAIS_POR_DOLAR_BARATAS = {baratas:.2f}\nREAIS_POR_DOLAR_CARAS = {caras:.2f}\n"
          f"ERRO_TIPICO_POR_CARTA = {por_carta:.2f}\nERRO_TIPICO_10_CARTAS = {soma_10:.2f}")


if __name__ == "__main__":
    main()

"""Comprar o que falta (fase 2, etapa 3): links e lista de compra da Liga Riftbound.

- Link de cada carta: a página dela na Liga, com o resumo de preços do marketplace. Com o código
  (galeria oficial, decks/codigos.py), o link vai direto na impressão certa
  ("?view=cards/card&card=Jinx - Loose Cannon (251)&ed=OGN&num=251", o formato da própria Liga);
  sem ele, vai pela busca por nome.
- Lista de compra: o texto "3 Nome" de tudo que falta num deck, pra colar na "Compra por Lista" da
  Liga, que monta o carrinho mais barato entre as lojas (o "carrinho geral" que o README pedia).

A Liga escreve as lendas como "Campeão - Título" ("Jinx - Loose Cannon"), e é assim que elas vão.
"""

from urllib.parse import urlencode

from decks.catalogo import Catalogo, nome_da_lenda
from juiz import config


def nome_na_liga(carta: str, catalogo: Catalogo) -> str:
    if carta in catalogo and "Legend" in catalogo.cartas[carta].tipos.split():
        return nome_da_lenda(carta, catalogo, separador=" - ")
    return carta


def link_da_carta(carta: str, catalogo: Catalogo) -> str:
    nome = nome_na_liga(carta, catalogo)
    codigo = catalogo.codigo_de(carta)  # "OGN-251" ou "VEN-R1"
    if codigo:
        colecao, _, numero = codigo.partition("-")
        if numero.startswith("R"):  # runas: a Liga numera "R04", e o código normalizado é "R4"
            numero = "R" + numero[1:].zfill(2)
        return config.LIGA_URL + "?" + urlencode({"view": "cards/card", "card": f"{nome} ({numero})",
                                                  "ed": colecao, "num": numero})
    return config.LIGA_URL + "?" + urlencode({"view": "cards/card", "card": nome})


def lista_de_compra(faltando: list[tuple[str, int]], catalogo: Catalogo) -> str:
    """[(carta, cópias que faltam)] -> "3 Jinx - Rebel\\n1 Jinx - Loose Cannon", pra Compra por Lista."""
    return "\n".join(f"{qtd} {nome_na_liga(carta, catalogo)}" for carta, qtd in faltando if qtd > 0)

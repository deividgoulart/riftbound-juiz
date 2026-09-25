"""Cartas pra trocar ou vender (fase 3): o que eu tenho a mais do que um deck usa.

Regra automática, pelo tipo da carta (config.GUARDAR_POR_TIPO):
- Battlefield e lenda: um deck usa 1 de cada, então guardo 1;
- runas básicas: o Rune Deck tem 12 (CRD 103.2), então guardo 12;
- o resto (unidades, campeões, spells, gear): até 3 cópias por nome num deck, então guardo 3.
O que passa disso vai pra lista.

Ajuste na mão (tabela trocas): pra uma carta, "quero trocar N" vale no lugar da regra. Com 0, a carta
sai da lista mesmo sobrando (quero guardar); acima do excedente, entra mesmo dentro do limite.
"""

from dataclasses import dataclass

from decks.banco import Banco
from decks.catalogo import Carta, Catalogo
from decks.colecao import listar as listar_colecao
from juiz import config


@dataclass
class CartaPraTrocar:
    carta: str
    tenho: int
    guardar: int  # quantas a regra do tipo manda guardar
    trocar: int  # quantas vão pra lista (regra ou ajuste)
    ajustado: bool  # o dono mudou a quantidade na mão

    @property
    def excedente(self) -> int:
        return max(0, self.tenho - self.guardar)


def quantas_guardar(carta: Carta | None) -> int:
    if carta is None:
        return config.GUARDAR_POR_TIPO["padrao"]
    for tipo in carta.tipos.split():
        if tipo in config.GUARDAR_POR_TIPO:
            return config.GUARDAR_POR_TIPO[tipo]
    return config.GUARDAR_POR_TIPO["padrao"]


def ajustes(banco: Banco) -> dict[str, int]:
    return {l["carta"]: l["quantidade"] for l in banco.consultar("SELECT carta, quantidade FROM trocas")}


def listar(banco: Banco, catalogo: Catalogo) -> list[CartaPraTrocar]:
    """As cartas que vão pra lista (trocar > 0), por nome."""
    na_mao = ajustes(banco)
    lista = []
    for nome, tenho in sorted(listar_colecao(banco).items()):
        guardar = quantas_guardar(catalogo.cartas.get(nome))
        ajustado = nome in na_mao
        trocar = min(na_mao[nome], tenho) if ajustado else max(0, tenho - guardar)
        if trocar > 0:
            lista.append(CartaPraTrocar(nome, tenho, guardar, trocar, ajustado))
    return lista


def ajustar(banco: Banco, carta: str, quantidade: int | None) -> None:
    """Quantas trocar dessa carta (0 = guardar todas). None volta pra regra do tipo."""
    if quantidade is None:
        banco.executar("DELETE FROM trocas WHERE carta = ?", (carta,))
    else:
        banco.executar("INSERT OR REPLACE INTO trocas (carta, quantidade) VALUES (?, ?)", (carta, int(quantidade)))

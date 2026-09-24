"""Quanto de cada deck eu já tenho (fase 2): porcentagem de conclusão e cartas que faltam.

Conta cópias, não cartas diferentes: um deck com 3 Jinx, Rebel, quando eu tenho 1, está com 1 de 3
cópias dessa carta. A porcentagem é a soma do que eu tenho (até o que o deck pede) dividida pelo
total de cópias do deck, então ter cópias a mais não passa de 100%.

- A mesma carta em duas seções (ex.: principal e sideboard) soma o que o deck pede.
- O sideboard fica de fora por padrão: ele não é necessário pra jogar.
- As runas básicas podem contar como "tenho": quase todo jogador tem as de um deck inicial.
"""

from dataclasses import dataclass, field

from decks.banco import Banco
from decks.meus_decks import listar_decks
from juiz import config


@dataclass
class CartaDoDeck:
    carta: str
    precisa: int
    tem: int

    @property
    def falta(self) -> int:
        return max(0, self.precisa - self.tem)


@dataclass
class Conclusao:
    deck: dict
    cartas: list[CartaDoDeck] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(c.precisa for c in self.cartas)

    @property
    def tenho(self) -> int:
        return sum(min(c.tem, c.precisa) for c in self.cartas)

    @property
    def porcentagem(self) -> float:
        return 100 * self.tenho / self.total if self.total else 0.0

    @property
    def faltando(self) -> list[CartaDoDeck]:
        return [c for c in self.cartas if c.falta]

    @property
    def copias_faltando(self) -> int:
        return sum(c.falta for c in self.cartas)


def _cartas(banco: Banco, deck_id: str | None, incluir_sideboard: bool, runas_garantidas: bool) -> dict[str, list[CartaDoDeck]]:
    """Cartas de um deck (ou de todos, com deck_id=None) com o que eu tenho, numa consulta só."""
    linhas = banco.consultar(
        """SELECT dc.deck_id, dc.carta, SUM(dc.quantidade) AS precisa, COALESCE(c.quantidade, 0) AS tem
           FROM deck_cartas dc LEFT JOIN colecao c ON c.carta = dc.carta
           WHERE (? IS NULL OR dc.deck_id = ?) AND (? OR dc.secao != 'sideboard')
           GROUP BY dc.deck_id, dc.carta ORDER BY dc.carta""",
        (deck_id, deck_id, int(incluir_sideboard)),
    )
    por_deck: dict[str, list[CartaDoDeck]] = {}
    for l in linhas:
        tem = l["precisa"] if runas_garantidas and l["carta"] in config.RUNAS_BASICAS else l["tem"]
        por_deck.setdefault(l["deck_id"], []).append(CartaDoDeck(l["carta"], l["precisa"], tem))
    return por_deck


def calcular(banco: Banco, deck: dict, incluir_sideboard: bool = False, runas_garantidas: bool = False) -> Conclusao:
    return Conclusao(deck, _cartas(banco, deck["id"], incluir_sideboard, runas_garantidas).get(deck["id"], []))


def ranking(banco: Banco, incluir_sideboard: bool = False, runas_garantidas: bool = False) -> list[Conclusao]:
    """Todos os decks, do mais fácil pro mais difícil de montar (mais completo, depois menos cópias faltando)."""
    por_deck = _cartas(banco, None, incluir_sideboard, runas_garantidas)
    conclusoes = [Conclusao(deck, por_deck.get(deck["id"], [])) for deck in listar_decks(banco)]
    return sorted(conclusoes, key=lambda c: (-c.porcentagem, c.copias_faltando, c.deck["nome"]))

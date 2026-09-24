"""Decks guardados no banco (fase 2): salvar, listar e apagar.

Cada deck guarda de onde veio (origem, link, data, torneio e colocação). Na importação manual, só o
nome é obrigatório; os outros campos já existem pros decks do meta, que virão de sites de torneio.
"""

import uuid
from datetime import datetime, timezone

from decks.banco import Banco
from decks.importar import ListaDeDeck


def salvar_deck(banco: Banco, nome: str, lista: ListaDeDeck, origem: str = "manual", url: str | None = None,
                data: str | None = None, torneio: str | None = None, colocacao: str | None = None) -> str:
    """Grava o deck e as cartas numa transação só. Devolve o id do deck."""
    if not lista.cartas:
        raise ValueError("a lista não tem nenhuma carta reconhecida")
    id_ = uuid.uuid4().hex[:12]  # gerado aqui, pra gravar o deck e as cartas no mesmo lote
    criado_em = datetime.now(timezone.utc).isoformat(timespec="seconds")
    comandos = [(
        "INSERT INTO decks (id, nome, origem, url, data, torneio, colocacao, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (id_, nome.strip() or "Deck sem nome", origem, url or None, data or None, torneio or None, colocacao or None, criado_em),
    )]
    comandos += [("INSERT INTO deck_cartas (deck_id, carta, secao, quantidade) VALUES (?, ?, ?, ?)", (id_, carta, secao, qtd))
                 for (secao, carta), qtd in lista.cartas.items()]
    banco.lote(comandos)
    return id_


def listar_decks(banco: Banco) -> list[dict]:
    return banco.consultar("SELECT * FROM decks ORDER BY criado_em DESC, nome")


def cartas_dos_decks(banco: Banco) -> dict[str, list[dict]]:
    """Cartas de todos os decks, numa consulta só (no Turso, cada consulta é uma ida à nuvem)."""
    por_deck: dict[str, list[dict]] = {}
    for linha in banco.consultar("SELECT deck_id, carta, secao, quantidade FROM deck_cartas ORDER BY secao, carta"):
        por_deck.setdefault(linha.pop("deck_id"), []).append(linha)
    return por_deck


def apagar_deck(banco: Banco, deck_id: str) -> None:
    banco.lote([("DELETE FROM deck_cartas WHERE deck_id = ?", (deck_id,)), ("DELETE FROM decks WHERE id = ?", (deck_id,))])

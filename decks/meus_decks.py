"""Decks guardados no banco (fase 2): salvar, listar e apagar.

Cada deck guarda de onde veio (origem, link, data, torneio e colocação). Na importação manual, só o
nome é obrigatório; os outros campos já existem pros decks do meta, que virão de sites de torneio.
"""

import uuid
from datetime import datetime, timezone

from decks.banco import Banco
from decks.importar import ListaDeDeck


def comandos_do_deck(nome: str, lista: ListaDeDeck, origem: str = "manual", url: str | None = None,
                     data: str | None = None, torneio: str | None = None,
                     colocacao: str | None = None) -> tuple[str, list[tuple[str, tuple]]]:
    """(id, comandos SQL) que gravam o deck e as cartas. Separado de salvar_deck pra quem precisa
    juntar vários decks numa transação só (os decks do meta, em decks/meta.py)."""
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
    return id_, comandos


def salvar_deck(banco: Banco, nome: str, lista: ListaDeDeck, **origem) -> str:
    """Grava o deck e as cartas numa transação só. Devolve o id do deck."""
    id_, comandos = comandos_do_deck(nome, lista, **origem)
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


# Cabeçalhos que ler_lista (decks/importar.py) entende, na ordem de uma lista de deck.
CABECALHOS = {"lenda": "Legend", "campeao": "Champion", "principal": "Main Deck", "battlefields": "Battlefields",
              "runas": "Runes", "sideboard": "Sideboard"}


def lista_em_texto(cartas: list[dict], nome_da_lenda=lambda carta: carta) -> str:
    """As cartas de um deck (como em cartas_dos_decks) no formato de texto da importação, pra editar.
    `nome_da_lenda` escreve a lenda como os jogadores escrevem ("Jinx, Loose Cannon"); a importação entende."""
    blocos = []
    for secao, cabecalho in CABECALHOS.items():
        linhas = [f"{l['quantidade']} {nome_da_lenda(l['carta']) if secao == 'lenda' else l['carta']}"
                  for l in sorted(cartas, key=lambda l: l["carta"]) if l["secao"] == secao]
        if linhas:
            blocos.append(f"{cabecalho}:\n" + "\n".join(linhas))
    return "\n\n".join(blocos)


def editar_deck(banco: Banco, deck_id: str, nome: str, lista: ListaDeDeck, url: str | None = None) -> None:
    """Troca o nome, o link e as cartas do deck, numa transação só (se falhar, o deck antigo continua)."""
    if not lista.cartas:
        raise ValueError("a lista não tem nenhuma carta reconhecida")
    comandos = [("UPDATE decks SET nome = ?, url = ? WHERE id = ?", (nome.strip() or "Deck sem nome", url or None, deck_id)),
                ("DELETE FROM deck_cartas WHERE deck_id = ?", (deck_id,))]
    comandos += [("INSERT INTO deck_cartas (deck_id, carta, secao, quantidade) VALUES (?, ?, ?, ?)", (deck_id, carta, secao, qtd))
                 for (secao, carta), qtd in lista.cartas.items()]
    banco.lote(comandos)


def copiar_deck(banco: Banco, deck: dict, cartas: list[dict], nome: str) -> str:
    """Uma cópia do deck (ex.: um do meta) como deck meu, que dá pra editar. Devolve o id da cópia."""
    lista = ListaDeDeck()
    for l in cartas:
        lista.cartas[(l["secao"], l["carta"])] = l["quantidade"]
    return salvar_deck(banco, nome, lista, url=deck.get("url"), data=deck.get("data"), torneio=deck.get("torneio"),
                       colocacao=deck.get("colocacao"))

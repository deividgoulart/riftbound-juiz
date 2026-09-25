"""Decks do meta (fase 2, etapa 2): decks de torneio de Riftbound, pela API oficial do TopDeck.gg.

Uso (a partir da raiz do projeto, com TOPDECK_API_KEY no .env):
    python -m decks.meta              # coleta se a última coleta tem mais de 7 dias
    python -m decks.meta --forcar     # coleta agora
    python -m decks.meta --dias 60    # torneios dos últimos 60 dias

Por que o TopDeck.gg: é uma API oficial e grátis (chave gratuita, ~100 pedidos por minuto), com os
torneios de Riftbound e as listas dos jogadores. O riftools.app, a outra fonte considerada, não tem
API, e ler o HTML dele pode quebrar a qualquer mudança no site.

Como a API responde (conferido no código de um projeto aberto que a usa, já que a documentação não
abria no ambiente de desenvolvimento):
- POST em config.TOPDECK_API_URL, com o header "Authorization: <chave>" (sem "Bearer") e o corpo
  {"game": "Riftbound", "format": "Constructed", "start": <unix>}. Sem "start", a API dá erro 500.
- Uma lista de torneios {TID, tournamentName, startDate, standings}; cada colocação traz
  {name, standing, decklist, deckObj}.
- deckObj tem as seções Legend, Champion, Mainboard, Battlefields, Runes e Sideboard, cada uma um
  objeto "nome da carta" -> {id, count}, e uma seção "metadata", que não é carta.

As cartas são reconhecidas pelo código (ex.: OGN-042, pela galeria oficial; veja decks/codigos.py) e,
se o código não for conhecido, pelo nome. Um deck com carta não reconhecida fica de fora, em vez de entrar com a conta de conclusão errada, e
o nome aparece no relatório. O nome do jogador não é guardado: é dado pessoal e não serve pra nada aqui.
"""

import argparse
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from decks.banco import Banco
from decks.catalogo import Catalogo, nome_da_lenda
from decks.importar import ListaDeDeck
from decks.meus_decks import comandos_do_deck
from juiz import config

ORIGEM = "topdeck"
SECOES = {"legend": "lenda", "champion": "campeao", "mainboard": "principal", "battlefields": "battlefields",
          "runes": "runas", "sideboard": "sideboard"}  # "metadata" e o que mais vier ficam de fora


class ErroNoMeta(RuntimeError):
    pass


@dataclass
class DeckDoMeta:
    nome: str
    lista: ListaDeDeck
    url: str
    data: str
    torneio: str
    colocacao: str


@dataclass
class RelatorioMeta:
    torneios: int = 0
    torneios_usados: int = 0
    decks: int = 0
    decks_ignorados: int = 0
    desconhecidas: Counter = field(default_factory=Counter)  # nome -> quantas vezes apareceu


def chave_topdeck() -> str:
    return os.environ.get("TOPDECK_API_KEY", "").strip()


def buscar_torneios(chave: str, dias: int = config.META_DIAS, cliente: httpx.Client | None = None,
                    agora: datetime | None = None) -> list[dict]:
    inicio = (agora or datetime.now(timezone.utc)) - timedelta(days=dias)
    cliente = cliente or httpx.Client(timeout=60)
    try:
        resposta = cliente.post(config.TOPDECK_API_URL, headers={"Authorization": chave},
                                json={"game": "Riftbound", "format": "Constructed", "start": int(inicio.timestamp())})
    except httpx.HTTPError as erro:
        raise ErroNoMeta(f"não consegui falar com o TopDeck.gg ({type(erro).__name__})") from None
    if resposta.status_code in (401, 403):
        raise ErroNoMeta("o TopDeck.gg recusou a chave: confira a TOPDECK_API_KEY")
    if resposta.status_code == 429:
        raise ErroNoMeta("o TopDeck.gg pediu pra esperar (limite de pedidos); tente de novo em 1 minuto")
    if resposta.status_code != 200:
        raise ErroNoMeta(f"o TopDeck.gg respondeu com erro HTTP {resposta.status_code}")
    torneios = resposta.json()
    if not isinstance(torneios, list):
        raise ErroNoMeta("o TopDeck.gg respondeu num formato inesperado")
    return torneios


def _nome_do_deck(lenda: str, catalogo: Catalogo, colocacao: int, torneio: str) -> str:
    return f"{nome_da_lenda(lenda, catalogo)} · {colocacao}º em {torneio}"


def ler_deck(deck_obj: dict, catalogo: Catalogo, relatorio: RelatorioMeta) -> ListaDeDeck | None:
    """deckObj -> ListaDeDeck. None se faltar a lenda ou se uma carta (fora do sideboard) não for reconhecida."""
    lista, completo = ListaDeDeck(), True
    for nome_da_secao, cartas in deck_obj.items():
        secao = SECOES.get(str(nome_da_secao).lower())
        if secao is None or not isinstance(cartas, dict):
            continue
        for nome, dados in cartas.items():
            quantidade = int((dados or {}).get("count") or 0) if isinstance(dados, dict) else 0
            if quantidade <= 0:
                continue
            oficial = catalogo.por_codigo(dados.get("id")) or catalogo.resolver(nome)  # o código é mais seguro
            if oficial is None:
                relatorio.desconhecidas[nome] += 1
                completo = completo and secao == "sideboard"
                continue
            lista.cartas[(secao, oficial)] = lista.cartas.get((secao, oficial), 0) + quantidade
    if not completo or not lista.total("lenda"):
        return None
    return lista


def ler_torneios(torneios: list[dict], catalogo: Catalogo, relatorio: RelatorioMeta) -> list[DeckDoMeta]:
    decks = []
    relatorio.torneios = len(torneios)
    for t in torneios:
        colocacoes = t.get("standings") or []
        if len(colocacoes) < config.META_MIN_JOGADORES or not t.get("TID"):
            continue
        relatorio.torneios_usados += 1
        nome_do_torneio = (t.get("tournamentName") or "Torneio sem nome").strip()
        data = datetime.fromtimestamp(t["startDate"], timezone.utc).date().isoformat() if t.get("startDate") else None
        for posicao, c in enumerate(colocacoes, start=1):
            try:
                colocacao = int(c.get("standing") or posicao)
            except (TypeError, ValueError):
                colocacao = posicao
            if colocacao > config.META_TOP_POR_TORNEIO or not isinstance(c.get("deckObj"), dict):
                continue
            lista = ler_deck(c["deckObj"], catalogo, relatorio)
            if lista is None:
                relatorio.decks_ignorados += 1
                continue
            lenda = next(carta for (secao, carta) in lista.cartas if secao == "lenda")
            decks.append(DeckDoMeta(_nome_do_deck(lenda, catalogo, colocacao, nome_do_torneio), lista,
                                    config.TOPDECK_BRACKET_URL.format(tid=t["TID"]), data, nome_do_torneio,
                                    str(colocacao)))
    relatorio.decks = len(decks)
    return decks


def _agrupar(comandos: list[tuple[str, tuple]], por_insert: int = 100) -> list[tuple[str, tuple]]:
    """Junta INSERTs iguais de uma linha em INSERTs de várias linhas: centenas de decks viram poucos
    comandos (no Turso, o lote inteiro vai numa ida só)."""
    agrupados: list[tuple[str, tuple]] = []
    por_sql: dict[str, list[tuple]] = {}
    for sql, params in comandos:
        if sql.startswith("INSERT INTO") and sql.endswith(")") and "VALUES (" in sql:
            por_sql.setdefault(sql, []).append(params)
        else:
            agrupados.append((sql, params))
    for sql, linhas in por_sql.items():
        base, valores = sql.split(" VALUES ")
        for inicio in range(0, len(linhas), por_insert):
            bloco = linhas[inicio:inicio + por_insert]
            agrupados.append((f"{base} VALUES {', '.join([valores] * len(bloco))}", tuple(v for l in bloco for v in l)))
    return agrupados


def atualizar_meta(banco: Banco, catalogo: Catalogo, chave: str, dias: int = config.META_DIAS,
                   cliente: httpx.Client | None = None, agora: datetime | None = None) -> RelatorioMeta:
    """Troca os decks do meta pelos da coleta nova, numa transação só. Os decks manuais não mudam."""
    agora = agora or datetime.now(timezone.utc)
    relatorio = RelatorioMeta()
    decks = ler_torneios(buscar_torneios(chave, dias, cliente, agora), catalogo, relatorio)
    comandos: list[tuple[str, tuple]] = []
    if decks:  # coleta vazia (ex.: semana sem torneios) não apaga os decks que já existem
        comandos += [("DELETE FROM deck_cartas WHERE deck_id IN (SELECT id FROM decks WHERE origem = ?)", (ORIGEM,)),
                     ("DELETE FROM decks WHERE origem = ?", (ORIGEM,))]
        novos = []
        for d in decks:
            novos += comandos_do_deck(d.nome, d.lista, origem=ORIGEM, url=d.url, data=d.data, torneio=d.torneio,
                                      colocacao=d.colocacao)[1]
        comandos += _agrupar(novos)
    comandos.append(("INSERT OR REPLACE INTO meta (chave, valor) VALUES ('meta_decks_em', ?)",
                     (agora.isoformat(timespec="seconds"),)))
    banco.lote(comandos)
    return relatorio


def ultima_coleta(banco: Banco) -> datetime | None:
    linha = banco.consultar("SELECT valor FROM meta WHERE chave = 'meta_decks_em'")
    return datetime.fromisoformat(linha[0]["valor"]) if linha else None


def precisa_atualizar_meta(banco: Banco, agora: datetime | None = None) -> bool:
    ultima = ultima_coleta(banco)
    agora = agora or datetime.now(timezone.utc)
    return ultima is None or agora - ultima > timedelta(days=config.META_ATUALIZAR_A_CADA_DIAS)


def resumo(relatorio: RelatorioMeta) -> str:
    texto = (f"{relatorio.decks} decks de {relatorio.torneios_usados} torneios "
             f"({relatorio.torneios} no período; os com menos de {config.META_MIN_JOGADORES} jogadores ficam de fora).")
    if relatorio.decks_ignorados:
        texto += f" {relatorio.decks_ignorados} decks ignorados por carta não reconhecida ou sem lenda."
    return texto


def main() -> None:
    from decks.banco import abrir_banco
    from decks.catalogo import preparar

    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Coleta os decks de torneio de Riftbound no TopDeck.gg.")
    parser.add_argument("--dias", type=int, default=config.META_DIAS, help="torneios dos últimos N dias")
    parser.add_argument("--forcar", action="store_true", help="coleta mesmo se a última coleta for recente")
    args = parser.parse_args()

    chave = chave_topdeck()
    if not chave:
        sys.exit("Falta a TOPDECK_API_KEY no .env (crie uma chave grátis na sua conta do TopDeck.gg).")
    banco = abrir_banco()
    catalogo = preparar(banco)
    if not args.forcar and not precisa_atualizar_meta(banco):
        print(f"A última coleta foi em {ultima_coleta(banco):%d/%m/%Y}; use --forcar pra coletar de novo.")
        return
    relatorio = atualizar_meta(banco, catalogo, chave, args.dias)
    print(f"Banco: {banco.onde}\n{resumo(relatorio)}")
    for nome, vezes in relatorio.desconhecidas.most_common(20):
        print(f"  Carta não reconhecida: \"{nome}\" ({vezes}x)")


if __name__ == "__main__":
    main()

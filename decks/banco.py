"""Banco do deck builder (fase 2): catálogo de cartas, coleção e decks, em SQL do SQLite.

Dois lugares possíveis, com o mesmo SQL:
- Local: um arquivo SQLite (config.DECKS_DB), usado no seu computador e nos testes (":memory:").
- Turso: um SQLite na nuvem, com plano grátis. É o que o app publicado usa, porque o disco do
  Streamlit Cloud é apagado a cada reinício do app, e a coleção sumiria junto.

Por que falar com o Turso pela API HTTP, e não pelo pacote oficial? O pacote do Turso é nativo
(Rust) e já teve problema de instalação no Windows. A API HTTP ("Hrana", em /v2/pipeline) é um
POST com JSON, e o httpx já é dependência do projeto (Groq).

Qual dos dois: com TURSO_DATABASE_URL e TURSO_AUTH_TOKEN no ambiente (.env ou secrets), o Turso;
sem elas, o arquivo local.
"""

import os
import sqlite3
import threading
from pathlib import Path

import httpx

from juiz import config

ESQUEMA = [
    """CREATE TABLE IF NOT EXISTS cartas (
        nome TEXT PRIMARY KEY,
        tipos TEXT NOT NULL,          -- "Unit", "Spell", "Legend", "Rune"... (vários separados por espaço)
        supertipos TEXT NOT NULL,     -- "Champion", "Signature", "Token"
        dominios TEXT NOT NULL,       -- "Fury, Chaos"
        tags TEXT NOT NULL,           -- "Jinx" (numa lenda, diz o campeão)
        custo_energia INTEGER,
        custo_poder INTEGER,
        might INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS colecao (
        carta TEXT PRIMARY KEY,       -- nome em cartas.nome
        quantidade INTEGER NOT NULL CHECK (quantidade > 0)
    )""",
    """CREATE TABLE IF NOT EXISTS decks (
        id TEXT PRIMARY KEY,
        nome TEXT NOT NULL,
        origem TEXT,                  -- "manual" por enquanto; depois, o site de onde o deck veio
        url TEXT,
        data TEXT,                    -- data do torneio ou da lista
        torneio TEXT,
        colocacao TEXT,
        criado_em TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS deck_cartas (
        deck_id TEXT NOT NULL,        -- decks.id
        carta TEXT NOT NULL,          -- cartas.nome
        secao TEXT NOT NULL,          -- lenda, campeao, principal, battlefields, runas, sideboard
        quantidade INTEGER NOT NULL CHECK (quantidade > 0),
        PRIMARY KEY (deck_id, carta, secao)
    )""",
    """CREATE TABLE IF NOT EXISTS precos_tcg (
        carta TEXT PRIMARY KEY,       -- cartas.nome
        usd REAL NOT NULL             -- preço de mercado no TCGplayer (EUA), a impressão mais barata da carta
    )""",
    """CREATE TABLE IF NOT EXISTS meta (
        chave TEXT PRIMARY KEY,
        valor TEXT
    )""",
]


def agrupar_inserts(comandos: list[tuple[str, tuple]], por_insert: int = 100) -> list[tuple[str, tuple]]:
    """Junta INSERTs iguais de uma linha em INSERTs de várias linhas: centenas de linhas viram poucos
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


class ErroNoBanco(RuntimeError):
    pass


class Banco:
    """O que o resto do deck builder usa. `params` são os valores dos "?" do SQL."""

    onde = ""

    def consultar(self, sql: str, params: tuple = ()) -> list[dict]:
        raise NotImplementedError

    def lote(self, comandos: list[tuple[str, tuple]]) -> None:
        """Roda vários comandos numa transação: ou todos valem, ou nenhum."""
        raise NotImplementedError

    def executar(self, sql: str, params: tuple = ()) -> None:
        self.lote([(sql, params)])

    def criar_tabelas(self) -> None:
        self.lote([(sql, ()) for sql in ESQUEMA])


class BancoLocal(Banco):
    def __init__(self, caminho: str | Path = ":memory:"):
        if caminho != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self.onde = "este computador" if caminho != ":memory:" else "memória"
        # check_same_thread=False + trava: o Streamlit atende cada visitante numa thread.
        self._conexao = sqlite3.connect(str(caminho), check_same_thread=False, isolation_level=None)
        self._conexao.row_factory = sqlite3.Row
        self._trava = threading.Lock()

    def consultar(self, sql, params=()):
        with self._trava:
            return [dict(linha) for linha in self._conexao.execute(sql, params)]

    def lote(self, comandos):
        with self._trava:
            cursor = self._conexao.cursor()
            cursor.execute("BEGIN")
            try:
                for sql, params in comandos:
                    cursor.execute(sql, params)
            except Exception:
                cursor.execute("ROLLBACK")
                raise
            cursor.execute("COMMIT")


# --- Turso (API HTTP "Hrana") ---

def _valor_para_turso(valor) -> dict:
    """O protocolo manda inteiros como texto (pra não perder precisão em JSON)."""
    if valor is None:
        return {"type": "null"}
    if isinstance(valor, bool):
        return {"type": "integer", "value": str(int(valor))}
    if isinstance(valor, int):
        return {"type": "integer", "value": str(valor)}
    if isinstance(valor, float):
        return {"type": "float", "value": valor}
    return {"type": "text", "value": str(valor)}


def _valor_do_turso(valor: dict):
    tipo = valor.get("type")
    if tipo == "null":
        return None
    if tipo == "integer":
        return int(valor["value"])
    if tipo == "float":
        return float(valor["value"])
    return valor.get("value")


def _comando(sql: str, params: tuple) -> dict:
    return {"sql": sql, "args": [_valor_para_turso(p) for p in params]}


class BancoTurso(Banco):
    onde = "nuvem (Turso)"

    def __init__(self, url: str, token: str, cliente: httpx.Client | None = None):
        # O painel do Turso mostra a URL como libsql://...; pela API HTTP, é https://
        self.url = url.strip().replace("libsql://", "https://", 1).rstrip("/") + "/v2/pipeline"
        self._token = token.strip()
        self._cliente = cliente or httpx.Client(timeout=30)

    def _enviar(self, pedido: dict) -> dict:
        corpo = {"requests": [pedido, {"type": "close"}]}
        try:
            resposta = self._cliente.post(self.url, json=corpo, headers={"Authorization": f"Bearer {self._token}"})
        except httpx.HTTPError as erro:
            raise ErroNoBanco(f"não consegui falar com o banco na nuvem ({type(erro).__name__})") from None
        if resposta.status_code in (401, 403):
            raise ErroNoBanco("o banco na nuvem recusou o acesso: confira o TURSO_AUTH_TOKEN")
        if resposta.status_code != 200:
            raise ErroNoBanco(f"o banco na nuvem respondeu com erro HTTP {resposta.status_code}")
        resultado = resposta.json()["results"][0]
        if resultado["type"] != "ok":
            raise ErroNoBanco(f"erro no banco: {resultado.get('error', {}).get('message', 'desconhecido')}")
        return resultado["response"]

    def consultar(self, sql, params=()):
        resultado = self._enviar({"type": "execute", "stmt": _comando(sql, params)})["result"]
        colunas = [c["name"] for c in resultado["cols"]]
        return [dict(zip(colunas, map(_valor_do_turso, linha))) for linha in resultado["rows"]]

    def lote(self, comandos):
        # Transação num "batch": cada passo só roda se o anterior deu certo; o COMMIT só se tudo
        # deu certo, e o ROLLBACK roda se o COMMIT não rodou.
        passos = [{"stmt": {"sql": "BEGIN"}}]
        for sql, params in comandos:
            passos.append({"stmt": _comando(sql, params), "condition": {"type": "ok", "step": len(passos) - 1}})
        commit = len(passos)
        passos.append({"stmt": {"sql": "COMMIT"}, "condition": {"type": "ok", "step": commit - 1}})
        passos.append({"stmt": {"sql": "ROLLBACK"},
                       "condition": {"type": "not", "cond": {"type": "ok", "step": commit}}})
        resultado = self._enviar({"type": "batch", "batch": {"steps": passos}})["result"]
        erros = [e for e in resultado.get("step_errors", []) if e]
        if erros:
            raise ErroNoBanco(f"erro no banco: {erros[0].get('message', 'desconhecido')}")


def turso_configurado() -> bool:
    return bool(os.environ.get("TURSO_DATABASE_URL") and os.environ.get("TURSO_AUTH_TOKEN"))


def abrir_banco() -> Banco:
    """Turso se as variáveis existirem; senão, o arquivo local."""
    if turso_configurado():
        return BancoTurso(os.environ["TURSO_DATABASE_URL"], os.environ["TURSO_AUTH_TOKEN"])
    return BancoLocal(config.DECKS_DB)

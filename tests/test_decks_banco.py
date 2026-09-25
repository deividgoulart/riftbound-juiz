"""Testes do banco do deck builder (fase 2): SQLite local e Turso pela API HTTP (sem rede)."""

import json
import pathlib

import httpx
import pytest

from decks import banco as modulo
from decks.banco import BancoLocal, BancoTurso, ErroNoBanco, abrir_banco


def test_local_cria_tabelas_grava_e_le(banco):
    banco.criar_tabelas()
    banco.criar_tabelas()  # de novo: não pode dar erro
    banco.executar("INSERT INTO colecao (carta, quantidade) VALUES (?, ?)", ("Abandon", 2))
    assert banco.consultar("SELECT * FROM colecao") == [{"carta": "Abandon", "quantidade": 2}]


def test_local_lote_desfaz_tudo_se_um_comando_falha(banco):
    banco.criar_tabelas()
    with pytest.raises(Exception):
        banco.lote([("INSERT INTO colecao (carta, quantidade) VALUES ('Abandon', 2)", ()),
                    ("INSERT INTO colecao (carta, quantidade) VALUES ('Jinx, Rebel', 0)", ())])  # CHECK > 0
    assert banco.consultar("SELECT * FROM colecao") == []


def test_abrir_banco_escolhe_pelo_ambiente(monkeypatch, tmp_path):
    monkeypatch.setattr(modulo.config, "DECKS_DB", tmp_path / "decks.sqlite")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    assert isinstance(abrir_banco(), BancoLocal)
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://meu-banco.turso.io")
    assert isinstance(abrir_banco(), BancoLocal)  # só a URL, sem o token, não basta
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "token")
    assert isinstance(abrir_banco(), BancoTurso)


# --- Turso: um servidor falso que guarda os pedidos e responde no formato da API ---

def turso_falso(resposta, pedidos, status=200):
    def atender(request: httpx.Request):
        pedidos.append(request)
        return httpx.Response(status, json=resposta)
    return httpx.Client(transport=httpx.MockTransport(atender))


def ok(response):
    return {"results": [{"type": "ok", "response": response}, {"type": "ok", "response": {"type": "close"}}]}


def test_turso_consulta_manda_argumentos_tipados_e_converte_as_linhas():
    pedidos = []
    resposta = ok({"type": "execute", "result": {
        "cols": [{"name": "carta"}, {"name": "quantidade"}, {"name": "nota"}],
        "rows": [[{"type": "text", "value": "Abandon"}, {"type": "integer", "value": "2"}, {"type": "null"}]],
    }})
    banco = BancoTurso("libsql://meu-banco.turso.io", "segredo", turso_falso(resposta, pedidos))
    linhas = banco.consultar("SELECT * FROM colecao WHERE carta = ? AND quantidade > ? AND x IS ?", ("Abandon", 1, None))

    assert linhas == [{"carta": "Abandon", "quantidade": 2, "nota": None}]
    pedido = pedidos[0]
    assert str(pedido.url) == "https://meu-banco.turso.io/v2/pipeline"
    assert pedido.headers["Authorization"] == "Bearer segredo"
    corpo = json.loads(pedido.content)
    assert corpo["requests"][0]["stmt"]["args"] == [
        {"type": "text", "value": "Abandon"}, {"type": "integer", "value": "1"}, {"type": "null"}]
    assert corpo["requests"][-1] == {"type": "close"}


def test_turso_lote_e_uma_transacao_com_commit_condicional():
    pedidos = []
    resposta = ok({"type": "batch", "result": {"step_results": [], "step_errors": [None, None, None, None]}})
    banco = BancoTurso("https://meu-banco.turso.io/", "segredo", turso_falso(resposta, pedidos))
    banco.lote([("INSERT INTO colecao VALUES (?, ?)", ("Abandon", 2))])

    passos = json.loads(pedidos[0].content)["requests"][0]["batch"]["steps"]
    assert [p["stmt"]["sql"] for p in passos] == ["BEGIN", "INSERT INTO colecao VALUES (?, ?)", "COMMIT", "ROLLBACK"]
    assert passos[1]["condition"] == {"type": "ok", "step": 0}
    assert passos[2]["condition"] == {"type": "ok", "step": 1}
    assert passos[3]["condition"] == {"type": "not", "cond": {"type": "ok", "step": 2}}


def test_turso_erro_num_passo_do_lote_vira_erro_claro():
    resposta = ok({"type": "batch", "result": {"step_results": [], "step_errors": [
        None, {"message": "CHECK constraint failed"}, None, None]}})
    banco = BancoTurso("https://b.turso.io", "segredo", turso_falso(resposta, []))
    with pytest.raises(ErroNoBanco, match="CHECK constraint failed"):
        banco.lote([("INSERT ...", ())])


@pytest.mark.parametrize("status, trecho", [(401, "TURSO_AUTH_TOKEN"), (500, "HTTP 500")])
def test_turso_erro_http_nao_mostra_o_token(status, trecho):
    banco = BancoTurso("https://b.turso.io", "token-secreto", turso_falso({}, [], status=status))
    with pytest.raises(ErroNoBanco) as erro:
        banco.consultar("SELECT 1")
    assert trecho in str(erro.value)
    assert "token-secreto" not in str(erro.value)


def test_turso_erro_de_sql_na_consulta():
    resposta = {"results": [{"type": "error", "error": {"message": "no such table: x"}}]}
    banco = BancoTurso("https://b.turso.io", "segredo", turso_falso(resposta, []))
    with pytest.raises(ErroNoBanco, match="no such table"):
        banco.consultar("SELECT * FROM x")


def test_pacote_decks_nao_depende_da_api():
    """A lógica fica fora da API: trocar a API ou o site no futuro não mexe em decks/."""
    for arquivo in (pathlib.Path(modulo.__file__).parent).glob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        assert "streamlit" not in texto and "fastapi" not in texto, arquivo.name

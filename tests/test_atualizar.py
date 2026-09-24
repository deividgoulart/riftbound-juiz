"""Testes do comando de atualização (etapa 8). Nada baixa da internet: os passos são trocados por falsos."""

import json
from datetime import datetime, timedelta, timezone

import pytest

import juiz.atualizar as atualizar_mod
from juiz import config


@pytest.fixture
def pastas(tmp_path, monkeypatch):
    for nome, caminho in {
        "PROCESSED_DIR": tmp_path / "processed", "INDEX_DIR": tmp_path / "index",
        "FAQ_SOURCES_DIR": tmp_path / "sources", "FAQ_DIR": tmp_path / "faq",
        "FAQ_SNAPSHOT": tmp_path / "faq_snapshot.json", "CRD_SNAPSHOT": tmp_path / "crd_snapshot.json",
        "ATUALIZACAO": tmp_path / "atualizacao.json",
    }.items():
        monkeypatch.setattr(config, nome, caminho)
    return tmp_path


def criar_dados(pastas):
    for arquivo in ["processed/faq_trechos.jsonl", "processed/crd_regras.jsonl", "processed/crd_trechos.jsonl",
                    "sources/card-catalog.json", f"index/{config.MODELO_EMBEDDINGS}/vetores.npy"]:
        (pastas / arquivo).parent.mkdir(parents=True, exist_ok=True)
        (pastas / arquivo).write_text("x", encoding="utf-8")


def test_precisa_atualizar_sem_dados_ou_com_dados_velhos(pastas):
    assert atualizar_mod.precisa_atualizar()  # nada baixado ainda
    criar_dados(pastas)
    agora = datetime.now(timezone.utc)
    config.ATUALIZACAO.write_text(json.dumps({"quando": agora.isoformat()}), encoding="utf-8")
    assert not atualizar_mod.precisa_atualizar(agora + timedelta(hours=1))
    assert atualizar_mod.precisa_atualizar(agora + timedelta(hours=config.ATUALIZAR_A_CADA_HORAS + 1))


@pytest.fixture
def passos(pastas, monkeypatch):
    """Troca cada passo por um falso que só anota que foi chamado."""
    chamados = []
    estado = {"commit": "abc", "crd_sha": "111"}

    def salvar_snapshot():
        config.FAQ_SNAPSHOT.write_text(json.dumps({"commit": estado["commit"]}), encoding="utf-8")
        return {"commit": estado["commit"]}

    def baixar_e_salvar(versao, nome):
        chamados.append("baixar_crd")
        (pastas / "crd.html").write_text("html", encoding="utf-8")
        snap = {"versao": versao, "arquivo": "crd.html", "sha256": estado["crd_sha"]}
        config.CRD_SNAPSHOT.write_text(json.dumps(snap), encoding="utf-8")
        return snap

    monkeypatch.setattr(config, "RAIZ", pastas)
    monkeypatch.setattr(atualizar_mod.baixar_faq, "clonar", lambda: chamados.append("clonar"))
    monkeypatch.setattr(atualizar_mod.baixar_faq, "atualizar", lambda: chamados.append("git_fetch"))
    monkeypatch.setattr(atualizar_mod.baixar_faq, "salvar_snapshot", salvar_snapshot)
    monkeypatch.setattr(atualizar_mod.baixar_crd, "versao_atual", lambda: ("1.4", "Vendetta"))
    monkeypatch.setattr(atualizar_mod.baixar_crd, "baixar_e_salvar", baixar_e_salvar)
    monkeypatch.setattr(atualizar_mod, "processar_faq", lambda log: chamados.append("processar_faq"))
    monkeypatch.setattr(atualizar_mod, "processar_crd", lambda log: chamados.append("processar_crd"))
    monkeypatch.setattr(atualizar_mod, "atualizar_indices", lambda log: chamados.append("indices") or {})
    return chamados, estado


def test_primeira_vez_baixa_e_processa_tudo(passos):
    chamados, _ = passos
    resultado = atualizar_mod.atualizar(log=lambda *_: None)
    assert chamados == ["clonar", "processar_faq", "baixar_crd", "processar_crd", "indices"]
    assert resultado["faq_mudou"] and resultado["crd_mudou"]
    assert json.loads(config.ATUALIZACAO.read_text(encoding="utf-8"))["faq_commit"] == "abc"


def test_sem_mudanca_nas_fontes_so_confere(passos, pastas):
    chamados, _ = passos
    atualizar_mod.atualizar(log=lambda *_: None)
    (pastas / "faq" / ".git").mkdir(parents=True)  # agora o FAQ já foi clonado
    for arquivo in ["faq_trechos.jsonl", "crd_regras.jsonl"]:
        (pastas / "processed").mkdir(exist_ok=True)
        (pastas / "processed" / arquivo).write_text("x", encoding="utf-8")
    chamados.clear()
    resultado = atualizar_mod.atualizar(log=lambda *_: None)
    assert chamados == ["git_fetch", "indices"]  # não reprocessa nem baixa o CRD de novo
    assert not resultado["faq_mudou"] and not resultado["crd_mudou"]


def test_faq_novo_baixa_o_crd_de_novo_mas_so_reprocessa_se_ele_mudou(passos, pastas):
    chamados, estado = passos
    atualizar_mod.atualizar(log=lambda *_: None)
    (pastas / "faq" / ".git").mkdir(parents=True)
    (pastas / "processed").mkdir(exist_ok=True)
    (pastas / "processed" / "crd_regras.jsonl").write_text("x", encoding="utf-8")
    estado["commit"] = "def"  # saiu um commit novo no FAQ; o CRD continua igual
    chamados.clear()
    resultado = atualizar_mod.atualizar(log=lambda *_: None)
    assert chamados == ["git_fetch", "processar_faq", "baixar_crd", "indices"]
    assert resultado["faq_mudou"] and not resultado["crd_mudou"]

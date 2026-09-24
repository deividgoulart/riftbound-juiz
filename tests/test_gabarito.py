"""Testes do gabarito (avaliacao/gabarito.yaml).

O gabarito é escrito à mão, então é fácil errar um ID de trecho ou um número de regra.
Estes testes pegam esse tipo de erro e também avisam se o FAQ mudar e um trecho citado sumir.
"""

import json
import re
from collections import Counter

import pytest
import yaml

from juiz import config
from juiz.limpar_faq import processar_tudo

CATEGORIAS = {"carta", "regra_geral", "mecanica", "so_crd", "definicao", "continuacao", "fora_do_escopo"}
COM_PAGINA_NO_FAQ = {"carta", "regra_geral", "mecanica"}  # essas sempre têm um trecho do FAQ como fonte
ESTILOS = {"formal", "informal", "termo_em_portugues"}
CAMPOS = {"id", "pergunta", "categoria", "estilo", "resposta_esperada", "fontes_esperadas", "regras_esperadas"}
CAMPOS_OPCIONAIS = {"conclusao", "historico", "origem"}
CONCLUSOES = {"sim", "não", "depende"}
RE_REGRA = re.compile(r"^\d{3}(\.[0-9a-z]+)*$")  # ex.: 355.9.a


@pytest.fixture(scope="module")
def gabarito() -> list[dict]:
    return yaml.safe_load(config.GABARITO.read_text(encoding="utf-8"))


def test_tamanho_e_ids_unicos(gabarito):
    assert 30 <= len(gabarito) <= 50
    ids = [q["id"] for q in gabarito]
    assert len(set(ids)) == len(ids)


def test_campos_e_valores_validos(gabarito):
    for q in gabarito:
        assert CAMPOS <= set(q) <= CAMPOS | CAMPOS_OPCIONAIS, q["id"]
        assert q["categoria"] in CATEGORIAS, q["id"]
        assert q["estilo"] in ESTILOS, q["id"]
        assert q["pergunta"].strip() and q["resposta_esperada"].strip(), q["id"]
        assert all(RE_REGRA.match(r) for r in q["regras_esperadas"]), q["id"]
        conclusoes = q.get("conclusao", "sim")
        assert set(conclusoes if isinstance(conclusoes, list) else [conclusoes]) <= CONCLUSOES, q["id"]
        assert q.get("origem", "real") == "real", q["id"]


def test_continuacao_tem_historico(gabarito):
    for q in gabarito:
        if q["categoria"] == "continuacao":
            assert q["historico"] and all(set(h) == {"pergunta", "resposta"} for h in q["historico"]), q["id"]
        else:
            assert "historico" not in q, q["id"]


def test_fontes_combinam_com_a_categoria(gabarito):
    for q in gabarito:
        if q["categoria"] == "fora_do_escopo":
            assert not q["fontes_esperadas"] and not q["regras_esperadas"], q["id"]
        elif q["categoria"] == "so_crd":
            assert not q["fontes_esperadas"] and q["regras_esperadas"], q["id"]
        elif q["categoria"] in COM_PAGINA_NO_FAQ:
            assert q["fontes_esperadas"] and q["regras_esperadas"], q["id"]
        else:  # definição e continuação: pode ser só CRD ou também glossário/FAQ
            assert q["regras_esperadas"], q["id"]


def test_cobre_todos_os_tipos_de_pergunta(gabarito):
    categorias = Counter(q["categoria"] for q in gabarito)
    estilos = Counter(q["estilo"] for q in gabarito)
    assert set(categorias) == CATEGORIAS and set(estilos) == ESTILOS
    assert categorias["fora_do_escopo"] >= 3


# ---------------------------------------------------------------------------
# Conferência com os dados reais (pulada se o FAQ ainda não foi baixado)
# ---------------------------------------------------------------------------

dados_reais = pytest.mark.skipif(
    not config.FAQ_CONTENT_DIR.exists(), reason="rode antes: python -m juiz.baixar_faq"
)


@pytest.fixture(scope="module")
def trechos() -> dict[str, dict]:
    lista, _ = processar_tudo()
    return {t["id"]: t for t in lista}


@dados_reais
def test_todo_trecho_citado_existe(gabarito, trechos):
    for q in gabarito:
        for fonte in q["fontes_esperadas"]:
            assert fonte in trechos, f"{q['id']}: trecho {fonte} não existe (o FAQ mudou?)"


@dados_reais
def test_regras_esperadas_sao_citadas_pelos_trechos(gabarito, trechos):
    # Pras perguntas do FAQ, as regras esperadas precisam aparecer nos trechos esperados.
    for q in gabarito:
        if q["categoria"] not in COM_PAGINA_NO_FAQ:  # glossário e continuações citam regras de outro jeito
            continue
        citadas = {r for fonte in q["fontes_esperadas"] for r in trechos[fonte]["regras"]}
        faltando = set(q["regras_esperadas"]) - citadas
        assert not faltando, f"{q['id']}: regras {faltando} não aparecem nos trechos esperados"


@pytest.mark.skipif(not config.CRD_SNAPSHOT.exists(), reason="rode antes: python -m juiz.baixar_crd")
def test_toda_regra_esperada_existe_no_crd(gabarito):
    from juiz.limpar_crd import processar

    regras, _ = processar()
    numeros = {r["numero"] for r in regras}
    for q in gabarito:
        faltando = set(q["regras_esperadas"]) - numeros
        assert not faltando, f"{q['id']}: regras {faltando} não existem no CRD"


@dados_reais
def test_carta_inventada_continua_nao_existindo():
    catalogo = json.loads((config.FAQ_SOURCES_DIR / "card-catalog.json").read_text(encoding="utf-8"))
    assert not any(c["name"].startswith("Singed") for c in catalogo), "Singed foi lançado: trocar a q27"

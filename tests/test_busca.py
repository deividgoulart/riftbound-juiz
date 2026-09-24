"""Testes do índice de busca e das métricas da etapa 4.

Não baixam nenhum modelo: usam um "modelo de mentira" que transforma o texto em um vetor de
contagem de palavras. A mecânica da busca (produto escalar, ranking, salvar e carregar) é a
mesma de um modelo de verdade.
"""

import numpy as np
import pytest

from juiz import config
from juiz.avaliar_busca import BuscaBM25, fontes_certas, metricas, posicao_do_acerto
from juiz.indice import Indice

VOCABULARIO = ["ambush", "base", "shield", "might", "chain", "counter"]


class ModeloFalso:
    nome = "falso"
    id = "modelo-de-teste"

    def _vetores(self, textos):
        m = np.array([[t.lower().count(p) for p in VOCABULARIO] for t in textos], dtype=np.float32) + 1e-6
        return m / np.linalg.norm(m, axis=1, keepdims=True)

    def documentos(self, textos, titulos=None):
        return self._vetores(textos)

    def perguntas(self, textos):
        return self._vetores(textos)


def trecho(id_, texto, fonte="faq", regras=()):
    return {"id": id_, "texto": texto, "fonte": fonte, "regras": list(regras), "pagina": id_,
            "subsecao": None, "secao": "s", "url": f"u/{id_}"}


TRECHOS = [
    trecho("faq/ambush", "Can I use Ambush to play a unit to my base? Ambush base"),
    trecho("faq/shield", "Shield increases might while defending. Shield shield"),
    trecho("crd/425", "Countering a spell clears it from the chain. counter counter", fonte="crd", regras=["425.1", "425.1.c"]),
]


# --- índice ---

def test_busca_traz_o_trecho_mais_parecido_primeiro():
    indice = Indice.construir(ModeloFalso(), TRECHOS)
    resultado = indice.buscar("ambush in base", ModeloFalso(), k=3)
    assert resultado[0][0]["id"] == "faq/ambush"
    assert resultado[0][1] > resultado[1][1]  # nota do 1º maior que a do 2º


def test_indice_salva_e_carrega_igual(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INDEX_DIR", tmp_path)
    original = Indice.construir(ModeloFalso(), TRECHOS)
    original.salvar()
    carregado = Indice.carregar("falso")
    assert np.allclose(original.vetores, carregado.vetores)
    assert [t["id"] for t in carregado.trechos] == [t["id"] for t in TRECHOS]
    assert carregado.atualizado(TRECHOS)
    assert not carregado.atualizado(TRECHOS[:2])  # se os trechos mudam, o índice fica velho


# --- métricas ---

def test_fontes_certas_aceita_trecho_do_faq_ou_regra_do_crd():
    questao = {"fontes_esperadas": ["faq/shield"], "regras_esperadas": ["425.1.c"]}
    assert fontes_certas(questao, TRECHOS) == {1, 2}
    assert fontes_certas({"fontes_esperadas": [], "regras_esperadas": []}, TRECHOS) == set()


def test_posicao_do_acerto():
    assert posicao_do_acerto([7, 3, 2], {2}) == 3
    assert posicao_do_acerto([7, 3, 2], {9}) is None


def test_metricas_hit_e_mrr():
    m = metricas([1, 2, None, 5])
    assert m["hit@1"] == 0.25 and m["hit@3"] == 0.5 and m["hit@5"] == 0.75
    assert m["mrr"] == pytest.approx((1 + 1 / 2 + 1 / 5) / 4)


# --- BM25 ---

def test_bm25_acha_palavra_exata_mas_nao_traducao():
    busca = BuscaBM25(TRECHOS)
    posicoes, _ = busca.ranquear(["shield might"], k=3)
    assert posicoes[0][0] == 1
    _, notas = busca.ranquear(["escudo"], k=3)  # "escudo" não aparece em nenhum trecho
    assert notas[0][0] == 0


# --- indexação incremental (etapa 6: a cota diária do Gemini é de 1.000 textos) ---

class ModeloQueConta(ModeloFalso):
    def __init__(self):
        self.enviados = []

    def documentos(self, textos, titulos=None):
        self.enviados.extend(textos)
        return super().documentos(textos, titulos)


def test_indexacao_incremental_so_envia_trechos_novos_ou_alterados():
    modelo = ModeloQueConta()
    anterior = Indice.construir(modelo, TRECHOS)
    assert len(modelo.enviados) == 3

    alterado = dict(TRECHOS[1], texto="Shield changed text. shield")
    novo = trecho("faq/novo", "A brand new chain ruling. chain")
    modelo.enviados.clear()
    atual = Indice.construir(modelo, [TRECHOS[0], alterado, TRECHOS[2], novo], anterior=anterior)

    assert modelo.enviados == [alterado["texto"], novo["texto"]]  # os 2 que não mudaram foram reaproveitados
    assert atual.info["trechos_reaproveitados"] == 2 and atual.info["trechos_enviados_ao_modelo"] == 2
    assert np.allclose(atual.vetores[0], anterior.vetores[0])
    assert np.allclose(atual.vetores[1], ModeloFalso().documentos([alterado["texto"]])[0])


def test_sem_mudanca_nada_e_enviado():
    modelo = ModeloQueConta()
    anterior = Indice.construir(modelo, TRECHOS)
    modelo.enviados.clear()
    atual = Indice.construir(modelo, TRECHOS, anterior=anterior)
    assert modelo.enviados == [] and np.allclose(atual.vetores, anterior.vetores)

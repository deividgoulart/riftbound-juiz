"""Testes da avaliação de respostas (etapa 7). Nada chama a API: juiz e avaliador são de mentira."""

import json

import pytest

from juiz import config
from juiz.avaliar_respostas import (
    avaliar,
    conclusao_da_resposta,
    gerar_revisao,
    metricas_automaticas,
    regras_e_fontes_citadas,
    resumir,
)
from juiz.erros import CotaEsgotada
from juiz.responder import NAO_ENCONTREI, Fonte, Resposta

QUESTAO = {
    "id": "q01", "pergunta": "O Flash pode mirar na base?", "categoria": "carta", "estilo": "formal",
    "conclusao": "sim", "resposta_esperada": "Sim, pode.",
    "fontes_esperadas": ["faq/cards/flash#target-in-base"], "regras_esperadas": ["355.9.a"],
}
FORA = {"id": "q25", "pergunta": "Melhor deck?", "categoria": "fora_do_escopo", "estilo": "informal",
        "resposta_esperada": "Não encontrei.", "fontes_esperadas": [], "regras_esperadas": []}
REGRAS_DO_CRD = {"355.9.a", "446.1"}


def resposta(texto, fontes=None, encontrou=True):
    return Resposta("?", texto, encontrou, fontes or [], uso={"modelo": "falso", "tokens_entrada": 10, "tokens_saida": 5},
                    nota_busca=0.8, modelo_busca="gemini-2")


FONTE_CERTA = Fonte(1, "faq", "t", "u", "x", trecho_id="faq/cards/flash#target-in-base", regras=["355.9.a"])
FONTE_OUTRA = Fonte(2, "faq", "t", "u", "x", trecho_id="faq/cards/outra#a", regras=["999.1"])


# --- conclusão ---

@pytest.mark.parametrize("texto,esperado", [
    ("**Sim.** Pode sim.", "sim"), ("Não necessariamente.", "não"), ("Depende da ordem.", "depende"),
    ("A Chain é uma fila.", None), ("", None), ("\n**Não**, porque...", "não"),
    ("Não.\n\nDurante um Showdown...", "não"),  # a 1ª palavra termina numa quebra de linha
    ("Não encontrei a resposta nas regras que eu consultei.", None),  # não é a conclusão "não"
])
def test_conclusao_da_resposta(texto, esperado):
    assert conclusao_da_resposta(texto) == esperado


# --- citações ---

def test_regras_e_fontes_citadas_so_dentro_das_citacoes():
    regras, fontes = regras_e_fontes_citadas("Tem 40 cartas [F1, F3] (CRD 355.9.a, 103.2). Custa [2].")
    assert regras == {"355.9.a", "103.2"} and fontes == {1, 3}


def test_metricas_de_uma_resposta_certa():
    m = metricas_automaticas(QUESTAO, resposta("Sim. Pode [F1] (CRD 355.9.a).", [FONTE_CERTA, FONTE_OUTRA]), REGRAS_DO_CRD)
    assert m["acertou_se_respondia"] and m["conclusao_certa"] and m["citou_fonte_certa"]
    assert m["regras_inventadas"] == [] and m["fontes_inexistentes"] == []


def test_detecta_regra_inventada_fonte_inexistente_e_fonte_errada():
    m = metricas_automaticas(QUESTAO, resposta("Não. Veja [F2, F7] (CRD 999.9).", [FONTE_CERTA, FONTE_OUTRA]), REGRAS_DO_CRD)
    assert m["conclusao_certa"] is False and m["citou_fonte_certa"] is False
    assert m["regras_inventadas"] == ["999.9"] and m["fontes_inexistentes"] == [7]


def test_fora_do_escopo_acerta_quando_nao_encontra():
    assert metricas_automaticas(FORA, resposta(NAO_ENCONTREI, encontrou=False), REGRAS_DO_CRD)["acertou_se_respondia"]
    assert not metricas_automaticas(FORA, resposta("O melhor deck é X."), REGRAS_DO_CRD)["acertou_se_respondia"]


# --- rodada ---

class JuizFalso:
    def __init__(self, erro_em=None):
        self.regras = {n: {} for n in REGRAS_DO_CRD}
        self.historicos, self.erro_em = [], erro_em

    def responder(self, pergunta, historico=None):
        self.historicos.append(historico)
        if pergunta == self.erro_em:
            raise CotaEsgotada("teste")
        return resposta("Sim. Pode [F1].", [FONTE_CERTA])


class AvaliadorFalso:
    def gerar(self, instrucoes, mensagem, esquema=None):
        assert esquema is not None and "RESPOSTA ESPERADA" in mensagem
        return json.dumps({"nota": "correta", "justificativa": "bate com a esperada"})


@pytest.fixture
def resultados(tmp_path, monkeypatch):
    import juiz.avaliar_respostas as mod

    monkeypatch.setattr(config, "RESULTADOS_DIR", tmp_path)
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    monkeypatch.setattr(mod, "carregar_gabarito", lambda: [QUESTAO, FORA])  # não depende do gabarito real
    (tmp_path / "avaliacao").mkdir()
    return tmp_path


def test_avaliar_grava_linha_a_linha_e_pula_as_ja_feitas(resultados):
    continuacao = dict(QUESTAO, id="q35", historico=[{"pergunta": "antes?", "resposta": "isso."}])
    juiz = JuizFalso()
    assert avaliar(juiz, "modelo-x", [QUESTAO, continuacao], AvaliadorFalso()) == 2
    assert juiz.historicos == [[], [("antes?", "isso.")]]  # a continuação recebe o histórico
    linhas = [json.loads(l) for l in (resultados / "respostas_modelo-x.jsonl").open(encoding="utf-8")]
    assert [l["nota"] for l in linhas] == ["correta", "correta"]
    assert avaliar(JuizFalso(), "modelo-x", [QUESTAO, continuacao], AvaliadorFalso()) == 0  # nada repetido


def test_cota_esgotada_para_a_rodada_sem_perder_o_que_foi_feito(resultados):
    segunda = dict(QUESTAO, id="q02", pergunta="outra")
    assert avaliar(JuizFalso(erro_em="outra"), "modelo-y", [QUESTAO, segunda], None) == 1
    assert (resultados / "respostas_modelo-y.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_resumo_e_revisao_humana(resultados):
    avaliar(JuizFalso(), "modelo-z", [QUESTAO, FORA], AvaliadorFalso())
    resumo = resumir()
    assert resumo.loc["modelo-z", "perguntas"] == 2 and resumo.loc["modelo-z", "nota_correta"] == 1.0
    gerar_revisao("modelo-z", quantidade=2)
    planilha = (resultados / "avaliacao" / "revisao_humana.csv").read_text(encoding="utf-8-sig")
    assert "sua_nota" in planilha and "nota" not in planilha.split("\n")[0].replace("sua_nota", "")  # revisão às cegas


def test_erro_temporario_espera_e_tenta_de_novo(resultados, monkeypatch):
    import juiz.avaliar_respostas as mod

    esperas = []
    monkeypatch.setattr(mod.time, "sleep", esperas.append)

    class JuizInstavel(JuizFalso):
        def __init__(self):
            super().__init__()
            self.chamadas = 0

        def responder(self, pergunta, historico=None):
            self.chamadas += 1
            if self.chamadas == 1:
                raise RuntimeError("429 por minuto")
            return super().responder(pergunta, historico)

    juiz = JuizInstavel()
    assert avaliar(juiz, "modelo-w", [QUESTAO], None, espera_erro=60) == 1
    assert juiz.chamadas == 2 and esperas == [60]


def test_completar_notas_preenche_so_as_que_faltam(resultados, monkeypatch):
    import juiz.avaliar_respostas as mod

    class AvaliadorQueFalha:
        def gerar(self, instrucoes, mensagem, esquema=None):
            raise RuntimeError("503")

    avaliar(JuizFalso(), "modelo-v", [QUESTAO], AvaliadorQueFalha())  # a nota fica em branco
    arquivo = resultados / "respostas_modelo-v.jsonl"
    assert "nota" not in json.loads(arquivo.read_text(encoding="utf-8"))

    assert mod.completar_notas("modelo-v", AvaliadorFalso()) == 1
    assert json.loads(arquivo.read_text(encoding="utf-8"))["nota"] == "correta"



def test_conclusao_esperada_pode_aceitar_mais_de_uma():
    from juiz.avaliar_respostas import conclusao_confere

    assert conclusao_confere(["não", "depende"], "depende") is True
    assert conclusao_confere(["não", "depende"], "sim") is False
    assert conclusao_confere("sim", "sim") is True and conclusao_confere(None, "sim") is None


# --- concordância humano x avaliador ---

def test_kappa_de_cohen():
    from juiz.avaliar_respostas import NOTAS, kappa_de_cohen

    assert kappa_de_cohen(["correta", "parcial"], ["correta", "parcial"], NOTAS) == 1.0
    # concordam em 1 de 2, mas é o que o acaso já daria com essas proporções
    assert kappa_de_cohen(["correta", "correta"], ["correta", "parcial"], NOTAS) == 0.0
    assert kappa_de_cohen(["correta", "parcial"], ["parcial", "correta"], NOTAS) == -1.0


def test_concordancia_junta_revisao_humana_e_avaliador(resultados):
    import pandas as pd

    from juiz.avaliar_respostas import COLUNA_NOTA_HUMANA, concordancia

    linhas = [{"id": "q01", "nota": "correta"}, {"id": "q02", "nota": "parcial"},
              {"id": "q03", "nota": "correta"}, {"id": "q04", "nota": "incorreta"}]
    (resultados / "respostas_modelo-c.jsonl").write_text(
        "".join(json.dumps(l) + "\n" for l in linhas), encoding="utf-8")
    pd.DataFrame({"id": ["q01", "q02", "q03", "q04"],
                  COLUNA_NOTA_HUMANA: ["Correta", "correta", "parcial", ""]}).to_csv(
        resultados / "avaliacao" / "revisao_humana.csv", sep=";", index=False, encoding="utf-8-sig")

    c = concordancia("modelo-c")
    assert c["respostas"] == 3  # a q04 ficou sem nota humana
    assert c["concordancia_exata"] == pytest.approx(1 / 3)
    assert c["avaliador_mais_severo"] == ["q02"] and c["avaliador_mais_brando"] == ["q03"]
    assert c["matriz"].loc["correta", "correta"] == 1


def test_resposta_vazia_e_incorreta_sem_chamar_o_avaliador():
    from juiz.avaliar_respostas import avaliar_com_llm

    class AvaliadorQueNaoPodeSerChamado:
        def gerar(self, *a, **k):
            raise AssertionError("não devia chamar o avaliador")

    assert avaliar_com_llm(AvaliadorQueNaoPodeSerChamado(), QUESTAO, "  ")["nota"] == "incorreta"

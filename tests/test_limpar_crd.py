"""Testes da leitura do CRD e da montagem dos trechos (etapa 3).

O primeiro bloco usa um HTML pequeno escrito aqui, com a mesma estrutura da página do
riftboundfaq.com. O segundo testa a divisão em trechos com regras de tamanho controlado.
O último roda nos dados reais e é pulado se o CRD não foi baixado.
"""

import json
import re
from collections import Counter

import pytest

from juiz import config
from juiz.limpar_crd import extrair_regras, montar_trechos, processar

HTML = """
<h1>Core Rules 1.4</h1>
<h2 class="core-rules-anchor" id="R100"><a href="#R100"><span>100<!-- -->.</span><span>Game Concepts</span></a></h2>
<h3 class="core-rules-anchor" id="R101"><a href="#R101"><span>101<!-- -->.</span><span>Deck Construction</span></a></h3>
<ol>
 <li class="core-rules-anchor" id="R103">
  <div class="grid"><a href="#R103">103.</a>
   <div><p>To play, you need a deck.<span data-slot="badge">Changed</span></p></div>
   <span data-slot="badge">Changed</span>
  </div>
  <ol>
   <li class="core-rules-anchor" id="R103.1">
    <div class="grid"><a href="#R103.1">103.1.</a>
     <div><p>1 Champion Legend</p><p class="text-sm">See <a href="#R197">rule 197</a>. Locations for more information.</p></div>
    </div>
   </li>
   <li class="core-rules-anchor" id="R103.2">
    <div class="grid"><a href="#R103.2">103.2.</a>
     <div>
      <p>A Main Deck.</p>
      <div class="border-amber-600">Example: <span aria-label="Preview Jinx, Rebel">Jinx, Rebel</span> is a champion.</div>
      <div class="flex gap-2"><span aria-hidden="true">•</span><p>Units say "I."</p></div>
     </div>
    </div>
   </li>
  </ol>
 </li>
</ol>
"""


@pytest.fixture(scope="module")
def regras_html():
    return {r["numero"]: r for r in extrair_regras(HTML, "1.4")}


# ---------------------------------------------------------------------------
# HTML -> regras
# ---------------------------------------------------------------------------

def test_titulos_viram_secao_e_subsecao(regras_html):
    assert regras_html["100"]["tipo"] == "secao" and regras_html["100"]["texto"] == "Game Concepts"
    assert regras_html["101"]["tipo"] == "subsecao" and regras_html["101"]["texto"] == "Deck Construction"


def test_etiquetas_new_changed_sao_removidas(regras_html):
    assert regras_html["103"]["texto"] == "To play, you need a deck."


def test_hierarquia_e_localizacao(regras_html):
    assert regras_html["103"]["pai"] is None
    assert regras_html["103.1"]["pai"] == "103"
    assert regras_html["103.2"]["secao"] == "100. Game Concepts"
    assert regras_html["103.2"]["subsecao"] == "101. Deck Construction"
    assert regras_html["103.1"]["url"] == "https://www.riftboundfaq.com/reference/core-rules/1.4#R103.1"


def test_referencias_exemplos_cartas_e_listas(regras_html):
    assert regras_html["103.1"]["texto"] == "1 Champion Legend\nSee rule 197. Locations for more information."
    assert regras_html["103.1"]["referencias"] == ["197"]
    assert regras_html["103.2"]["texto"] == 'A Main Deck.\nExample: Jinx, Rebel is a champion.\n- Units say "I."'
    assert regras_html["103.2"]["cartas_mencionadas"] == ["Jinx, Rebel"]


# ---------------------------------------------------------------------------
# Regras -> trechos
# ---------------------------------------------------------------------------

def regra(numero: str, palavras: int, pai: str | None = None, subsecao: str = "101. Deck Construction") -> dict:
    """Regra de mentira com um número controlado de palavras."""
    return {
        "numero": numero, "tipo": "regra", "texto": " ".join([f"r{numero}"] * palavras), "pai": pai,
        "secao": "100. Game Concepts", "subsecao": subsecao, "versao": "1.4",
        "url": f"u#{numero}", "referencias": [], "cartas_mencionadas": [],
    }


def conteudo(trechos: list[dict]) -> list[list[str]]:
    return [t["regras"] for t in trechos]


def test_galho_pequeno_vira_um_trecho_so():
    regras = [regra("103", 10), regra("103.1", 10, "103"), regra("103.2", 10, "103")]
    assert conteudo(montar_trechos(regras, limite=100)) == [["103", "103.1", "103.2"]]


def test_galho_grande_e_dividido_e_a_mae_vira_contexto():
    regras = [regra("359", 70), regra("359.1", 60, "359"), regra("359.2", 60, "359")]
    trechos = montar_trechos(regras, limite=100)
    # A mãe entra inteira como conteúdo no primeiro pedaço...
    assert conteudo(trechos) == [["359"], ["359.1"], ["359.2"]]
    # ...e resumida como contexto nos outros.
    assert [t["contexto"] for t in trechos] == [[], ["359"], ["359"]]
    assert "359. r359" in trechos[1]["texto_com_regras"] and "…" in trechos[1]["texto_com_regras"]


def test_vizinhos_pequenos_sao_agrupados():
    regras = [regra("110", 30), regra("111", 30), regra("112", 30), regra("113", 30)]
    assert conteudo(montar_trechos(regras, limite=70)) == [["110", "111"], ["112", "113"]]


def test_pacote_pequeno_desce_junto_com_o_galho_grande():
    # "102" é pequena e o galho seguinte é grande: ela não pode virar um trecho sozinha.
    regras = [regra("102", 10), regra("103", 10), regra("103.1", 60, "103"), regra("103.2", 60, "103")]
    assert conteudo(montar_trechos(regras, limite=100)) == [["102", "103", "103.1"], ["103.2"]]


def test_subsecoes_diferentes_nunca_se_misturam():
    regras = [regra("102", 10, subsecao="101. A"), regra("105", 10, subsecao="104. B")]
    assert conteudo(montar_trechos(regras, limite=100)) == [["102"], ["105"]]


def test_texto_de_busca_nao_tem_numeros_de_regra():
    trecho = montar_trechos([regra("103", 5), regra("103.1", 5, "103")], limite=100)[0]
    assert trecho["texto"] == "# Game Concepts > Deck Construction\n" + "r103 " * 4 + "r103\n" + "r103.1 " * 4 + "r103.1"
    assert "103.1. r103.1" in trecho["texto_com_regras"]


# ---------------------------------------------------------------------------
# Dados reais (pulados se o CRD ainda não foi baixado)
# ---------------------------------------------------------------------------

dados_reais = pytest.mark.skipif(not config.CRD_SNAPSHOT.exists(), reason="rode antes: python -m juiz.baixar_crd")


@pytest.fixture(scope="module")
def crd():
    return processar()


@dados_reais
def test_crd_tem_regras_com_texto(crd):
    regras, _ = crd
    assert len(regras) > 2000
    assert all(r["texto"].strip() for r in regras)
    assert not any(re.search(r"(New|Changed)$", r["texto"]) for r in regras), "sobrou etiqueta New/Changed"


@dados_reais
def test_toda_regra_aparece_em_exatamente_um_trecho(crd):
    regras, trechos = crd
    contagem = Counter(n for t in trechos for n in t["regras"])
    numeros = [r["numero"] for r in regras if r["tipo"] == "regra"]
    assert sorted(contagem) == sorted(numeros)
    assert set(contagem.values()) == {1}


@dados_reais
def test_toda_regra_citada_pelo_faq_existe_no_crd(crd):
    from juiz.limpar_faq import processar_tudo

    if not config.FAQ_CONTENT_DIR.exists():
        pytest.skip("rode antes: python -m juiz.baixar_faq")
    regras, _ = crd
    numeros = {r["numero"] for r in regras}
    citadas = {n for t in processar_tudo()[0] for n in t["regras"]}
    assert not citadas - numeros


@dados_reais
def test_trechos_tem_tamanho_razoavel(crd):
    _, trechos = crd
    assert all(t["palavras"] <= 450 for t in trechos)
    assert all(t["url"].startswith(config.FAQ_SITE_URL) and "#R" in t["url"] for t in trechos)
    assert len({t["id"] for t in trechos}) == len(trechos)


@dados_reais
def test_versao_bate_com_o_manifesto_do_faq(crd):
    regras, _ = crd
    manifesto = json.loads((config.FAQ_SOURCES_DIR / "rules-manifest.json").read_text(encoding="utf-8"))
    assert {r["versao"] for r in regras} == {manifesto["coreRules"]["current"]}

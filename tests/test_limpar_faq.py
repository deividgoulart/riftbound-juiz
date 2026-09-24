"""Testes da limpeza do FAQ (etapa 2).

Rodar a partir da raiz do projeto:
    python -m pytest

Os testes do bloco de cima usam pedacinhos de MDX escritos aqui mesmo, no formato do FAQ.
Os do bloco de baixo rodam em cima dos dados reais e são pulados se o FAQ não foi baixado.
"""

import re
from collections import Counter

import pytest

from juiz import config
from juiz.limpar_faq import dividir_em_perguntas, extrair_glossario, extrair_metadados, limpar, processar_tudo, url_da_pagina


# ---------------------------------------------------------------------------
# Limpeza de cada tipo de componente (antes -> depois)
# ---------------------------------------------------------------------------

def test_regras_saem_do_texto_de_busca():
    bruto = 'Yes, Flash can target it.<Rule number="355.9.a" /><Rule number="355.10" />'
    assert limpar(bruto, manter_regras=False) == "Yes, Flash can target it."


def test_regras_seguidas_viram_uma_citacao_so():
    bruto = 'Yes, Flash can target it.<Rule number="355.9.a" /><Rule number="355.10" />'
    assert limpar(bruto, manter_regras=True) == "Yes, Flash can target it. [CRD 355.9.a, 355.10]"


def test_term_mantem_so_o_texto_de_dentro():
    bruto = 'When Flash <Term item="resolution">resolves</Term>, nothing moves.'
    assert limpar(bruto, manter_regras=False) == "When Flash resolves, nothing moves."


def test_card_vira_o_nome_da_carta():
    bruto = 'They play <Card name="Hextech Ray" /> targeting it.'
    assert limpar(bruto, manter_regras=False) == "They play Hextech Ray targeting it."


def test_custos_runas_e_universal():
    bruto = 'Reduce the cost by <Energy value={1} /><Universal />, or pay <Energy value={2} /><Fury />.'
    assert limpar(bruto, manter_regras=False) == "Reduce the cost by [1][Universal], or pay [2][Fury]."


def test_palavras_chave_usam_o_rotulo_do_jogo():
    bruto = "Its <Shield /> and <QuickDraw /> apply. <Flow value={2} /> too."
    assert limpar(bruto, manter_regras=False) == "Its [Shield] and [Quick-Draw] apply. [Flow 2] too."


def test_passos_viram_lista_numerada():
    bruto = "<Steps>\n<Step>\nChoose a unit.\n</Step>\n<Step>\nDeal damage.\nThen draw.\n</Step>\n</Steps>"
    assert limpar(bruto, manter_regras=False) == "1. Choose a unit.\n2. Deal damage.\n   Then draw."


def test_callout_vira_paragrafo_com_o_titulo():
    bruto = '<Callout type="idea" title="Example">\n\tYou play a spell.\n\tIt resolves.\n</Callout>'
    assert limpar(bruto, manter_regras=False) == "Example: You play a spell.\nIt resolves."


def test_componente_desconhecido_e_removido_e_reportado():
    desconhecidos = Counter()
    texto = limpar('Antes <Novidade foo="x" /> depois <Caixa>dentro</Caixa>.', False, desconhecidos)
    assert texto == "Antes depois dentro."
    assert desconhecidos == Counter({"Novidade": 1, "Caixa": 2})  # abertura e fechamento


def test_espacos_e_linhas_em_branco_sao_normalizados():
    assert limpar("a  b   \n\n\n\nc", manter_regras=False) == "a b\n\nc"


# ---------------------------------------------------------------------------
# Metadados
# ---------------------------------------------------------------------------

def test_metadados_de_regras_cartas_e_palavras_chave():
    bruto = (
        'Play <Card name="Hextech Ray" />.<Rule number="323.5" /> '
        'Its <Shield /> works.<Rule number="346" /><Rule number="323.5" /> <Card name="Hextech Ray" />'
    )
    meta = extrair_metadados(bruto)
    assert meta["regras"] == ["323.5", "346"]  # sem repetir, na ordem em que apareceram
    assert meta["cartas_mencionadas"] == ["Hextech Ray"]
    assert meta["palavras_chave"] == ["Shield"]
    assert meta["citacao_pendente"] is False


def test_aviso_rules_citation_needed_marca_citacao_pendente():
    bruto = (
        '<Callout type="idea" title="Example">x</Callout>\n'
        '<Callout type="warn" title="Rules citation needed">y</Callout>'
    )
    meta = extrair_metadados(bruto)
    assert meta["avisos"] == ["Rules citation needed"]  # exemplos ("idea") não são avisos
    assert meta["citacao_pendente"] is True


# ---------------------------------------------------------------------------
# Divisão em perguntas e URL
# ---------------------------------------------------------------------------

def test_subsecao_entra_no_trecho_da_pergunta_de_cima():
    corpo = (
        "## How does it resolve? [#resolution]\n\nFirst part.\n\n"
        "### Steps [#resolution-sequence]\n\n1. Do this.\n\n"
        "## Another question? [#other]\n\nOther answer.\n"
    )
    perguntas = dividir_em_perguntas(corpo)
    assert [p["pergunta"] for p in perguntas] == ["How does it resolve?", "Another question?"]
    assert perguntas[0]["subsecoes"] == [{"titulo": "Steps", "ancora": "resolution-sequence"}]
    assert "### Steps" in perguntas[0]["bruto"] and "1. Do this." in perguntas[0]["bruto"]
    assert perguntas[1]["bruto"] == "Other answer."


def test_url_nao_tem_o_grupo_de_rotas():
    caminho = config.FAQ_CONTENT_DIR / "(rulings)" / "cards" / "flash.mdx"
    assert url_da_pagina(caminho) == "https://www.riftboundfaq.com/cards/flash"


# ---------------------------------------------------------------------------
# Dados reais (pulados se o FAQ ainda não foi baixado)
# ---------------------------------------------------------------------------

dados_reais = pytest.mark.skipif(
    not config.FAQ_CONTENT_DIR.exists(), reason="rode antes: python -m juiz.baixar_faq"
)


@pytest.fixture(scope="module")
def resultado():
    return processar_tudo()


@dados_reais
def test_nenhum_componente_desconhecido(resultado):
    _, desconhecidos = resultado
    assert not desconhecidos, f"componentes novos no FAQ, atualizar limpar_faq.py: {dict(desconhecidos)}"


@dados_reais
def test_nenhuma_tag_sobra_no_texto(resultado):
    trechos, _ = resultado
    for t in trechos:
        for campo in ("texto", "texto_com_regras"):
            assert not re.search(r"</?[A-Z]\w*", t[campo]), f"{t['id']}: sobrou tag em {campo}"


@dados_reais
def test_ids_unicos_e_toda_url_tem_ancora(resultado):
    trechos, _ = resultado
    assert len({t["id"] for t in trechos}) == len(trechos)
    paginas = [t for t in trechos if t["categoria"] != "glossario"]  # o glossário aponta pra linha no GitHub
    assert all(t["ancora"] and t["url"].endswith("#" + t["ancora"]) for t in paginas)


@dados_reais
def test_toda_regra_citada_aparece_no_texto_do_llm(resultado):
    trechos, _ = resultado
    for t in trechos:
        citadas = {n for grupo in re.findall(r"\[CRD ([^\]]+)\]", t["texto_com_regras"]) for n in grupo.split(", ")}
        assert set(t["regras"]) == citadas, t["id"]


@dados_reais
def test_texto_de_busca_nao_tem_numero_de_regra(resultado):
    trechos, _ = resultado
    assert not any("[CRD" in t["texto"] for t in trechos)


@dados_reais
def test_paginas_de_carta_tem_o_nome_da_carta(resultado):
    trechos, _ = resultado
    cartas = [t for t in trechos if t["categoria"] == "cards"]
    assert cartas and all(t["carta"] == t["pagina"] for t in cartas)
    assert all(t["carta"] is None for t in trechos if t["categoria"] != "cards")


# ---------------------------------------------------------------------------
# Glossário do FAQ (src/lib/glossary.ts)
# ---------------------------------------------------------------------------

# String "crua" (r"""): o \' fica igual ao do arquivo TypeScript de verdade.
GLOSSARIO_TS = r"""export const GLOSSARY = {
	chain: {
		title: 'Chain',
		explanation:
			'The chain is a waiting area. It\'s temporary.',
	},
	focus: {
		title: 'Focus',
		explanation: 'Focus marks a player.',
	},
} as const
"""


def test_glossario_vira_um_trecho_por_termo_com_link_pra_linha():
    trechos = extrair_glossario(GLOSSARIO_TS, commit="abc123")
    assert [t["pagina"] for t in trechos] == ["Chain", "Focus"]
    assert trechos[0]["texto"] == "# Glossary\n## What is Chain?\n\nThe chain is a waiting area. It's temporary."
    assert trechos[0]["id"] == "faq/glossario#chain" and trechos[0]["categoria"] == "glossario"
    assert trechos[0]["url"].endswith("/blob/abc123/src/lib/glossary.ts#L2")
    assert trechos[1]["url"].endswith("#L7")


@dados_reais
def test_glossario_real_tem_os_termos_de_iniciante(resultado):
    trechos, _ = resultado
    termos = {t["pagina"] for t in trechos if t["categoria"] == "glossario"}
    assert {"Chain", "Priority", "Focus", "Cleanup"} <= termos

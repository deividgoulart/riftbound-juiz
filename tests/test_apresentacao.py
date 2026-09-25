"""Testes da conversão das citações em números sobrescritos com link (etapa 6)."""

from juiz.apresentacao import linkar_citacoes
from juiz.responder import Fonte

FONTES = [Fonte(1, "faq", "t1", "https://faq/1", "x"), Fonte(3, "carta", "t3", "https://carta/3", "x")]
REGRAS = {"355.9.a": "https://crd#R355.9.a"}
CRD = "https://www.riftboundfaq.com/reference/core-rules/1.4#R"


def linkar(texto):
    return linkar_citacoes(texto, FONTES, REGRAS, versao_crd="1.4")


def a(rotulo, url):
    return f'<a href="{url}" target="_blank">{rotulo}</a>'


def test_fonte_vira_numero_sobrescrito_com_link_grudado_na_palavra():
    assert linkar("Sim, pode [F1].") == f"Sim, pode<sup>{a('F1', 'https://faq/1')}</sup>."


def test_grupo_de_fontes_vira_um_sobrescrito_so():
    assert linkar("Sim [F1, F3].") == f"Sim<sup>{a('F1', 'https://faq/1')}, {a('F3', 'https://carta/3')}</sup>."


def test_fonte_que_nao_existe_fica_sem_link():
    assert linkar("Sim [F9].") == "Sim<sup>F9</sup>."


def test_custo_da_carta_nao_vira_citacao():
    assert linkar("Custa [1] ou [Universal] a menos.") == "Custa [1] ou [Universal] a menos."


def test_regras_do_crd_viram_sobrescrito_com_link():
    assert linkar("Vale a regra (CRD 355.9.a).") == f"Vale a regra<sup>CRD {a('355.9.a', 'https://crd#R355.9.a')}</sup>."
    # Regra fora do contexto também ganha link, montado a partir da versão do CRD.
    assert linkar("Não (CRD 425.1.c, CRD 425.1.c.1).") == (
        f"Não<sup>CRD {a('425.1.c', CRD + '425.1.c')}, {a('425.1.c.1', CRD + '425.1.c.1')}</sup>."
    )


def test_crd_dentro_dos_colchetes_da_fonte():
    assert linkar("Sim [F1, CRD 355.9.a].") == (
        f"Sim<sup>{a('F1', 'https://faq/1')}, {a('CRD 355.9.a', 'https://crd#R355.9.a')}</sup>."
    )


def test_numero_de_regra_escrito_como_fonte_vira_link_de_regra():
    # O LLM reserva às vezes escreve [F1, F331.2] ou [F310]: 3 dígitos é regra, não fonte.
    assert linkar("Não [F1, F331.2].") == f"Não<sup>{a('F1', 'https://faq/1')}, {a('CRD 331.2', CRD + '331.2')}</sup>."
    assert linkar("Ver [F310].") == f"Ver<sup>{a('CRD 310', CRD + '310')}</sup>."


def test_sufixo_inventado_depois_da_fonte_e_descartado():
    # O LLM reserva escreveu [F1.4.3] em vez de [F1]: fica só o link da fonte.
    assert linkar("Vence com 8 pontos [F1.4.3].") == f"Vence com 8 pontos<sup>{a('F1', 'https://faq/1')}</sup>."
    assert linkar("Sim [F1.94.1, F3.2.a].") == f"Sim<sup>{a('F1', 'https://faq/1')}, {a('F3', 'https://carta/3')}</sup>."


def test_html_do_llm_nao_entra_na_pagina():
    assert linkar("<script>alert(1)</script> [F1]") == f"&lt;script&gt;alert(1)&lt;/script&gt;<sup>{a('F1', 'https://faq/1')}</sup>"


def test_cifrao_fica_como_esta():
    assert linkar("custa $5") == "custa $5"


def test_citacoes_soltas_de_regra_e_glossario():
    assert linkar("Permite reagir [813.1.c.1].") == f"Permite reagir<sup>CRD {a('813.1.c.1', CRD + '813.1.c.1')}</sup>."
    assert linkar("Pendente [Glossário].") == "Pendente<sup>glossário do FAQ</sup>."
    assert linkar("Custa [2] a menos.") == "Custa [2] a menos."  # custo continua igual


def test_citacoes_vizinhas_viram_um_grupo_so():
    assert linkar("Passa a vez [F1] (CRD 355.9.a).") == (
        f"Passa a vez<sup>{a('F1', 'https://faq/1')}, CRD {a('355.9.a', 'https://crd#R355.9.a')}</sup>."
    )

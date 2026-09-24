"""Testes da etapa 5: glossário, cartas e o juiz.

Nenhum teste chama a API: o juiz recebe um índice e um LLM "de mentira", e os testes conferem
o que ele monta e manda pro LLM, que é a parte que a gente controla.
"""

import pytest

from juiz import config as _config

dados_reais_crd = pytest.mark.skipif(not (_config.PROCESSED_DIR / "crd_regras.jsonl").exists(),
                                     reason="rode antes: python -m juiz.limpar_crd")

from juiz.cartas import Catalogo, aplicar_errata, url_da_carta
from juiz.glossario import encontrar_termos, expandir_pergunta
from juiz.erros import CotaEsgotada
from juiz.responder import INSTRUCOES, NAO_ENCONTREI, Busca, Juiz, e_pedido_de_explicacao, fontes_citadas, mesclar, sem_citacoes

# ---------------------------------------------------------------------------
# Glossário
# ---------------------------------------------------------------------------


def test_glossario_acha_termo_com_acento_e_terminacao_diferente():
    assert encontrar_termos("A Vex atordoa a unidade?") == [("atordoa", "Stun"), ("unidade", "Unit")]
    assert encontrar_termos("Posso usar EMBOSCADA?") == [("emboscada", "Ambush")]


def test_glossario_prefere_o_termo_mais_longo():
    # "pilha de descarte" é Trash; não pode virar também "pilha" (Chain).
    assert encontrar_termos("foi pra pilha de descarte") == [("pilha de descarte", "Trash")]


def test_glossario_ignora_palavras_comuns():
    assert encontrar_termos("vou poder usar isso em ordem de turno?") == []


def test_expandir_pergunta_acrescenta_os_termos_oficiais():
    assert expandir_pergunta("posso usar emboscada na base?") == "posso usar emboscada na base? (Ambush)"
    assert expandir_pergunta("qual o melhor deck?") == "qual o melhor deck?"


# ---------------------------------------------------------------------------
# Cartas
# ---------------------------------------------------------------------------


def carta(nome, texto="Do something."):
    return {"name": nome, "energyCost": 2, "powerCost": None, "might": 3, "domains": ["Calm"],
            "cardTypes": ["Unit"], "superTypes": [], "tags": [], "abilities": texto, "effects": None}


CATALOGO = Catalogo(
    [carta("Irelia, Fervent"), carta("Irelia, Graceful"), carta("Vi, Hotheaded"), carta("Flash"),
     carta("Buff"), carta("Hextech Ray"), carta("Astral Heron", "your next card costs [2] less.")],
    {"Astral Heron": [{"oldText": "your next card costs [2] less.", "newText": "the next card you play this turn costs [2] less."}]},
)


def test_nome_completo_em_qualquer_caixa_e_sem_contar_duas_vezes():
    assert CATALOGO.encontrar("a irelia, fervent ganha might?") == ["Irelia, Fervent"]


def test_nome_curto_de_campeao_traz_todas_as_versoes():
    assert CATALOGO.encontrar("a Irelia pode atacar?") == ["Irelia, Fervent", "Irelia, Graceful"]


def test_nome_curto_ou_de_uma_palavra_exige_maiuscula():
    assert CATALOGO.encontrar("eu vi que dá pra dar buff") == []
    assert CATALOGO.encontrar("a Vi recebe Buff?") == ["Vi, Hotheaded", "Buff"]
    assert CATALOGO.encontrar("posso usar Flash e Hextech Ray?") == ["Flash", "Hextech Ray"]


def test_errata_troca_o_texto_antigo_pelo_novo():
    texto = CATALOGO.texto("Astral Heron")
    assert "the next card you play this turn costs [2] less." in texto
    assert "your next card costs" not in texto
    assert "errata" in texto


def test_errata_ja_aplicada_nao_muda_o_texto():
    c = aplicar_errata(carta("X", "new text"), [{"oldText": "old text", "newText": "new text"}])
    assert c["abilities"] == "new text" and c["errata"]


def test_link_da_carta_segue_o_padrao_do_faq():
    assert url_da_carta("Irelia, Fervent") == "https://wiki.leagueoflegends.com/en-us/Riftbound:Irelia%2C_Fervent"


# ---------------------------------------------------------------------------
# Juiz (com índice e LLM de mentira)
# ---------------------------------------------------------------------------

TRECHO_FAQ = {
    "id": "faq/cards/flash#target-in-base", "fonte": "faq", "pagina": "Flash", "carta": "Flash",
    "pergunta": "Can Flash target a unit that is already in base?",
    "url": "https://www.riftboundfaq.com/cards/flash#target-in-base",
    "texto_com_regras": "# Flash\n## Can Flash target...?\n\nYes. [CRD 355.9.a, 446.1]",
    "regras": ["355.9.a", "446.1"], "citacao_pendente": True,
}
TRECHO_CRD = {
    "id": "crd/1.4/446", "fonte": "crd", "versao": "1.4", "numero": "446", "subsecao": "445. Movement",
    "secao": "300. Playing the Game", "url": "u#R446", "texto_com_regras": "446. Moving...\n  446.1. ...",
    "regras": ["446", "446.1"], "contexto": [],
}
REGRAS = {n: {"numero": n, "texto": f"texto da regra {n}", "url": f"u#R{n}"} for n in ["355.9.a", "446", "446.1"]}


class IndiceFalso:
    def __init__(self, resultados):
        self.resultados = resultados
        self.consultas = []
        self.ks = []

    def buscar(self, pergunta, modelo, k=5):
        self.consultas.append(pergunta)
        self.ks.append(k)
        return self.resultados[:k]


class LLMFalso:
    def __init__(self, resposta="Sim. Flash pode [F1] (CRD 355.9.a)."):
        self.resposta = resposta
        self.chamadas = []

    def gerar(self, instrucoes, mensagem):
        self.chamadas.append((instrucoes, mensagem))
        return self.resposta


def juiz(resultados, llm=None):
    return Juiz([Busca("principal", None, IndiceFalso(resultados), 0.70)], llm=llm or LLMFalso(),
                regras=REGRAS, catalogo=CATALOGO, k=5)


def test_nota_baixa_sem_carta_responde_nao_encontrei_sem_chamar_o_llm():
    llm = LLMFalso()
    resposta = juiz([(TRECHO_FAQ, 0.60)], llm).responder("qual o melhor deck do meta?")
    assert resposta.texto == NAO_ENCONTREI and not resposta.encontrou
    assert llm.chamadas == []


def test_nota_baixa_mas_com_carta_na_pergunta_ainda_consulta_o_llm():
    llm = LLMFalso()
    juiz([(TRECHO_FAQ, 0.60)], llm).responder("o que faz a Irelia?")
    assert len(llm.chamadas) == 1


def test_glossario_so_entra_na_busca_se_ligado():
    j = juiz([(TRECHO_FAQ, 0.80)])
    j.responder("posso usar emboscada?")
    consultas = j.buscas[0].indice.consultas
    assert consultas == ["posso usar emboscada?"]  # padrão: pergunta original
    j.glossario_na_busca = True
    j.responder("posso usar emboscada?")
    assert consultas[-1] == "posso usar emboscada? (Ambush)"


def test_mensagem_tem_fontes_numeradas_cartas_regras_e_avisos():
    llm = LLMFalso()
    resposta = juiz([(TRECHO_FAQ, 0.85), (TRECHO_CRD, 0.75)], llm).responder("o Flash atordoa a unidade?")
    _, mensagem = llm.chamadas[0]
    assert "[F1] FAQ não oficial" in mensagem and "[F2] Core Rules 1.4 oficial: regra 446" in mensagem
    assert "[F3] Carta Flash (texto oficial atual)" in mensagem  # carta da pergunta (e da página do FAQ)
    assert "CITAÇÃO PENDENTE" in mensagem
    assert '"atordoa" -> Stun' in mensagem
    # A 355.9.a (citada pelo FAQ) entra com o texto oficial; a 446.1 não, porque já está no trecho do CRD.
    assert "355.9.a: texto da regra 355.9.a" in mensagem
    assert "446.1: texto da regra" not in mensagem
    assert [f.citada for f in resposta.fontes] == [True, False, False]
    assert resposta.regras_citadas() == {"355.9.a": "u#R355.9.a"}


def test_resposta_de_nao_encontrei_do_llm_e_marcada():
    llm = LLMFalso("Não encontrei a resposta nas regras que eu consultei. Chame um juiz.")
    resposta = juiz([(TRECHO_FAQ, 0.85)], llm).responder("pergunta qualquer")
    assert not resposta.encontrou


def test_citacoes_no_formato_F_e_custos_de_carta_nao_se_confundem():
    assert fontes_citadas("Custa [1] ou [Universal] a menos [F6].") == {6}
    assert fontes_citadas("Sim [F1, F3]. Ver também [F2][F4].") == {1, 2, 3, 4}
    assert fontes_citadas("Sem citação nenhuma [2].") == set()


@pytest.mark.parametrize("trecho", [
    "Responda em português do Brasil",
    "Mantenha em inglês os nomes de cartas",
    "Use SOMENTE as fontes fornecidas",
    "Não encontrei a resposta nas regras que eu consultei.",
    "prevalece sobre o FAQ não oficial",
    "FAQ oficial da Riot tem precedência",
    "CITAÇÃO PENDENTE",
    "NÃO é voltar para a mão (CRD 455)",  # Recall em Riftbound vai pra base (em LoR, vai pra mão)
    "são CUSTOS da carta, não fontes",
    "nunca [F1.4.3]",  # o LLM reserva juntou números à fonte: [F1.4.3] em vez de [F1]
])
def test_instrucoes_cobrem_os_requisitos_do_projeto(trecho):
    assert trecho in INSTRUCOES


def test_so_entram_cartas_da_pergunta_e_de_paginas_com_nota_perto_da_melhor():
    outra_pagina = dict(TRECHO_FAQ, id="faq/cards/buff#x", pagina="Buff", carta="Buff")
    llm = LLMFalso()
    resposta = juiz([(TRECHO_FAQ, 0.85), (outra_pagina, 0.75)], llm).responder("pergunta sem carta")
    cartas = [f.resumo for f in resposta.fontes if f.tipo == "carta"]
    assert cartas == ["Flash"]  # "Buff" ficou de fora: nota 0,10 abaixo da melhor


def test_trechos_abaixo_do_limiar_saem_do_contexto_mas_o_primeiro_fica():
    llm = LLMFalso()
    resposta = juiz([(TRECHO_FAQ, 0.72), (TRECHO_CRD, 0.65)], llm).responder("o Flash move?")
    assert [f.tipo for f in resposta.fontes] == ["faq", "carta"]


def test_fonte_tem_titulo_curto_pra_tela():
    resposta = juiz([(TRECHO_FAQ, 0.85), (TRECHO_CRD, 0.75)]).responder("pergunta")
    assert resposta.fontes[0].resumo == "Flash — Can Flash target a unit that is already in base?"
    assert resposta.fontes[1].resumo == "Regra 446 — Movement"



# ---------------------------------------------------------------------------
# Busca reserva (e5-small quando o Gemini falha)
# ---------------------------------------------------------------------------

class IndiceQueFalha:
    def __init__(self, erro):
        self.erro = erro
        self.chamadas = 0

    def buscar(self, pergunta, modelo, k=5):
        self.chamadas += 1
        raise self.erro


def juiz_com_reserva(principal, reserva_resultados, limiar_reserva=0.70, llm=None):
    return Juiz([Busca("gemini", None, principal, 0.60), Busca("e5", None, IndiceFalso(reserva_resultados), limiar_reserva)],
                llm=llm or LLMFalso(), regras=REGRAS, catalogo=CATALOGO, k=5)


def test_sem_cota_na_principal_usa_a_reserva_e_nao_insiste_na_proxima_pergunta():
    principal = IndiceQueFalha(CotaEsgotada("gemini-embedding-2"))
    j = juiz_com_reserva(principal, [(TRECHO_FAQ, 0.85)])
    resposta = j.responder("o Flash mira na base?")
    assert resposta.modelo_busca == "e5" and resposta.encontrou
    j.responder("outra pergunta")
    assert principal.chamadas == 1  # a principal ficou pausada: a 2ª pergunta foi direto pra reserva


def test_qualquer_falha_da_principal_cai_na_reserva():
    j = juiz_com_reserva(IndiceQueFalha(ConnectionError("sem internet")), [(TRECHO_FAQ, 0.85)])
    assert j.responder("pergunta").modelo_busca == "e5"


def test_cada_busca_usa_o_proprio_corte():
    llm = LLMFalso()
    # Nota 0,75 passaria no corte do Gemini (0,60), mas não no da reserva (0,80).
    j = juiz_com_reserva(IndiceQueFalha(CotaEsgotada()), [(TRECHO_FAQ, 0.75)], limiar_reserva=0.80, llm=llm)
    resposta = j.responder("pergunta sem carta")
    assert resposta.texto == NAO_ENCONTREI and llm.chamadas == []


def test_se_todas_as_buscas_falham_o_erro_aparece():
    j = Juiz([Busca("gemini", None, IndiceQueFalha(CotaEsgotada()), 0.6), Busca("e5", None, IndiceQueFalha(OSError("sem índice")), 0.8)],
             llm=LLMFalso(), regras=REGRAS, catalogo=CATALOGO)
    with pytest.raises(OSError):
        j.responder("pergunta")


def test_numero_de_regra_com_F_nao_conta_como_fonte_citada():
    assert fontes_citadas("Não [F1, F331.2]. Ver [F310, F343].") == {1}


def test_sufixo_inventado_depois_da_fonte_conta_como_a_fonte():
    # O LLM reserva escreveu [F1.4.3] e [F1.94.1] em vez de [F1]: com 1 ou 2 dígitos depois do F, é fonte.
    assert fontes_citadas("O Victory Score é 8 [F1.4.3]. Você vence [F1.94.2].") == {1}
    assert fontes_citadas("Sim [F2.1, F12.3.a].") == {2, 12}
    assert fontes_citadas("Não [F331.2.a]. Ver [F100].") == set()  # 3 dígitos continua sendo regra


def test_resposta_com_sufixo_inventado_marca_a_fonte_como_citada():
    texto = ("O Victory Score padrão é 8 pontos [F1.4.3].\n\nVocê ganha pontos segurando (Hold) os Battlefields "
             "[F1.94.1]. Durante um cleanup [Glossário], você vence se tiver essa pontuação [F1.94.2].")
    resposta = juiz([(TRECHO_FAQ, 0.85), (TRECHO_CRD, 0.75)], LLMFalso(texto)).responder("quantos pontos preciso pra ganhar?")
    assert [f.citada for f in resposta.fontes] == [True, False, False]  # antes: nenhuma citada



# ---------------------------------------------------------------------------
# Tipo de pergunta e conversa (memória)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pergunta", [
    "explicação completa de como funciona as chains", "me explique as chains", "o que é open state?",
    "não consigo entender essas nuances de chains", "qual a diferença entre Recall e Move?", "como funcionam os showdowns?",
])
def test_pedidos_de_explicacao(pergunta):
    assert e_pedido_de_explicacao(pergunta)


@pytest.mark.parametrize("pergunta", [
    "toda spell inicia uma chain?", "spell de reaction pode iniciar uma chain?", "o que eu faço se o alvo morrer?",
    "o Guardian Angel salva minha unidade do Smite?",
])
def test_perguntas_diretas(pergunta):
    assert not e_pedido_de_explicacao(pergunta)


def test_explicacao_busca_mais_trechos_e_avisa_o_tipo_ao_llm():
    llm = LLMFalso()
    j = juiz([(TRECHO_FAQ, 0.85)], llm)
    resposta = j.responder("me explique as chains")
    assert j.buscas[0].indice.ks == [8] and resposta.tipo == "explicação"
    assert "TIPO DE PERGUNTA: explicação" in llm.chamadas[0][1]
    j.responder("toda spell inicia uma chain?")
    assert j.buscas[0].indice.ks[-1] == 5 and "TIPO DE PERGUNTA: direta" in llm.chamadas[1][1]


def test_sem_citacoes_limpa_a_resposta_anterior():
    assert sem_citacoes("A Chain é uma fila [F1] (CRD 328). Resolve [F2, F3].") == "A Chain é uma fila. Resolve."


def test_mesclar_junta_sem_repetir_e_fica_com_a_maior_nota():
    a, b = {"id": "a"}, {"id": "b"}
    assert mesclar([(a, 0.7), (b, 0.6)], [(b, 0.9)], k=5) == [(b, 0.9), (a, 0.7)]


def test_continuacao_usa_a_conversa_na_busca_e_na_mensagem():
    llm = LLMFalso()
    j = juiz([(TRECHO_FAQ, 0.85)], llm)
    historico = [("p1", "r1"), ("p2", "r2"), ("como funciona a Chain?", "A Chain é uma fila [F1] (CRD 328).")]
    j.responder("e se for durante um showdown?", historico=[("p0", "r0")] + historico)
    consultas = j.buscas[0].indice.consultas
    assert consultas == ["e se for durante um showdown?", "como funciona a Chain? e se for durante um showdown?"]
    mensagem = llm.chamadas[0][1]
    assert "CONVERSA ANTERIOR" in mensagem
    assert "Juiz: A Chain é uma fila." in mensagem  # sem as citações antigas
    assert "p0" not in mensagem and "p1" in mensagem  # só as 3 trocas mais recentes


# ---------------------------------------------------------------------------
# Definições oficiais dos termos técnicos
# ---------------------------------------------------------------------------

DEFINICOES = [
    {"termos": ["Chain"], "regras": ["328"], "glossario": "chain"},
    {"termos": ["Open State", "Closed State"], "regras": ["309.1", "309.2"]},
    {"termos": ["Action"], "regras": ["806.1.c"]},
]
REGRAS_DEF = {
    "328": {"texto": "The Chain is a Non-Board Zone.", "pai": None},
    "309.1": {"texto": "If a Chain exists, the turn is in a Closed State.", "pai": "309"},
    "309.2": {"texto": "If no Chain exists, the turn is in an Open State.", "pai": "309"},
    "806.1.c": {"texto": "Action is functionally short for the following:", "pai": "806.1"},
    "806.1.c.1": {"texto": "You may play me in showdowns.", "pai": "806.1.c"},
}


def juiz_com_definicoes():
    return Juiz([Busca("b", None, IndiceFalso([]), 0.7)], llm=LLMFalso(), regras=REGRAS_DEF, catalogo=CATALOGO,
                definicoes=DEFINICOES, glossario={"chain": "The chain is a waiting area."})


def test_definicao_junta_glossario_regra_e_sub_regras():
    defs = dict(juiz_com_definicoes().definicoes_relevantes(["o que é action?"], []))
    assert defs["Action"] == "806.1.c: Action is functionally short for the following: | 806.1.c.1: You may play me in showdowns."


def test_definicoes_da_pergunta_vem_antes_das_fontes_e_plural_conta():
    defs = juiz_com_definicoes().definicoes_relevantes(["open state é quando?"], ["cards wait on the chains"])
    assert [rotulo for rotulo, _ in defs] == ["Open State / Closed State", "Chain"]
    assert defs[1][1].startswith("Glossário do FAQ: The chain is a waiting area. || 328:")


def test_termo_dentro_de_outra_palavra_nao_conta():
    assert juiz_com_definicoes().definicoes_relevantes(["transaction reactions"], []) == []


@dados_reais_crd
def test_toda_regra_do_arquivo_de_definicoes_existe_no_crd():
    import json

    import yaml

    from juiz import config

    regras = {json.loads(l)["numero"] for l in (config.PROCESSED_DIR / "crd_regras.jsonl").open(encoding="utf-8")}
    for d in yaml.safe_load(config.DEFINICOES.read_text(encoding="utf-8")):
        assert set(d.get("regras", [])) <= regras, d["termos"]


def test_passar_a_prioridade_vira_pass_no_glossario():
    # Etapa 7: "meu oponente passa" precisa trazer a definição oficial de passar a prioridade (CRD 339.1).
    assert "Pass" in [en for _, en in encontrar_termos("meu oponente passa, o que acontece?")]
    assert all(en != "Pass" for _, en in encontrar_termos("posso jogar na minha base?"))


# --- plano B (etapa 8): nenhum LLM respondeu ---

class LLMForaDoAr:
    def gerar(self, instrucoes, mensagem):
        from google.genai.errors import ServerError

        raise ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})


def test_plano_b_devolve_os_trechos_com_o_motivo():
    resposta = juiz([(TRECHO_FAQ, 0.85), (TRECHO_CRD, 0.75)], LLMForaDoAr()).responder("o Flash mira na base?", plano_b=True)
    assert "instável" in resposta.sem_llm and "503" in resposta.sem_llm
    assert resposta.encontrou and resposta.fontes[0].url == TRECHO_FAQ["url"]
    assert not any(f.citada for f in resposta.fontes)


def test_sem_plano_b_o_erro_continua_subindo():
    from google.genai.errors import ServerError

    with pytest.raises(ServerError):  # a avaliação precisa saber que o LLM falhou
        juiz([(TRECHO_FAQ, 0.85)], LLMForaDoAr()).responder("o Flash mira na base?")

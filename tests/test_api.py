"""Testes da API (api/main.py), com o TestClient do FastAPI: um juiz "de mentira" (nada chama o Gemini)
e um banco em memória com o catálogo pequeno do conftest."""

import json

import pytest
from fastapi.testclient import TestClient

from api import acesso
from api.main import criar_app
from api.recursos import Recurso
from decks import colecao
from decks.importar import ler_lista
from decks.meus_decks import listar_decks, salvar_deck
from juiz import config
from juiz.erros import CotaEsgotada
from juiz.responder import NAO_ENCONTREI, Fonte, Resposta

LISTA = "Legend:\n1 Jinx, Loose Cannon\nMain Deck:\n3 Jinx, Rebel\n2 Abandon\nRunes:\n6 Fury Rune\n6 Chaos Rune"


class JuizFalso:
    def __init__(self, resposta=None, erro=None):
        self.resposta, self.erro = resposta, erro
        self.historicos, self.decks = [], []

    def responder(self, pergunta, historico=None, plano_b=False, deck=None):
        self.historicos.append(list(historico or []))
        self.decks.append(deck)
        if self.erro:
            raise self.erro
        self.resposta.pergunta = pergunta
        return self.resposta


def resposta_com_fontes():
    fontes = [
        Fonte(1, "faq", "FAQ: Can I use Ambush to play a unit to my base?", "https://faq/ambush", "x", 0.84,
              citacao_pendente=True, citada=True),
        Fonte(2, "crd", "Core Rules: regra 822", "https://crd#R822", "x", 0.71),
    ]
    return Resposta("?", "Não. O Ambush só vale em battlefields [F1] (CRD 822.1.b).", True, fontes,
                    regras={"822.1.b": "https://crd#R822.1.b"}, termos=[("emboscada", "Ambush")],
                    nota_busca=0.84, uso={"modelo": "modelo-falso", "tokens_entrada": 10, "tokens_saida": 5},
                    modelo_busca=config.MODELO_EMBEDDINGS)


@pytest.fixture
def api(tmp_path, monkeypatch, banco, catalogo):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    for nome in ("SENHA_DO_APP", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "TOPDECK_API_KEY", "SITE_URL"):
        monkeypatch.delenv(nome, raising=False)  # sem senha = rodando no seu computador, sem limites

    def criar(juiz=None, senha=None, topdeck=None):
        if senha:
            monkeypatch.setenv("SENHA_DO_APP", senha)
        if topdeck:
            monkeypatch.setenv("TOPDECK_API_KEY", topdeck)
        app = criar_app(Recurso.pronto(juiz or JuizFalso(resposta_com_fontes())),
                        Recurso.pronto((banco, catalogo)), aquecer=False)
        return TestClient(app)

    return criar


def eventos(tmp_path):
    arquivo = tmp_path / "conversas.jsonl"
    return [json.loads(l) for l in arquivo.open(encoding="utf-8")] if arquivo.exists() else []


def perguntar(cliente, texto="posso usar emboscada na base?", headers=None, **extra):
    return cliente.post("/api/perguntar", json={"pergunta": texto, **extra}, headers=headers)


# --- Juiz ---

def test_info_tem_exemplos_creditos_e_versoes(api):
    info = api().get("/api/info").json()
    assert len(info["exemplos"]) == 4
    assert "CC BY-SA 4.0" in info["creditos"] and "não oficial" in info["creditos"]
    assert info["publico"] is False and info["dono"] is True and info["convidado"] is None
    assert set(info["fontes"]) == {"faq_data", "faq_commit", "crd_versao", "crd_nome"}


def test_pergunta_devolve_resposta_com_links_e_fontes(api, tmp_path):
    r = perguntar(api())
    assert r.status_code == 200
    dados = r.json()
    assert '<a href="https://faq/ambush" target="_blank">F1</a>' in dados["html"]
    assert '<a href="https://crd#R822.1.b" target="_blank">822.1.b</a>' in dados["html"]
    assert dados["original"] == resposta_com_fontes().texto
    assert [(f["numero"], f["citada"], f["citacao_pendente"]) for f in dados["fontes"]] == [(1, True, True), (2, False, False)]
    assert dados["fontes"][0]["rotulo"] == "FAQ não oficial" and dados["fontes"][0]["trecho"] is None
    assert dados["busca_reserva"] is False and dados["termos"] == [["emboscada", "Ambush"]]
    registro = eventos(tmp_path)
    assert registro[-1]["tipo"] == "resposta" and registro[-1]["pergunta"] == "posso usar emboscada na base?"


def test_historico_vai_pro_juiz(api):
    juiz = JuizFalso(resposta_com_fontes())
    cliente = api(juiz)
    perguntar(cliente, "como funciona a Chain?")
    perguntar(cliente, "e num showdown?", historico=[["como funciona a Chain?", "É a fila."]])
    assert juiz.historicos == [[], [("como funciona a Chain?", "É a fila.")]]


def test_nao_encontrei(api):
    dados = perguntar(api(JuizFalso(Resposta("?", NAO_ENCONTREI, False, nota_busca=0.3)))).json()
    assert dados["encontrou"] is False and dados["fontes"] == []


def test_erro_na_api_vira_mensagem_amigavel_e_registra(api, tmp_path):
    r = perguntar(api(JuizFalso(erro=RuntimeError("Coloque GEMINI_API_KEY no arquivo .env"))))
    assert r.status_code == 502
    assert "Não consegui responder agora" in r.json()["detail"] and "GEMINI_API_KEY" in r.json()["detail"]
    assert eventos(tmp_path)[-1]["tipo"] == "erro"


def test_cota_esgotada_tem_aviso_especifico(api):
    r = perguntar(api(JuizFalso(erro=CotaEsgotada())))
    assert r.status_code == 503 and "cota diária grátis" in r.json()["detail"]


def test_busca_reserva_e_avisada(api):
    resposta = resposta_com_fontes()
    resposta.modelo_busca = "e5-small"
    assert perguntar(api(JuizFalso(resposta))).json()["busca_reserva"] is True


def test_pergunta_vazia_ou_longa_demais_e_recusada(api):
    cliente = api()
    assert perguntar(cliente, "").status_code == 422
    assert perguntar(cliente, "x" * 501).status_code == 422


def test_deck_em_foco_vai_pro_juiz(api, banco, catalogo):
    id_ = salvar_deck(banco, "Jinx do sábado", ler_lista(LISTA, catalogo))
    juiz = JuizFalso(resposta_com_fontes())
    dados = perguntar(api(juiz), "quais cartas do meu deck dão Stun?", deck_id=id_).json()
    deck = juiz.decks[-1]
    assert deck.nome == "Jinx do sábado" and ("principal", "Jinx, Rebel", 3) in deck.cartas
    assert dados["deck"] == "Jinx do sábado"


def test_deck_em_foco_que_nao_existe(api):
    assert perguntar(api(), deck_id="nao-existe").status_code == 404


def test_avaliacao_vai_pro_registro_local(api, tmp_path):
    assert api().post("/api/avaliar", json={"id": "abc", "gostou": True}).status_code == 200
    assert eventos(tmp_path)[-1] == {**eventos(tmp_path)[-1], "tipo": "avaliacao", "id": "abc", "gostou": True}


# --- Publicado: convidados e senha ---

@pytest.fixture
def publica(api, monkeypatch):
    monkeypatch.setattr(config, "LIMITE_POR_VISITANTE", 2)
    return lambda juiz=None, **kw: api(juiz, senha="segredo", **kw)


def test_publicado_tem_modo_convidado_e_nao_registra(publica, tmp_path):
    cliente = publica()
    info = cliente.get("/api/info").json()
    assert info["publico"] and not info["dono"] and info["convidado"]["restantes"] == 2
    assert "Não escreva dados pessoais" in info["privacidade"]
    assert perguntar(cliente).json()["restantes"] == 1
    assert eventos(tmp_path) == []
    assert cliente.post("/api/avaliar", json={"id": "abc", "gostou": True}).status_code == 404


def test_convidado_fica_bloqueado_depois_do_limite(publica):
    juiz = JuizFalso(resposta_com_fontes())
    cliente = publica(juiz)
    perguntar(cliente), perguntar(cliente)
    r = perguntar(cliente)
    assert r.status_code == 429 and "Você usou as 2 perguntas de hoje" in r.json()["detail"]
    assert len(juiz.historicos) == 2
    assert cliente.get("/api/info").json()["convidado"]["bloqueio"]


def test_limite_do_dia_vale_pra_todos_os_visitantes(publica, monkeypatch):
    monkeypatch.setattr(config, "LIMITE_DIARIO", 1)
    cliente = publica()
    assert perguntar(cliente).status_code == 200
    r = perguntar(cliente, headers={"X-Forwarded-For": "10.0.0.2"})  # outro visitante
    assert r.status_code == 429 and "limite de perguntas de convidados de hoje" in r.json()["detail"]


def test_erro_devolve_a_pergunta_ao_limite(publica, monkeypatch):
    monkeypatch.setattr(config, "LIMITE_DIARIO", 1)
    cliente = publica(JuizFalso(erro=RuntimeError("503")))
    assert perguntar(cliente).status_code == 502
    assert cliente.get("/api/info").json()["convidado"]["restantes"] == 1  # a pergunta que deu erro não contou


def test_plano_b_mostra_os_trechos_e_nao_conta_no_limite(publica):
    fontes = [Fonte(1, "faq", "FAQ: Ambush", "https://faq/ambush", "# Ambush\n## Can I?\n\nNo. Ambush only works on battlefields.", 0.84)]
    plano_b = Resposta("?", "Não consegui escrever a resposta em português agora.", True, fontes,
                       nota_busca=0.84, sem_llm="o Gemini está instável agora (erro 503)")
    dados = perguntar(publica(JuizFalso(plano_b))).json()
    assert dados["sem_llm"] == "o Gemini está instável agora (erro 503)"
    assert dados["fontes"][0]["trecho"] == "No. Ambush only works on battlefields."
    assert dados["restantes"] == 2


def test_senha_certa_da_token_que_libera_tudo(publica):
    cliente = publica()
    token = cliente.post("/api/entrar", json={"senha": "segredo"}).json()["token"]
    dono = {"Authorization": f"Bearer {token}"}
    assert cliente.get("/api/info", headers=dono).json()["dono"] is True
    for _ in range(3):  # passa do limite de 2
        assert perguntar(cliente, headers=dono).status_code == 200


def test_senha_errada_nao_libera_e_as_tentativas_acabam(publica, monkeypatch):
    cliente = publica()
    for _ in range(config.TENTATIVAS_DE_SENHA):
        assert cliente.post("/api/entrar", json={"senha": "chute"}).status_code == 401
    assert cliente.post("/api/entrar", json={"senha": "segredo"}).status_code == 429


def test_token_vence_e_troca_de_senha_desconecta(monkeypatch):
    monkeypatch.setenv("SENHA_DO_APP", "segredo")
    token = acesso.criar_token(agora=1000)
    assert acesso.token_valido(token, agora=2000)
    assert not acesso.token_valido(token, agora=1000 + acesso.TOKEN_VALIDO_POR_DIAS * 86400 + 1)
    assert not acesso.token_valido(token.replace(".", ".0"), agora=2000)
    monkeypatch.setenv("SENHA_DO_APP", "outra")
    assert not acesso.token_valido(token, agora=2000)


# --- Deck builder ---

def test_catalogo_e_colecao(api, banco):
    colecao.salvar_alteracoes(banco, {"Abandon": 2, "Jinx, Rebel": 1})
    cliente = api()
    cartas = cliente.get("/api/cartas").json()
    jinx = next(c for c in cartas if c["nome"] == "Loose Cannon")
    assert jinx["tipo"] == "Legend" and jinx["dominios"] == ["Fury", "Chaos"] and jinx["tags"] == ["Jinx"]
    assert cliente.get("/api/colecao").json() == {"cartas": {"Abandon": 2, "Jinx, Rebel": 1}, "diferentes": 2, "copias": 3}


def test_mudar_a_colecao(api, banco):
    cliente = api()
    r = cliente.put("/api/colecao", json={"mudancas": {"Abandon": 3, "Void Seeker": 0}})
    assert r.status_code == 200 and r.json()["cartas"] == {"Abandon": 3}
    assert cliente.put("/api/colecao", json={"mudancas": {"Carta Inventada": 1}}).status_code == 400
    assert cliente.put("/api/colecao", json={"mudancas": {"Abandon": -1}}).status_code == 400


def test_importar_e_exportar_csv(api, banco):
    colecao.definir(banco, "Void Seeker", 1)
    cliente = api()
    r = cliente.post("/api/colecao/importar", json={"texto": "carta,quantidade\nAbandon,2\nJinks Rebel,1\n", "substituir": True})
    dados = r.json()
    assert dados["importadas"] == 1 and dados["copias"] == 2
    assert dados["desconhecidas"] == [{"texto": "Jinks Rebel", "sugestoes": ["Jinx, Rebel"]}]
    assert colecao.listar(banco) == {"Abandon": 2}  # substituiu: a Void Seeker saiu
    csv = cliente.get("/api/colecao/exportar")
    assert csv.text == "carta,quantidade\nAbandon,2\n" and "attachment" in csv.headers["content-disposition"]


def test_publicado_sem_senha_e_so_leitura(api, banco, catalogo):
    salvar_deck(banco, "Jinx", ler_lista(LISTA, catalogo))
    cliente = api(senha="segredo")
    assert cliente.put("/api/colecao", json={"mudancas": {"Abandon": 3}}).status_code == 401
    assert cliente.post("/api/colecao/importar", json={"texto": "Abandon,2"}).status_code == 401
    assert cliente.post("/api/decks", json={"texto": LISTA}).status_code == 401
    deck = cliente.get("/api/decks").json()["decks"][0]
    assert cliente.delete(f"/api/decks/{deck['id']}").status_code == 401
    assert cliente.get(f"/api/decks/{deck['id']}").status_code == 200  # ver continua liberado


def test_previa_e_importar_deck(api, banco):
    colecao.salvar_alteracoes(banco, {"Abandon": 2, "Jinx, Rebel": 1})
    cliente = api()
    previa = cliente.post("/api/decks/previa", json={"texto": "3 Jinks Rebel\n2 Abandon"}).json()
    assert previa["nao_reconhecidas"] == [{"texto": "Jinks Rebel", "sugestoes": ["Jinx, Rebel"]}]
    r = cliente.post("/api/decks", json={"nome": "Errado", "texto": "3 Jinks Rebel\n2 Abandon"})
    assert r.status_code == 400 and "(quis dizer Jinx, Rebel?)" in r.json()["detail"]
    assert listar_decks(banco) == []

    r = cliente.post("/api/decks", json={"nome": "Jinx de teste", "texto": LISTA})
    assert r.status_code == 200 and any("mínimo é 40" in a for a in r.json()["avisos"])
    deck = cliente.get("/api/decks").json()["decks"][0]
    # runas básicas contam como "tenho" (padrão): Abandon 2 + Jinx 1 + 12 runas de 18 cópias
    assert (deck["nome"], deck["tenho"], deck["total"], deck["copias_faltando"], deck["cartas_faltando"]) == \
        ("Jinx de teste", 15, 18, 3, 2)
    assert deck["lenda"]["rotulo"] == "Jinx, Loose Cannon" and deck["lenda"]["dominios"] == ["Fury", "Chaos"]
    sem_runas = cliente.get("/api/decks", params={"runas": False}).json()["decks"][0]
    assert sem_runas["tenho"] == 3


def test_ignorar_desconhecidas_salva_sem_elas(api, banco):
    r = api().post("/api/decks", json={"texto": "3 Jinks Rebel\n2 Abandon", "ignorar_desconhecidas": True})
    assert r.status_code == 200 and listar_decks(banco)[0]["nome"] == "Deck sem nome"


def test_detalhe_do_deck_tem_lista_de_compra_links_e_custo(api, banco, catalogo):
    id_ = salvar_deck(banco, "Jinx", ler_lista("Loose Cannon\n3 Jinx, Rebel\n2 Abandon", catalogo))
    colecao.salvar_alteracoes(banco, {"Abandon": 2, "Jinx, Rebel": 1})
    banco.executar("INSERT INTO precos_tcg (carta, usd) VALUES ('Jinx, Rebel', 0.5)")
    banco.executar("INSERT INTO meta (chave, valor) VALUES ('precos_data_tcg', '2026-09-24')")
    deck = api().get(f"/api/decks/{id_}").json()
    assert deck["lista_de_compra"] == "2 Jinx - Rebel\n1 Jinx - Loose Cannon"
    assert [(f["carta"], f["falta"]) for f in deck["faltando"]] == [("Jinx, Rebel", 2), ("Loose Cannon", 1)]
    assert deck["faltando"][0]["liga"].startswith("https://www.ligariftbound.com.br/?view=cards%2Fcard&card=Jinx+-+Rebel")
    assert deck["custo"] == 1.66 and deck["sem_preco"] == 1
    assert "TCGplayer (EUA) de 24/09/2026" in deck["legenda_dos_precos"] and "R$ 1,67 por dólar" in deck["legenda_dos_precos"]
    assert [c["secao"] for c in deck["cartas"]] == ["lenda", "principal", "principal"]
    assert deck["compra_por_lista"] == config.LIGA_COMPRA_POR_LISTA
    assert api().get("/api/decks/nao-existe").status_code == 404


def test_ordena_pelo_mais_barato_ou_por_menos_faltando(api, banco, catalogo):
    salvar_deck(banco, "Caro e quase completo", ler_lista("3 Jinx, Rebel", catalogo))
    salvar_deck(banco, "Barato", ler_lista("3 Abandon", catalogo))
    colecao.definir(banco, "Jinx, Rebel", 2)
    cliente = api()
    nomes = lambda **p: [d["nome"] for d in cliente.get("/api/decks", params=p).json()["decks"]]
    banco.executar("INSERT INTO precos_tcg (carta, usd) VALUES ('Jinx, Rebel', 20.0), ('Abandon', 0.1)")
    assert nomes() == ["Barato", "Caro e quase completo"]  # padrão: mais barato de completar primeiro
    assert nomes(ordem="faltando") == ["Caro e quase completo", "Barato"]  # falta 1 cópia contra 3


def test_sem_precos_so_ordena_por_cartas_faltando(api, banco, catalogo):
    salvar_deck(banco, "Um", ler_lista("3 Abandon", catalogo))
    dados = api().get("/api/decks", params={"ordem": "barato"}).json()
    assert dados["ordem"] == "faltando" and dados["tem_precos"] is False


def test_apagar_deck(api, banco, catalogo):
    id_ = salvar_deck(banco, "Velho", ler_lista("2 Abandon", catalogo))
    assert api().delete(f"/api/decks/{id_}").status_code == 200
    assert listar_decks(banco) == []


# --- Decks do meta ---

def coletar_meta(banco, catalogo):
    from tests.test_decks_meta import AGORA, cliente_falso, deck_obj, torneio
    from decks.meta import atualizar_meta

    decks = {2: deck_obj(lenda="Kennen, Heart of the Tempest")}
    atualizar_meta(banco, catalogo, "k", cliente=cliente_falso([torneio(decks=decks)], []), agora=AGORA)


def test_decks_do_meta_ficam_separados_dos_meus(api, banco, catalogo):
    salvar_deck(banco, "Meu deck", ler_lista("2 Abandon", catalogo))
    coletar_meta(banco, catalogo)
    cliente = api(topdeck="k")
    meus = cliente.get("/api/decks", params={"tipo": "meus"}).json()
    assert [d["nome"] for d in meus["decks"]] == ["Meu deck"] and meus["meta"] is None
    do_meta = cliente.get("/api/decks", params={"tipo": "meta"}).json()
    assert do_meta["total"] == 8 and all("º em Liga de Sábado" in d["nome"] for d in do_meta["decks"])
    assert do_meta["meta"]["ultima_coleta"].startswith("2026-09-24") and do_meta["meta"]["chave"] is True
    assert {l["rotulo"]: l["decks"] for l in do_meta["lendas"]} == {"Jinx, Loose Cannon": 7, "Kennen, Heart of the Tempest": 1}

    kennen = cliente.get("/api/decks", params={"tipo": "meta", "lenda": "Heart of the Tempest"}).json()
    assert [(d["nome"], d["url"], d["data"], d["colocacao"]) for d in kennen["decks"]] == \
        [("Kennen, Heart of the Tempest · 2º em Liga de Sábado", "https://topdeck.gg/bracket/t1", "2026-09-20", "2")]
    assert cliente.delete(f"/api/decks/{kennen['decks'][0]['id']}").status_code == 400  # só o manual pode ser apagado
    assert cliente.get("/api/decks", params={"tipo": "meta", "limite": 3}).json()["total"] == 8


def test_atualizar_meta_sem_chave_explica_como_ligar(api):
    cliente = api()
    assert cliente.get("/api/info").json()["topdeck"] is False
    r = cliente.post("/api/meta/atualizar")
    assert r.status_code == 400 and "TOPDECK_API_KEY" in r.json()["detail"]


def test_banco_fora_do_ar_da_erro_claro(tmp_path, monkeypatch):
    monkeypatch.delenv("SENHA_DO_APP", raising=False)

    def falha():
        raise RuntimeError("o banco na nuvem recusou o acesso: confira o TURSO_AUTH_TOKEN")

    cliente = TestClient(criar_app(Recurso.pronto(JuizFalso()), Recurso(falha, 60), aquecer=False))
    r = cliente.get("/api/colecao")
    assert r.status_code == 503 and "TURSO_AUTH_TOKEN" in r.json()["detail"]


def test_recurso_recarrega_em_segundo_plano_sem_parar_os_pedidos():
    import threading
    import time

    liberar, versoes = threading.Event(), iter([1, 2])

    def carregar():
        versao = next(versoes)
        if versao == 2:
            liberar.wait(5)  # a recarga demora
        return versao

    recurso = Recurso(carregar, validade_em_segundos=0)
    assert recurso.obter() == 1
    assert recurso.obter() == 1  # venceu: continua servindo o antigo enquanto recarrega
    liberar.set()
    for _ in range(100):
        if recurso._valor == 2:
            break
        time.sleep(0.01)
    assert recurso._valor == 2


def test_raiz_aponta_pra_documentacao(api):
    assert api().get("/").json()["rotas"] == "/docs"


@pytest.mark.parametrize("site_url, permitidas, bloqueadas", [
    ("", ["https://qualquer.com"], []),
    ("https://juiz-riftbound.vercel.app/", ["https://juiz-riftbound.vercel.app", "https://juiz-riftbound-git-main-deivid.vercel.app"],
     ["https://outro.vercel.app", "https://juiz-riftbound.vercel.app.golpe.com"]),
    ("meusite.com.br", ["https://meusite.com.br"], ["https://outro.com"]),
])
def test_site_url_aceita_barra_no_fim_e_libera_as_previas_da_vercel(api, monkeypatch, site_url, permitidas, bloqueadas):
    monkeypatch.setenv("SITE_URL", site_url)
    cliente = api()
    for origem in permitidas:
        assert cliente.get("/api/saude", headers={"Origin": origem}).headers.get("access-control-allow-origin") in (origem, "*")
    for origem in bloqueadas:
        assert "access-control-allow-origin" not in cliente.get("/api/saude", headers={"Origin": origem}).headers


def test_juiz_e_deck_builder_nao_baixam_o_faq_ao_mesmo_tempo(monkeypatch, tmp_path):
    import threading
    import time

    from juiz import atualizar, baixar_faq

    monkeypatch.setattr(config, "FAQ_DIR", tmp_path / "faq")
    monkeypatch.setattr(config, "FAQ_SNAPSHOT", tmp_path / "snapshot.json")
    dentro, maximo = [0], [0]

    def clonar():
        dentro[0] += 1
        maximo[0] = max(maximo[0], dentro[0])
        time.sleep(0.05)
        (tmp_path / "faq" / ".git").mkdir(parents=True, exist_ok=True)
        dentro[0] -= 1

    monkeypatch.setattr(baixar_faq, "clonar", clonar)
    monkeypatch.setattr(baixar_faq, "atualizar", clonar)
    monkeypatch.setattr(baixar_faq, "salvar_snapshot", lambda: {"commit": "abc"})
    threads = [threading.Thread(target=atualizar.atualizar_faq, args=(lambda *_: None,)) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert maximo[0] == 1


# --- Ficha da carta (fase 3) ---

def carta_do_faq(nome, abilities, tipos=("Unit",), dominios=("Fury",)):
    return {"name": nome, "energyCost": 3, "powerCost": None, "might": 2, "domains": list(dominios),
            "cardTypes": list(tipos), "superTypes": [], "tags": [], "abilities": abilities, "effects": None}


TRECHOS_DO_FAQ = [
    {"id": "faq/cards/void-seeker#a", "fonte": "faq", "categoria": "cards", "pagina": "Void Seeker", "carta": "Void Seeker",
     "pergunta": "Can Void Seeker target my own unit?", "url": "https://faq/void-seeker#a", "texto": "Yes.",
     "cartas_mencionadas": []},
    {"id": "faq/cards/abandon#b", "fonte": "faq", "categoria": "cards", "pagina": "Abandon", "carta": "Abandon",
     "pergunta": "Does Abandon work on Void Seeker?", "url": "https://faq/abandon#b", "texto": "No.",
     "cartas_mencionadas": ["Void Seeker"]},
    {"id": "faq/mechanics/ambush#c", "fonte": "faq", "categoria": "mechanics", "pagina": "Ambush", "carta": None,
     "pergunta": "Can I Ambush to my base?", "url": "https://faq/ambush#c", "texto": "No.", "cartas_mencionadas": []},
]


class LlmFalso:
    def __init__(self):
        self.chamadas = []

    def gerar(self, instrucoes, mensagem, esquema=None):
        from juiz.fichas import INSTRUCOES_DA_DUVIDA

        self.chamadas.append(mensagem)
        if instrucoes == INSTRUCOES_DA_DUVIDA:  # um cuidado: uma frase sobre uma dúvida do FAQ
            return "Sim, pode mirar a sua própria unidade." if "own unit" in mensagem else "Não, o Abandon não afeta."
        return "**O que a carta faz**\nCausa 4 de dano numa unidade.\n\n**Exemplos**\n- Você tira uma unidade do caminho."


@pytest.fixture
def com_fichas():
    from juiz.cartas import Catalogo as CatalogoDoJuiz
    from juiz.fichas import Fichario

    llm = LlmFalso()
    catalogo = CatalogoDoJuiz([carta_do_faq("Void Seeker", "[Ambush] (You may play me as a [Reaction].)\nDeal 4 to a unit."),
                               carta_do_faq("Abandon", "Counter a spell.", tipos=("Spell",))], {})
    juiz = JuizFalso(resposta_com_fontes())
    juiz.fichario = Fichario(catalogo, TRECHOS_DO_FAQ, llm)
    return juiz, llm


def test_ficha_tem_texto_duvidas_e_mecanicas(api, com_fichas):
    juiz, llm = com_fichas
    ficha = api(juiz).get("/api/carta", params={"nome": "Void Seeker"}).json()
    assert ficha["texto"].startswith("[Ambush]") and ficha["atributos"]["energia"] == 3
    assert [d["pergunta"] for d in ficha["duvidas"]] == ["Can Void Seeker target my own unit?", "Does Abandon work on Void Seeker?"]
    assert ficha["mecanicas"] == [{"pagina": "Ambush", "url": "https://faq/ambush"}]
    assert ficha["explicacao"] is None  # ainda não gerada
    assert llm.chamadas == []  # a API nunca chama um LLM pra ficha


def test_runa_basica_nao_tem_texto(api, com_fichas):
    juiz, _ = com_fichas
    assert api(juiz).get("/api/carta", params={"nome": "Fury Rune"}).json()["texto"] is None


def test_api_nao_gera_explicacao_na_hora(api, com_fichas):
    juiz, _ = com_fichas
    assert api(juiz).post("/api/carta/explicar", json={"nome": "Void Seeker"}).status_code in (404, 405)


def test_explicacao_gerada_no_computador_aparece_na_ficha(api, com_fichas, banco, catalogo):
    from api.gerar_explicacoes import gerar, ordem_das_cartas

    juiz, llm = com_fichas
    salvar_deck(banco, "Com Abandon", ler_lista("2 Abandon", catalogo))
    assert ordem_das_cartas(banco, ["Void Seeker", "Abandon"]) == ["Abandon", "Void Seeker"]  # as dos decks primeiro

    mensagens = []
    assert gerar(juiz.fichario, banco, ["Void Seeker", "Fury Rune"], log=mensagens.append) == \
        {"feitas": 1, "falhas": 0, "reprovadas": 0, "restantes": 0}  # a runa não tem texto: fica de fora
    # 1 chamada pra parte principal + 1 por dúvida do FAQ sobre a carta (a página Ambush é de mecânica: não)
    assert len(llm.chamadas) == 3
    assert "TEXTO OFICIAL DA CARTA" in llm.chamadas[0] and "Can Void Seeker target my own unit?" in llm.chamadas[0]
    explicacao = api(juiz).get("/api/carta", params={"nome": "Void Seeker"}).json()["explicacao"]
    assert "Sim, pode mirar a sua própria unidade." in explicacao["html"]
    assert '<a href="https://faq/void-seeker#a" target="_blank">F2</a>' in explicacao["html"]
    assert [f["numero"] for f in explicacao["fontes"]] == [2, 3]  # só as citadas

    gerar(juiz.fichario, banco, ["Void Seeker"], log=mensagens.append)
    assert len(llm.chamadas) == 3  # já estava pronta: pulou
    juiz.fichario.catalogo.cartas["Void Seeker"]["abilities"] = "Deal 5 to a unit."  # errata
    assert api(juiz).get("/api/carta", params={"nome": "Void Seeker"}).json()["explicacao"] is None
    gerar(juiz.fichario, banco, ["Void Seeker"], log=mensagens.append)
    assert len(llm.chamadas) == 6  # a assinatura mudou: refez


def test_gerar_para_quando_o_ollama_nao_responde(com_fichas, banco, catalogo):
    from api.gerar_explicacoes import gerar

    juiz, _ = com_fichas

    class Desligado(LlmFalso):
        def gerar(self, *a, **k):
            raise RuntimeError("o Ollama não está rodando")

    juiz.fichario.llm = Desligado()
    mensagens = []
    r = gerar(juiz.fichario, banco, ["Void Seeker", "Abandon", "Void Seeker", "Abandon"], log=mensagens.append)
    assert r["feitas"] == 0 and r["falhas"] == 3
    assert any("Ollama está aberto" in m for m in mensagens)


class LlmQueErra(LlmFalso):
    """Na 1ª vez, a parte principal sai com "mana" e cita outra carta; na 2ª, certa."""

    def gerar(self, instrucoes, mensagem, esquema=None):
        if not self.chamadas:
            self.chamadas.append((mensagem, self.temperatura))
            return "**O que a carta faz**\nCancela um Spell e devolve a mana.\n\n**Exemplos**\n- Use contra o Void Seeker."
        self.chamadas.append((mensagem, self.temperatura))
        return super().gerar(instrucoes, mensagem, esquema)

    temperatura = 0.0


def test_parte_errada_e_pedida_de_novo_com_mais_variacao(com_fichas):
    juiz, _ = com_fichas
    juiz.fichario.llm = llm = LlmQueErra()
    explicacao = juiz.fichario.explicar("Abandon")
    assert "mana" not in explicacao.texto and "Não, o Abandon não afeta. [F2]" in explicacao.texto
    assert [t for _, t in llm.chamadas[:2]] == [0.0, 0.3]  # a 2ª tentativa varia um pouco
    assert "ATENÇÃO" not in llm.chamadas[1][0]  # sem repetir a versão errada nem listar os erros


def test_cuidado_que_nao_sai_vira_a_pergunta_do_faq(com_fichas):
    juiz, _ = com_fichas

    class NaoResume(LlmFalso):
        def gerar(self, instrucoes, mensagem, esquema=None):
            from juiz.fichas import INSTRUCOES_DA_DUVIDA

            return "- Spell: correct\n- mana: ok" if instrucoes == INSTRUCOES_DA_DUVIDA else super().gerar(instrucoes, mensagem)

    juiz.fichario.llm = NaoResume()
    texto = juiz.fichario.explicar("Void Seeker").texto
    assert "- Can Void Seeker target my own unit? [F2]" in texto  # a pergunta original, com o link


def test_explicacao_que_nao_melhora_fica_de_fora_e_o_lote_segue(com_fichas, banco, catalogo):
    from api.gerar_explicacoes import gerar
    from juiz.fichas import TENTATIVAS

    juiz, _ = com_fichas

    class SempreTraduz(LlmFalso):
        def gerar(self, *a, **k):
            self.chamadas.append(a)
            return "**O que a carta faz**\nCancela um Spell.\n\n**Exemplos**\n- Custa mana."

        temperatura = 0.0

    juiz.fichario.llm = llm = SempreTraduz()
    mensagens = []
    r = gerar(juiz.fichario, banco, ["Abandon", "Void Seeker", "Abandon", "Void Seeker"], log=mensagens.append)
    assert r["reprovadas"] == 4 and r["feitas"] == 0 and len(llm.chamadas) == 4 * TENTATIVAS  # não parou no 3º erro
    assert any("reprovada na conferência" in m and "mana" in m for m in mensagens)


def test_ajustar_conserta_titulos_e_traducoes_diretas():
    from juiz.fichas import ajustar

    texto = ajustar("### O que a carta faz\nÉ um feitiço de Caos: um unitário vai pro lixo.\n\n---\n\n**Exemplos:**\n- x\n\n"
                    "**Cuidados e Exceções**\n- y [F2]")
    assert texto == ("**O que a carta faz**\nÉ um Spell de Chaos: uma unidade vai pro Trash.\n\n**Exemplos**\n- x\n\n"
                     "**Cuidados e exceções**\n- y [F2]")


def test_carta_sem_duvidas_no_faq_nao_tem_secao_de_cuidados(com_fichas):
    from juiz.fichas import Fichario

    juiz, llm = com_fichas
    sem_faq = Fichario(juiz.fichario.catalogo, [], llm)
    texto = sem_faq.explicar("Abandon").texto
    assert "Cuidados" not in texto and len(llm.chamadas) == 1
    assert any("não foi pedida" in p for p in sem_faq.problemas(
        "Abandon", "**O que a carta faz**\nx\n\n**Exemplos**\n- y\n\n**Cuidados e exceções**\n- z", sem_faq._fontes("Abandon")))

"""API do Juiz Riftbound: o juiz de regras (fase 1) e o deck builder (fase 2), pro site em web/.

Rodar (a partir da raiz do projeto):
    uvicorn api.main:app --reload --port 8000

Documentação interativa de cada rota: http://localhost:8000/docs

Toda a lógica continua em juiz/ e decks/; aqui só entram e saem JSONs. Publicada (com SENHA_DO_APP), a
API tem o modo convidado e a senha do dono: veja api/acesso.py.
"""

import os
import re
import threading
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from api.acesso import Convidados, TentativasDeSenha, criar_token, e_dono
from api.recursos import Recurso, recursos_padrao
from decks import colecao, conclusao, meta, precos
from decks.banco import turso_configurado
from decks.catalogo import nome_da_lenda
from decks.compras import link_da_carta, lista_de_compra
from decks.importar import NOMES_DAS_SECOES, ler_lista
from decks.meus_decks import apagar_deck, cartas_dos_decks, listar_decks, salvar_deck
from juiz import config
from juiz.apresentacao import CREDITOS, ROTULOS, linkar_citacoes, procedencia, trecho_para_ler
from juiz.erros import CotaEsgotada, explicar_erro
from juiz.fichas import Fichario
from juiz.limites import modo_publico, senha_confere
from juiz.registro import registrar_avaliacao, registrar_erro, registrar_resposta

PRIVACIDADE = ("As perguntas são processadas pelo Google Gemini no plano gratuito: o Google pode usá-las pra "
               "melhorar os produtos dele, e pessoas podem revisá-las. Não escreva dados pessoais.")

EXEMPLOS = [
    "Posso usar Emboscada pra jogar uma unidade na minha base?",
    "O Guardian Angel salva minha unidade do Smite?",
    "Se counterarem minha carta, eu recebo a mana de volta?",
    "Quantos pontos preciso pra ganhar?",
]

MAX_DECKS_POR_PAGINA = 20  # a coleta do meta traz centenas; o site mostra os primeiros na ordem escolhida
ORDENS = ("barato", "faltando")


def criar_app(juiz: Recurso | None = None, deck_builder: Recurso | None = None, aquecer: bool = True) -> FastAPI:
    """`juiz` e `deck_builder` só são passados nos testes; sem eles, a API carrega os de verdade."""
    padrao_juiz, padrao_decks = recursos_padrao()
    juiz, deck_builder = juiz or padrao_juiz, deck_builder or padrao_decks

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        if aquecer:  # prepara tudo assim que liga, em segundo plano: o 1º visitante espera menos
            for recurso in (deck_builder, juiz):
                threading.Thread(target=_aquecer, args=(recurso,), daemon=True).start()
        yield

    app = FastAPI(title="Juiz Riftbound", version="3.0", lifespan=ciclo_de_vida,
                  description="Juiz de regras e deck builder de Riftbound TCG, em português.")
    app.state.juiz, app.state.deck_builder = juiz, deck_builder
    app.state.convidados, app.state.tentativas = Convidados(), TentativasDeSenha()
    # A senha vai num header (não em cookie), então liberar outros sites não abre brecha de CSRF.
    origens, previas = origens_do_site(os.environ.get("SITE_URL", ""))
    app.add_middleware(CORSMiddleware, allow_origins=origens, allow_origin_regex=previas,
                       allow_methods=["*"], allow_headers=["*"])
    @app.get("/", include_in_schema=False)
    def raiz():
        """Quem abre o endereço da API no navegador (ou o Render, conferindo se ela subiu) cai aqui."""
        return {"api": "Juiz Riftbound", "rotas": "/docs", "saude": "/api/saude"}

    app.include_router(rotas_juiz())
    app.include_router(rotas_decks())
    return app


def origens_do_site(site_url: str) -> tuple[list[str], str | None]:
    """Quais sites podem chamar a API pelo navegador (CORS), a partir de SITE_URL: endereços separados
    por vírgula. Sem SITE_URL, qualquer um.

    O navegador compara o endereço exato, sem "/" no fim: "https://x.vercel.app/" colado do navegador
    bloquearia o próprio site. Por isso o endereço é limpo aqui. Um endereço da Vercel também libera as
    previas do mesmo projeto (https://x-git-branch-usuario.vercel.app, https://x-abc123-usuario.vercel.app)."""
    origens, projetos = [], []
    for bruto in site_url.split(","):
        endereco = bruto.strip().rstrip("/").lower()
        if not endereco:
            continue
        if "://" not in endereco:
            endereco = "https://" + endereco
        origem = "/".join(endereco.split("/")[:3])  # só esquema + domínio: "https://x.vercel.app/decks" também vale
        origens.append(origem)
        dominio = origem.split("://", 1)[1]
        if dominio.endswith(".vercel.app"):
            projetos.append(re.escape(dominio.removesuffix(".vercel.app")))
    if not origens:
        return ["*"], None
    return origens, (rf"https://({'|'.join(projetos)})(-[a-z0-9-]+)?\.vercel\.app" if projetos else None)


def _aquecer(recurso: Recurso) -> None:
    try:
        recurso.obter()
    except Exception:
        traceback.print_exc()  # o erro aparece de novo (e explicado) no 1º pedido


# ---------------------------------------------------------------------------
# Peças comuns
# ---------------------------------------------------------------------------

def ip_de(request: Request) -> str:
    """IP do visitante. Na nuvem a API fica atrás de um proxy, que manda o IP original no X-Forwarded-For."""
    encaminhado = request.headers.get("x-forwarded-for", "")
    return encaminhado.split(",")[0].strip() or (request.client.host if request.client else "?")


def dono(authorization: str | None = Header(default=None)) -> bool:
    return e_dono(authorization)


def so_o_dono(eh_dono: bool = Depends(dono)) -> None:
    if not eh_dono:
        raise HTTPException(401, "Só o dono do app pode editar. Entre com a senha.")


def obter_deck_builder(request: Request):
    try:
        return request.app.state.deck_builder.obter()
    except Exception as erro:
        traceback.print_exc()
        raise HTTPException(503, f"Não consegui abrir o banco da coleção ({explicar_erro(erro)}). "
                                 "Tente de novo em alguns instantes.") from None


def lendas_dos_decks(listas: dict[str, list[dict]]) -> dict[str, str]:
    """{id do deck: lenda}"""
    return {deck_id: l["carta"] for deck_id, cartas in listas.items() for l in cartas if l["secao"] == "lenda"}


def json_da_lenda(lenda: str | None, catalogo) -> dict | None:
    if not lenda:
        return None
    carta = catalogo.cartas.get(lenda)
    return {"nome": lenda, "rotulo": nome_da_lenda(lenda, catalogo), "imagem": catalogo.imagem_de(lenda),
            "dominios": [d for d in carta.dominios.split(", ") if d] if carta else []}


def resumo_do_deck(c: conclusao.Conclusao, lenda: str | None, catalogo, precos_usd: dict[str, float]) -> dict:
    custo, sem_preco = conclusao.custo(c, precos_usd)
    tem_custo = bool(c.faltando) and len(sem_preco) < len(c.faltando)
    d = c.deck
    return {
        "id": d["id"], "nome": d["nome"], "origem": d["origem"], "url": d.get("url"), "data": d.get("data"),
        "torneio": d.get("torneio"), "colocacao": d.get("colocacao"), "lenda": json_da_lenda(lenda, catalogo),
        "porcentagem": round(c.porcentagem, 1), "tenho": c.tenho, "total": c.total,
        "copias_faltando": c.copias_faltando, "cartas_faltando": len(c.faltando),
        "custo": round(custo, 2) if tem_custo else (0.0 if not c.faltando else None),
        "sem_preco": len(sem_preco),
    }


def legenda_dos_precos(data_dos_precos: str | None) -> str:
    baratas, caras = (f"{v:.2f}".replace(".", ",") for v in (config.REAIS_POR_DOLAR_BARATAS, config.REAIS_POR_DOLAR_CARAS))
    return ("Estimativa do menor preço na Liga, não é o preço de lá: preço de mercado do TCGplayer (EUA)"
            + (f" de {date.fromisoformat(data_dos_precos):%d/%m/%Y}" if data_dos_precos else "")
            + f" convertido com as razões medidas contra o menor preço da Liga (R$ {baratas} por dólar nas cartas "
            f"baratas, R$ {caras} nas caras). Erro típico: {config.ERRO_TIPICO_POR_CARTA:.0%} numa carta e "
            f"{config.ERRO_TIPICO_10_CARTAS:.0%} na soma de 10 cartas; por isso não há preço por carta. O preço de "
            "verdade está no link de cada carta e na Compra por Lista.")


# ---------------------------------------------------------------------------
# Juiz
# ---------------------------------------------------------------------------

class Pergunta(BaseModel):
    pergunta: str = Field(min_length=1, max_length=500)
    historico: list[tuple[str, str]] = Field(default_factory=list, max_length=20)  # [(pergunta, resposta)]
    deck_id: str | None = None


class Avaliacao(BaseModel):
    id: str = Field(max_length=16)
    gostou: bool


class Senha(BaseModel):
    senha: str = Field(max_length=200)


def fonte_json(f, com_trecho: bool) -> dict:
    return {"numero": f.numero, "tipo": f.tipo, "rotulo": ROTULOS.get(f.tipo, f.tipo), "titulo": f.resumo or f.titulo,
            "url": f.url or None, "nota": f.nota, "citada": f.citada, "citacao_pendente": f.citacao_pendente,
            "trecho": trecho_para_ler(f.texto) if com_trecho else None}


def deck_em_foco(request: Request, deck_id: str | None):
    """O deck escolhido no chat, com as cartas, pro juiz. None se não houver (ou se o banco falhar)."""
    if not deck_id:
        return None
    from juiz.responder import DeckEmFoco  # aqui, e não no topo: juiz.responder é pesado de importar

    banco, _ = obter_deck_builder(request)
    deck = next((d for d in listar_decks(banco) if d["id"] == deck_id), None)
    if deck is None:
        raise HTTPException(404, "Esse deck não existe mais.")
    cartas = cartas_dos_decks(banco).get(deck_id, [])
    return DeckEmFoco(deck["nome"], [(l["secao"], l["carta"], l["quantidade"]) for l in cartas])


def rotas_juiz():
    from fastapi import APIRouter

    r = APIRouter(prefix="/api")

    @r.get("/saude")
    def saude(request: Request):
        """Pra plataforma saber que a API está no ar (e acordar o servidor, no plano grátis)."""
        return {"ok": True, "juiz_pronto": request.app.state.juiz.carregado,
                "decks_prontos": request.app.state.deck_builder.carregado}

    @r.get("/info")
    def info(request: Request, eh_dono: bool = Depends(dono)):
        publico = modo_publico()
        convidados: Convidados = request.app.state.convidados
        ip = ip_de(request)
        return {
            "publico": publico, "dono": eh_dono, "fontes": procedencia(), "exemplos": EXEMPLOS,
            "privacidade": PRIVACIDADE, "creditos": CREDITOS.strip(),
            "convidado": None if eh_dono else {"restantes": convidados.restantes(ip),
                                                "limite": convidados.por_visitante.limite,
                                                "bloqueio": convidados.motivo_do_bloqueio(ip)},
            "avaliacao": not publico,  # 👍/👎 só vai pro registro local, que fica desligado quando publicado
            "turso": turso_configurado(), "topdeck": bool(meta.chave_topdeck()),
        }

    @r.post("/entrar")
    def entrar(dados: Senha, request: Request):
        if not modo_publico():
            return {"token": None}  # rodando no seu computador: não precisa de senha
        tentativas: TentativasDeSenha = request.app.state.tentativas
        ip = ip_de(request)
        if tentativas.bloqueado(ip):
            raise HTTPException(429, "Tentativas esgotadas. Tente de novo daqui a uma hora.")
        if not senha_confere(dados.senha):
            tentativas.errou(ip)
            raise HTTPException(401, "Senha incorreta.")
        return {"token": criar_token()}

    @r.post("/perguntar")
    def perguntar(dados: Pergunta, request: Request, eh_dono: bool = Depends(dono)):
        publico, ip = modo_publico(), ip_de(request)
        convidados: Convidados = request.app.state.convidados
        reservou = False
        if not eh_dono:
            reservou = convidados.reservar(ip)
            if not reservou:
                raise HTTPException(429, convidados.motivo_do_bloqueio(ip) or "Limite de perguntas atingido.")
        try:
            deck = deck_em_foco(request, dados.deck_id)
            juiz = request.app.state.juiz.obter()
            resposta = juiz.responder(dados.pergunta, historico=list(dados.historico), plano_b=True, deck=deck)
        except Exception as erro:
            if reservou:
                convidados.devolver(ip)
            if isinstance(erro, HTTPException):
                raise
            traceback.print_exc()  # o detalhe completo vai pro log do servidor
            if not publico:
                registrar_erro(dados.pergunta, erro)
            if isinstance(erro, CotaEsgotada):
                raise HTTPException(503, f"{CotaEsgotada.MENSAGEM} Até lá, o juiz não consegue responder.") from None
            raise HTTPException(502, f"Não consegui responder agora ({explicar_erro(erro)}). "
                                     "Tente de novo em alguns instantes.") from None
        if resposta.sem_llm and reservou:  # plano B: não gastou o LLM, então não conta no limite
            convidados.devolver(ip)
        id_ = uuid.uuid4().hex[:8]
        if not publico:
            registrar_resposta(id_, resposta)
        versao = procedencia()["crd_versao"] or "1.4"
        return {
            "id": id_,
            # Markdown com as citações já como <sup><a>; o texto do LLM passou por html.escape antes.
            "html": linkar_citacoes(resposta.texto, resposta.fontes, resposta.regras, versao),
            "original": resposta.texto,  # sem links: é o que volta como histórico nas próximas perguntas
            "tipo": resposta.tipo, "encontrou": resposta.encontrou, "sem_llm": resposta.sem_llm,
            "fontes": [fonte_json(f, com_trecho=bool(resposta.sem_llm)) for f in resposta.fontes],
            "nota": resposta.nota_busca, "uso": resposta.uso, "termos": resposta.termos,
            "busca": resposta.modelo_busca,
            "busca_reserva": bool(resposta.modelo_busca and resposta.modelo_busca != config.MODELO_EMBEDDINGS),
            "deck": deck.nome if deck else None,
            "restantes": None if eh_dono else convidados.restantes(ip),
        }

    @r.post("/avaliar")
    def avaliar(dados: Avaliacao):
        if modo_publico():  # publicado, o registro local fica desligado (privacidade)
            raise HTTPException(404, "A avaliação só funciona rodando no seu computador.")
        registrar_avaliacao(dados.id, dados.gostou)
        return {"ok": True}

    return r


# ---------------------------------------------------------------------------
# Deck builder
# ---------------------------------------------------------------------------

def obter_fichario(request: Request):
    """As fichas usam o catálogo, o FAQ e o LLM do juiz: uma por juiz carregado (ele é recarregado 1x por dia)."""
    try:
        juiz = request.app.state.juiz.obter()
    except Exception as erro:
        traceback.print_exc()
        raise HTTPException(503, f"O juiz ainda não está pronto ({explicar_erro(erro)}). Tente de novo em instantes.") from None
    if getattr(juiz, "fichario", None) is None:
        juiz.fichario = Fichario.do_juiz(juiz)
    return juiz.fichario


class MudancasNaColecao(BaseModel):
    mudancas: dict[str, int] = Field(max_length=2000)  # carta -> quantidade (0 tira da coleção)


class CsvDaColecao(BaseModel):
    texto: str = Field(max_length=2_000_000)
    substituir: bool = False


class ListaDoDeck(BaseModel):
    texto: str = Field(max_length=20_000)


class NovoDeck(ListaDoDeck):
    nome: str = Field(default="", max_length=120)
    url: str = Field(default="", max_length=500)
    ignorar_desconhecidas: bool = False


def json_da_lista(lista, catalogo) -> dict:
    return {
        "cartas": [{"secao": secao, "secao_nome": NOMES_DAS_SECOES.get(secao, secao), "carta": carta, "quantidade": qtd,
                    "imagem": catalogo.imagem_de(carta)} for (secao, carta), qtd in lista.cartas.items()],
        "nao_reconhecidas": [{"texto": t, "sugestoes": s} for t, s in lista.nao_reconhecidas],
        "avisos": lista.avisos,
    }


def rotas_decks():
    from fastapi import APIRouter

    r = APIRouter(prefix="/api")

    @r.get("/cartas")
    def cartas(request: Request):
        """O catálogo inteiro (~940 cartas), com a imagem da galeria oficial quando houver."""
        _, catalogo = obter_deck_builder(request)
        return [{"nome": c.nome, "tipo": c.tipo_principal, "tipos": c.tipos.split(), "supertipos": c.supertipos.split(),
                 "dominios": [d for d in c.dominios.split(", ") if d], "tags": [t for t in c.tags.split(", ") if t],
                 "energia": c.custo_energia, "poder": c.custo_poder, "might": c.might,
                 "codigo": catalogo.codigo_de(c.nome), "imagem": catalogo.imagem_de(c.nome)}
                for c in catalogo.cartas.values()]

    @r.get("/carta")
    def ficha_da_carta(nome: str, request: Request):
        """Texto oficial e dúvidas do FAQ sobre a carta. Não chama nenhum LLM."""
        banco, catalogo = obter_deck_builder(request)
        fichario = obter_fichario(request)
        f = fichario.ficha(nome)
        return {
            "nome": f.nome, "texto": f.texto, "atributos": f.atributos, "errata": f.errata, "url_wiki": f.url_wiki,
            "imagem": catalogo.imagem_de(nome),
            "duvidas": [{"pergunta": d.pergunta, "url": d.url, "pagina": d.pagina} for d in f.duvidas],
            "mecanicas": [{"pagina": d.pagina, "url": d.url} for d in f.mecanicas],
        }

    @r.get("/colecao")
    def ver_colecao(request: Request):
        banco, _ = obter_deck_builder(request)
        tenho = colecao.listar(banco)
        return {"cartas": tenho, "diferentes": len(tenho), "copias": sum(tenho.values())}

    @r.put("/colecao", dependencies=[Depends(so_o_dono)])
    def mudar_colecao(dados: MudancasNaColecao, request: Request):
        banco, catalogo = obter_deck_builder(request)
        desconhecidas = [c for c in dados.mudancas if c not in catalogo]
        if desconhecidas:
            raise HTTPException(400, f"Cartas desconhecidas: {', '.join(desconhecidas[:5])}")
        if any(not 0 <= q <= 99 for q in dados.mudancas.values()):
            raise HTTPException(400, "A quantidade vai de 0 a 99.")
        colecao.salvar_alteracoes(banco, dados.mudancas)
        return ver_colecao(request)

    @r.post("/colecao/importar", dependencies=[Depends(so_o_dono)])
    def importar_colecao(dados: CsvDaColecao, request: Request):
        banco, catalogo = obter_deck_builder(request)
        relatorio = colecao.importar_csv(banco, catalogo, dados.texto.lstrip("﻿"), substituir=dados.substituir)
        return {"importadas": len(relatorio.importadas), "copias": sum(relatorio.importadas.values()),
                "desconhecidas": [{"texto": t, "sugestoes": s} for t, s in relatorio.desconhecidas],
                "invalidas": len(relatorio.invalidas), "substituiu": dados.substituir}

    @r.get("/colecao/exportar", response_class=PlainTextResponse)
    def exportar_colecao(request: Request):
        banco, _ = obter_deck_builder(request)
        return PlainTextResponse(colecao.exportar_csv(banco), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": 'attachment; filename="colecao_riftbound.csv"'})

    @r.get("/decks")
    def ver_decks(request: Request, tipo: str = Query("meus", pattern="^(meus|meta)$"),
                  ordem: str = Query("barato", pattern="^(barato|faltando)$"), sideboard: bool = False,
                  runas: bool = True, lenda: str | None = None, limite: int = Query(MAX_DECKS_POR_PAGINA, ge=1, le=500)):
        """Meus decks (tipo=meus) ou os do meta (tipo=meta), na ordem escolhida: mais barato de completar
        (ordem=barato) ou menos cartas faltando (ordem=faltando). Sem preços guardados, vale "faltando"."""
        banco, catalogo = obter_deck_builder(request)
        ranking = conclusao.ranking(banco, incluir_sideboard=sideboard, runas_garantidas=runas)
        do_tipo = [c for c in ranking if (c.deck["origem"] == meta.ORIGEM) == (tipo == "meta")]
        listas = cartas_dos_decks(banco) if do_tipo else {}
        lendas = lendas_dos_decks(listas)
        precos_usd = precos.precos_guardados(banco) if do_tipo else {}
        ordem = ordem if precos_usd else "faltando"
        ordenados = conclusao.mais_baratos(do_tipo, precos_usd) if ordem == "barato" else conclusao.menos_faltando(do_tipo)
        contagem: dict[str, int] = {}
        for c in do_tipo:
            if lendas.get(c.deck["id"]):
                contagem[lendas[c.deck["id"]]] = contagem.get(lendas[c.deck["id"]], 0) + 1
        filtrados = [c for c in ordenados if not lenda or lendas.get(c.deck["id"]) == lenda]
        ultima = meta.ultima_coleta(banco) if tipo == "meta" else None
        return {
            "decks": [resumo_do_deck(c, lendas.get(c.deck["id"]), catalogo, precos_usd) for c in filtrados[:limite]],
            "total": len(filtrados), "ordem": ordem, "tem_precos": bool(precos_usd),
            "lendas": [{**json_da_lenda(l, catalogo), "decks": n}
                       for l, n in sorted(contagem.items(), key=lambda par: (-par[1], par[0]))],
            "meta": {"ultima_coleta": ultima.isoformat() if ultima else None, "chave": bool(meta.chave_topdeck()),
                     "dias": config.META_DIAS, "atualizar_a_cada_dias": config.META_ATUALIZAR_A_CADA_DIAS}
            if tipo == "meta" else None,
        }

    @r.get("/decks/{deck_id}")
    def ver_deck(deck_id: str, request: Request, sideboard: bool = False, runas: bool = True):
        banco, catalogo = obter_deck_builder(request)
        deck = next((d for d in listar_decks(banco) if d["id"] == deck_id), None)
        if deck is None:
            raise HTTPException(404, "Deck não encontrado.")
        c = conclusao.calcular(banco, deck, incluir_sideboard=sideboard, runas_garantidas=runas)
        cartas = cartas_dos_decks(banco).get(deck_id, [])
        lenda = next((l["carta"] for l in cartas if l["secao"] == "lenda"), None)
        precos_usd = precos.precos_guardados(banco)
        por_carta = {x.carta: x for x in c.cartas}
        faltando = [(x.carta, x.falta) for x in c.faltando]
        ordem_das_secoes = list(NOMES_DAS_SECOES)
        return {
            **resumo_do_deck(c, lenda, catalogo, precos_usd),
            "cartas": [{"secao": l["secao"], "secao_nome": NOMES_DAS_SECOES.get(l["secao"], l["secao"]),
                        "carta": l["carta"], "quantidade": l["quantidade"],
                        "tem": por_carta[l["carta"]].tem if l["carta"] in por_carta else None,
                        "imagem": catalogo.imagem_de(l["carta"])}
                       for l in sorted(cartas, key=lambda l: (ordem_das_secoes.index(l["secao"])
                                                              if l["secao"] in ordem_das_secoes else 99, l["carta"]))],
            "faltando": [{"carta": x.carta, "precisa": x.precisa, "tem": x.tem, "falta": x.falta,
                          "imagem": catalogo.imagem_de(x.carta), "liga": link_da_carta(x.carta, catalogo)}
                         for x in c.faltando],
            "lista_de_compra": lista_de_compra(faltando, catalogo),
            "compra_por_lista": config.LIGA_COMPRA_POR_LISTA,
            "legenda_dos_precos": legenda_dos_precos(precos.data_dos_precos(banco)) if precos_usd else None,
        }

    @r.post("/decks/previa")
    def previa(dados: ListaDoDeck, request: Request):
        """Lê a lista sem salvar: mostra o que foi reconhecido, o que não foi (com sugestões) e os avisos."""
        _, catalogo = obter_deck_builder(request)
        return json_da_lista(ler_lista(dados.texto, catalogo), catalogo)

    @r.post("/decks", dependencies=[Depends(so_o_dono)])
    def novo_deck(dados: NovoDeck, request: Request):
        banco, catalogo = obter_deck_builder(request)
        lista = ler_lista(dados.texto, catalogo)
        if lista.nao_reconhecidas and not dados.ignorar_desconhecidas:
            raise HTTPException(400, "Não reconheci estas cartas: " + "; ".join(
                f"\"{t}\"" + (f" (quis dizer {' / '.join(s)}?)" if s else "") for t, s in lista.nao_reconhecidas)
                + ". Corrija a lista ou marque a opção de salvar sem elas.")
        if not lista.cartas:
            raise HTTPException(400, "A lista não tem nenhuma carta reconhecida.")
        id_ = salvar_deck(banco, dados.nome, lista, url=dados.url.strip())
        return {"id": id_, "avisos": lista.avisos}

    @r.delete("/decks/{deck_id}", dependencies=[Depends(so_o_dono)])
    def apagar(deck_id: str, request: Request):
        banco, _ = obter_deck_builder(request)
        deck = next((d for d in listar_decks(banco) if d["id"] == deck_id), None)
        if deck is None:
            raise HTTPException(404, "Deck não encontrado.")
        if deck["origem"] == meta.ORIGEM:
            raise HTTPException(400, "Os decks do meta são trocados sozinhos a cada coleta; não dá pra apagar um.")
        apagar_deck(banco, deck_id)
        return {"ok": True}

    @r.post("/meta/atualizar", dependencies=[Depends(so_o_dono)])
    def atualizar_meta(request: Request):
        banco, catalogo = obter_deck_builder(request)
        if not meta.chave_topdeck():
            raise HTTPException(400, "Falta a TOPDECK_API_KEY (uma chave grátis da sua conta no TopDeck.gg) "
                                     "nos secrets da API.")
        try:
            relatorio = meta.atualizar_meta(banco, catalogo, meta.chave_topdeck())
        except Exception as erro:
            traceback.print_exc()
            raise HTTPException(502, f"Não consegui atualizar os decks do meta ({explicar_erro(erro)}).") from None
        return {"resumo": meta.resumo(relatorio),
                "desconhecidas": [n for n, _ in relatorio.desconhecidas.most_common(10)]}

    return r


app = criar_app()

"""Ficha da carta (fase 3): o texto oficial, as dúvidas do FAQ sobre ela e uma explicação com exemplos.

É o que aparece quando se toca numa carta no site.
- Texto oficial: o do catálogo do FAQ, com a errata aplicada (juiz/cartas.py).
- Dúvidas: as perguntas do FAQ sobre a carta (a página dela e as que a citam) e as páginas das mecânicas
  que aparecem no texto ("[Ambush]" leva à página Ambush). Não gasta nada: é só procurar nos trechos.
- Explicação: escrita pelo LLM a partir do texto, das definições oficiais e das dúvidas do FAQ, citando
  as fontes ([F1]). Custa uma chamada ao LLM, e o resultado fica guardado no banco (decks/banco.py,
  tabela explicacoes): cada carta gasta a cota uma vez só, até o texto dela ou as dúvidas do FAQ
  mudarem (a assinatura muda e a explicação é refeita). São geradas de antemão, no seu computador, por
  um LLM local (python -m api.gerar_explicacoes, com o Ollama): o site não gasta o Gemini com elas.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field

from juiz import config
from juiz.cartas import url_da_carta
from juiz.responder import Fonte

VERSAO_DA_EXPLICACAO = "1"  # mude se as instruções mudarem: as explicações guardadas são refeitas
MAX_DUVIDAS = 8

INSTRUCOES_DA_FICHA = """\
Você é o Juiz Riftbound, explicando UMA carta do Riftbound TCG (o card game de League of Legends) para jogadores brasileiros, muitos deles iniciantes.

Escreva em português do Brasil, como um amigo experiente explicando na mesa: frases curtas, voz ativa, sem juridiquês.
Mantenha em inglês os nomes de cartas, palavras-chave, zonas e fases, exatamente como nas fontes (Stun, Deathknell, Showdown, Might, Chain, Battlefield, Trash). Na primeira vez que usar um termo técnico, explique em poucas palavras, usando SÓ as DEFINIÇÕES OFICIAIS e as FONTES da mensagem.

Use exatamente estas seções, em Markdown:
**O que a carta faz** — 2 a 4 frases, em linguagem simples, cobrindo todo o texto da carta (inclusive custo e palavras-chave).
**Exemplos** — 2 exemplos curtos e concretos de jogada, numa lista. Use só o que a carta e as fontes dizem; não invente interações com outras cartas.
**Cuidados e exceções** — uma lista com os pontos que costumam confundir, cada um citando a fonte no fim da frase, como [F1] ou [F1, F2]. Se as fontes não trazem nenhuma dúvida sobre a carta, escreva uma linha dizendo que o FAQ ainda não tem dúvidas registradas sobre ela e não invente nenhuma.

Nunca invente regras. Se algo não estiver no texto da carta nem nas fontes, não afirme.
"""


@dataclass
class Duvida:
    pergunta: str
    url: str
    pagina: str
    trecho_id: str


@dataclass
class Ficha:
    nome: str
    texto: str | None  # habilidades e efeitos, em inglês, como na carta
    atributos: dict = field(default_factory=dict)
    errata: bool = False
    url_wiki: str | None = None
    duvidas: list[Duvida] = field(default_factory=list)  # perguntas do FAQ sobre a carta
    mecanicas: list[Duvida] = field(default_factory=list)  # páginas das mecânicas do texto


@dataclass
class Explicacao:
    texto: str  # Markdown com [Fn]
    fontes: list[Fonte]
    assinatura: str


# --- explicações guardadas (tabela explicacoes do banco do deck builder: decks/banco.py) ---

def explicacao_guardada(banco, nome: str, assinatura: str) -> dict | None:
    """{"texto", "fontes"} da explicação guardada, se ela ainda vale (mesma assinatura)."""
    linha = banco.consultar("SELECT texto, fontes FROM explicacoes WHERE carta = ? AND assinatura = ?", (nome, assinatura))
    return {"texto": linha[0]["texto"], "fontes": json.loads(linha[0]["fontes"])} if linha else None


def fontes_pra_guardar(explicacao: "Explicacao") -> list[dict]:
    campos = ("numero", "tipo", "titulo", "url", "texto", "citacao_pendente", "citada", "resumo")
    return [{c: getattr(f, c) for c in campos} for f in explicacao.fontes]


def guardar_explicacao(banco, nome: str, explicacao: "Explicacao") -> dict:
    fontes = fontes_pra_guardar(explicacao)
    banco.executar("INSERT OR REPLACE INTO explicacoes (carta, assinatura, texto, fontes, criado_em) "
                   "VALUES (?, ?, ?, ?, datetime('now'))",
                   (nome, explicacao.assinatura, explicacao.texto, json.dumps(fontes, ensure_ascii=False)))
    return {"texto": explicacao.texto, "fontes": fontes}


def _palavras_chave(texto: str) -> list[str]:
    """ "[Assault 2] ... [Ambush]" -> ["assault", "ambush"] (sem números, em minúsculas)."""
    return list(dict.fromkeys(re.sub(r"\s*\d+$", "", m).strip().lower() for m in re.findall(r"\[([^\]]+)\]", texto)))


class Fichario:
    """Monta as fichas a partir do catálogo de cartas do juiz e dos trechos do FAQ."""

    def __init__(self, catalogo, trechos_faq: list[dict], llm, definicoes=None):
        self.catalogo = catalogo  # juiz.cartas.Catalogo
        self.trechos = [t for t in trechos_faq if t.get("fonte", "faq") == "faq" and t.get("pergunta")]
        self.llm = llm
        self.definicoes = definicoes or (lambda textos: [])  # Juiz.definicoes_relevantes

    @classmethod
    def do_juiz(cls, juiz) -> "Fichario":
        caminho = config.PROCESSED_DIR / "faq_trechos.jsonl"
        trechos = [json.loads(l) for l in caminho.open(encoding="utf-8")] if caminho.exists() else []
        # Sem LLM: na API, a ficha só mostra as explicações já geradas (o LLM local entra no gerar_explicacoes).
        return cls(juiz.catalogo, trechos, None, lambda textos: juiz.definicoes_relevantes(textos, []))

    def _trechos_da_carta(self, nome: str, texto: str) -> tuple[list[dict], list[dict]]:
        da_carta = [t for t in self.trechos if t.get("carta") == nome]
        citada = [t for t in self.trechos if nome in (t.get("cartas_mencionadas") or []) and t not in da_carta]
        chaves = set(_palavras_chave(texto))
        mecanicas = [t for t in self.trechos if t.get("categoria") == "mechanics" and t.get("pagina", "").lower() in chaves]
        return (da_carta + citada)[:MAX_DUVIDAS], mecanicas

    def ficha(self, nome: str) -> Ficha:
        carta = self.catalogo.cartas.get(nome)
        if carta is None:  # runa básica ou carta fora do catálogo do FAQ
            return Ficha(nome, None)
        texto = "\n".join(filter(None, [carta.get("abilities"), carta.get("effects")])) or None
        duvidas, mecanicas = self._trechos_da_carta(nome, texto or "")
        paginas_de_mecanica = {}
        for t in mecanicas:  # uma entrada por página (a página inteira, sem a âncora da pergunta)
            paginas_de_mecanica.setdefault(t["pagina"], Duvida(t["pagina"], t["url"].split("#")[0], t["pagina"], t["id"]))
        atributos = {"tipos": carta["superTypes"] + carta["cardTypes"], "dominios": carta["domains"],
                     "energia": carta["energyCost"], "poder": carta["powerCost"], "might": carta["might"],
                     "tags": carta["tags"]}
        return Ficha(nome, texto, atributos, bool(carta.get("errata")), url_da_carta(nome),
                     [Duvida(t["pergunta"], t["url"], t["pagina"], t["id"]) for t in duvidas],
                     list(paginas_de_mecanica.values()))

    def _fontes(self, nome: str) -> list[Fonte]:
        carta = self.catalogo.cartas[nome]
        texto = "\n".join(filter(None, [carta.get("abilities"), carta.get("effects")]))
        duvidas, mecanicas = self._trechos_da_carta(nome, texto)
        fontes = [Fonte(1, "carta", f"Texto oficial da carta {nome}", url_da_carta(nome), self.catalogo.texto(nome),
                        resumo=nome, trecho_id=f"carta/{nome}")]
        for t in duvidas + mecanicas[:3]:
            fontes.append(Fonte(len(fontes) + 1, "faq", f'FAQ não oficial, página "{t["pagina"]}": {t["pergunta"]}',
                                t["url"], t.get("texto_com_regras") or t["texto"],
                                citacao_pendente=bool(t.get("citacao_pendente")),
                                resumo=f'{t["pagina"]} — {t["pergunta"]}', trecho_id=t["id"]))
        return fontes

    def assinatura(self, nome: str) -> str:
        """Muda quando o texto da carta, as dúvidas do FAQ ou as instruções mudam."""
        fontes = self._fontes(nome)
        conteudo = json.dumps([VERSAO_DA_EXPLICACAO, INSTRUCOES_DA_FICHA] + [f.texto for f in fontes], ensure_ascii=False)
        return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:16]

    def explicar(self, nome: str) -> Explicacao:
        if nome not in self.catalogo.cartas:
            raise KeyError(nome)
        fontes = self._fontes(nome)
        definicoes = self.definicoes([f.texto for f in fontes[:1]])
        partes = [f"CARTA: {nome}", ""]
        if definicoes:
            partes.append("DEFINIÇÕES OFICIAIS DOS TERMOS TÉCNICOS (use estas pra explicar os termos; não invente outras)")
            partes += [f"- {rotulo}: {texto}" for rotulo, texto in definicoes] + [""]
        partes.append("FONTES")
        for f in fontes:
            partes.append(f"[F{f.numero}] {f.titulo}")
            if f.citacao_pendente:
                partes.append("CITAÇÃO PENDENTE: o próprio FAQ avisa que o CRD ainda não sustenta esta resposta por completo.")
            partes += [f.texto, ""]
        if self.llm is None:
            raise RuntimeError("sem LLM pra explicar cartas: use python -m api.gerar_explicacoes")
        texto = self.llm.gerar(INSTRUCOES_DA_FICHA, "\n".join(partes).strip())
        citadas = {int(n) for n in re.findall(r"F(\d{1,2})", texto)}
        for f in fontes:
            f.citada = f.numero in citadas
        return Explicacao(texto, fontes, self.assinatura(nome))

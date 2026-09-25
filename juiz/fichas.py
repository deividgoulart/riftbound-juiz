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

VERSAO_DA_EXPLICACAO = "3"  # mude se as instruções mudarem: as explicações guardadas são refeitas
MAX_DUVIDAS = 8
TENTATIVAS = 3  # a explicação que não passa na conferência volta pro LLM com os problemas apontados

INSTRUCOES_DA_FICHA = """\
Você é o Juiz Riftbound, explicando UMA carta do Riftbound TCG (o card game de League of Legends) para jogadores brasileiros, muitos deles iniciantes.

LINGUAGEM
- Português do Brasil, como um amigo experiente explicando na mesa: frases curtas, voz ativa, sem juridiquês.
- NUNCA traduza os termos do jogo. Escreva exatamente assim, em inglês: Spell, Gear, Unit (ou "unidade"), Battlefield, Base, Trash, Main Deck, Rune, Legend, Champion, Might, Energy, Power, Chain, Showdown, Buff, Stun, Recycle, Counter, e os domínios Fury, Calm, Mind, Body, Chaos e Order.
- Palavras PROIBIDAS (são traduções erradas ou termos de outros jogos): feitiço, unitário, lixo, cemitério, item, equipamento, campo de batalha, Força, mana, banimento, lacaio, criatura, Caos, Fúria.
- Os verbos ficam em português: "a unidade morre", "você compra uma carta".

O QUE ESCREVER (Markdown, com os títulos em negrito, cada um sozinho numa linha)
**O que a carta faz**
2 a 4 frases simples que dizem o que o TEXTO OFICIAL da carta [F1] faz, sem acrescentar nada que não esteja nele.

**Exemplos**
Uma lista com 2 jogadas curtas usando SÓ esta carta e o que o texto dela diz. Não cite nenhuma outra carta pelo nome.
{secao_de_cuidados}
REGRAS
- Nunca invente regras, números, efeitos ou interações. Se não está no texto da carta nem nas fontes, não escreva.
- Cite a fonte no fim da frase, só com o número: [F1] ou [F2, F3]. Nunca cite uma fonte que não está na mensagem.
- Números entre colchetes no texto da carta, como [2] ou [Fury], são custos, não fontes.
"""

CUIDADOS_COM_FAQ = """
**Cuidados e exceções**
Uma lista com um item para cada pergunta do FAQ (as fontes F2 em diante): diga em 1 frase, em português, o que o FAQ responde, e termine com a fonte, ex.: [F2]. Não escreva itens que não venham de uma dessas fontes.
"""
SEM_CUIDADOS = """
Não escreva a seção de cuidados e exceções: o FAQ não tem dúvidas sobre esta carta.
"""

# Traduções que o LLM local costuma fazer (e o juiz não aceita): "feitiço" no lugar de Spell etc.
TERMOS_PROIBIDOS = re.compile(
    r"\b(feiti[çc]os?|unit[áa]rios?|lixo|cemit[ée]rio|itens|item|equipamentos?|campos? de batalha|for[çc]a|mana|"
    r"banimento|lacaios?|criaturas?|caos|f[úu]ria)\b", re.IGNORECASE)


# Termos do jogo que também são nomes de carta ("Buff", "Stun"...): não contam como "citou outra carta".
TERMOS_DO_JOGO = {"spell", "gear", "unit", "battlefield", "base", "trash", "main deck", "rune", "legend", "champion",
                  "might", "energy", "power", "chain", "showdown", "buff", "stun", "recycle", "counter"}


# Traduções que dá pra consertar sem pedir outra explicação ao LLM: sempre viram o mesmo termo do jogo.
# ("item", "mana" e "banimento" ficam de fora: não dá pra saber o termo certo, então o LLM reescreve.)
TROCAS = [
    (r"\bfeiti[çc]os\b", "Spells"), (r"\bfeiti[çc]o\b", "Spell"),
    # "unitário" é masculino e "unidade", feminino: os artigos mais comuns mudam junto
    *[(rf"\b{m}\s+unit[áa]rios?\b", f) for m, f in [("um", "uma unidade"), ("o", "a unidade"), ("os", "as unidades"),
                                                       ("do", "da unidade"), ("no", "na unidade"), ("ao", "à unidade"),
                                                       ("seu", "sua unidade"), ("seus", "suas unidades"),
                                                       ("este", "esta unidade"), ("esse", "essa unidade")]],
    (r"\bunit[áa]rios\b", "unidades"), (r"\bunit[áa]rio\b", "unidade"),
    (r"\b(?:lixo|cemit[ée]rio)\b", "Trash"),
    (r"\bcampos de batalha\b", "Battlefields"), (r"\bcampo de batalha\b", "Battlefield"),
    (r"\bequipamentos\b", "Gear"), (r"\bequipamento\b", "Gear"),
    (r"\b(?:deck|baralho) principal\b", "Main Deck"),
    (r"\bFor[çc]a\b", "Might"), (r"\bCaos\b", "Chaos"), (r"\bF[úu]ria\b", "Fury"),
]
# Os títulos das seções, em qualquer formato que o LLM escreva ("### Exemplos", "**Cuidados e Exceções:**").
TITULOS = {"O que a carta faz": r"o que a carta faz", "Exemplos": r"exemplos?",
           "Cuidados e exceções": r"cuidados e exce[çc][õo]es"}


def ajustar(texto: str) -> str:
    """Conserta o que tem conserto certo: títulos das seções no formato padrão e traduções diretas."""
    for titulo, padrao in TITULOS.items():
        texto = re.sub(rf"(?im)^[ \t]*(?:#+[ \t]*)?(?:\*\*)?[ \t]*{padrao}[ \t]*:?[ \t]*(?:\*\*)?[ \t]*:?[ \t]*$",
                       f"**{titulo}**", texto)
    for padrao, termo in TROCAS:
        texto = re.sub(padrao, termo, texto, flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"(?m)^[ \t]*-{3,}[ \t]*$", "", texto)).strip()  # tira as linhas "---"


class ExplicacaoRuim(RuntimeError):
    """O LLM não fez uma explicação aceitável, nem depois de ser corrigido."""


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
        conteudo = json.dumps([VERSAO_DA_EXPLICACAO, INSTRUCOES_DA_FICHA, CUIDADOS_COM_FAQ] + [f.texto for f in fontes], ensure_ascii=False)
        return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:16]

    def problemas(self, nome: str, texto: str, fontes: list[Fonte]) -> list[str]:
        """O que está errado na explicação, pra pedir outra ao LLM. Vazio: pode guardar."""
        problemas = []
        proibidos = sorted({m.group(0).lower() for m in TERMOS_PROIBIDOS.finditer(texto)})
        if proibidos:
            problemas.append("usou palavras proibidas (traduza nada; use os termos em inglês): " + ", ".join(proibidos))
        numeros = {f.numero for f in fontes}
        inexistentes = sorted({int(n) for n in re.findall(r"\bF(\d{1,2})\b", texto)} - numeros)
        if inexistentes:
            problemas.append("citou fontes que não existem: " + ", ".join(f"F{n}" for n in inexistentes))
        outras = [c for c in self.catalogo.encontrar(texto)
                  if c != nome and c.lower() not in TERMOS_DO_JOGO and not any(c in f.texto for f in fontes)]
        if outras:
            problemas.append("citou outras cartas, que não estão nas fontes: " + ", ".join(outras[:5]))
        tem_faq = len(fontes) > 1
        cuidados = texto.split("**Cuidados e exceções**", 1)[1] if "**Cuidados e exceções**" in texto else ""
        if tem_faq:
            itens = [l for l in cuidados.splitlines() if re.match(r"\s*(?:[-•]|\*(?!\*)|\d+\.)\s", l)]
            if not itens:
                problemas.append("faltou a seção **Cuidados e exceções**, com um item por pergunta do FAQ")
            sem_faq = [l.strip() for l in itens if not re.search(r"\bF(?:[2-9]|\d{2})\b", l)]
            if sem_faq:
                problemas.append("estes cuidados não citam nenhuma pergunta do FAQ (F2 em diante); tire-os ou cite a "
                                 "fonte certa: " + " | ".join(sem_faq[:3]))
            if re.search(r"n[ãa]o tem (nenhuma )?d[úu]vidas", texto, re.IGNORECASE):
                problemas.append("disse que o FAQ não tem dúvidas, mas as fontes F2 em diante são dúvidas do FAQ")
        elif cuidados:
            problemas.append("escreveu a seção de cuidados, mas o FAQ não tem dúvidas sobre esta carta: tire a seção")
        for secao in ("O que a carta faz", "Exemplos"):
            if f"**{secao}**" not in texto:
                problemas.append(f"faltou a seção **{secao}**")
        return problemas

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
        instrucoes = INSTRUCOES_DA_FICHA.format(secao_de_cuidados=CUIDADOS_COM_FAQ if len(fontes) > 1 else SEM_CUIDADOS)
        mensagem = "\n".join(partes).strip()
        for tentativa in range(1, TENTATIVAS + 1):
            texto = ajustar(self.llm.gerar(instrucoes, mensagem))
            problemas = self.problemas(nome, texto, fontes)
            if not problemas:
                break
            if tentativa == TENTATIVAS:
                raise ExplicacaoRuim("; ".join(problemas))
            # Sem a versão errada na mensagem: com ela, o modelo respondia com uma lista de conferência
            # ("Spell: correct") em vez de reescrever.
            mensagem = ("\n".join(partes).strip() + "\n\nATENÇÃO: uma versão anterior da sua explicação foi recusada por "
                        "estes motivos:\n" + "\n".join(f"- {p}" for p in problemas)
                        + "\n\nEscreva a explicação INTEIRA de novo, do começo, só com as seções pedidas e sem "
                        "comentar os erros nem fazer listas de conferência.")
        citadas = {int(n) for n in re.findall(r"F(\d{1,2})", texto)}
        for f in fontes:
            f.citada = f.numero in citadas
        return Explicacao(texto, fontes, self.assinatura(nome))

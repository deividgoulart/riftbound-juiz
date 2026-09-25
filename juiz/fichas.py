"""Ficha da carta (fase 3): o texto oficial e as dúvidas do FAQ sobre ela.

É o que aparece quando se toca numa carta no site.
- Texto oficial: o do catálogo do FAQ, com a errata aplicada (juiz/cartas.py).
- Dúvidas: as perguntas do FAQ sobre a carta (a página dela e as que a citam) e as páginas das mecânicas
  que aparecem no texto ("[Ambush]" leva à página Ambush). Não gasta nada: é só procurar nos trechos.
Pra uma dúvida que o FAQ não cobre, a ficha tem um atalho que abre o juiz com a pergunta sobre a carta.

(Uma explicação "como usar" escrita por IA foi testada e abandonada: os modelos que rodam de graça no
computador traduziam os termos do jogo e inventavam regras, e o Gemini fica reservado pro juiz.)
"""

import json
import re
from dataclasses import dataclass, field

from juiz import config
from juiz.cartas import url_da_carta

MAX_DUVIDAS = 8


@dataclass
class Duvida:
    pergunta: str
    url: str
    pagina: str


@dataclass
class Ficha:
    nome: str
    texto: str | None  # habilidades e efeitos, em inglês, como na carta
    atributos: dict = field(default_factory=dict)
    errata: bool = False
    url_wiki: str | None = None
    duvidas: list[Duvida] = field(default_factory=list)  # perguntas do FAQ sobre a carta
    mecanicas: list[Duvida] = field(default_factory=list)  # páginas das mecânicas do texto


def _palavras_chave(texto: str) -> list[str]:
    """ "[Assault 2] ... [Ambush]" -> ["assault", "ambush"] (sem números, em minúsculas)."""
    return list(dict.fromkeys(re.sub(r"\s*\d+$", "", m).strip().lower() for m in re.findall(r"\[([^\]]+)\]", texto)))


class Fichario:
    """Monta as fichas a partir do catálogo de cartas do juiz e dos trechos do FAQ."""

    def __init__(self, catalogo, trechos_faq: list[dict]):
        self.catalogo = catalogo  # juiz.cartas.Catalogo
        self.trechos = [t for t in trechos_faq if t.get("fonte", "faq") == "faq" and t.get("pergunta")]

    @classmethod
    def do_juiz(cls, juiz) -> "Fichario":
        caminho = config.PROCESSED_DIR / "faq_trechos.jsonl"
        trechos = [json.loads(l) for l in caminho.open(encoding="utf-8")] if caminho.exists() else []
        return cls(juiz.catalogo, trechos)

    def ficha(self, nome: str) -> Ficha:
        carta = self.catalogo.cartas.get(nome)
        if carta is None:  # runa básica ou carta fora do catálogo do FAQ
            return Ficha(nome, None)
        texto = "\n".join(filter(None, [carta.get("abilities"), carta.get("effects")])) or None
        da_carta = [t for t in self.trechos if t.get("carta") == nome]
        citada = [t for t in self.trechos if nome in (t.get("cartas_mencionadas") or []) and t not in da_carta]
        chaves = set(_palavras_chave(texto or ""))
        paginas_de_mecanica: dict[str, Duvida] = {}
        for t in self.trechos:  # uma entrada por página (a página inteira, sem a âncora da pergunta)
            if t.get("categoria") == "mechanics" and t.get("pagina", "").lower() in chaves:
                paginas_de_mecanica.setdefault(t["pagina"], Duvida(t["pagina"], t["url"].split("#")[0], t["pagina"]))
        atributos = {"tipos": carta["superTypes"] + carta["cardTypes"], "dominios": carta["domains"],
                     "energia": carta["energyCost"], "poder": carta["powerCost"], "might": carta["might"],
                     "tags": carta["tags"]}
        return Ficha(nome, texto, atributos, bool(carta.get("errata")), url_da_carta(nome),
                     [Duvida(t["pergunta"], t["url"], t["pagina"]) for t in (da_carta + citada)[:MAX_DUVIDAS]],
                     list(paginas_de_mecanica.values()))

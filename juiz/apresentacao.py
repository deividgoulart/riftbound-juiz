"""Etapa 6: transforma a resposta do juiz em texto pra tela (links, rótulos, créditos).

Fica separado do app.py pra dar pra testar sem abrir o navegador.
"""

import html
import json
import re
from datetime import datetime

from juiz import config

RE_NUMERO_DE_REGRA = re.compile(r"\d{3}(?:\.[0-9a-z]+)*")  # 355.9.a
# [F1], [F1, F3] ou até [F1, CRD 372]; os espaços antes entram junto, pra citação grudar na palavra.
RE_GRUPO_DE_FONTES = re.compile(r"\s*\[([^\[\]]*\bF\d+[^\[\]]*)\]")
# (CRD 355.9.a) ou (CRD 425.1.c, 425.1.c.1). Não pega o "CRD" que já está dentro de um link (">CRD").
RE_CITACAO_CRD = re.compile(
    r"\s*(?<![>\w])\(?CRD\s+(\d{3}(?:\.[0-9a-z]+)*(?:\s*,\s*(?:CRD\s+)?\d{3}(?:\.[0-9a-z]+)*)*)\)?"
)
# Citações "soltas" que o LLM às vezes escreve: [813.1.c.1] (regra sem "CRD") e [Glossário].
# Custos de carta como [1] ou [2] têm no máximo 2 dígitos, então não se confundem com regras.
RE_REGRA_SOLTA = re.compile(r"\s*\[(\d{3}(?:\.[0-9a-z]+)*(?:\s*,\s*\d{3}(?:\.[0-9a-z]+)*)*)\]")
RE_GLOSSARIO_SOLTO = re.compile(r"\s*\[Gloss[áa]rio(?: do FAQ)?\]", re.IGNORECASE)

ROTULOS = {"faq": "FAQ não oficial", "crd": "Core Rules (oficial)", "carta": "Carta"}


def trecho_para_ler(texto: str, limite: int = 700) -> str:
    """Texto de uma fonte pra mostrar no plano B: sem os títulos (# ...) e cortado no fim de uma palavra."""
    linhas = [l.strip() for l in texto.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    corrido = " ".join(linhas)
    if len(corrido) <= limite:
        return corrido
    return corrido[:limite].rsplit(" ", 1)[0] + " …"


def plural(n: int, singular: str, plural_: str) -> str:
    """plural(1, "citada", "citadas") -> "1 citada"; plural(2, ...) -> "2 citadas"."""
    return f"{n} {singular if n == 1 else plural_}"


def _link(rotulo: str, url: str | None) -> str:
    return f'<a href="{html.escape(url)}" target="_blank">{rotulo}</a>' if url else rotulo


def linkar_citacoes(texto: str, fontes, regras: dict[str, str], versao_crd: str) -> str:
    """Transforma as citações em números pequenos com link (como notas num artigo):
    [F1, F3] -> <sup>F1, F3</sup> e (CRD 355.9.a) -> <sup>CRD 355.9.a</sup>, cada um levando à fonte.

    O resultado é Markdown com um pouco de HTML (st.markdown(..., unsafe_allow_html=True)). Por isso
    o texto do LLM passa antes por html.escape: ele não consegue colocar HTML próprio na página.
    """
    urls = {f.numero: f.url for f in fontes}

    def url_da_regra(numero: str) -> str:
        return regras.get(numero) or config.CRD_REGRA_URL.format(versao=versao_crd, regra=numero)

    def grupo_de_fontes(m: re.Match) -> str:
        links = []
        for parte in (p.strip() for p in m.group(1).split(",")):
            regra = re.fullmatch(r"(?:CRD\s+)?F?(\d{3}(?:\.[0-9a-z]+)*)", parte)
            fonte = re.fullmatch(r"F(\d{1,2})(?:\.[0-9a-z]+)*", parte)
            if regra:  # "CRD 372" dentro dos colchetes, ou "F331.2" (o LLM misturou regra com fonte)
                links.append(_link(f"CRD {regra.group(1)}", url_da_regra(regra.group(1))))
            elif fonte:  # "F1", ou "F1.4.3" (sufixo inventado pelo LLM: fica só o F1)
                links.append(_link(f"F{fonte.group(1)}", urls.get(int(fonte.group(1)))))
            elif parte:
                links.append(parte)
        return f"<sup>{', '.join(links)}</sup>"

    def citacao_crd(m: re.Match) -> str:
        numeros = RE_NUMERO_DE_REGRA.findall(m.group(1))
        return "<sup>CRD " + ", ".join(_link(n, url_da_regra(n)) for n in numeros) + "</sup>"

    texto = html.escape(texto, quote=False)
    texto = RE_GRUPO_DE_FONTES.sub(grupo_de_fontes, texto)
    texto = RE_CITACAO_CRD.sub(citacao_crd, texto)
    texto = RE_REGRA_SOLTA.sub(citacao_crd, texto)
    texto = RE_GLOSSARIO_SOLTO.sub("<sup>glossário do FAQ</sup>", texto)
    texto = texto.replace("</sup><sup>", ", ")  # citações vizinhas viram um grupo só: "F4, F5, CRD 313.1.a"
    return texto.replace("$", "\\$")  # "$" no Markdown do Streamlit vira fórmula matemática


def procedencia() -> dict:
    """Versões das fontes usadas no índice, pra mostrar na tela."""
    info = {"faq_data": None, "faq_commit": None, "crd_versao": None, "crd_nome": None}
    if config.FAQ_SNAPSHOT.exists():
        faq = json.loads(config.FAQ_SNAPSHOT.read_text(encoding="utf-8"))
        info["faq_data"] = datetime.fromisoformat(faq["data_commit"]).strftime("%d/%m/%Y")
        info["faq_commit"] = faq["commit"][:7]
    if config.CRD_SNAPSHOT.exists():
        crd = json.loads(config.CRD_SNAPSHOT.read_text(encoding="utf-8"))
        info["crd_versao"], info["crd_nome"] = crd["versao"], crd.get("nome")
    return info


CREDITOS = f"""
**De onde vêm as respostas**
- [Riftbound FAQ]({config.FAQ_SITE_URL}), de {config.FAQ_AUTOR}, sob a licença
  [{config.FAQ_LICENCA}](https://creativecommons.org/licenses/by-sa/4.0/). Os trechos
  mostrados aqui continuam sob a mesma licença.
- [Core Rules Document]({config.CRD_RULES_HUB_URL}) oficial da Riot Games. O texto é lido da
  versão HTML do Riftbound FAQ; em caso de dúvida, vale o [PDF oficial]({config.CRD_PDF_URL}).
- Textos das cartas: catálogo do repositório do Riftbound FAQ, com as erratas aplicadas.
- Glossário para iniciantes (Chain, Priority, Focus...): do código do Riftbound FAQ,
  sob a licença [MIT]({config.FAQ_GITHUB_URL}/blob/main/LICENSE-MIT).

**Aviso legal:** projeto não oficial, sem vínculo com a Riot Games e sem aprovação dela.
Riftbound e o conteúdo relacionado são propriedade da Riot Games, Inc. Criado sob a política
["Legal Jibber Jabber"](https://www.riotgames.com/en/legal) da Riot.
"""

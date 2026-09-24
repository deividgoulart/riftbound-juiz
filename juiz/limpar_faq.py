"""Etapa 2: transforma as páginas MDX do FAQ em trechos limpos, com metadados.

Uso (a partir da raiz do projeto):
    python -m juiz.limpar_faq

Entrada: data/raw/riftboundfaq/content/**/*.mdx  (baixados por juiz.baixar_faq)
Saída:   data/processed/faq_trechos.jsonl       (um trecho por linha, em JSON)

Decisões principais:
- 1 trecho = 1 pergunta "##". As subseções "###" entram no mesmo trecho, porque quase
  todas continuam a resposta de cima ("Steps", "Cost Sequence"...) e não fazem sentido
  sozinhas.
- Os componentes MDX viram texto simples, e o que eles informam (regras citadas, cartas,
  palavras-chave, avisos) vira metadado.
- Cada trecho tem dois textos:
    texto            -> sem os números de regra: é o que vai para a busca (embeddings)
    texto_com_regras -> com "[CRD 355.9.a]" no fim das frases: é o que o LLM vai ler,
                        para conseguir dizer qual regra sustenta cada afirmação
- Usamos expressões regulares em vez de um parser de MDX completo, porque a exploração
  (notebooks/01_explorar_faq.ipynb) mostrou que o vocabulário de componentes é pequeno
  e conhecido. Qualquer componente novo é reportado, pra gente não perder texto sem ver.
"""

import json
import re
import sys
import textwrap
from collections import Counter
from pathlib import Path

import yaml

from juiz import config

# --- Vocabulário de componentes (fonte: src/lib/mdx-vocabulary.ts do repositório do FAQ) ---
# Palavras-chave do jogo que o site mostra como etiqueta. Valor = como escrever no texto.
PALAVRAS_CHAVE = {
    "Accelerate": "Accelerate", "Action": "Action", "Add": "Add", "Ambush": "Ambush",
    "Assault": "Assault", "Burn": "Burn", "Deathknell": "Deathknell", "Deflect": "Deflect",
    "Equip": "Equip", "Empower": "Empower", "Empowered": "Empowered", "Flow": "Flow",
    "Hidden": "Hidden", "Legion": "Legion", "Mighty": "Mighty", "Predict": "Predict",
    "QuickDraw": "Quick-Draw", "Reaction": "Reaction", "Repeat": "Repeat", "Shield": "Shield",
    "Stun": "Stun", "Temporary": "Temporary", "Weaponmaster": "Weaponmaster",
}
# Runas/domínios e o poder "Universal" (paga custo de qualquer domínio). Mesma notação do
# texto das cartas no card-catalog.json: "[1][Fury]", "[2][Universal]".
SIMBOLOS = {"Fury", "Calm", "Mind", "Body", "Chaos", "Order", "Universal"}

AVISO_CITACAO_PENDENTE = "Rules citation needed"

RE_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
RE_TITULO = re.compile(r"^(#{2,3}) (.+?)(?: \[#([\w-]+)\])?[ \t]*$", re.MULTILINE)
RE_STEPS = re.compile(r"<Steps>(.*?)</Steps>", re.DOTALL)
RE_STEP = re.compile(r"<Step>(.*?)</Step>", re.DOTALL)
RE_CALLOUT = re.compile(r'<Callout type="(\w+)" title="([^"]*)">(.*?)</Callout>', re.DOTALL)
RE_TERM = re.compile(r'<Term item="[^"]*">(.*?)</Term>', re.DOTALL)
RE_CARD = re.compile(r'<Card name="([^"]+)"\s*/>')
RE_ENERGY = re.compile(r'<Energy value=(?:\{(\d+)\}|"(\d+)")\s*/>')
RE_REGRA = re.compile(r'<Rule number="([^"]+)"\s*/>')
RE_REGRAS_SEGUIDAS = re.compile(r'(?:[ \t]*<Rule number="[^"]+"\s*/>)+')
RE_ICONE = re.compile(r'<([A-Z]\w*)(?:\s+value=(?:\{(\d+)\}|"(\d+)"))?\s*/>')
RE_TAG_RESTANTE = re.compile(r"</?([A-Z]\w*)[^>]*>")


# ---------------------------------------------------------------------------
# Leitura e divisão em perguntas
# ---------------------------------------------------------------------------

def ler_mdx(caminho: Path) -> tuple[dict, str]:
    """Separa o frontmatter (YAML) do corpo (Markdown + componentes)."""
    texto = caminho.read_text(encoding="utf-8")
    m = RE_FRONTMATTER.match(texto)
    if not m:
        raise ValueError(f"{caminho}: frontmatter não encontrado")
    return yaml.safe_load(m.group(1)), texto[m.end():]


def url_da_pagina(caminho: Path) -> str:
    """content/(rulings)/cards/flash.mdx -> https://www.riftboundfaq.com/cards/flash"""
    rel = caminho.relative_to(config.FAQ_CONTENT_DIR).with_suffix("")
    partes = [p for p in rel.parts if not p.startswith("(")]  # grupos "(...)" não entram na URL
    if partes and partes[-1] == "index":
        partes = partes[:-1]
    return config.FAQ_SITE_URL + "/" + "/".join(partes)


def dividir_em_perguntas(corpo: str) -> list[dict]:
    """Divide o corpo em perguntas "##". Cada "###" entra no texto da "##" de cima."""
    titulos = list(RE_TITULO.finditer(corpo))
    perguntas: list[dict] = []
    for i, t in enumerate(titulos):
        fim = titulos[i + 1].start() if i + 1 < len(titulos) else len(corpo)
        texto = corpo[t.end():fim].strip("\n")
        nivel, titulo, ancora = len(t.group(1)), t.group(2).strip(), t.group(3)
        if nivel == 2 or not perguntas:
            perguntas.append({"pergunta": titulo, "ancora": ancora, "bruto": texto, "subsecoes": []})
        else:
            atual = perguntas[-1]
            atual["bruto"] += f"\n\n### {titulo}\n{texto}"
            atual["subsecoes"].append({"titulo": titulo, "ancora": ancora})
    return perguntas


# ---------------------------------------------------------------------------
# Metadados e limpeza do texto
# ---------------------------------------------------------------------------

def _unicos(itens) -> list:
    """Remove repetidos mantendo a ordem em que apareceram."""
    return list(dict.fromkeys(itens))


def extrair_metadados(bruto: str) -> dict:
    """Lê o texto ainda com componentes e devolve o que eles informam."""
    avisos = [titulo for tipo, titulo, _ in RE_CALLOUT.findall(bruto) if tipo != "idea"]
    icones = [m.group(1) for m in RE_ICONE.finditer(bruto)]
    return {
        "regras": _unicos(RE_REGRA.findall(bruto)),
        "cartas_mencionadas": _unicos(RE_CARD.findall(bruto)),
        "palavras_chave": _unicos(PALAVRAS_CHAVE[n] for n in icones if n in PALAVRAS_CHAVE),
        "avisos": _unicos(avisos),
        "citacao_pendente": AVISO_CITACAO_PENDENTE in avisos,
    }


def _formatar_passos(m: re.Match) -> str:
    """<Steps><Step>a</Step><Step>b</Step></Steps>  ->  "1. a" / "2. b" """
    linhas = []
    for n, passo in enumerate(RE_STEP.findall(m.group(1)), start=1):
        conteudo = textwrap.dedent(passo).strip().splitlines()
        linhas.append(f"{n}. {conteudo[0]}")
        linhas.extend(f"   {linha}" for linha in conteudo[1:])  # continuação alinhada no item
    return "\n".join(linhas)


def _formatar_callout(m: re.Match) -> str:
    """<Callout title="Example">texto</Callout>  ->  "Example: texto" """
    _, titulo, conteudo = m.groups()
    return f"{titulo}: {textwrap.dedent(conteudo).strip()}"


def _formatar_regras(m: re.Match) -> str:
    """<Rule number="1"/><Rule number="2"/>  ->  " [CRD 1, 2]" """
    return " [CRD " + ", ".join(RE_REGRA.findall(m.group(0))) + "]"


def _formatar_icone(m: re.Match, desconhecidos: Counter) -> str:
    """<Shield />  ->  [Shield]      <Energy value={2} />  ->  [2]      <Fury />  ->  [Fury]"""
    nome, valor = m.group(1), m.group(2) or m.group(3)
    if nome in PALAVRAS_CHAVE:
        rotulo = PALAVRAS_CHAVE[nome]
    elif nome in SIMBOLOS:
        rotulo = nome
    else:
        desconhecidos[nome] += 1
        return ""
    return f"[{rotulo} {valor}]" if valor else f"[{rotulo}]"


def limpar(bruto: str, manter_regras: bool, desconhecidos: Counter | None = None) -> str:
    """Troca os componentes MDX por texto simples.

    A ordem importa: primeiro as estruturas que envolvem outros componentes
    (Steps, Callout, Term), depois os componentes "folha" (Card, Energy, Rule, ícones).
    """
    if desconhecidos is None:
        desconhecidos = Counter()
    texto = RE_STEPS.sub(_formatar_passos, bruto)
    texto = RE_CALLOUT.sub(_formatar_callout, texto)
    texto = RE_TERM.sub(r"\1", texto)
    texto = RE_CARD.sub(r"\1", texto)
    texto = RE_ENERGY.sub(lambda m: f"[{m.group(1) or m.group(2)}]", texto)
    texto = RE_REGRAS_SEGUIDAS.sub(_formatar_regras if manter_regras else "", texto)
    texto = RE_ICONE.sub(lambda m: _formatar_icone(m, desconhecidos), texto)

    # Rede de segurança: tira qualquer tag de componente que sobrou, mas mantém o texto de dentro.
    def _remover(m: re.Match) -> str:
        desconhecidos[m.group(1)] += 1
        return ""

    texto = RE_TAG_RESTANTE.sub(_remover, texto)

    # Espaços: sem espaço sobrando no fim da linha, sem espaço duplo no meio, no máximo 1 linha em branco.
    texto = re.sub(r"[ \t]+$", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"(?<=\S)[ \t]{2,}", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


# ---------------------------------------------------------------------------
# Montagem dos trechos
# ---------------------------------------------------------------------------

def titulos_das_categorias() -> dict[str, str]:
    """Lê o título "bonito" de cada pasta nos meta.json (ex.: general-rules -> General Rules)."""
    titulos = {}
    for meta in config.FAQ_CONTENT_DIR.rglob("meta.json"):
        dados = json.loads(meta.read_text(encoding="utf-8"))
        if "title" in dados:
            titulos[meta.parent.name] = dados["title"]
    return titulos


def processar_arquivo(caminho: Path, titulos_categoria: dict[str, str], desconhecidos: Counter) -> list[dict]:
    fm, corpo = ler_mdx(caminho)
    categoria = caminho.parent.name
    pagina = fm["title"]
    url = url_da_pagina(caminho)
    trechos = []
    for p in dividir_em_perguntas(corpo):
        cabecalho = f"# {pagina}\n## {p['pergunta']}\n\n"
        texto = cabecalho + limpar(p["bruto"], manter_regras=False, desconhecidos=desconhecidos)
        texto_com_regras = cabecalho + limpar(p["bruto"], manter_regras=True)
        trechos.append({
            "id": f"faq/{categoria}/{caminho.stem}#{p['ancora']}",
            "fonte": "faq",
            "categoria": categoria,
            "categoria_titulo": titulos_categoria.get(categoria, categoria),
            "pagina": pagina,
            "carta": pagina if categoria == "cards" else None,
            "pergunta": p["pergunta"],
            "ancora": p["ancora"],
            "url": f"{url}#{p['ancora']}" if p["ancora"] else url,
            "subsecoes": p["subsecoes"],
            "texto": texto,
            "texto_com_regras": texto_com_regras,
            **extrair_metadados(p["bruto"]),
            "crd_revisado": fm.get("reviewedCoreRulesVersion"),
            "criado_em": fm.get("createdAt"),
            "arquivo": caminho.relative_to(config.FAQ_CONTENT_DIR).as_posix(),
            "palavras": len(texto.split()),
        })
    return trechos


RE_TERMO_DO_GLOSSARIO = re.compile(
    r"(\w+):\s*\{\s*title:\s*'((?:[^'\\]|\\.)*)',\s*explanation:\s*'((?:[^'\\]|\\.)*)'", re.DOTALL
)


def extrair_glossario(codigo: str, commit: str = "main") -> list[dict]:
    """Transforma o glossário do FAQ (src/lib/glossary.ts) em trechos, um por termo.

    São explicações curtas, escritas pra iniciantes, dos conceitos mais confusos (Chain,
    Priority, Focus...). O site mostra esses textos quando o leitor passa o mouse num termo.
    """
    trechos = []
    for m in RE_TERMO_DO_GLOSSARIO.finditer(codigo):
        chave, titulo, explicacao = m.group(1), m.group(2), m.group(3).replace("\\'", "'")
        linha = codigo[:m.start()].count("\n") + 1
        texto = f"# Glossary\n## What is {titulo}?\n\n{explicacao}"
        trechos.append({
            "id": f"faq/glossario#{chave}", "fonte": "faq", "categoria": "glossario",
            "categoria_titulo": "Glossary", "pagina": titulo, "carta": None,
            "pergunta": f"What is {titulo}?", "ancora": chave,
            "url": f"{config.FAQ_GITHUB_URL}/blob/{commit}/src/lib/glossary.ts#L{linha}",
            "subsecoes": [], "texto": texto, "texto_com_regras": texto,
            "regras": [], "cartas_mencionadas": [], "palavras_chave": [], "avisos": [],
            "citacao_pendente": False, "crd_revisado": None, "criado_em": None,
            "arquivo": "src/lib/glossary.ts", "palavras": len(texto.split()),
        })
    return trechos


def processar_tudo() -> tuple[list[dict], Counter]:
    """Processa as páginas de regras e o glossário. Devolve os trechos e os componentes desconhecidos."""
    titulos = titulos_das_categorias()
    desconhecidos: Counter = Counter()
    trechos = []
    for caminho in sorted(config.FAQ_CONTENT_DIR.rglob("*.mdx")):
        if caminho.parent.name.startswith("("):
            continue  # index.mdx ("About this site") fala do site, não de regras
        trechos.extend(processar_arquivo(caminho, titulos, desconhecidos))
    if config.FAQ_GLOSSARIO.exists():
        commit = json.loads(config.FAQ_SNAPSHOT.read_text(encoding="utf-8"))["commit"] if config.FAQ_SNAPSHOT.exists() else "main"
        trechos.extend(extrair_glossario(config.FAQ_GLOSSARIO.read_text(encoding="utf-8"), commit))
    return trechos, desconhecidos


def salvar_jsonl(trechos: list[dict], destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8") as f:
        for t in trechos:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


def main() -> None:
    sys.stdout.reconfigure(errors="replace")  # evita erro no terminal do Windows com caracteres especiais
    if not config.FAQ_CONTENT_DIR.exists():
        sys.exit("Dados não encontrados. Rode antes: python -m juiz.baixar_faq")

    trechos, desconhecidos = processar_tudo()
    destino = config.PROCESSED_DIR / "faq_trechos.jsonl"
    salvar_jsonl(trechos, destino)

    palavras = sorted(t["palavras"] for t in trechos)
    por_categoria = Counter(t["categoria"] for t in trechos)
    print(f"{len(trechos)} trechos salvos em {destino.relative_to(config.RAIZ)}")
    for categoria, n in sorted(por_categoria.items()):
        print(f"  {categoria:<15} {n}")
    print(f"Palavras por trecho: mín {palavras[0]}, mediana {palavras[len(palavras) // 2]}, máx {palavras[-1]}")
    print(f"Regras citadas (únicas): {len({r for t in trechos for r in t['regras']})}")
    print(f"Trechos com 'Rules citation needed': {sum(t['citacao_pendente'] for t in trechos)}")
    if desconhecidos:
        print(f"ATENÇÃO: componentes desconhecidos removidos: {dict(desconhecidos)}")
    else:
        print("Componentes desconhecidos: nenhum")


if __name__ == "__main__":
    main()

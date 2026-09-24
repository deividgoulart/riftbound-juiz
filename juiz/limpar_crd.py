"""Etapa 3: transforma o HTML do CRD em regras e trechos, com metadados.

Uso (depois de rodar juiz.baixar_crd):
    python -m juiz.limpar_crd

Entrada: data/raw/crd/core-rules-<versão>.html
Saídas:
    data/processed/crd_regras.jsonl   uma linha por regra (inclusive títulos de seção).
                                      Serve pra CONSULTA direta: "qual é o texto da regra 355.9.a?"
    data/processed/crd_trechos.jsonl  regras agrupadas em trechos. Serve pra BUSCA (embeddings).

Como os trechos são montados:
O CRD é uma árvore (355 -> 355.9 -> 355.9.a -> 355.9.a.1). Pra cada subseção do CRD:
- um galho que cabe no limite de palavras vira um trecho inteiro;
- um galho grande demais é dividido nos galhos filhos. O texto da regra "mãe" entra inteiro
  no primeiro pedaço e resumido (como contexto) nos outros, porque muitas vezes a filha
  continua a frase da mãe: "...meets all of the following requirements:";
- galhos pequenos vizinhos são agrupados no mesmo trecho, pra não gerar trechos minúsculos.
"""

import json
import re
import sys
from collections import Counter, defaultdict

from bs4 import BeautifulSoup

from juiz import config

LIMITE_PALAVRAS = 250  # palavras de regras por trecho, sem contar o contexto
MAX_PALAVRAS_CONTEXTO = 40  # cada regra "mãe" usada como contexto é resumida a este tamanho
MIN_PALAVRAS_TRECHO = 60  # pacote menor que isso não vira trecho sozinho se der pra juntar com o próximo
RE_TITULO_NUMERO = re.compile(r"^(\d{3})\.(.*)$")  # "100.Game Concepts"


# ---------------------------------------------------------------------------
# HTML -> lista de regras
# ---------------------------------------------------------------------------

def _texto_do_bloco(bloco) -> str:
    """Texto de um parágrafo, exemplo ou item de lista, com os espaços normalizados."""
    for marcador in bloco.select('span[aria-hidden="true"]'):
        if marcador.get_text(strip=True) == "•":
            marcador.replace_with("- ")
    return " ".join(bloco.get_text("").split())


def _titulo(el) -> tuple[str, str]:
    """<h2 id="R100">100.Game Concepts</h2>  ->  ("100", "Game Concepts")"""
    m = RE_TITULO_NUMERO.match(el.get_text("", strip=True))
    return m.group(1), m.group(2).strip()


def extrair_regras(html: str, versao: str) -> list[dict]:
    """Lê o HTML do CRD e devolve as regras na ordem do documento."""
    soup = BeautifulSoup(html, "html.parser")
    # As etiquetas "New"/"Changed" (mudanças desde a versão anterior) são do site, não do CRD.
    for etiqueta in soup.select('span[data-slot="badge"]'):
        etiqueta.decompose()

    regras: list[dict] = []
    secao = subsecao = None
    for el in soup.find_all(["h2", "h3", "li"]):
        if not el.get("id", "").startswith("R"):
            continue
        base = {"versao": versao, "url": config.CRD_REGRA_URL.format(versao=versao, regra=el["id"][1:])}

        if el.name in ("h2", "h3"):
            numero, titulo = _titulo(el)
            if el.name == "h2":
                secao, subsecao = f"{numero}. {titulo}", None
            else:
                subsecao = f"{numero}. {titulo}"
            regras.append({
                "numero": numero, "tipo": "secao" if el.name == "h2" else "subsecao", "texto": titulo,
                "pai": None, "secao": secao, "subsecao": subsecao,
                "referencias": [], "cartas_mencionadas": [], **base,
            })
            continue

        # <li id="R355.9"> <div> <a>355.9.</a> <div>parágrafos</div> </div> <ol>sub-regras</ol> </li>
        conteudo = el.find("div", recursive=False).find_all("div", recursive=False)[0]
        texto = "\n".join(t for t in (_texto_do_bloco(b) for b in conteudo.find_all(recursive=False)) if t)
        pai = el.find_parent("li", class_="core-rules-anchor")
        regras.append({
            "numero": el["id"][1:], "tipo": "regra", "texto": texto,
            "pai": pai["id"][1:] if pai else None, "secao": secao, "subsecao": subsecao,
            "referencias": list(dict.fromkeys(a["href"][2:] for a in conteudo.select('a[href^="#R"]'))),
            "cartas_mencionadas": list(dict.fromkeys(
                s["aria-label"].removeprefix("Preview ") for s in conteudo.select('span[aria-label^="Preview "]')
            )),
            **base,
        })
    return regras


# ---------------------------------------------------------------------------
# Regras -> trechos
# ---------------------------------------------------------------------------

def montar_trechos(regras: list[dict], limite: int = LIMITE_PALAVRAS) -> list[dict]:
    por_numero = {r["numero"]: r for r in regras}
    filhos: dict[str, list[str]] = defaultdict(list)
    topo_por_subsecao: dict[str, list[str]] = defaultdict(list)  # dict mantém a ordem do documento
    for r in regras:
        if r["tipo"] != "regra":
            continue
        if r["pai"]:
            filhos[r["pai"]].append(r["numero"])
        else:
            topo_por_subsecao[r["subsecao"] or r["secao"]].append(r["numero"])

    # Um item da lista de irmãos é o número de uma regra (= o galho inteiro dela) ou "=número"
    # (= só o texto próprio da regra, sem as sub-regras). O segundo caso aparece quando um galho
    # grande é dividido: o texto da regra "mãe" entra como conteúdo no primeiro pedaço.
    def palavras(n: str) -> int:
        return len(por_numero[n]["texto"].split())

    tamanhos: dict[str, int] = {}

    def tamanho(item: str) -> int:
        """Palavras do item: a regra + todas as sub-regras (ou só a regra, se for "=número")."""
        if item.startswith("="):
            return palavras(item[1:])
        if item not in tamanhos:
            tamanhos[item] = palavras(item) + sum(tamanho(f) for f in filhos[item])
        return tamanhos[item]

    def galho(item: str) -> list[str]:
        """Os números de regra do item, na ordem do documento."""
        if item.startswith("="):
            return [item[1:]]
        return [item] + [x for f in filhos[item] for x in galho(f)]

    def resumo(texto: str, maximo: int = MAX_PALAVRAS_CONTEXTO) -> str:
        partes = texto.split()
        return texto if len(partes) <= maximo else " ".join(partes[:maximo]) + " …"

    trechos: list[dict] = []

    def emitir(itens: list[str], contexto: list[str]) -> None:
        numeros = [x for item in itens for x in galho(item)]
        contexto = [c for c in contexto if c not in numeros]  # a mãe que já é conteúdo não se repete
        primeira = por_numero[numeros[0]]
        caminho = " > ".join(p for p in (primeira["secao"], primeira["subsecao"]) if p)
        versao = primeira["versao"]

        linhas_llm = [f"# Core Rules {versao} > {caminho}"]
        linhas_busca = ["# " + re.sub(r"\d{3}\. ", "", caminho)]  # sem números: não ajudam na busca
        for c in contexto:  # regras "mãe", resumidas, só pra situar o trecho
            linhas_llm.append(f"{'  ' * c.count('.')}{c}. {resumo(por_numero[c]['texto'])}")
            linhas_busca.append(resumo(por_numero[c]["texto"]))
        for n in numeros:
            recuo = "  " * n.count(".")
            texto = por_numero[n]["texto"].replace("\n", "\n" + recuo + "  ")
            linhas_llm.append(f"{recuo}{n}. {texto}")
            linhas_busca.append(por_numero[n]["texto"])

        texto_busca = "\n".join(linhas_busca)
        trechos.append({
            "id": f"crd/{versao}/{numeros[0]}",
            "fonte": "crd",
            "versao": versao,
            "secao": primeira["secao"],
            "subsecao": primeira["subsecao"],
            "numero": numeros[0],
            "regras": numeros,
            "contexto": contexto,
            "url": primeira["url"],
            "url_pdf_oficial": config.CRD_PDF_URL,
            "texto": texto_busca,
            "texto_com_regras": "\n".join(linhas_llm),
            "referencias": list(dict.fromkeys(ref for n in numeros for ref in por_numero[n]["referencias"])),
            "cartas_mencionadas": list(dict.fromkeys(c for n in numeros for c in por_numero[n]["cartas_mencionadas"])),
            "palavras": len(texto_busca.split()),
        })

    def dividir(irmaos: list[str], contexto: list[str]) -> None:
        pacote: list[str] = []
        soma = 0
        for n in irmaos:
            t = tamanho(n)
            if t > limite and not n.startswith("=") and filhos[n]:
                # Galho grande: divide nos filhos. O texto próprio da regra entra como primeiro
                # item ("=n") e ela vira contexto dos pedaços seguintes. Um pacote pequeno que
                # estava sendo montado desce junto, em vez de virar um trecho minúsculo sozinho.
                descer = pacote if soma < MIN_PALAVRAS_TRECHO else []
                if pacote and not descer:
                    emitir(pacote, contexto)
                pacote, soma = [], 0
                dividir(descer + ["=" + n] + filhos[n], contexto + [n])
            elif pacote and soma + t > limite:
                emitir(pacote, contexto)
                pacote, soma = [n], t
            else:
                pacote.append(n)
                soma += t
        if pacote:
            emitir(pacote, contexto)

    for topo in topo_por_subsecao.values():
        dividir(topo, [])
    return trechos


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

def salvar_jsonl(itens: list[dict], destino) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8") as f:
        for item in itens:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def processar() -> tuple[list[dict], list[dict]]:
    snapshot = json.loads(config.CRD_SNAPSHOT.read_text(encoding="utf-8"))
    html = (config.RAIZ / snapshot["arquivo"]).read_text(encoding="utf-8")
    regras = extrair_regras(html, snapshot["versao"])
    return regras, montar_trechos(regras)


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    if not config.CRD_SNAPSHOT.exists():
        sys.exit("CRD não encontrado. Rode antes: python -m juiz.baixar_crd")

    regras, trechos = processar()
    salvar_jsonl(regras, config.PROCESSED_DIR / "crd_regras.jsonl")
    salvar_jsonl(trechos, config.PROCESSED_DIR / "crd_trechos.jsonl")

    tipos = Counter(r["tipo"] for r in regras)
    palavras = sorted(t["palavras"] for t in trechos)
    print(f"{len(regras)} regras salvas em data/processed/crd_regras.jsonl "
          f"({tipos['regra']} regras, {tipos['secao']} seções, {tipos['subsecao']} subseções)")
    print(f"{len(trechos)} trechos salvos em data/processed/crd_trechos.jsonl")
    print(f"Palavras por trecho (com contexto): mín {palavras[0]}, mediana {palavras[len(palavras) // 2]}, máx {palavras[-1]}")

    # Ponte com o FAQ: toda regra citada pelo FAQ precisa existir no CRD.
    faq = config.PROCESSED_DIR / "faq_trechos.jsonl"
    if faq.exists():
        citadas = {r for linha in faq.open(encoding="utf-8") for r in json.loads(linha)["regras"]}
        faltando = sorted(citadas - {r["numero"] for r in regras})
        print(f"Regras citadas pelo FAQ encontradas no CRD: {len(citadas) - len(faltando)} de {len(citadas)}")
        if faltando:
            print(f"ATENÇÃO: não encontradas: {faltando}")


if __name__ == "__main__":
    main()

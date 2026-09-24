"""Baixa o Core Rules Document (CRD) na versão HTML publicada pelo riftboundfaq.com.

Uso (a partir da raiz do projeto, depois de rodar juiz.baixar_faq):
    python -m juiz.baixar_crd

Por que HTML e não o PDF oficial?
- O PDF é feito pra leitura humana. Extrair o texto dele em ordem, separando cada regra
  e sub-regra, dá bastante trabalho e é fácil de errar.
- O riftboundfaq.com já faz esse trabalho e publica o CRD como uma página com uma âncora
  por regra (#R355.9.a) e as sub-regras aninhadas. É o formato estruturado que a gente queria.
- O PDF oficial continua sendo a autoridade. O próprio site avisa que o parsing pode ter erros,
  então o app vai sempre mostrar o link do PDF oficial também.

Qual versão? A que o manifesto do FAQ (sources/rules-manifest.json) marca como atual.
Assim, quando o FAQ passar a usar o CRD 1.5, este script baixa a 1.5 sozinho.
"""

import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone

from juiz import config

USER_AGENT = "riftbound-juiz/0.1 (projeto pessoal de estudo; download ocasional)"


def versao_atual() -> tuple[str, str | None]:
    """Lê a versão atual do CRD (e o nome, ex. "Vendetta") no manifesto do FAQ."""
    caminho = config.FAQ_SOURCES_DIR / "rules-manifest.json"
    if not caminho.exists():
        sys.exit("Manifesto do FAQ não encontrado. Rode antes: python -m juiz.baixar_faq")
    core = json.loads(caminho.read_text(encoding="utf-8"))["coreRules"]
    versao = core["current"]
    return versao, core["versions"].get(versao, {}).get("name")


def baixar(url: str) -> bytes:
    pedido = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(pedido, timeout=60) as resposta:
        return resposta.read()


def main() -> None:
    versao, nome = versao_atual()
    url = config.CRD_HTML_URL.format(versao=versao)
    print(f"Baixando o CRD {versao} ({nome}) de {url} ...")
    conteudo = baixar(url)

    config.CRD_RAW_DIR.mkdir(parents=True, exist_ok=True)
    destino = config.CRD_RAW_DIR / f"core-rules-{versao}.html"
    destino.write_bytes(conteudo)

    snapshot = {
        "versao": versao,
        "nome": nome,
        "url_html": url,
        "url_pdf_oficial": config.CRD_PDF_URL,
        "rules_hub": config.CRD_RULES_HUB_URL,
        "arquivo": destino.relative_to(config.RAIZ).as_posix(),
        "bytes": len(conteudo),
        "sha256": hashlib.sha256(conteudo).hexdigest(),
        "baixado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    config.CRD_SNAPSHOT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Salvo em {snapshot['arquivo']} ({len(conteudo) / 1e6:.1f} MB)")
    print(f"Procedência salva em {config.CRD_SNAPSHOT.relative_to(config.RAIZ)}")


if __name__ == "__main__":
    main()

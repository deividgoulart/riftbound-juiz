"""Baixa ou atualiza o conteúdo do FAQ não oficial riftboundfaq.com.

Uso (a partir da raiz do projeto):
    python -m juiz.baixar_faq

Na primeira vez ele clona o repositório. Nas próximas, só atualiza.

Por que usar git em vez de baixar um .zip?
- O git baixa só o que mudou desde a última vez.
- Cada versão tem um identificador único (o hash do commit). Guardamos esse hash
  pra saber de qual versão do FAQ os dados vieram (a "procedência").

Por que "clone raso" e "sparse checkout"?
- --depth 1: traz só a versão mais recente, sem o histórico inteiro.
- --filter=blob:none + sparse checkout: só baixa o conteúdo dos arquivos das
  pastas que pedimos (config.FAQ_SPARSE_PATHS). O repositório tem uns 220 MB
  de PDFs que não precisamos aqui.
"""

import json
import subprocess
from datetime import datetime, timezone

from juiz import config


def git(*args: str, cwd=None) -> str:
    """Roda um comando git e devolve a saída como texto. Se der erro, levanta exceção."""
    resultado = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} falhou:\n{resultado.stderr.strip()}")
    return resultado.stdout.strip()


def clonar() -> None:
    """Primeira vez: clone raso, sem baixar arquivos, e depois checkout só das pastas escolhidas."""
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    git(
        "clone", "--depth", "1", "--filter=blob:none", "--no-checkout",
        "--branch", config.FAQ_BRANCH, config.FAQ_REPO_URL, str(config.FAQ_DIR),
    )
    git("sparse-checkout", "set", "--no-cone", *config.FAQ_SPARSE_PATHS, cwd=config.FAQ_DIR)
    git("checkout", config.FAQ_BRANCH, cwd=config.FAQ_DIR)


def atualizar() -> list[str]:
    """Próximas vezes: busca a versão mais recente e devolve a lista de arquivos alterados."""
    commit_antigo = git("rev-parse", "HEAD", cwd=config.FAQ_DIR)
    # Reaplica os caminhos, caso a lista em config.FAQ_SPARSE_PATHS tenha mudado.
    git("sparse-checkout", "set", "--no-cone", *config.FAQ_SPARSE_PATHS, cwd=config.FAQ_DIR)
    git("fetch", "--depth", "1", "origin", config.FAQ_BRANCH, cwd=config.FAQ_DIR)
    # data/raw/riftboundfaq é só uma cópia dos dados, então podemos sobrescrever sem medo.
    git("reset", "--hard", "FETCH_HEAD", cwd=config.FAQ_DIR)
    commit_novo = git("rev-parse", "HEAD", cwd=config.FAQ_DIR)
    if commit_antigo == commit_novo:
        return []
    diff = git("diff", "--name-status", commit_antigo, commit_novo, "--", "content", cwd=config.FAQ_DIR)
    return diff.splitlines()


def contar_mdx() -> dict[str, int]:
    """Conta os arquivos .mdx por categoria (nome da pasta onde o arquivo está)."""
    contagem: dict[str, int] = {}
    for arquivo in config.FAQ_CONTENT_DIR.rglob("*.mdx"):
        # Pastas entre parênteses, como "(rulings)", só agrupam arquivos no site.
        # O único MDX direto nela é o index.mdx ("About this site").
        categoria = "about" if arquivo.parent.name.startswith("(") else arquivo.parent.name
        contagem[categoria] = contagem.get(categoria, 0) + 1
    return dict(sorted(contagem.items()))


def salvar_snapshot() -> dict:
    """Grava a procedência dos dados em data/raw/faq_snapshot.json."""
    manifesto = json.loads((config.FAQ_SOURCES_DIR / "rules-manifest.json").read_text(encoding="utf-8"))
    mdx_por_categoria = contar_mdx()
    snapshot = {
        "repositorio": config.FAQ_REPO_URL,
        "commit": git("rev-parse", "HEAD", cwd=config.FAQ_DIR),
        "data_commit": git("log", "-1", "--format=%cI", cwd=config.FAQ_DIR),
        "mensagem_commit": git("log", "-1", "--format=%s", cwd=config.FAQ_DIR),
        "baixado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_mdx": sum(mdx_por_categoria.values()),
        "mdx_por_categoria": mdx_por_categoria,
        "crd_versao_atual": manifesto["coreRules"]["current"],
    }
    config.FAQ_SNAPSHOT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    return snapshot


def main() -> None:
    if (config.FAQ_DIR / ".git").exists():
        print(f"Atualizando o FAQ em {config.FAQ_DIR.relative_to(config.RAIZ)} ...")
        alterados = atualizar()
        if alterados:
            print(f"{len(alterados)} arquivo(s) de conteúdo mudaram:")
            for linha in alterados:
                print(f"  {linha}")  # A = adicionado, M = modificado, D = removido
        else:
            print("Já estava na versão mais recente.")
    else:
        print(f"Clonando {config.FAQ_REPO_URL} (só as pastas necessárias) ...")
        clonar()

    snap = salvar_snapshot()
    print()
    print(f"Commit:       {snap['commit'][:12]} ({snap['data_commit']})")
    print(f"Mensagem:     {snap['mensagem_commit']}")
    print(f"Arquivos MDX: {snap['total_mdx']}")
    for categoria, n in snap["mdx_por_categoria"].items():
        print(f"  {categoria:<15} {n}")
    print(f"CRD atual (segundo o FAQ): v{snap['crd_versao_atual']}")
    print(f"Procedência salva em {config.FAQ_SNAPSHOT.relative_to(config.RAIZ)}")


if __name__ == "__main__":
    main()

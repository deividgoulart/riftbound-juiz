"""Etapa 8: atualiza tudo de uma vez: FAQ, CRD, trechos e índices de busca.

Uso (a partir da raiz do projeto):
    python -m juiz.atualizar            # só refaz o que mudou
    python -m juiz.atualizar --forcar   # refaz os trechos mesmo sem mudança nas fontes

Cada passo só trabalha se algo mudou:
  1. FAQ: baixa na 1ª vez, depois só atualiza (git). Compara o commit de antes e o de depois.
  2. Trechos do FAQ: refeitos se o commit mudou.
  3. CRD: baixa a versão que o FAQ marca como atual. Se o FAQ mudou, baixa de novo pra pegar
     correções do site, mas só considera "mudou" se o conteúdo for diferente (hash).
  4. Regras e trechos do CRD: refeitos se o CRD mudou.
  5. Índices (a busca principal e a reserva): só os trechos novos ou alterados vão pro modelo.
     Sem índice local, parte dos vetores publicados em data/vetores/ (veja juiz/indice.py).

O app chama a mesma função quando sobe (na nuvem, a pasta data/ começa vazia) e uma vez por dia.
O resultado fica em data/atualizacao.json.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from juiz import baixar_crd, baixar_faq, config, limpar_crd, limpar_faq

def _ler_json(caminho) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}


def dados_prontos() -> bool:
    """O juiz consegue subir? (trechos, regras, catálogo de cartas e o índice de ao menos uma busca)"""
    necessarios = [config.PROCESSED_DIR / "faq_trechos.jsonl", config.PROCESSED_DIR / "crd_regras.jsonl",
                   config.PROCESSED_DIR / "crd_trechos.jsonl", config.FAQ_SOURCES_DIR / "card-catalog.json"]
    from juiz.embeddings import modelos_de_busca

    indices = [config.INDEX_DIR / nome / "vetores.npy" for nome in modelos_de_busca()]
    return all(c.exists() for c in necessarios) and any(i.exists() for i in indices)


def ultima_atualizacao() -> datetime | None:
    """Quando os dados foram atualizados pela última vez (ou baixados, se nunca rodou este módulo)."""
    quando = _ler_json(config.ATUALIZACAO).get("quando") or _ler_json(config.FAQ_SNAPSHOT).get("baixado_em")
    return datetime.fromisoformat(quando) if quando else None


def precisa_atualizar(agora: datetime | None = None) -> bool:
    agora = agora or datetime.now(timezone.utc)
    ultima = ultima_atualizacao()
    return not dados_prontos() or ultima is None or agora - ultima > timedelta(hours=config.ATUALIZAR_A_CADA_HORAS)


# --- passos ---

def atualizar_faq(log) -> bool:
    """Baixa ou atualiza o FAQ. Devolve True se o commit mudou."""
    antes = _ler_json(config.FAQ_SNAPSHOT).get("commit")
    if (config.FAQ_DIR / ".git").exists():
        baixar_faq.atualizar()
    else:
        log("Baixando o FAQ (só as pastas necessárias) ...")
        baixar_faq.clonar()
    depois = baixar_faq.salvar_snapshot()["commit"]
    log(f"FAQ: commit {depois[:12]}" + (" (novo)" if depois != antes else " (sem mudança)"))
    return depois != antes


def processar_faq(log) -> None:
    trechos, desconhecidos = limpar_faq.processar_tudo()
    limpar_faq.salvar_jsonl(trechos, config.PROCESSED_DIR / "faq_trechos.jsonl")
    log(f"FAQ: {len(trechos)} trechos")
    if desconhecidos:
        log(f"ATENÇÃO: componentes do FAQ que a limpeza não conhece: {dict(desconhecidos)}")


def atualizar_crd(faq_mudou: bool, log) -> bool:
    """Baixa o CRD se a versão mudou, se ainda não existe ou se o FAQ mudou. True se o conteúdo mudou."""
    versao, nome = baixar_crd.versao_atual()
    anterior = _ler_json(config.CRD_SNAPSHOT)
    arquivo = config.RAIZ / anterior["arquivo"] if anterior else None
    if anterior.get("versao") == versao and arquivo and arquivo.exists() and not faq_mudou:
        return False
    snapshot = baixar_crd.baixar_e_salvar(versao, nome)
    mudou = snapshot["sha256"] != anterior.get("sha256")
    log(f"CRD: v{versao} ({nome})" + (" (novo conteúdo)" if mudou else " (sem mudança)"))
    return mudou


def processar_crd(log) -> None:
    regras, trechos = limpar_crd.processar()
    limpar_crd.salvar_jsonl(regras, config.PROCESSED_DIR / "crd_regras.jsonl")
    limpar_crd.salvar_jsonl(trechos, config.PROCESSED_DIR / "crd_trechos.jsonl")
    log(f"CRD: {len(regras)} regras, {len(trechos)} trechos")


def atualizar_indices(log) -> dict[str, str]:
    """Atualiza a busca principal e a reserva. Um erro numa (ex.: cota) não impede a outra."""
    from juiz.embeddings import carregar_modelo, modelos_de_busca
    from juiz.indice import carregar_trechos, obter_indice

    trechos = carregar_trechos()
    situacao = {}
    for nome in modelos_de_busca():
        try:
            indice = obter_indice(carregar_modelo(nome), trechos)
            info = indice.info
            situacao[nome] = (f"{info['trechos_enviados_ao_modelo']} trechos enviados ao modelo, "
                              f"{info['trechos_reaproveitados']} reaproveitados"
                              if indice.acabou_de_ser_construido else "já estava em dia")
        except Exception as erro:  # cota, sem internet, sem chave...: o juiz sobe com o índice que tiver
            situacao[nome] = f"erro: {type(erro).__name__}: {erro}"
        log(f"Índice {nome}: {situacao[nome]}")
    return situacao


# --- tudo junto ---

def atualizar(forcar: bool = False, log=print) -> dict:
    faq_mudou = atualizar_faq(log)
    if forcar or faq_mudou or not (config.PROCESSED_DIR / "faq_trechos.jsonl").exists():
        processar_faq(log)
    crd_mudou = atualizar_crd(faq_mudou, log)
    if forcar or crd_mudou or not (config.PROCESSED_DIR / "crd_regras.jsonl").exists():
        processar_crd(log)
    indices = atualizar_indices(log)
    resultado = {
        "quando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "faq_commit": _ler_json(config.FAQ_SNAPSHOT).get("commit"),
        "faq_mudou": faq_mudou,
        "crd_versao": _ler_json(config.CRD_SNAPSHOT).get("versao"),
        "crd_mudou": crd_mudou,
        "indices": indices,
    }
    config.ATUALIZACAO.parent.mkdir(parents=True, exist_ok=True)
    config.ATUALIZACAO.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    return resultado


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Atualiza FAQ, CRD, trechos e índices (só o que mudou).")
    parser.add_argument("--forcar", action="store_true", help="refaz os trechos mesmo sem mudança nas fontes")
    args = parser.parse_args()
    resultado = atualizar(forcar=args.forcar)
    mudou = resultado["faq_mudou"] or resultado["crd_mudou"]
    print("\nPronto." + (" Se os vetores em data/vetores/ mudaram, faça commit deles pro app publicado reaproveitar."
                         if mudou else " Nada mudou nas fontes."))


if __name__ == "__main__":
    main()

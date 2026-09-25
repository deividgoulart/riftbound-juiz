"""Etapa 4: compara os modelos de embeddings (e a busca por palavra-chave) usando o gabarito.

Uso (a partir da raiz do projeto):
    python -m juiz.avaliar_busca                          # BM25 + modelos locais (+ Gemini, se tiver chave)
    python -m juiz.avaliar_busca --modelos bm25 e5-small  # só alguns

Métricas, calculadas nas perguntas do gabarito que têm resposta:
    hit@k  fração das perguntas em que uma fonte certa aparece entre os k primeiros resultados
    MRR    média de 1/posição da primeira fonte certa (1 = sempre em 1º lugar; 0,5 = em média em 2º)

Fonte certa = um trecho do FAQ listado em fontes_esperadas, ou um trecho do CRD que contém
uma das regras_esperadas.

Pras perguntas SEM resposta, guardamos a similaridade do 1º resultado. Se ela for bem menor
que a das perguntas com resposta, dá pra usar como "termômetro" do "não encontrei".

Saídas: avaliacao/resultados/busca_resumo.csv e avaliacao/resultados/busca_detalhe.csv
"""

import argparse
import os
import re
import sys
import time

import numpy as np
import pandas as pd
import yaml
from rank_bm25 import BM25Okapi

from juiz import config
from juiz.embeddings import carregar_modelo
from juiz.glossario import expandir_pergunta
from juiz.indice import carregar_trechos, obter_indice

K_MAX = 10  # quantos resultados olhamos por pergunta
# O qwen3-0.6b foi testado e descartado: no processador, levou mais de 20 min pra indexar
# (o e5-base leva 2) e usou 3,3 GB de RAM, mais que os 2,7 GB do Streamlit Community Cloud, onde o app ficava até a fase 2.
# Continua disponível: python -m juiz.avaliar_busca --modelos qwen3-0.6b
MODELOS_PADRAO = ["bm25", "e5-small", "e5-base", "gemini-2"]


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------

def fontes_certas(questao: dict, trechos: list[dict]) -> set[int]:
    """Posições (no índice) dos trechos que contam como acerto pra esta pergunta."""
    ids = set(questao["fontes_esperadas"])
    regras = set(questao["regras_esperadas"])
    return {
        i for i, t in enumerate(trechos)
        if t["id"] in ids or (t["fonte"] == "crd" and regras & set(t["regras"]))
    }


def posicao_do_acerto(ranking, certas: set[int]) -> int | None:
    """Em que posição (1, 2, 3...) aparece a primeira fonte certa. None se não aparecer."""
    for posicao, i in enumerate(ranking, start=1):
        if i in certas:
            return posicao
    return None


def metricas(posicoes: list[int | None], ks=(1, 3, 5)) -> dict:
    n = len(posicoes)
    resultado = {f"hit@{k}": sum(p is not None and p <= k for p in posicoes) / n for k in ks}
    resultado["mrr"] = sum(1 / p for p in posicoes if p) / n
    return resultado


# ---------------------------------------------------------------------------
# Linha de base: busca por palavra-chave (BM25)
# ---------------------------------------------------------------------------

def tokenizar(texto: str) -> list[str]:
    return re.findall(r"\w+", texto.lower())


class BuscaBM25:
    """Busca "clássica" por palavras em comum, a mesma ideia dos buscadores antigos.

    Não entende sentido nem tradução: "emboscada" não encontra "Ambush". Serve de comparação
    pra mostrar o que os embeddings acrescentam.
    """

    def __init__(self, trechos: list[dict]):
        self.bm25 = BM25Okapi([tokenizar(t["texto"]) for t in trechos])

    def ranquear(self, perguntas: list[str], k: int) -> tuple[np.ndarray, np.ndarray]:
        posicoes, notas = [], []
        for pergunta in perguntas:
            pontuacao = self.bm25.get_scores(tokenizar(pergunta))
            melhores = np.argsort(-pontuacao)[:k]
            posicoes.append(melhores)
            notas.append(pontuacao[melhores])
        return np.array(posicoes), np.array(notas)


# ---------------------------------------------------------------------------
# Comparação
# ---------------------------------------------------------------------------

def ranquear(nome: str, trechos: list[dict], perguntas: list[str], reconstruir: bool):
    """Roda a busca de todas as perguntas com um modelo. Devolve ranking, notas e informações."""
    if nome == "bm25":
        inicio = time.perf_counter()
        busca = BuscaBM25(trechos)
        posicoes, notas = busca.ranquear(perguntas, K_MAX)
        return posicoes, notas, {"segundos_para_indexar": round(time.perf_counter() - inicio, 1)}

    modelo = carregar_modelo(nome)
    indice = obter_indice(modelo, trechos, reconstruir=reconstruir)
    inicio = time.perf_counter()
    posicoes, notas = indice.ranquear(modelo.perguntas(perguntas), K_MAX)
    info = dict(indice.info)
    info["ms_por_pergunta"] = round(1000 * (time.perf_counter() - inicio) / len(perguntas), 1)
    return posicoes, notas, info


def _mesclar_ranking(pos_a, notas_a, pos_b, notas_b) -> tuple[np.ndarray, np.ndarray]:
    """Junta dois rankings do mesmo modelo (sem repetir trecho, fica a maior nota), como o juiz faz."""
    melhores: dict[int, float] = {}
    for p, n in list(zip(pos_a, notas_a)) + list(zip(pos_b, notas_b)):
        melhores[int(p)] = max(float(n), melhores.get(int(p), float("-inf")))
    ordem = sorted(melhores, key=lambda p: -melhores[p])[:len(pos_a)]
    return np.array(ordem), np.array([melhores[p] for p in ordem])


def _juntar_com_anterior(novo: pd.DataFrame, arquivo) -> pd.DataFrame:
    """Substitui só as linhas dos modelos avaliados agora; mantém as dos outros."""
    if not arquivo.exists():
        return novo
    anterior = pd.read_csv(arquivo)
    return pd.concat([anterior[~anterior.modelo.isin(novo.modelo)], novo], ignore_index=True)


def avaliar(nomes: list[str], reconstruir: bool = False, glossario: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    gabarito = yaml.safe_load(config.GABARITO.read_text(encoding="utf-8"))
    trechos = carregar_trechos()
    perguntas = [q["pergunta"] for q in gabarito]
    if glossario:  # etapa 5: acrescenta os termos oficiais em inglês, como o juiz faz
        perguntas = [expandir_pergunta(p) for p in perguntas]
    certas = [fontes_certas(q, trechos) for q in gabarito]
    # Perguntas de continuação ("e se...?"): o juiz busca também junto com a pergunta anterior.
    continuacoes = [(i, f"{q['historico'][-1]['pergunta']} {perguntas[i]}")
                    for i, q in enumerate(gabarito) if q.get("historico")]

    detalhe, resumo = [], []
    for nome in nomes:
        print(f"\n=== {nome} ===")
        posicoes, notas, info = ranquear(nome, trechos, perguntas, reconstruir)
        if continuacoes:
            pos_extra, notas_extra, _ = ranquear(nome, trechos, [c for _, c in continuacoes], False)
            for (i, _), pe, ne in zip(continuacoes, pos_extra, notas_extra):
                posicoes[i], notas[i] = _mesclar_ranking(posicoes[i], notas[i], pe, ne)
        rotulo = f"{nome}+glossario" if glossario else nome
        linhas = []
        for q, cert, ranking, nts in zip(gabarito, certas, posicoes, notas):
            linhas.append({
                "modelo": rotulo, "id": q["id"], "categoria": q["categoria"], "estilo": q["estilo"],
                "tem_resposta": bool(cert),
                "posicao": posicao_do_acerto(ranking, cert) if cert else None,
                "nota_top1": round(float(nts[0]), 4),
                "top1": trechos[ranking[0]]["id"],
                "pergunta": q["pergunta"],
            })
        detalhe.extend(linhas)

        com = [l for l in linhas if l["tem_resposta"]]
        sem = [l for l in linhas if not l["tem_resposta"]]
        linha_resumo = {"modelo": rotulo, **metricas([l["posicao"] for l in com])}
        for estilo in ("formal", "informal", "termo_em_portugues"):
            linha_resumo[f"hit@5_{estilo}"] = metricas([l["posicao"] for l in com if l["estilo"] == estilo])["hit@5"]
        linha_resumo["nota_top1_com_resposta"] = np.mean([l["nota_top1"] for l in com])
        linha_resumo["nota_top1_sem_resposta"] = np.mean([l["nota_top1"] for l in sem])
        linha_resumo["segundos_para_indexar"] = info.get("segundos_para_indexar")
        linha_resumo["ms_por_pergunta"] = info.get("ms_por_pergunta")
        linha_resumo["trechos_cortados"] = info.get("trechos_cortados")
        resumo.append(linha_resumo)
        print(pd.Series(linha_resumo).to_string())

    df_resumo = pd.DataFrame(resumo).round(3)
    df_detalhe = pd.DataFrame(detalhe)
    config.RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    for df, nome_arquivo in ((df_resumo, "busca_resumo.csv"), (df_detalhe, "busca_detalhe.csv")):
        _juntar_com_anterior(df, config.RESULTADOS_DIR / nome_arquivo).to_csv(config.RESULTADOS_DIR / nome_arquivo, index=False)
    return df_resumo, df_detalhe


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Compara modelos de busca usando o gabarito.")
    parser.add_argument("--modelos", nargs="+", help=f"padrão: {' '.join(MODELOS_PADRAO)}")
    parser.add_argument("--reconstruir", action="store_true", help="recria os índices mesmo se já existirem")
    parser.add_argument("--glossario", action="store_true", help="expande as perguntas com o glossário PT->EN (etapa 5)")
    args = parser.parse_args()

    nomes = args.modelos or [m for m in MODELOS_PADRAO if m != "gemini-2" or os.environ.get("GEMINI_API_KEY")]
    if "gemini-2" not in nomes and not args.modelos:
        print("(gemini-2 fora da comparação: GEMINI_API_KEY não está no .env)")
    resumo, _ = avaliar(nomes, reconstruir=args.reconstruir, glossario=args.glossario)

    colunas = ["modelo", "hit@1", "hit@3", "hit@5", "mrr", "hit@5_termo_em_portugues",
               "nota_top1_com_resposta", "nota_top1_sem_resposta"]
    print("\n" + resumo[colunas].to_string(index=False))
    print(f"\nTabelas salvas em {config.RESULTADOS_DIR.relative_to(config.RAIZ)}")


if __name__ == "__main__":
    main()

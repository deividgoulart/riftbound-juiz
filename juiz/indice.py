"""Índice de busca: guarda um vetor por trecho e acha os trechos mais parecidos com a pergunta.

Uso (a partir da raiz do projeto):
    python -m juiz.indice                                            # atualiza a principal e a reserva
    python -m juiz.indice --buscar "posso usar emboscada na base?"   # e faz uma busca de teste
    python -m juiz.indice --modelo e5-small --buscar "..."           # só um modelo

Arquivos em data/index/<modelo>/ (fora do git):
    vetores.npy    matriz com um vetor por trecho (NumPy)
    trechos.jsonl  os trechos na mesma ordem dos vetores (texto + metadados)
    info.json      qual modelo gerou, quando e a partir de qual versão das fontes

Vetores publicados em data/vetores/<modelo>/ (esses VÃO pro GitHub, etapa 8):
    vetores.npy    os mesmos vetores
    trechos.json   só o id e a "assinatura" (hash) de cada trecho, sem o texto
    Servem pro app na nuvem montar o índice sem gastar a cota de embeddings: ele baixa o FAQ e o
    CRD, e só manda pro modelo os trechos cuja assinatura não está aqui. Como não têm o texto,
    não republicam o conteúdo das fontes.

Como a busca funciona: os vetores são normalizados, então a similaridade de cosseno entre
a pergunta e cada trecho é um produto escalar (vetores @ pergunta). Com ~500 trechos,
comparar com todos leva milissegundos. Um banco vetorial só faria diferença com centenas de
milhares de trechos.
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone

import numpy as np

from juiz import config
from juiz.embeddings import carregar_modelo
from juiz.erros import CotaEsgotada

ARQUIVOS_TRECHOS = ["faq_trechos.jsonl", "crd_trechos.jsonl"]


def carregar_trechos() -> list[dict]:
    """Junta os trechos do FAQ e do CRD (gerados nas etapas 2 e 3)."""
    trechos = []
    for nome in ARQUIVOS_TRECHOS:
        caminho = config.PROCESSED_DIR / nome
        if not caminho.exists():
            sys.exit(f"{caminho.name} não encontrado. Rode antes: python -m juiz.limpar_faq e python -m juiz.limpar_crd")
        trechos.extend(json.loads(linha) for linha in caminho.open(encoding="utf-8"))
    return trechos


def titulo_do_trecho(t: dict) -> str:
    """Título curto do trecho (o Gemini usa no formato "title: ... | text: ...")."""
    return t["pagina"] if t["fonte"] == "faq" else (t["subsecao"] or t["secao"])


def hash_dos_trechos(trechos: list[dict]) -> str:
    """Uma "impressão digital" dos trechos. Se o FAQ ou o CRD mudarem, ela muda e o índice fica velho."""
    h = hashlib.sha256()
    for t in trechos:
        h.update(t["id"].encode() + b"\0" + t["texto"].encode() + b"\0")
    return h.hexdigest()


def assinatura(t: dict) -> str:
    """Hash do que gerou o vetor (título + texto). Se a assinatura é igual, o vetor pode ser reaproveitado."""
    return hashlib.sha256(f"{titulo_do_trecho(t)}\0{t['texto']}".encode()).hexdigest()[:20]


def _procedencia() -> dict:
    """De qual versão do FAQ e do CRD o índice foi gerado."""
    if not (config.FAQ_SNAPSHOT.exists() and config.CRD_SNAPSHOT.exists()):
        return {}
    faq = json.loads(config.FAQ_SNAPSHOT.read_text(encoding="utf-8"))
    crd = json.loads(config.CRD_SNAPSHOT.read_text(encoding="utf-8"))
    return {"faq_commit": faq["commit"], "faq_data": faq["data_commit"], "crd_versao": crd["versao"]}


class Indice:
    def __init__(self, nome_modelo: str, vetores: np.ndarray, trechos: list[dict], info: dict):
        self.nome_modelo = nome_modelo
        self.vetores = vetores
        self.trechos = trechos
        self.info = info
        self.acabou_de_ser_construido = False  # distingue "atualizei agora" de "já estava em dia"

    # --- criar, salvar e carregar ---

    @classmethod
    def construir(cls, modelo, trechos: list[dict], anterior: "Indice | None" = None) -> "Indice":
        """Cria o índice. Se receber o índice anterior do mesmo modelo, reaproveita os vetores dos
        trechos que não mudaram e só manda pro modelo os novos ou alterados (indexação incremental).
        Isso importa porque o tier grátis do Gemini tem cota diária de textos."""
        inicio = time.perf_counter()
        reaproveitados: dict[int, np.ndarray] = {}
        if anterior is not None and anterior.info.get("id_modelo") == modelo.id:
            # Os vetores publicados guardam só a assinatura; os índices locais, o trecho inteiro.
            antigos = {t["id"]: (t.get("assinatura") or assinatura(t), v) for t, v in zip(anterior.trechos, anterior.vetores)}
            for i, t in enumerate(trechos):
                antigo = antigos.get(t["id"])
                if antigo and antigo[0] == assinatura(t):
                    reaproveitados[i] = antigo[1]
        novos = [i for i in range(len(trechos)) if i not in reaproveitados]
        if novos:
            vetores_novos = modelo.documentos([trechos[i]["texto"] for i in novos], [titulo_do_trecho(trechos[i]) for i in novos])
            dimensoes = vetores_novos.shape[1]
        else:
            dimensoes = anterior.vetores.shape[1]
        vetores = np.empty((len(trechos), dimensoes), dtype=np.float32)
        for i, v in reaproveitados.items():
            vetores[i] = v
        for k, i in enumerate(novos):
            vetores[i] = vetores_novos[k]
        info = {
            "modelo": modelo.nome,
            "id_modelo": modelo.id,
            "dimensoes": int(dimensoes),
            "trechos": len(trechos),
            "trechos_reaproveitados": len(reaproveitados),
            "trechos_enviados_ao_modelo": len(novos),
            "hash_trechos": hash_dos_trechos(trechos),
            "segundos_para_indexar": round(time.perf_counter() - inicio, 1),
            "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **_procedencia(),
        }
        if hasattr(modelo, "contar_tokens"):
            # Quantos trechos passam do limite do modelo (o excesso é cortado sem aviso).
            info["max_tokens"] = modelo.max_tokens
            info["trechos_cortados"] = sum(modelo.contar_tokens(t["texto"]) > modelo.max_tokens for t in trechos)
        indice = cls(modelo.nome, vetores, trechos, info)
        indice.acabou_de_ser_construido = True
        return indice

    def salvar(self) -> None:
        pasta = config.INDEX_DIR / self.nome_modelo
        pasta.mkdir(parents=True, exist_ok=True)
        np.save(pasta / "vetores.npy", self.vetores)
        with (pasta / "trechos.jsonl").open("w", encoding="utf-8") as f:
            for t in self.trechos:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        (pasta / "info.json").write_text(json.dumps(self.info, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def carregar(cls, nome_modelo: str) -> "Indice":
        pasta = config.INDEX_DIR / nome_modelo
        vetores = np.load(pasta / "vetores.npy")
        trechos = [json.loads(linha) for linha in (pasta / "trechos.jsonl").open(encoding="utf-8")]
        info = json.loads((pasta / "info.json").read_text(encoding="utf-8"))
        return cls(nome_modelo, vetores, trechos, info)

    @staticmethod
    def existe(nome_modelo: str) -> bool:
        return (config.INDEX_DIR / nome_modelo / "vetores.npy").exists()

    # --- vetores publicados (etapa 8) ---

    def publicar_vetores(self) -> None:
        """Grava em data/vetores/<modelo>/ os vetores com id e assinatura, sem o texto dos trechos."""
        pasta = config.VETORES_DIR / self.nome_modelo
        pasta.mkdir(parents=True, exist_ok=True)
        np.save(pasta / "vetores.npy", self.vetores)
        ids = [{"id": t["id"], "assinatura": t.get("assinatura") or assinatura(t)} for t in self.trechos]
        linhas = ",\n".join(json.dumps(i, ensure_ascii=False) for i in ids)  # um trecho por linha: diffs legíveis
        (pasta / "trechos.json").write_text(f"[\n{linhas}\n]\n", encoding="utf-8", newline="\n")
        # Só campos que não mudam se os trechos não mudarem (a data de criação ficaria sempre diferente no git).
        info = {c: self.info[c] for c in ("modelo", "id_modelo", "dimensoes", "trechos", "hash_trechos",
                                          "faq_commit", "crd_versao") if c in self.info}
        (pasta / "info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    @classmethod
    def carregar_vetores_publicados(cls, nome_modelo: str) -> "Indice | None":
        pasta = config.VETORES_DIR / nome_modelo
        if not (pasta / "vetores.npy").exists():
            return None
        trechos = json.loads((pasta / "trechos.json").read_text(encoding="utf-8"))
        info = json.loads((pasta / "info.json").read_text(encoding="utf-8"))
        return cls(nome_modelo, np.load(pasta / "vetores.npy"), trechos, info)

    def atualizado(self, trechos: list[dict]) -> bool:
        """O índice foi gerado a partir destes mesmos trechos?"""
        return self.info.get("hash_trechos") == hash_dos_trechos(trechos)

    # --- busca ---

    def ranquear(self, vetores_perguntas: np.ndarray, k: int = 10) -> tuple[np.ndarray, np.ndarray]:
        """Pra cada pergunta, as posições dos k trechos mais parecidos e as similaridades."""
        similaridades = vetores_perguntas @ self.vetores.T  # (perguntas x trechos)
        melhores = np.argsort(-similaridades, axis=1)[:, :k]
        return melhores, np.take_along_axis(similaridades, melhores, axis=1)

    def buscar(self, pergunta: str, modelo, k: int = 5) -> list[tuple[dict, float]]:
        posicoes, notas = self.ranquear(modelo.perguntas([pergunta]), k)
        return [(self.trechos[p], float(n)) for p, n in zip(posicoes[0], notas[0])]


def obter_indice(modelo, trechos: list[dict], reconstruir: bool = False) -> Indice:
    """Carrega o índice salvo, ou cria um novo se não existir ou se os trechos mudaram."""
    anterior = Indice.carregar(modelo.nome) if Indice.existe(modelo.nome) else None
    if anterior is not None and not reconstruir and anterior.atualizado(trechos):
        indice = anterior
    else:
        if anterior is not None and not reconstruir:
            print("Os trechos mudaram desde a última vez: atualizando o índice.")
        if anterior is None and not reconstruir:
            # Sem índice local (ex.: o app acabou de subir na nuvem): parte dos vetores publicados.
            anterior = Indice.carregar_vetores_publicados(modelo.nome)
        print(f"Indexando com {modelo.id} ({len(trechos)} trechos) ...")
        # --reconstruir refaz tudo do zero; senão, só os trechos novos ou alterados vão pro modelo.
        indice = Indice.construir(modelo, trechos, anterior=None if reconstruir else anterior)
        indice.salvar()
        info = indice.info
        print(f"Pronto em {info['segundos_para_indexar']} s: {info['trechos_enviados_ao_modelo']} trechos enviados ao modelo, "
              f"{info['trechos_reaproveitados']} reaproveitados ({info['dimensoes']} dimensões)")
    indice.publicar_vetores()  # mantém data/vetores/ igual ao índice, pra ir pro GitHub no próximo commit
    return indice


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    padrao = [config.MODELO_EMBEDDINGS, config.MODELO_EMBEDDINGS_RESERVA]
    parser = argparse.ArgumentParser(description="Cria/atualiza os índices de busca e/ou faz uma busca de teste.")
    parser.add_argument("--modelo", help=f"só este modelo (padrão: a principal e a reserva, {' e '.join(padrao)})")
    parser.add_argument("--buscar", help="pergunta de teste")
    parser.add_argument("--reconstruir", action="store_true", help="recria o índice do zero mesmo se já existir")
    args = parser.parse_args()

    trechos = carregar_trechos()
    prontos = []  # (modelo, índice) que ficaram atualizados
    for nome in [args.modelo] if args.modelo else padrao:
        modelo = carregar_modelo(nome)
        try:
            prontos.append((modelo, obter_indice(modelo, trechos, reconstruir=args.reconstruir)))
        except CotaEsgotada as erro:
            print(f"{nome}: {erro}\n  O índice anterior continua salvo; rode de novo amanhã pra atualizar.")

    if args.buscar and prontos:
        modelo, indice = prontos[0]
        print(f'\nPergunta: "{args.buscar}" (busca com {modelo.nome})\n')
        for trecho, nota in indice.buscar(args.buscar, modelo):
            titulo = trecho.get("pergunta") or f"Regra {trecho['numero']} ({trecho['subsecao']})"
            print(f"{nota:.3f}  [{trecho['fonte'].upper()}] {titulo}\n       {trecho['url']}")


if __name__ == "__main__":
    main()

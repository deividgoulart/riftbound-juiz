"""Etapa 7: avalia as respostas do juiz de ponta a ponta, usando o gabarito.

Uso (a partir da raiz do projeto):
    python -m juiz.avaliar_respostas --modelo gemini-3.5-flash-lite           # todas as perguntas
    python -m juiz.avaliar_respostas --modelo gemini-3.8-flash --comparacao   # só as 18 da comparação
    python -m juiz.avaliar_respostas --modelo gemini-3.5-flash-lite --ids q01 q05
    python -m juiz.avaliar_respostas --revisao gemini-3.5-flash-lite          # planilha pra revisão humana
    python -m juiz.avaliar_respostas --completar-notas gemini-3.5-flash-lite  # notas que ficaram em branco
    python -m juiz.avaliar_respostas --resumo                                 # só recalcula o resumo
    python -m juiz.avaliar_respostas --concordancia flash-lite_e5             # revisão humana x avaliador

Pra cada pergunta, o juiz responde (com o histórico, nas continuações) e medimos:

  Métricas automáticas (não dependem de outro LLM, então são objetivas):
    acertou_se_respondia  respondeu quando o gabarito tem resposta; disse "não encontrei" quando não tem
    conclusao_certa       começou com a conclusão esperada (sim/não/depende), quando o gabarito tem uma
    citou_fonte_certa     citou uma fonte esperada, ou uma das regras esperadas
    citacoes_inventadas   regras citadas que NÃO existem no CRD, ou fontes [Fn] que não existem

  Métrica do avaliador (um LLM compara com a resposta esperada):
    nota                  correta / parcial / incorreta, com uma justificativa

Os resultados são gravados pergunta a pergunta em avaliacao/resultados/respostas_<modelo>.jsonl.
Se a cota do dia acabar no meio, é só rodar de novo depois: as perguntas já avaliadas são puladas.
"""

import argparse
import json
import re
import sys
import time
from typing import Literal

import pandas as pd
import yaml
from pydantic import BaseModel

from juiz import config
from juiz.erros import CotaEsgotada
from juiz.glossario import normalizar
from juiz.llm import LLMGemini

INSTRUCOES_AVALIADOR = """\
Você avalia as respostas de um juiz de regras do Riftbound TCG. Compare a RESPOSTA DO JUIZ com a
RESPOSTA ESPERADA, que foi escrita por uma pessoa a partir das regras oficiais.

Dê uma nota:
- "correta": chega à mesma conclusão da esperada e não afirma nada que a contradiga.
- "parcial": a conclusão está certa, mas falta um ponto importante da esperada, ou há um erro secundário.
- "incorreta": a conclusão é diferente da esperada, ou afirma algo que contradiz a esperada.

Quando a resposta esperada diz que o juiz deve dizer que NÃO ENCONTROU a resposta:
"correta" se ele disse que não encontrou e não inventou nada; "incorreta" se respondeu como se soubesse.

Não julgue estilo, tamanho nem citações: só se o conteúdo está certo. A resposta do juiz pode ter
mais detalhes que a esperada; detalhes a mais só pesam se estiverem errados.
Julgue só o que a PERGUNTA pede. A resposta esperada às vezes traz informações extras, que a pergunta
não pediu (ex.: a pergunta é só sobre quanto dano uma carta causa, e a esperada também explica quando
ela pode ser jogada). A falta dessas informações extras não é motivo pra "parcial"; o que conta é
faltar algo que responde à pergunta.
Escreva a justificativa em português, em uma frase."""


class Avaliacao(BaseModel):
    """Formato da resposta do avaliador (o LLM é obrigado a responder neste JSON)."""

    nota: Literal["correta", "parcial", "incorreta"]
    justificativa: str


# ---------------------------------------------------------------------------
# Métricas automáticas
# ---------------------------------------------------------------------------

RE_GRUPO_CITACAO = re.compile(r"\((?:CRD)[^)]*\)|\[[^\]]*\]")  # (CRD 355.9.a) ou [F1, CRD 372]
RE_NUMERO_DE_REGRA = re.compile(r"(?<![\d.])\d{3}(?:\.[0-9a-z]+)*")


def conclusao_da_resposta(texto: str) -> str | None:
    """A conclusão com que a resposta começa: "sim", "não", "depende" ou None."""
    limpo = re.sub(r"[*_#>]", "", texto).strip()
    if not limpo or normalizar(limpo).startswith("nao encontrei"):
        return None  # "Não encontrei a resposta" não é a conclusão "não"
    primeira = re.sub(r"\W", "", normalizar(limpo.split()[0]))  # split() também corta em "Não.\n\n..."
    return {"sim": "sim", "nao": "não", "depende": "depende"}.get(primeira)


def conclusao_confere(esperada, obtida: str | None) -> bool | None:
    """A conclusão esperada pode ser uma só ("sim") ou uma lista de aceitas (["não", "depende"])."""
    if not esperada:
        return None
    return obtida in (esperada if isinstance(esperada, list) else [esperada])


def regras_e_fontes_citadas(texto: str) -> tuple[set[str], set[int]]:
    """Números de regra e de fonte que aparecem nas citações da resposta."""
    regras, fontes = set(), set()
    for grupo in RE_GRUPO_CITACAO.findall(texto):
        regras.update(RE_NUMERO_DE_REGRA.findall(grupo))
        fontes.update(int(n) for n in re.findall(r"F(\d{1,2})(?![\d.])", grupo))
    return regras, fontes


def metricas_automaticas(questao: dict, resposta, regras_do_crd: set[str]) -> dict:
    tem_resposta = questao["categoria"] != "fora_do_escopo"
    regras, fontes = regras_e_fontes_citadas(resposta.texto)
    esperadas_ids = set(questao["fontes_esperadas"])
    esperadas_regras = set(questao["regras_esperadas"])
    citadas = [f for f in resposta.fontes if f.numero in fontes]
    citou_certa = (
        any(f.trecho_id in esperadas_ids or set(f.regras) & esperadas_regras for f in citadas)
        or bool(regras & esperadas_regras)
    )
    conclusao = conclusao_da_resposta(resposta.texto)
    return {
        "acertou_se_respondia": resposta.encontrou == tem_resposta,
        "conclusao_esperada": questao.get("conclusao"),
        "conclusao_da_resposta": conclusao,
        "conclusao_certa": conclusao_confere(questao.get("conclusao"), conclusao),
        "citou_fonte_certa": citou_certa if tem_resposta else None,
        "regras_inventadas": sorted(regras - regras_do_crd),
        "fontes_inexistentes": sorted(n for n in fontes if n > len(resposta.fontes)),
    }


# ---------------------------------------------------------------------------
# Avaliador (LLM)
# ---------------------------------------------------------------------------

def avaliar_com_llm(avaliador, questao: dict, texto_da_resposta: str) -> dict:
    partes = []
    for h in questao.get("historico", []):
        partes += [f"(Conversa anterior) Jogador: {h['pergunta']}", f"(Conversa anterior) Juiz: {h['resposta']}"]
    partes += [f"PERGUNTA: {questao['pergunta']}", "", f"RESPOSTA ESPERADA: {questao['resposta_esperada']}", "",
               f"RESPOSTA DO JUIZ: {texto_da_resposta}"]
    bruto = avaliador.gerar(INSTRUCOES_AVALIADOR, "\n".join(partes), esquema=Avaliacao)
    avaliacao = Avaliacao.model_validate_json(bruto)
    return {"nota": avaliacao.nota, "justificativa": avaliacao.justificativa}


# ---------------------------------------------------------------------------
# Rodada de avaliação
# ---------------------------------------------------------------------------

def carregar_gabarito() -> list[dict]:
    return yaml.safe_load(config.GABARITO.read_text(encoding="utf-8"))


def arquivo_do_modelo(modelo: str):
    return config.RESULTADOS_DIR / f"respostas_{modelo}.jsonl"


def ja_avaliadas(modelo: str) -> set[str]:
    arquivo = arquivo_do_modelo(modelo)
    if not arquivo.exists():
        return set()
    return {json.loads(linha)["id"] for linha in arquivo.open(encoding="utf-8")}


def responder_com_paciencia(juiz, pergunta: str, historico, espera_erro: float = 60):
    """Chama o juiz; num erro temporário (ex.: limite POR MINUTO do tier grátis), espera e tenta de
    novo uma vez. Cota do DIA esgotada não adianta esperar: o erro sobe na hora."""
    try:
        return juiz.responder(pergunta, historico=historico)
    except CotaEsgotada:
        raise
    except Exception as erro:
        print(f"  erro temporário ({type(erro).__name__}); esperando {espera_erro:.0f} s pra tentar de novo...")
        time.sleep(espera_erro)
        return juiz.responder(pergunta, historico=historico)


def avaliar(juiz, modelo: str, questoes: list[dict], avaliador=None, regras_do_crd: set[str] | None = None,
            pausa: float = 0, espera_erro: float = 60) -> int:
    """Responde e avalia cada questão, gravando linha a linha. Devolve quantas foram avaliadas agora.

    `pausa`: segundos entre uma pergunta e outra, pra não estourar o limite por minuto da API.
    """
    config.RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
    feitas = ja_avaliadas(modelo)
    regras_do_crd = regras_do_crd if regras_do_crd is not None else set(juiz.regras)
    novas = 0
    for q in questoes:
        if q["id"] in feitas:
            continue
        if novas and pausa:
            time.sleep(pausa)
        historico = [(h["pergunta"], h["resposta"]) for h in q.get("historico", [])]
        inicio = time.perf_counter()
        try:
            resposta = responder_com_paciencia(juiz, q["pergunta"], historico, espera_erro)
        except CotaEsgotada as erro:
            print(f"\nCota esgotada em {q['id']}: {erro}\nRode de novo depois; as perguntas já feitas serão puladas.")
            break
        except Exception as erro:  # falhou de novo depois de esperar: melhor parar e tentar mais tarde
            print(f"\nErro em {q['id']}: {type(erro).__name__}: {erro}\nRode de novo depois; as feitas serão puladas.")
            break
        linha = {
            "id": q["id"], "modelo": modelo, "categoria": q["categoria"], "estilo": q["estilo"],
            "origem": q.get("origem", "escrita"), "pergunta": q["pergunta"],
            "resposta": resposta.texto, "resposta_esperada": q["resposta_esperada"],
            "encontrou": resposta.encontrou, "tipo": resposta.tipo, "busca": resposta.modelo_busca,
            "nota_busca": resposta.nota_busca, "modelo_que_respondeu": resposta.uso.get("modelo"),
            "tokens_entrada": resposta.uso.get("tokens_entrada"), "tokens_saida": resposta.uso.get("tokens_saida"),
            "segundos": round(time.perf_counter() - inicio, 1),
            "fontes_citadas": [f.trecho_id for f in resposta.fontes if f.citada],
            **metricas_automaticas(q, resposta, regras_do_crd),
        }
        if avaliador is not None:
            try:
                linha.update(avaliar_com_llm(avaliador, q, resposta.texto))
            except Exception as erro:  # cota do avaliador, sobrecarga ou JSON inválido
                print(f"Avaliador falhou em {q['id']} ({type(erro).__name__}): a nota fica em branco.")
        with arquivo_do_modelo(modelo).open("a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
        novas += 1
        print(f"{q['id']:>4} {linha.get('nota', '-'):>10}  resp.certa={linha['acertou_se_respondia']!s:5} "
              f"conclusão={linha['conclusao_certa']!s:5} fonte={linha['citou_fonte_certa']!s:5} {linha['segundos']:>5}s")
    return novas


def completar_notas(modelo: str, avaliador) -> int:
    """Dá nota às respostas que ficaram sem (o avaliador tinha falhado). Devolve quantas completou."""
    arquivo = arquivo_do_modelo(modelo)
    linhas = [json.loads(l) for l in arquivo.open(encoding="utf-8")]
    gabarito = {q["id"]: q for q in carregar_gabarito()}
    completadas = 0
    for linha in linhas:
        if linha.get("nota") or linha["id"] not in gabarito:
            continue
        try:
            linha.update(avaliar_com_llm(avaliador, gabarito[linha["id"]], linha["resposta"]))
            completadas += 1
        except Exception as erro:
            print(f"Avaliador falhou de novo em {linha['id']} ({type(erro).__name__}).")
            break
    arquivo.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in linhas), encoding="utf-8")
    return completadas


def resumir() -> pd.DataFrame:
    """Uma linha por modelo com as métricas, a partir dos arquivos respostas_*.jsonl."""
    linhas = [json.loads(l) for arq in sorted(config.RESULTADOS_DIR.glob("respostas_*.jsonl"))
              for l in arq.open(encoding="utf-8")]
    if not linhas:
        return pd.DataFrame()
    df = pd.DataFrame(linhas)
    # A conclusão é recalculada com o gabarito e o código ATUAIS: se uma resposta esperada for
    # corrigida depois (ex.: aceitar "depende" além de "não"), ou a leitura da conclusão melhorar,
    # não precisa rodar o juiz de novo.
    gabarito = {q["id"]: q for q in carregar_gabarito()}
    df["conclusao_da_resposta"] = df.resposta.map(conclusao_da_resposta)
    df["conclusao_certa"] = [conclusao_confere(gabarito.get(i, {}).get("conclusao"), c)
                             for i, c in zip(df.id, df.conclusao_da_resposta)]
    resumo = df.groupby("modelo").apply(lambda g: pd.Series({
        "perguntas": len(g),
        "acertou_se_respondia": g.acertou_se_respondia.mean(),
        "conclusao_certa": g.conclusao_certa.dropna().astype(bool).mean(),
        "citou_fonte_certa": g.citou_fonte_certa.dropna().astype(bool).mean(),
        "com_citacao_inventada": (g.regras_inventadas.str.len() + g.fontes_inexistentes.str.len() > 0).mean(),
        "nota_correta": (g.get("nota") == "correta").mean() if "nota" in g else None,
        "nota_parcial": (g.get("nota") == "parcial").mean() if "nota" in g else None,
        "nota_incorreta": (g.get("nota") == "incorreta").mean() if "nota" in g else None,
        "segundos_medio": g.segundos.mean(),
        "tokens_entrada_medio": g.tokens_entrada.dropna().mean(),
    }), include_groups=False).round(3)
    resumo.to_csv(config.RESULTADOS_DIR / "respostas_resumo.csv")
    return resumo


def gerar_revisao(modelo: str, quantidade: int = 12) -> None:
    """Escolhe respostas pra revisão humana, SEM mostrar a nota do avaliador (revisão às cegas).

    A amostra prioriza os casos difíceis, que são onde o avaliador pode errar: nota diferente de
    "correta", ou conclusão da resposta diferente da esperada. Depois completa com respostas
    "corretas" sorteadas de categorias variadas, pra ver se o avaliador também acerta as fáceis.
    """
    df = pd.read_json(arquivo_do_modelo(modelo), lines=True)
    gabarito = {q["id"]: q for q in carregar_gabarito()}
    df["conclusao_da_resposta"] = df.resposta.map(conclusao_da_resposta)
    conclusao_errada = [conclusao_confere(gabarito.get(i, {}).get("conclusao"), c) is False
                        for i, c in zip(df.id, df.conclusao_da_resposta)]
    dificil = (df.get("nota", pd.Series("", index=df.index)) != "correta") | pd.Series(conclusao_errada, index=df.index)
    faceis = df[~dificil].sample(frac=1, random_state=7).drop_duplicates("categoria")
    amostra = pd.concat([df[dificil], faceis]).head(quantidade).sample(frac=1, random_state=7)  # embaralha
    planilha = amostra[["id", "pergunta", "resposta_esperada", "resposta"]].rename(columns={"resposta": "resposta_do_juiz"})
    planilha["sua_nota (correta/parcial/incorreta)"] = ""
    planilha["comentario"] = ""
    destino = config.RAIZ / "avaliacao" / "revisao_humana.csv"
    # ";" e utf-8 com BOM: é o formato que o Excel em português abre direto, com acentos.
    planilha.to_csv(destino, sep=";", index=False, encoding="utf-8-sig")
    pagina = destino.with_suffix(".html")
    pagina.write_text(pagina_de_revisao(planilha), encoding="utf-8")
    print(f"{len(planilha)} respostas em {destino.relative_to(config.RAIZ)} (pra ler: {pagina.name}).")


NOTAS = ["correta", "parcial", "incorreta"]
COLUNA_NOTA_HUMANA = "sua_nota (correta/parcial/incorreta)"


def kappa_de_cohen(a: list[str], b: list[str], categorias: list[str]) -> float:
    """Concordância entre dois avaliadores, descontando a que aconteceria por sorte.

    kappa = (observada - esperada) / (1 - esperada). A "esperada" é a chance de os dois darem a
    mesma nota se cada um sorteasse as notas nas proporções que costuma usar. 1 = concordância
    perfeita, 0 = igual ao acaso, negativo = pior que o acaso.
    """
    n = len(a)
    observada = sum(x == y for x, y in zip(a, b)) / n
    esperada = sum((a.count(c) / n) * (b.count(c) / n) for c in categorias)
    return 1.0 if esperada == 1 else (observada - esperada) / (1 - esperada)


def concordancia(modelo: str) -> dict:
    """Compara as notas da revisão humana com as do avaliador LLM, nas mesmas respostas."""
    humano = pd.read_csv(config.RAIZ / "avaliacao" / "revisao_humana.csv", sep=";", encoding="utf-8-sig")
    humano = humano.rename(columns={COLUNA_NOTA_HUMANA: "humano"})
    humano["humano"] = humano.humano.fillna("").str.strip().str.lower()
    humano = humano[humano.humano.isin(NOTAS)]
    llm = pd.read_json(arquivo_do_modelo(modelo), lines=True)[["id", "nota"]].rename(columns={"nota": "avaliador"})
    df = humano[["id", "humano"]].merge(llm, on="id").dropna(subset=["avaliador"])
    h, a = df.humano.tolist(), df.avaliador.tolist()
    matriz = pd.crosstab(pd.Categorical(h, NOTAS), pd.Categorical(a, NOTAS),
                         rownames=["humano"], colnames=["avaliador"], dropna=False)
    ordem = {nota: i for i, nota in enumerate(NOTAS)}  # 0 = correta ... 2 = incorreta
    diferenca = [ordem[y] - ordem[x] for x, y in zip(h, a)]
    return {
        "respostas": len(df),
        "concordancia_exata": sum(x == y for x, y in zip(h, a)) / len(df),
        "kappa": kappa_de_cohen(h, a, NOTAS),
        # Pergunta mais simples: os dois concordam se a resposta está "correta" ou não?
        "concordancia_correta_ou_nao": sum((x == "correta") == (y == "correta") for x, y in zip(h, a)) / len(df),
        "avaliador_mais_severo": [i for i, d in zip(df.id, diferenca) if d > 0],
        "avaliador_mais_brando": [i for i, d in zip(df.id, diferenca) if d < 0],
        "matriz": matriz,
        "detalhe": df,
    }


def pagina_de_revisao(planilha: pd.DataFrame) -> str:
    """Página simples pra ler as respostas com calma (célula de Excel é ruim pra texto longo)."""
    from html import escape

    cartoes = []
    for i, linha in enumerate(planilha.itertuples(index=False), start=1):
        cartoes.append(
            f'<section><h2>{i}. <code>{escape(linha.id)}</code> {escape(linha.pergunta)}</h2>'
            f'<div class="lado"><div><h3>Resposta esperada</h3><p>{escape(linha.resposta_esperada)}</p></div>'
            f'<div><h3>Resposta do juiz</h3><p>{escape(linha.resposta_do_juiz)}</p></div></div></section>'
        )
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Revisão das respostas</title>
<style>
:root {{ --fundo:#fcfcfb; --texto:#1b1b1a; --suave:#5c5b57; --borda:#e4e3df; --cartao:#ffffff; }}
@media (prefers-color-scheme: dark) {{ :root {{ --fundo:#1a1a19; --texto:#f2f1ec; --suave:#b5b4ab; --borda:#3a3936; --cartao:#232321; }} }}
body {{ background:var(--fundo); color:var(--texto); font:16px/1.55 system-ui, sans-serif; margin:0 auto; max-width:1100px; padding:24px 16px; }}
h1 {{ font-size:1.5rem; margin:0 0 4px; }} .ajuda {{ color:var(--suave); margin:0 0 24px; }}
section {{ background:var(--cartao); border:1px solid var(--borda); border-radius:10px; padding:16px 20px; margin:0 0 16px; }}
h2 {{ font-size:1.05rem; margin:0 0 12px; }} h3 {{ font-size:.8rem; text-transform:uppercase; letter-spacing:.04em; color:var(--suave); margin:0 0 6px; }}
.lado {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }} p {{ margin:0; white-space:pre-wrap; }}
@media (max-width:720px) {{ .lado {{ grid-template-columns:1fr; }} }}
</style></head><body>
<h1>Revisão das respostas do juiz</h1>
<p class="ajuda">Pra cada pergunta, compare a resposta do juiz com a esperada e dê uma nota: <b>correta</b>
(mesma conclusão, nada que contradiga), <b>parcial</b> (conclusão certa, mas falta algo importante ou tem um erro
secundário) ou <b>incorreta</b> (conclusão diferente ou afirma algo errado). Estilo e tamanho não contam.</p>
{"".join(cartoes)}</body></html>"""


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Avalia as respostas do juiz com o gabarito.")
    parser.add_argument("--modelo", default=config.MODELO_LLM, help="LLM que responde (sem reserva)")
    parser.add_argument("--comparacao", action="store_true", help="só as perguntas de config.IDS_COMPARACAO")
    parser.add_argument("--ids", nargs="+", help="só estas perguntas")
    parser.add_argument("--sem-avaliador", action="store_true", help="só as métricas automáticas")
    parser.add_argument("--revisao", metavar="MODELO", help="gera a planilha de revisão humana")
    parser.add_argument("--completar-notas", metavar="MODELO", help="dá nota às respostas que ficaram sem")
    parser.add_argument("--resumo", action="store_true", help="só recalcula o resumo")
    parser.add_argument("--pausa", type=float, default=4, help="segundos entre perguntas (limite por minuto)")
    parser.add_argument("--busca", help="usa só esta busca (ex.: e5-small, quando a cota do Gemini acabou)")
    parser.add_argument("--rotulo", help="nome dos resultados (padrão: o nome do modelo)")
    parser.add_argument("--concordancia", metavar="MODELO", help="compara a revisão humana com o avaliador")
    args = parser.parse_args()

    if args.concordancia:
        c = concordancia(args.concordancia)
        print(f"{c['respostas']} respostas revisadas | concordância exata {c['concordancia_exata']:.0%} | "
              f"kappa {c['kappa']:.2f} | correta ou não {c['concordancia_correta_ou_nao']:.0%}")
        print(f"avaliador mais severo em {c['avaliador_mais_severo']}; mais brando em {c['avaliador_mais_brando']}")
        print("\n" + c["matriz"].to_string())
        return
    if args.revisao:
        gerar_revisao(args.revisao)
        return
    if args.completar_notas:
        n = completar_notas(args.completar_notas, LLMGemini(modelos=[config.MODELO_AVALIADOR]))
        print(f"{n} notas completadas.")
    elif not args.resumo:
        from juiz.responder import Juiz

        ids = set(args.ids or (config.IDS_COMPARACAO if args.comparacao else []))
        questoes = [q for q in carregar_gabarito() if not ids or q["id"] in ids]
        juiz = Juiz.padrao()
        juiz.llm = LLMGemini(modelos=[args.modelo])  # sem reserva: queremos a qualidade DESTE modelo
        if args.busca:
            juiz.buscas = [b for b in juiz.buscas if b.nome == args.busca]
        rotulo = args.rotulo or args.modelo
        avaliador = None if args.sem_avaliador else LLMGemini(modelos=[config.MODELO_AVALIADOR])
        print(f"Avaliando {len(questoes)} perguntas com {args.modelo}, busca {[b.nome for b in juiz.buscas]} "
              f"(avaliador: {config.MODELO_AVALIADOR}); resultados: respostas_{rotulo}.jsonl")
        avaliar(juiz, rotulo, questoes, avaliador, pausa=args.pausa)
    print("\n" + resumir().to_string())


if __name__ == "__main__":
    main()

"""Gera as explicações das cartas (a ficha que abre ao tocar numa carta no site) com um LLM local.

Quem escreve é um LLM rodando no seu computador, pelo Ollama: não gasta a cota do Gemini, que fica
só pro juiz do site. O site não gera explicações; ele mostra as que este comando guardou no banco.

Antes, uma vez:
    1. Instale o Ollama (https://ollama.com) e baixe o modelo: ollama pull qwen3:30b-a3b
    2. No .env, as variáveis do Turso (TURSO_DATABASE_URL e TURSO_AUTH_TOKEN), pra gravar no mesmo
       banco que o site usa.

Rodar (a partir da raiz do projeto):
    python -m api.gerar_explicacoes                       # todas as que faltam
    python -m api.gerar_explicacoes --limite 20           # só 20 nesta rodada
    python -m api.gerar_explicacoes --carta "Jinx, Rebel" --refazer
    python -m api.gerar_explicacoes --modelo gemma3:12b   # outro modelo do Ollama

Antes de guardar, cada explicação passa por uma conferência (juiz/fichas.py, Fichario.problemas): termo do
jogo traduzido ("feitiço", "lixo"), outra carta citada, fonte que não existe ou "cuidado" que não vem do
FAQ fazem o modelo escrever de novo, com os erros apontados. Depois de 3 tentativas, a carta fica de fora
(não vai pro site) e o comando segue pras outras.

Pode parar (Ctrl+C) e rodar de novo quando quiser: ele pula as cartas que já têm explicação com a
mesma assinatura, e as cartas dos decks (meus e do meta) vêm primeiro. Quando o texto de uma carta
muda (errata) ou o FAQ ganha dúvidas novas sobre ela, a assinatura muda e a carta volta pra fila.

Por que não o e5-small (a busca reserva, que também roda no computador): ele só transforma texto em
vetores pra busca; não escreve texto.
"""

import argparse
import sys

from juiz import config
from juiz.erros import explicar_erro
from juiz.fichas import ExplicacaoRuim, Fichario, explicacao_guardada, guardar_explicacao


def ordem_das_cartas(banco, nomes: list[str]) -> list[str]:
    """As cartas dos decks primeiro (são as que mais vão ser abertas), depois as outras, em ordem alfabética."""
    nos_decks = {l["carta"] for l in banco.consultar("SELECT DISTINCT carta FROM deck_cartas")}
    return sorted(nomes, key=lambda n: (n not in nos_decks, n))


def gerar(fichario: Fichario, banco, cartas: list[str], limite: int | None = None, refazer: bool = False,
          log=print) -> dict:
    """Gera e guarda as explicações que faltam, uma por uma (cada uma fica salva assim que sai)."""
    feitas = falhas = reprovadas = 0
    pendentes = [n for n in cartas if fichario.ficha(n).texto
                 and (refazer or not explicacao_guardada(banco, n, fichario.assinatura(n)))]
    log(f"{len(cartas) - len(pendentes)} cartas já têm explicação (ou não têm texto); faltam {len(pendentes)}.")
    for i, nome in enumerate(pendentes[:limite], start=1):
        try:
            explicacao = fichario.explicar(nome)
        except ExplicacaoRuim as erro:  # o modelo errou até depois de corrigido: a carta fica de fora, as outras seguem
            reprovadas += 1
            log(f"  ✗ {nome}: reprovada na conferência ({erro})")
            continue
        except Exception as erro:
            falhas += 1
            log(f"  ✗ {nome}: {explicar_erro(erro)}")
            if falhas >= 3 and feitas == 0:
                log("Três falhas seguidas sem nenhum acerto: parando (o Ollama está aberto, com o modelo baixado?).")
                break
            continue
        guardar_explicacao(banco, nome, explicacao)
        feitas += 1
        log(f"  ✓ [{i}/{len(pendentes[:limite])}] {nome}")
    restantes = len(pendentes) - feitas
    log(f"Pronto: {feitas} geradas agora, {restantes} ainda faltam"
        + (f" ({reprovadas} reprovadas na conferência: rode de novo: a reprovada volta pra fila)."
           if reprovadas else "."))
    return {"feitas": feitas, "falhas": falhas, "reprovadas": reprovadas, "restantes": restantes}


def main() -> None:
    from api.recursos import carregar_juiz
    from decks.banco import abrir_banco
    from juiz.llm import LLMOllama

    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Gera as explicações das cartas com um LLM local (Ollama).")
    parser.add_argument("--modelo", default=config.MODELO_OLLAMA, help=f"modelo do Ollama (padrão {config.MODELO_OLLAMA})")
    parser.add_argument("--limite", type=int, help="no máximo N cartas nesta rodada")
    parser.add_argument("--carta", action="append", help="só esta carta (pode repetir)")
    parser.add_argument("--refazer", action="store_true", help="gera de novo mesmo se já existir")
    args = parser.parse_args()

    juiz = carregar_juiz()
    banco = abrir_banco()
    banco.criar_tabelas()
    print(f"Banco: {banco.onde} · modelo: {args.modelo}")
    fichario = Fichario.do_juiz(juiz)
    fichario.llm = LLMOllama(args.modelo)
    cartas = args.carta or ordem_das_cartas(banco, list(fichario.catalogo.cartas))
    try:
        gerar(fichario, banco, cartas, limite=args.limite, refazer=args.refazer)
    except KeyboardInterrupt:
        print("\nParado. As que já saíram estão guardadas; rode de novo pra continuar.")


if __name__ == "__main__":
    main()

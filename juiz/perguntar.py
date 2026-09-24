"""Pergunte ao juiz pelo terminal (etapa 5).

Uso (a partir da raiz do projeto):
    python -m juiz.perguntar "posso usar emboscada na base?"
    python -m juiz.perguntar "..." --detalhes      # mostra também notas da busca e tokens gastos
    python -m juiz.perguntar --chat                # conversa: várias perguntas seguidas, com memória
"""

import argparse
import sys

from juiz.responder import Juiz, Resposta


def mostrar(resposta: Resposta, detalhes: bool) -> None:
    print(resposta.texto)
    if resposta.fontes:
        print("\nFontes:")
        for f in resposta.fontes:
            marca = "*" if f.citada else " "
            print(f" {marca}[F{f.numero}] {f.resumo or f.titulo}\n       {f.url}")
        print("  (* = citada na resposta)")
    regras = resposta.regras_citadas()
    if regras:
        print("\nRegras do Core Rules citadas:")
        for numero, url in regras.items():
            print(f"  {numero}: {url}")

    if detalhes:
        print(f"\nTipo: {resposta.tipo} · busca: {resposta.modelo_busca} · nota do 1º resultado: {resposta.nota_busca}")
        if resposta.termos:
            print("Termos do glossário: " + ", ".join(f"{pt} -> {en}" for pt, en in resposta.termos))
        if resposta.uso:
            print(f"Tokens: {resposta.uso}")


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Pergunte ao Juiz Riftbound.")
    parser.add_argument("pergunta", nargs="?", help="a pergunta (sem ela, abre o modo conversa)")
    parser.add_argument("--chat", action="store_true", help="modo conversa: várias perguntas seguidas, com memória")
    parser.add_argument("--detalhes", action="store_true", help="mostra a busca por dentro")
    args = parser.parse_args()

    juiz = Juiz.padrao()
    if args.pergunta and not args.chat:
        mostrar(juiz.responder(args.pergunta), args.detalhes)
        return

    print("Modo conversa: o juiz lembra das últimas perguntas. Enter vazio pra sair.")
    historico: list[tuple[str, str]] = []
    pergunta = args.pergunta
    while True:
        pergunta = pergunta or input("\nVocê: ").strip()
        if not pergunta:
            break
        resposta = juiz.responder(pergunta, historico=historico)
        print()
        mostrar(resposta, args.detalhes)
        historico.append((pergunta, resposta.texto))
        pergunta = None


if __name__ == "__main__":
    main()

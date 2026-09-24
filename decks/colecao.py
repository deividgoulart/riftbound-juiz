"""Minha coleção de cartas (fase 2): quantas cópias eu tenho de cada carta.

Uso pelo terminal (a partir da raiz do projeto):
    python -m decks.colecao exportar colecao.csv     # backup (ou pra editar numa planilha)
    python -m decks.colecao importar colecao.csv     # define as quantidades das cartas do arquivo
    python -m decks.colecao importar export.csv --substituir   # coleção = exatamente o arquivo
    python -m decks.colecao definir "Jinx, Rebel" 2

O CSV tem duas colunas, carta e quantidade. Aceita vírgula ou ponto e vírgula (o Excel em português
salva com ponto e vírgula) e os cabeçalhos em inglês (name, quantity).

Também aceita direto a exportação de coleção da Liga Riftbound (ligariftbound.com.br): a carta é achada
pelo código ("Edicao (Sigla)" + "Card #", ex.: OGN + 42) e, se ele não for conhecido, pelo nome da coluna
"Card (EN)" (ou "Card (PT)", se a em inglês estiver vazia). A mesma carta aparece em várias
linhas, uma por qualidade, idioma ou foil. Por isso, linhas da mesma carta somam.

Importar define a quantidade de cada carta do arquivo; as que não estão nele ficam como estavam. Com
--substituir (ou a opção na tela), a coleção passa a ser exatamente a do arquivo: útil com a
exportação completa da Liga, em que uma carta vendida some do arquivo.
"""

import argparse
import csv
import io
import sys
from dataclasses import dataclass, field
from pathlib import Path

from decks.banco import Banco
from decks.catalogo import Catalogo

# Em ordem de preferência: o catálogo é em inglês, então o nome em português da Liga é só reserva.
COLUNAS_CARTA = ("carta", "nome", "name", "card", "card name", "card (en)", "card (pt)")
COLUNAS_QUANTIDADE = ("quantidade", "qtd", "quantity", "qty", "count", "copies")


def listar(banco: Banco) -> dict[str, int]:
    return {l["carta"]: l["quantidade"] for l in banco.consultar("SELECT carta, quantidade FROM colecao ORDER BY carta")}


def _comando(carta: str, quantidade: int) -> tuple[str, tuple]:
    if quantidade <= 0:
        return "DELETE FROM colecao WHERE carta = ?", (carta,)
    return "INSERT OR REPLACE INTO colecao (carta, quantidade) VALUES (?, ?)", (carta, quantidade)


def salvar_alteracoes(banco: Banco, mudancas: dict[str, int]) -> None:
    """Grava várias quantidades de uma vez (0 tira a carta da coleção)."""
    if mudancas:
        banco.lote([_comando(carta, int(qtd)) for carta, qtd in mudancas.items()])


def definir(banco: Banco, carta: str, quantidade: int) -> None:
    salvar_alteracoes(banco, {carta: quantidade})


@dataclass
class RelatorioImportacao:
    importadas: dict[str, int] = field(default_factory=dict)
    desconhecidas: list[tuple[str, list[str]]] = field(default_factory=list)  # (nome, sugestões)
    invalidas: list[str] = field(default_factory=list)  # linhas com quantidade que não é número


def _colunas(cabecalho: list[str], opcoes: tuple[str, ...]) -> list[int]:
    """Posições das colunas do cabeçalho que estão em `opcoes`, na ordem de preferência."""
    normal = [c.strip().lower() for c in cabecalho]
    return [normal.index(o) for o in opcoes if o in normal]


def ler_csv(texto: str, catalogo: Catalogo) -> RelatorioImportacao:
    """Lê o CSV e reconhece os nomes. Não grava nada: veja importar_csv."""
    texto = texto.lstrip("﻿")  # o Excel põe um BOM no começo
    try:
        dialeto = csv.Sniffer().sniff(texto.splitlines()[0] if texto.strip() else ",", delimiters=",;\t")
    except csv.Error:
        dialeto = csv.excel
    linhas = [l for l in csv.reader(io.StringIO(texto), dialeto) if any(c.strip() for c in l)]
    relatorio = RelatorioImportacao()
    if not linhas:
        return relatorio
    i_cartas, i_qtds = _colunas(linhas[0], COLUNAS_CARTA), _colunas(linhas[0], COLUNAS_QUANTIDADE)
    i_sigla, i_numero = _colunas(linhas[0], ("edicao (sigla)",)), _colunas(linhas[0], ("card #",))  # Liga
    if not i_cartas or not i_qtds:  # sem cabeçalho: carta, quantidade
        i_cartas, i_qtd, i_sigla, i_numero = [0], 1, [], []
    else:
        i_qtd = i_qtds[0]
        linhas = linhas[1:]
    for linha in linhas:
        nome = next((linha[i].strip() for i in i_cartas if i < len(linha) and linha[i].strip()), "")
        qtd = linha[i_qtd].strip() if i_qtd < len(linha) else ""
        if not nome or not qtd.isdigit():
            relatorio.invalidas.append(";".join(linha))
            continue
        # Pelo código (Liga: "OGN" + "42") quando o arquivo tem, que não depende de como o nome foi escrito
        codigo = (f"{linha[i_sigla[0]]}-{linha[i_numero[0]]}"
                  if i_sigla and i_numero and max(i_sigla[0], i_numero[0]) < len(linha) else None)
        oficial = catalogo.por_codigo(codigo) or catalogo.resolver(nome)
        if oficial is None:
            relatorio.desconhecidas.append((nome, catalogo.sugestoes(nome)))
        else:  # a mesma carta em várias linhas (qualidade, idioma, foil) soma
            relatorio.importadas[oficial] = relatorio.importadas.get(oficial, 0) + int(qtd)
    return relatorio


def importar_csv(banco: Banco, catalogo: Catalogo, texto: str, substituir: bool = False) -> RelatorioImportacao:
    """Grava as quantidades do arquivo. Com substituir=True, as cartas fora do arquivo saem da coleção
    (na mesma transação: se algo falhar, a coleção antiga continua)."""
    relatorio = ler_csv(texto, catalogo)
    comandos = [("DELETE FROM colecao", ())] if substituir else []
    comandos += [_comando(carta, qtd) for carta, qtd in relatorio.importadas.items()]
    if comandos:
        banco.lote(comandos)
    return relatorio


def exportar_csv(banco: Banco) -> str:
    saida = io.StringIO()
    escritor = csv.writer(saida, lineterminator="\n")
    escritor.writerow(["carta", "quantidade"])
    escritor.writerows(listar(banco).items())
    return saida.getvalue()


def main() -> None:
    from decks.banco import abrir_banco
    from decks.catalogo import preparar

    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Importa, exporta ou altera a coleção de cartas.")
    sub = parser.add_subparsers(dest="acao", required=True)
    importar_ = sub.add_parser("importar")
    importar_.add_argument("arquivo")
    importar_.add_argument("--substituir", action="store_true",
                           help="a coleção passa a ser exatamente a do arquivo (cartas fora dele saem)")
    sub.add_parser("exportar").add_argument("arquivo", nargs="?")
    definir_ = sub.add_parser("definir")
    definir_.add_argument("carta")
    definir_.add_argument("quantidade", type=int)
    args = parser.parse_args()

    banco = abrir_banco()
    catalogo = preparar(banco)
    print(f"Banco: {banco.onde}")
    if args.acao == "importar":
        r = importar_csv(banco, catalogo, Path(args.arquivo).read_text(encoding="utf-8-sig"), substituir=args.substituir)
        print(f"{len(r.importadas)} cartas importadas.")
        for nome, sugestoes in r.desconhecidas:
            print(f"  Não reconheci \"{nome}\"" + (f" (quis dizer {' / '.join(sugestoes)}?)" if sugestoes else ""))
        for linha in r.invalidas:
            print(f"  Linha ignorada (quantidade inválida): {linha}")
    elif args.acao == "exportar":
        texto = exportar_csv(banco)
        if args.arquivo:
            Path(args.arquivo).write_text(texto, encoding="utf-8")
            print(f"Coleção salva em {args.arquivo}")
        else:
            print(texto, end="")
    else:
        oficial = catalogo.resolver(args.carta)
        if oficial is None:
            sugestoes = catalogo.sugestoes(args.carta)
            sys.exit(f"Não reconheci \"{args.carta}\"." + (f" Quis dizer {' / '.join(sugestoes)}?" if sugestoes else ""))
        definir(banco, oficial, args.quantidade)
        print(f"{oficial}: {max(args.quantidade, 0)}")


if __name__ == "__main__":
    main()

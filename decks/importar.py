"""Importação manual de deck (fase 2): lê a lista em texto que os sites de deck exportam.

Formatos de linha aceitos:
    3 Jinx, Rebel          3x Jinx, Rebel          Jinx, Rebel x3          Jinx, Rebel
(sem número, conta 1 cópia). Linhas vazias e comentários (# ou //) são ignorados.

Cabeçalhos de seção (em inglês ou português, com ou sem ":" e contagem, como "Main Deck (40):")
dizem onde as cartas entram: lenda, campeão, deck principal, battlefields, runas e sideboard. Sem
cabeçalho, a seção vem do tipo da carta (lenda, battlefield, runa; o resto vai pro principal).

A lista é conferida com as regras de construção do Core Rules (CRD 103.2), mas só como aviso:
um deck em construção pode estar incompleto de propósito.
"""

import re
from dataclasses import dataclass, field

from decks.catalogo import Catalogo, chave

SECOES = {  # como aparece no cabeçalho (já passado por catalogo.chave) -> seção
    "legend": "lenda", "champion legend": "lenda", "lenda": "lenda",
    "champion": "campeao", "chosen champion": "campeao", "campeao": "campeao", "campeao escolhido": "campeao",
    "main": "principal", "main deck": "principal", "maindeck": "principal", "deck": "principal",
    "deck principal": "principal", "principal": "principal",
    "battlefield": "battlefields", "battlefields": "battlefields", "campo de batalha": "battlefields",
    "campos de batalha": "battlefields",
    "rune": "runas", "runes": "runas", "rune deck": "runas", "runa": "runas", "runas": "runas",
    "sideboard": "sideboard", "side": "sideboard", "side deck": "sideboard",
}
NOMES_DAS_SECOES = {"lenda": "Lenda", "campeao": "Campeão escolhido", "principal": "Deck principal",
                    "battlefields": "Battlefields", "runas": "Runas", "sideboard": "Sideboard"}
SECAO_PELO_TIPO = {"Legend": "lenda", "Battlefield": "battlefields", "Rune": "runas"}

# Regras de construção (CRD 103.2)
MINIMO_PRINCIPAL = 40  # Main Deck com pelo menos 40 cartas, contando o Chosen Champion
MAXIMO_COPIAS = 3  # cartas com o mesmo nome no Main Deck (o Chosen Champion conta)
RUNAS_NO_DECK = 12

_QTD_ANTES = re.compile(r"^(\d+)\s*[xX]?\s+(.+)$")
_QTD_DEPOIS = re.compile(r"^(.+?)\s+[xX]\s*(\d+)$")


@dataclass
class ListaDeDeck:
    cartas: dict[tuple[str, str], int] = field(default_factory=dict)  # (seção, carta) -> cópias
    nao_reconhecidas: list[tuple[str, list[str]]] = field(default_factory=list)  # (texto, sugestões)
    avisos: list[str] = field(default_factory=list)

    def total(self, *secoes: str) -> int:
        return sum(q for (s, _), q in self.cartas.items() if s in secoes)


def _secao_do_cabecalho(linha: str) -> str | None:
    texto = re.sub(r"[\(\[]?\d+[\)\]]?", "", linha).strip().rstrip(":").strip()
    return SECOES.get(chave(texto))


def _ler_linha(linha: str) -> tuple[str, int]:
    if m := _QTD_ANTES.match(linha):
        return m.group(2).strip(), int(m.group(1))
    if m := _QTD_DEPOIS.match(linha):
        return m.group(1).strip(), int(m.group(2))
    return linha, 1


def ler_lista(texto: str, catalogo: Catalogo) -> ListaDeDeck:
    lista = ListaDeDeck()
    secao = None
    for bruta in texto.splitlines():
        linha = bruta.strip()
        if not linha or linha.startswith(("#", "//")):
            continue
        if (nova := _secao_do_cabecalho(linha)) is not None:
            secao = nova
            continue
        nome, quantidade = _ler_linha(linha)
        oficial = catalogo.resolver(nome)
        if oficial is None:
            if linha.endswith(":"):
                lista.avisos.append(f"Cabeçalho desconhecido ignorado: \"{linha}\".")
            else:
                lista.nao_reconhecidas.append((nome, catalogo.sugestoes(nome)))
            continue
        if quantidade <= 0:
            continue
        tipo = catalogo.cartas[oficial].tipo_principal
        destino = secao if secao == "sideboard" else SECAO_PELO_TIPO.get(tipo, secao or "principal")
        if destino in SECAO_PELO_TIPO.values() and tipo not in SECAO_PELO_TIPO:
            destino = "principal"  # ex.: uma unidade debaixo de "Runes:" por engano
        lista.cartas[(destino, oficial)] = lista.cartas.get((destino, oficial), 0) + quantidade
    lista.avisos.extend(conferir_regras(lista))
    return lista


def conferir_regras(lista: ListaDeDeck) -> list[str]:
    """Avisos das regras de construção (CRD 103.2). Não impedem salvar o deck."""
    avisos = []
    lendas = lista.total("lenda")
    if lendas != 1:
        avisos.append(f"O deck precisa de 1 lenda (Champion Legend), e a lista tem {lendas}.")
    principal = lista.total("principal", "campeao")
    if principal < MINIMO_PRINCIPAL:
        avisos.append(f"O deck principal tem {principal} cartas; o mínimo é {MINIMO_PRINCIPAL}, contando o campeão escolhido.")
    copias: dict[str, int] = {}
    for (s, carta), q in lista.cartas.items():
        if s in ("principal", "campeao"):
            copias[carta] = copias.get(carta, 0) + q
    for carta, q in sorted(copias.items()):
        if q > MAXIMO_COPIAS:
            avisos.append(f"{carta}: {q} cópias; o máximo é {MAXIMO_COPIAS} por nome.")
    runas = lista.total("runas")
    if runas != RUNAS_NO_DECK:
        avisos.append(f"O Rune Deck tem {runas} runas; precisa ter {RUNAS_NO_DECK}.")
    return avisos

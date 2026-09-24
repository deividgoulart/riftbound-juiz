"""Glossário português -> inglês (etapa 5): acha termos do jogo escritos em português na pergunta.

Exemplo:
    >>> encontrar_termos("posso usar emboscada na base?")
    [("emboscada", "Ambush")]
    >>> expandir_pergunta("posso usar emboscada na base?")
    "posso usar emboscada na base? (Ambush)"

A lista de termos fica em juiz/glossario.yaml, pra dar pra editar sem mexer no código.
"""

import re
import unicodedata
from functools import lru_cache

import yaml

from juiz import config


def normalizar(texto: str) -> str:
    """Minúsculas e sem acento: "Confrontó" -> "confronto"."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).lower()


@lru_cache
def _padroes(caminho: str = str(config.GLOSSARIO)) -> list[tuple[re.Pattern, str]]:
    """Uma expressão regular por forma em português, das mais longas pras mais curtas."""
    itens = yaml.safe_load(open(caminho, encoding="utf-8"))
    padroes = []
    for item in itens:
        for forma in item["pt"]:
            forma = normalizar(forma)
            corpo = re.escape(forma.rstrip("*")) + (r"\w*" if forma.endswith("*") else "")
            padroes.append((len(forma), re.compile(rf"(?<!\w){corpo}(?!\w)"), item["en"]))
    # Mais longas primeiro: "pilha de descarte" (Trash) tem que ganhar de "pilha" (Chain).
    return [(p, en) for _, p, en in sorted(padroes, key=lambda x: -x[0])]


def encontrar_termos(pergunta: str) -> list[tuple[str, str]]:
    """Lista de (como apareceu na pergunta, termo oficial em inglês), sem repetir o termo."""
    texto = normalizar(pergunta)
    achados: dict[str, str] = {}
    for padrao, en in _padroes():
        for m in padrao.finditer(texto):
            if en not in achados:
                achados[en] = m.group(0)
        # Apaga o trecho já reconhecido pra ele não ser lido de novo por um termo mais curto.
        texto = padrao.sub(lambda m: " " * len(m.group(0)), texto)
    ordem = {en: normalizar(pergunta).find(pt) for en, pt in achados.items()}
    return [(achados[en], en) for en in sorted(achados, key=ordem.get)]


def expandir_pergunta(pergunta: str) -> str:
    """Acrescenta os termos oficiais em inglês no fim da pergunta (usado só na busca)."""
    termos = [en for _, en in encontrar_termos(pergunta)]
    return f"{pergunta} ({', '.join(termos)})" if termos else pergunta

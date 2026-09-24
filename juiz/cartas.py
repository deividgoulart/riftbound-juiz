"""Catálogo de cartas (etapa 5): texto oficial de cada carta, já com a errata aplicada.

Fonte: sources/card-catalog.json e sources/card-errata.json do repositório do FAQ.
O catálogo já traz o texto corrigido na maioria das cartas com errata, mas não em todas.
Por isso aplicamos a errata aqui: se o texto antigo ainda está no catálogo, trocamos pelo novo.

Como as cartas são encontradas na pergunta:
- nomes completos ("Irelia, Fervent", "Hextech Ray"): em qualquer caixa ("irelia, fervent");
- nome curto de campeão ("Irelia"): também em qualquer caixa, e traz todas as versões;
- nomes de uma palavra ou muito curtos ("Flash", "Buff", "Vi"): só com inicial maiúscula,
  porque "buff", "block" e "vi" (de "eu vi") são palavras comuns numa pergunta.
"""

import json
import re
from functools import cached_property
from urllib.parse import quote

from juiz import config
from juiz.glossario import normalizar

URL_WIKI = "https://wiki.leagueoflegends.com/en-us/Riftbound:"  # mesmo link que o FAQ usa


def url_da_carta(nome: str) -> str:
    return URL_WIKI + quote(nome, safe="-_.!~*'()").replace("%20", "_")


def aplicar_errata(carta: dict, mudancas: list[dict]) -> dict:
    """Troca o texto antigo pelo novo, se o catálogo ainda estiver com o antigo."""
    carta = dict(carta, errata=True)
    for campo in ("abilities", "effects"):
        texto = carta.get(campo) or ""
        for m in mudancas:
            if m["oldText"] in texto:
                texto = texto.replace(m["oldText"], m["newText"])
        carta[campo] = texto or None
    return carta


def formatar_carta(carta: dict) -> str:
    """Texto da carta pro LLM, com os atributos em inglês, como na carta de verdade."""
    atributos = [f"Type: {' '.join(carta['superTypes'] + carta['cardTypes'])}"]
    if carta["domains"]:
        atributos.append(f"Domain: {', '.join(carta['domains'])}")
    if carta["energyCost"] is not None:
        atributos.append(f"Energy cost: {carta['energyCost']}")
    if carta["powerCost"] is not None:
        atributos.append(f"Power cost: {carta['powerCost']}")
    if carta["might"] is not None:
        atributos.append(f"Might: {carta['might']}")
    if carta["tags"]:
        atributos.append(f"Tags: {', '.join(carta['tags'])}")
    linhas = [f"{carta['name']} ({' · '.join(atributos)})"]
    for campo in ("abilities", "effects"):
        if carta.get(campo):
            linhas.append(carta[campo])
    if carta.get("errata"):
        linhas.append("(Esta carta recebeu errata; o texto acima já é o atualizado.)")
    return "\n".join(linhas)


class Catalogo:
    def __init__(self, cartas: list[dict], erratas: dict[str, list[dict]]):
        self.cartas = {
            c["name"]: aplicar_errata(c, erratas[c["name"]]) if c["name"] in erratas else c
            for c in cartas
        }

    @classmethod
    def carregar(cls) -> "Catalogo":
        fontes = config.FAQ_SOURCES_DIR
        cartas = json.loads((fontes / "card-catalog.json").read_text(encoding="utf-8"))
        erratas = json.loads((fontes / "card-errata.json").read_text(encoding="utf-8"))
        return cls(cartas, erratas)

    @cached_property
    def _padroes(self) -> list[tuple[re.Pattern, list[str], bool]]:
        """(expressão, cartas que ela indica, se exige a caixa exata), dos nomes mais longos pros mais curtos."""
        nomes: dict[str, list[str]] = {}
        for nome in self.cartas:
            nomes.setdefault(nome, []).append(nome)
            if "," in nome:  # "Irelia, Fervent" -> também "Irelia"
                nomes.setdefault(nome.split(",")[0], []).append(nome)
        padroes = []
        for apelido, cartas in nomes.items():
            exige_maiuscula = " " not in apelido.strip() and ("," not in apelido) and (
                apelido in self.cartas or len(apelido) < 4  # nome de 1 palavra ou curto demais
            )
            corpo = re.escape(apelido if exige_maiuscula else normalizar(apelido))
            padroes.append((len(apelido), re.compile(rf"(?<!\w){corpo}(?!\w)"), cartas, exige_maiuscula))
        return [(p, c, e) for _, p, c, e in sorted(padroes, key=lambda x: -x[0])]

    def encontrar(self, texto: str) -> list[str]:
        """Nomes das cartas citadas no texto, na ordem em que aparecem."""
        normal, original = normalizar(texto), texto
        if len(normal) != len(original):  # caractere raro que muda de tamanho ao normalizar
            original = normal
        achadas: list[tuple[int, str]] = []
        for padrao, cartas, exige_maiuscula in self._padroes:
            for inicio, fim in [m.span() for m in padrao.finditer(original if exige_maiuscula else normal)]:
                achadas.extend((inicio, c) for c in cartas)
                # Apaga o que já foi reconhecido (nas duas versões do texto): "Irelia, Fervent"
                # não pode contar de novo como "Irelia".
                branco = " " * (fim - inicio)
                normal = normal[:inicio] + branco + normal[fim:]
                original = original[:inicio] + branco + original[fim:]
        return list(dict.fromkeys(c for _, c in sorted(achadas)))

    def texto(self, nome: str) -> str:
        return formatar_carta(self.cartas[nome])

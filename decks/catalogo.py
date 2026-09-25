"""Catálogo de cartas do deck builder (fase 2): a tabela mestre que a coleção e os decks usam.

Fonte: sources/card-catalog.json do repositório do FAQ (o mesmo do juiz, baixado por juiz.atualizar).
O nome da carta é a chave: é único no catálogo e é o que as listas de deck usam.

Duas coisas que o catálogo não resolve sozinho:
- Não tem as runas básicas (Fury Rune, Calm Rune...), que entram no Rune Deck. Elas são acrescentadas
  aqui (config.RUNAS_BASICAS).
- As lendas aparecem só com o título ("Loose Cannon", com a tag "Jinx"), mas as listas exportadas
  pelos sites costumam escrever "Jinx, Loose Cannon" ou "Jinx - Loose Cannon". As duas formas viram
  apelidos da lenda.

Quando um nome não é reconhecido, o catálogo sugere os parecidos, mas nunca escolhe sozinho: numa
lista de deck, trocar uma carta por outra "parecida" daria uma conta de conclusão errada.
"""

import difflib
import hashlib
import json
import re
from dataclasses import dataclass

from decks import codigos as cod
from decks.banco import Banco
from juiz import config
from juiz.glossario import normalizar

VERSAO_DA_TABELA = "1"  # mude se as colunas de "cartas" mudarem: força a sincronização


@dataclass
class Carta:
    nome: str
    tipos: str
    supertipos: str
    dominios: str
    tags: str
    custo_energia: int | None
    custo_poder: int | None
    might: int | None

    @property
    def tipo_principal(self) -> str:
        return self.tipos.split()[0] if self.tipos else ""


def chave(nome: str) -> str:
    """Forma de comparar nomes: sem caixa e acento, apóstrofo reto e ", " no lugar de " - "."""
    texto = normalizar(nome).replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    texto = re.sub(r"\s+-\s+", ", ", texto)
    texto = re.sub(r"\s*,\s*", ", ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def carta_do_json(c: dict) -> Carta:
    return Carta(
        nome=c["name"], tipos=" ".join(c["cardTypes"]), supertipos=" ".join(c["superTypes"]),
        dominios=", ".join(c["domains"]), tags=", ".join(c["tags"]),
        custo_energia=c["energyCost"], custo_poder=c["powerCost"], might=c["might"],
    )


def runas_basicas() -> list[Carta]:
    return [Carta(nome, "Rune", "Basic", dominio, "", None, None, None) for nome, dominio in config.RUNAS_BASICAS.items()]


def ler_catalogo_do_faq() -> list[Carta]:
    """Cartas do card-catalog.json + runas básicas. Baixa o FAQ se ainda não estiver no computador."""
    arquivo = config.FAQ_SOURCES_DIR / "card-catalog.json"
    if not arquivo.exists():
        from juiz.atualizar import atualizar_faq

        atualizar_faq(log=print)
    cartas = [carta_do_json(c) for c in json.loads(arquivo.read_text(encoding="utf-8"))]
    return cartas + runas_basicas()


class Catalogo:
    def __init__(self, cartas: list[Carta], galeria: list[dict] | None = None):
        self.cartas = {c.nome: c for c in cartas}
        self._por_chave: dict[str, str] = {}
        for c in cartas:  # apelidos primeiro: um nome de verdade sempre ganha de um apelido igual
            if "Legend" in c.tipos.split():
                for tag in filter(None, c.tags.split(", ")):
                    self._por_chave.setdefault(chave(f"{tag}, {c.nome}"), c.nome)
        for c in cartas:
            self._por_chave[chave(c.nome)] = c.nome
        # código ("OGN-42") -> nome, pela galeria oficial (decks/codigos.py); vazio se ela não estiver disponível
        self.codigos = cod.mapa_de_codigos(galeria or [], self.resolver)
        # A impressão normal de cada carta: sem sufixo de variante ("a", "*"), número só com dígitos (promos
        # "SP5" e runas "R1" ficam de reserva) e o menor número, porque as overnumbered vêm depois do total
        # da coleção (a Vi lenda é UNL-187; a UNL-229 é a overnumbered).
        def ordem(par: tuple[str, str]) -> tuple[bool, int]:
            numero = par[0].split("-")[-1]
            return not numero.isdigit(), int(re.sub(r"\D", "", numero) or 0)

        self._codigo_por_nome: dict[str, str] = {}
        for codigo, nome in sorted(self.codigos.items(), key=ordem):
            if cod.codigo_base(codigo) == codigo:
                self._codigo_por_nome.setdefault(nome, codigo)

    def __len__(self) -> int:
        return len(self.cartas)

    def __contains__(self, nome: str) -> bool:
        return nome in self.cartas

    def resolver(self, texto: str) -> str | None:
        """Nome oficial da carta escrita em `texto`, ou None se não for reconhecida."""
        texto = texto.strip()
        if texto in self.cartas:
            return texto
        achada = self._por_chave.get(chave(texto))
        if achada:
            return achada
        # "Jinx, Rebel (OGN-123)" ou "Jinx, Rebel [OGN]": código de coleção no fim
        sem_codigo = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]\s*$", "", texto)
        if sem_codigo != texto:
            return self.resolver(sem_codigo)
        return None

    def por_codigo(self, codigo: str | None) -> str | None:
        """Nome da carta pelo código ("OGN-042", "OGN-042/298", "VEN-R04"), ou None se não conhecer.
        Uma variante sem código próprio no mapa (ex.: arte alternativa) cai no código da carta normal."""
        if not codigo:
            return None
        normal = cod.normalizar_codigo(codigo)
        return self.codigos.get(normal) or self.codigos.get(cod.codigo_base(normal))

    def codigo_de(self, nome: str) -> str | None:
        """Código de uma impressão normal da carta ("OGN-251"), ou None sem a galeria."""
        return self._codigo_por_nome.get(nome)

    def sugestoes(self, texto: str, n: int = 3) -> list[str]:
        """Nomes parecidos, pra mostrar quando `resolver` não reconhece."""
        chaves = difflib.get_close_matches(chave(texto), list(self._por_chave), n=n * 2, cutoff=0.6)
        return list(dict.fromkeys(self._por_chave[k] for k in chaves))[:n]


def nome_da_lenda(lenda: str, catalogo: Catalogo, separador: str = ", ") -> str:
    """ "Loose Cannon" (tag Jinx) -> "Jinx, Loose Cannon", como os jogadores chamam a lenda."""
    tags = [t for t in catalogo.cartas[lenda].tags.split(", ") if t] if lenda in catalogo else []
    return f"{tags[-1]}{separador}{lenda}" if tags and not lenda.startswith(tags[-1]) else lenda


# --- banco ---

def _assinatura(cartas: list[Carta]) -> str:
    conteudo = json.dumps([list(vars(c).values()) for c in cartas], ensure_ascii=False)
    return hashlib.sha256((VERSAO_DA_TABELA + conteudo).encode("utf-8")).hexdigest()


def sincronizar(banco: Banco, cartas: list[Carta]) -> bool:
    """Grava as cartas na tabela `cartas`, só se o catálogo mudou (no Turso, cada escrita conta na
    cota). Devolve True se gravou."""
    assinatura = _assinatura(cartas)
    atual = banco.consultar("SELECT valor FROM meta WHERE chave = 'catalogo'")
    if atual and atual[0]["valor"] == assinatura:
        return False
    comandos: list[tuple[str, tuple]] = [("DELETE FROM cartas", ())]
    colunas = list(vars(cartas[0]))
    for inicio in range(0, len(cartas), 100):  # 100 cartas por INSERT: menos idas e voltas
        bloco = cartas[inicio:inicio + 100]
        marcadores = ", ".join(["(" + ", ".join("?" * len(colunas)) + ")"] * len(bloco))
        valores = tuple(v for c in bloco for v in vars(c).values())
        comandos.append((f"INSERT INTO cartas ({', '.join(colunas)}) VALUES {marcadores}", valores))
    comandos.append(("INSERT OR REPLACE INTO meta (chave, valor) VALUES ('catalogo', ?)", (assinatura,)))
    banco.lote(comandos)
    return True


def preparar(banco: Banco, cartas: list[Carta] | None = None, galeria: list[dict] | None = None) -> Catalogo:
    """Cria as tabelas, sincroniza o catálogo e devolve o catálogo pronto pra reconhecer nomes e códigos.
    Sem `cartas` e `galeria`, lê o catálogo do FAQ e a galeria oficial (baixando se preciso)."""
    banco.criar_tabelas()
    if cartas is None:
        cartas = ler_catalogo_do_faq()
        galeria = galeria if galeria is not None else cod.carregar_galeria()
    sincronizar(banco, cartas)
    return Catalogo(cartas, galeria)

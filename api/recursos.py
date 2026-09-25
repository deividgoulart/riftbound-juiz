"""O que a API carrega uma vez e reaproveita entre os pedidos: o juiz e o deck builder (banco + catálogo).

Os dois demoram pra ficar prontos (na 1ª vez, o servidor baixa o FAQ, o Core Rules, o catálogo e a
galeria de cartas). A API começa a carregar os dois assim que liga, em segundo plano, e o 1º pedido
que chegar antes espera o carregamento terminar.

A cada config.ATUALIZAR_A_CADA_HORAS, o recurso é recarregado em segundo plano (cartas novas no FAQ,
regras novas no Core Rules, decks do meta da semana) enquanto os pedidos continuam usando o antigo.
"""

import threading
import time
import traceback
from collections.abc import Callable

from juiz import config
from juiz.erros import explicar_erro


class Recurso:
    def __init__(self, carregar: Callable[[], object], validade_em_segundos: float):
        self._carregar = carregar
        self.validade = validade_em_segundos
        self._valor = None
        self._carregado_em = 0.0
        self._trava = threading.Lock()
        self._recarregando = False

    @classmethod
    def pronto(cls, valor) -> "Recurso":
        """Um recurso já carregado (os testes usam pra trocar o juiz e o banco por versões de teste)."""
        recurso = cls(lambda: valor, float("inf"))
        recurso._valor, recurso._carregado_em = valor, time.monotonic()
        return recurso

    @property
    def carregado(self) -> bool:
        return self._valor is not None

    def obter(self):
        if self._valor is None:
            with self._trava:  # dois pedidos ao mesmo tempo: o segundo espera o primeiro carregar
                if self._valor is None:
                    self._valor = self._carregar()
                    self._carregado_em = time.monotonic()
            return self._valor
        if time.monotonic() - self._carregado_em > self.validade and not self._recarregando:
            self._recarregando = True
            threading.Thread(target=self._recarregar, daemon=True).start()
        return self._valor

    def _recarregar(self) -> None:
        try:
            valor = self._carregar()
            self._valor = valor
        except Exception:  # sem internet, fonte fora do ar: segue com o que já tem
            traceback.print_exc()
        finally:
            self._carregado_em = time.monotonic()
            self._recarregando = False


def carregar_juiz():
    """Baixa e prepara as regras se preciso (juiz.atualizar) e devolve o juiz."""
    from juiz.atualizar import atualizar, dados_prontos, precisa_atualizar
    from juiz.responder import Juiz

    if precisa_atualizar():
        try:
            atualizar()
        except Exception as erro:  # ex.: sem internet. Se já existem dados, segue com eles.
            traceback.print_exc()
            if not dados_prontos():
                raise RuntimeError(f"não consegui baixar e preparar as regras: {explicar_erro(erro)}") from erro
            print(f"Não consegui atualizar as fontes; usando os dados que já existem ({erro})")
    return Juiz.padrao()


def carregar_deck_builder():
    """Abre o banco (Turso ou local), sincroniza o catálogo e, se estiverem velhos, os decks do meta e os
    preços. Devolve (banco, catálogo)."""
    from decks import meta, precos
    from decks.banco import abrir_banco
    from decks.catalogo import preparar

    banco = abrir_banco()
    catalogo = preparar(banco)
    # Decks do meta: coleta de novo quando a última tem mais de uma semana. Se o TopDeck.gg falhar,
    # ficam os decks que já existem.
    if meta.chave_topdeck() and meta.precisa_atualizar_meta(banco):
        try:
            print("Decks do meta: " + meta.resumo(meta.atualizar_meta(banco, catalogo, meta.chave_topdeck())))
        except Exception:
            traceback.print_exc()
    # Preços de referência (TCGplayer): uma cópia por semana. Se falhar, ficam os que já existem.
    if precos.precisa_atualizar_precos(banco):
        try:
            print(f"Preços: {precos.atualizar_precos(banco, catalogo)} cartas com preço")
        except Exception:
            traceback.print_exc()
    return banco, catalogo


def recursos_padrao() -> tuple[Recurso, Recurso]:
    validade = config.ATUALIZAR_A_CADA_HORAS * 3600
    return Recurso(carregar_juiz, validade), Recurso(carregar_deck_builder, validade)

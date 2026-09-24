"""Peças compartilhadas pelos testes do deck builder (fase 2): um catálogo pequeno e um banco em memória."""

import pytest

from decks.banco import BancoLocal
from decks.catalogo import Carta, preparar, runas_basicas


def carta(nome, tipos="Unit", supertipos="", dominios="Fury", tags="", energia=2):
    return Carta(nome, tipos, supertipos, dominios, tags, energia, None, None)


CARTAS = [
    carta("Loose Cannon", "Legend", dominios="Fury, Chaos", tags="Jinx", energia=None),
    carta("Heart of the Tempest", "Legend", dominios="Order, Chaos", tags="Yordle, Kennen", energia=None),
    carta("Jinx, Demolitionist", supertipos="Champion", tags="Jinx"),
    carta("Jinx, Rebel", supertipos="Champion", tags="Jinx"),
    carta("Super Mega Death Rocket!", "Spell", supertipos="Signature", tags="Jinx"),
    carta("Abandon", "Spell", dominios="Chaos"),
    carta("Void Seeker", "Spell", dominios="Fury"),
    carta("Altar of Blood", "Battlefield", dominios="Colorless", energia=None),
    carta("Dark Child - Starter", "Legend", supertipos="Champion", dominios="Fury, Chaos", tags="Annie", energia=None),
] + runas_basicas()


@pytest.fixture
def banco():
    return BancoLocal(":memory:")


@pytest.fixture
def catalogo(banco):
    return preparar(banco, CARTAS)

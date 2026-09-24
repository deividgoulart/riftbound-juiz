"""Testes da proteção do app publicado (etapa 8): limites de convidado e senha."""

from datetime import date

from juiz.limites import ContadorDiario, modo_publico, senha_confere


def test_contador_para_no_limite_e_devolve_quando_da_erro():
    contador = ContadorDiario(2, hoje=lambda: date(2026, 9, 24))
    assert contador.consumir() and contador.consumir()
    assert not contador.consumir() and contador.restantes() == 0
    contador.devolver()  # a pergunta deu erro: não conta
    assert contador.restantes() == 1


def test_contador_zera_quando_vira_o_dia():
    dia = [date(2026, 9, 24)]
    contador = ContadorDiario(1, hoje=lambda: dia[0])
    assert contador.consumir() and not contador.consumir()
    dia[0] = date(2026, 9, 25)
    assert contador.restantes() == 1 and contador.consumir()


def test_sem_senha_configurada_nao_ha_modo_publico_nem_senha_que_sirva(monkeypatch):
    monkeypatch.delenv("SENHA_DO_APP", raising=False)
    assert not modo_publico()
    assert not senha_confere("")  # senha vazia nunca libera


def test_senha_confere(monkeypatch):
    monkeypatch.setenv("SENHA_DO_APP", "cafe com pao")
    assert modo_publico()
    assert senha_confere("cafe com pao")
    assert not senha_confere("cafe com pão") and not senha_confere("")

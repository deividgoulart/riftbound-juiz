"""Testes da coleção (fase 2): quantidades e CSV."""

from decks import colecao


def test_definir_e_zerar(banco, catalogo):
    colecao.definir(banco, "Abandon", 3)
    colecao.salvar_alteracoes(banco, {"Jinx, Rebel": 1, "Void Seeker": 2})
    assert colecao.listar(banco) == {"Abandon": 3, "Jinx, Rebel": 1, "Void Seeker": 2}
    colecao.definir(banco, "Abandon", 0)  # 0 tira da coleção
    assert "Abandon" not in colecao.listar(banco)


def test_csv_ida_e_volta(banco, catalogo):
    colecao.salvar_alteracoes(banco, {"Abandon": 3, "Jinx, Rebel": 1})
    texto = colecao.exportar_csv(banco)
    assert texto.splitlines()[0] == "carta,quantidade"
    colecao.definir(banco, "Abandon", 0)
    colecao.importar_csv(banco, catalogo, texto)
    assert colecao.listar(banco) == {"Abandon": 3, "Jinx, Rebel": 1}


def test_csv_do_excel_em_portugues_com_nomes_desconhecidos(banco, catalogo):
    texto = "﻿Carta;Quantidade\njinx - rebel;2\nJinks Rebell;1\nAbandon;muitas\n\n"
    relatorio = colecao.importar_csv(banco, catalogo, texto)
    assert relatorio.importadas == {"Jinx, Rebel": 2}
    assert relatorio.desconhecidas == [("Jinks Rebell", ["Jinx, Rebel"])]
    assert relatorio.invalidas == ["Abandon;muitas"]
    assert colecao.listar(banco) == {"Jinx, Rebel": 2}


def test_csv_sem_cabecalho_e_em_ingles(banco, catalogo):
    assert colecao.ler_csv("Abandon,2\nFury Rune,6", catalogo).importadas == {"Abandon": 2, "Fury Rune": 6}
    assert colecao.ler_csv("quantity,name\n3,Abandon", catalogo).importadas == {"Abandon": 3}


def test_importar_nao_mexe_nas_cartas_fora_do_arquivo(banco, catalogo):
    colecao.definir(banco, "Void Seeker", 2)
    colecao.importar_csv(banco, catalogo, "carta,quantidade\nAbandon,1")
    assert colecao.listar(banco) == {"Abandon": 1, "Void Seeker": 2}

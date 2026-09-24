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


LIGA = '''"Edicao (PTBR)","Edicao (EN)","Edicao (Sigla)","Card (PT)","Card (EN)",Quantidade,"Qualidade (M NM SP MP HP D)","Idioma (BR EN DE ES FR IT JP KO RU TW)",Raridade,"Cor (C D O E Y F R G L M P W)",Extras,"Card #",Comentario,"# Cards na Edicao"
,Origins,OGN,,"Fury Rune",6,,,C,F,,R01,,
,Vendetta,VEN,,"Jinx - Rebel",1,NM,EN,R,F,Foil,15,,
,Vendetta,VEN,,"Jinx - Rebel",2,,,R,F,,15,,
,Vendetta,VEN,,"Jinx - Loose Cannon",1,NM,EN,R,0,Foil,149,,
,Vendetta,VEN,,"Abandon (Overnumbered)",1,NM,EN,E,O,Foil,185,,
,Vendetta,VEN,Abandonar,,2,,,C,O,,1,,
'''


def test_csv_da_liga_riftbound(banco, catalogo):
    """Exportação de coleção da Liga Riftbound: nome na coluna Card (EN), linhas repetidas somam."""
    relatorio = colecao.importar_csv(banco, catalogo, LIGA)
    # "Abandonar" (Card (PT), sem o nome em inglês) não está no catálogo, que é em inglês: vira desconhecida
    assert relatorio.importadas == {"Fury Rune": 6, "Jinx, Rebel": 3, "Loose Cannon": 1, "Abandon": 1}
    assert [nome for nome, _ in relatorio.desconhecidas] == ["Abandonar"]
    assert relatorio.invalidas == []


def test_card_pt_e_reserva_quando_card_en_esta_vazio(banco, catalogo):
    texto = '"Card (PT)","Card (EN)",Quantidade\nAbandon,,2\n'
    assert colecao.ler_csv(texto, catalogo).importadas == {"Abandon": 2}


def test_substituir_a_colecao_inteira(banco, catalogo):
    colecao.salvar_alteracoes(banco, {"Void Seeker": 2, "Abandon": 1})
    colecao.importar_csv(banco, catalogo, "carta,quantidade\nAbandon,3", substituir=True)
    assert colecao.listar(banco) == {"Abandon": 3}

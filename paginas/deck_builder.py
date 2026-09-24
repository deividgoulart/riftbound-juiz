"""Deck builder (fase 2): minha coleção de cartas e quanto de cada deck eu já tenho.

Página do app.py. Toda a lógica fica no pacote decks/ (sem Streamlit): esta página só mostra e
chama as funções de lá. Publicado (com SENHA_DO_APP), o visitante só vê; editar pede a senha.
"""

import traceback
from datetime import timedelta

import pandas as pd
import streamlit as st

from decks import colecao, conclusao
from decks.banco import abrir_banco, turso_configurado
from decks.catalogo import preparar
from decks.importar import NOMES_DAS_SECOES, ler_lista
from decks.meus_decks import apagar_deck, cartas_dos_decks, salvar_deck
from juiz import config
from juiz.acesso import acesso_com_senha
from juiz.erros import explicar_erro
from juiz.limites import modo_publico
from juiz.segredos import aplicar_segredos

st.set_page_config(page_title="Deck builder · Juiz Riftbound", page_icon="🃏", layout="wide")
aplicar_segredos(st.secrets.to_dict)  # a página pode ser aberta direto: lê o Turso e a senha dos secrets
PUBLICO = modo_publico()

EXEMPLO_DE_LISTA = """Legend:
1 Jinx, Loose Cannon
Champion:
1 Jinx, Demolitionist
Main Deck:
3 Jinx, Rebel
...
Battlefields:
1 Altar of Blood
Runes:
6 Fury Rune
6 Chaos Rune"""


@st.cache_resource(show_spinner="Preparando o catálogo de cartas...", ttl=timedelta(hours=config.ATUALIZAR_A_CADA_HORAS))
def carregar():
    """Abre o banco (Turso ou local) e sincroniza o catálogo, uma vez só pra todos os visitantes.
    Como no juiz, o cache expira uma vez por dia: cartas novas no FAQ entram no catálogo."""
    banco = abrir_banco()
    return banco, preparar(banco)


def obter():
    # Os testes automáticos colocam aqui um banco em memória com um catálogo pequeno.
    return st.session_state.get("deck_builder_de_teste") or carregar()


def avisar_depois(tipo: str, texto: str) -> None:
    """Mensagem que aparece depois do st.rerun() (senão ela sumiria junto com a tela antiga)."""
    st.session_state.setdefault("avisos_deck_builder", []).append((tipo, texto))


def com_sugestoes(nome: str, sugestoes: list[str]) -> str:
    return f"\"{nome}\"" + (f" (quis dizer {' / '.join(sugestoes)}?)" if sugestoes else "")


pode_editar = not PUBLICO or st.session_state.get("dono", False)

# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 🃏 Deck builder")
    st.markdown("Cadastre as cartas que você tem, importe listas de deck e veja quanto falta pra montar cada uma.")
    if PUBLICO:
        acesso_com_senha("Tem a senha? Edite a coleção", "Edição liberada.")
    st.caption("Cartas: catálogo do [Riftbound FAQ](https://www.riftboundfaq.com). Riftbound é da Riot Games; "
               "este projeto não é oficial.")

# ---------------------------------------------------------------------------
# Conteúdo
# ---------------------------------------------------------------------------

st.title("🃏 Deck builder")
for tipo, texto in st.session_state.pop("avisos_deck_builder", []):
    getattr(st, tipo)(texto)

try:
    banco, catalogo = obter()
except Exception as erro:
    traceback.print_exc()
    st.error(f"Não consegui abrir o banco da coleção ({explicar_erro(erro)}). Recarregue a página em alguns instantes.")
    st.stop()

if PUBLICO and not turso_configurado():
    st.warning("O banco na nuvem (Turso) não está configurado: o que for salvo aqui some quando o app reiniciar.",
               icon=":material/cloud_off:")
if not pode_editar:
    st.caption("Modo leitura: você vê a coleção e os decks do dono do app.")

# Com key, a aba escolhida continua aberta depois de salvar (senão o st.rerun() voltaria pra 1ª)
aba_colecao, aba_decks = st.tabs(["Minha coleção", "Decks"], key="aba_deck_builder")

# --- Coleção ---

with aba_colecao:
    tenho = colecao.listar(banco)
    c1, c2 = st.columns(2)
    c1.metric("Cartas diferentes", len(tenho))
    c2.metric("Cópias", sum(tenho.values()))

    cartas = list(catalogo.cartas.values())
    f1, f2, f3, f4 = st.columns([3, 2, 2, 1.3], vertical_alignment="bottom")
    busca = f1.text_input("Buscar pelo nome ou campeão", placeholder="Ex.: jinx")
    tipos = f2.multiselect("Tipo", sorted({c.tipo_principal for c in cartas}), placeholder="Todos")
    dominios = f3.multiselect("Domínio", sorted({d for c in cartas for d in c.dominios.split(", ") if d}),
                              placeholder="Todos")
    so_as_minhas = f4.toggle("Só as que tenho")

    tabela = pd.DataFrame([{
        "Carta": c.nome, "Tipo": c.tipos, "Domínios": c.dominios, "Energia": c.custo_energia,
        "Quantidade": tenho.get(c.nome, 0),
    } for c in cartas if (not busca or busca.lower() in f"{c.nome} {c.tags}".lower())  # tags: "jinx" acha a lenda
        and (not tipos or c.tipo_principal in tipos)
        and (not dominios or any(d in c.dominios.split(", ") for d in dominios))
        and (not so_as_minhas or c.nome in tenho)])

    altura = min(420, 35 * (len(tabela) + 1) + 3)  # sem linhas vazias quando o filtro acha poucas cartas
    if tabela.empty:
        st.info("Nenhuma carta com esses filtros.")
    elif pode_editar:
        # Dentro de um formulário: a tabela só é enviada no "Salvar", e não a cada número digitado.
        with st.form("form_colecao", border=False):
            editada = st.data_editor(
                tabela, hide_index=True, width="stretch", height=altura,
                # A chave muda com os filtros: edições feitas numa lista filtrada não vão parar em outra.
                key=f"editor_{busca}_{tipos}_{dominios}_{so_as_minhas}",
                disabled=["Carta", "Tipo", "Domínios", "Energia"],
                column_config={"Quantidade": st.column_config.NumberColumn(min_value=0, max_value=99, step=1)},
            )
            if st.form_submit_button("Salvar alterações", type="primary"):
                novas = editada["Quantidade"].fillna(0).astype(int)
                mudancas = {carta: qtd for carta, qtd, antes in zip(tabela["Carta"], novas, tabela["Quantidade"])
                            if qtd != antes}
                try:
                    colecao.salvar_alteracoes(banco, mudancas)
                except Exception as erro:
                    traceback.print_exc()
                    st.error(f"Não consegui salvar ({explicar_erro(erro)}).")
                else:
                    avisar_depois("success", f"Coleção salva ({len(mudancas)} cartas alteradas)." if mudancas
                                  else "Nada mudou na coleção.")
                    st.rerun()
    else:
        st.dataframe(tabela, hide_index=True, width="stretch", height=altura)

    with st.expander("Importar ou exportar (CSV)"):
        st.markdown("O CSV tem as colunas **carta** e **quantidade**. Importar define a quantidade das cartas do "
                    "arquivo; as outras ficam como estão.")
        st.download_button("Baixar minha coleção (CSV)", colecao.exportar_csv(banco), file_name="colecao_riftbound.csv",
                           mime="text/csv", icon=":material/download:")
        if pode_editar:
            arquivo = st.file_uploader("Arquivo CSV", type=["csv"])
            if arquivo and st.button("Importar CSV", icon=":material/upload:"):
                try:
                    relatorio = colecao.importar_csv(banco, catalogo, arquivo.getvalue().decode("utf-8-sig"))
                except Exception as erro:
                    traceback.print_exc()
                    st.error(f"Não consegui importar ({explicar_erro(erro)}).")
                else:
                    avisar_depois("success", f"{len(relatorio.importadas)} cartas importadas.")
                    if relatorio.desconhecidas:
                        avisar_depois("warning", "Não reconheci: " + "; ".join(
                            com_sugestoes(n, s) for n, s in relatorio.desconhecidas))
                    if relatorio.invalidas:
                        avisar_depois("warning", f"{len(relatorio.invalidas)} linhas ignoradas (quantidade inválida).")
                    st.rerun()

# --- Decks ---

with aba_decks:
    o1, o2 = st.columns(2)
    runas_garantidas = o1.toggle("Conto com as runas básicas", value=True,
                                 help="Quase todo jogador tem as runas de um deck inicial. Desligue pra contar as "
                                      "runas pela sua coleção.")
    incluir_sideboard = o2.toggle("Incluir o sideboard", help="O sideboard não é necessário pra jogar.")
    ranking = conclusao.ranking(banco, incluir_sideboard=incluir_sideboard, runas_garantidas=runas_garantidas)

    if pode_editar:
        with st.expander("Importar um deck", expanded=not ranking, icon=":material/add:"):
            with st.form("form_deck"):
                nome = st.text_input("Nome do deck", placeholder="Ex.: Jinx do torneio de sábado")
                texto = st.text_area("Lista do deck", height=260, placeholder=EXEMPLO_DE_LISTA,
                                     help="Cole a lista exportada pelo site de decks. Aceita \"3 Carta\", "
                                          "\"3x Carta\" e \"Carta x3\", com ou sem cabeçalhos de seção.")
                url = st.text_input("Link da lista (opcional)")
                ignorar = st.checkbox("Salvar mesmo com cartas não reconhecidas (elas ficam de fora)")
                if st.form_submit_button("Importar deck", type="primary"):
                    lista = ler_lista(texto, catalogo)
                    if lista.nao_reconhecidas and not ignorar:
                        st.error("Não reconheci estas cartas: " + "; ".join(
                            com_sugestoes(n, s) for n, s in lista.nao_reconhecidas)
                                 + ". Corrija a lista ou marque a opção de salvar sem elas.")
                    elif not lista.cartas:
                        st.error("A lista não tem nenhuma carta reconhecida.")
                    else:
                        try:
                            salvar_deck(banco, nome, lista, url=url)
                        except Exception as erro:
                            traceback.print_exc()
                            st.error(f"Não consegui salvar o deck ({explicar_erro(erro)}).")
                        else:
                            avisar_depois("success", f"Deck \"{nome.strip() or 'Deck sem nome'}\" importado.")
                            for aviso in lista.avisos:
                                avisar_depois("info", f"Regras de construção: {aviso}")
                            st.rerun()

    listas = cartas_dos_decks(banco) if ranking else {}
    if not ranking:
        st.info("Nenhum deck ainda." + (" Importe uma lista acima." if pode_editar else ""))

    for c in ranking:
        with st.container(border=True):
            st.markdown(f"**{c.deck['nome']}**" + (f" · [lista original]({c.deck['url']})" if c.deck.get("url") else ""))
            st.progress(min(c.porcentagem / 100, 1.0),
                        text=f"{c.porcentagem:.0f}% · tenho {c.tenho} de {c.total} cópias")
            if c.faltando:
                with st.expander(f"Faltam {c.copias_faltando} cópias de {len(c.faltando)} cartas"):
                    st.dataframe(pd.DataFrame([{"Carta": x.carta, "Precisa": x.precisa, "Tenho": x.tem, "Falta": x.falta}
                                               for x in c.faltando]), hide_index=True, width="stretch")
            else:
                st.success("Tenho todas as cartas deste deck!", icon=":material/check_circle:")
            with st.expander("Lista completa"):
                st.dataframe(pd.DataFrame([{"Seção": NOMES_DAS_SECOES.get(l["secao"], l["secao"]), "Carta": l["carta"],
                                            "Cópias": l["quantidade"]} for l in listas.get(c.deck["id"], [])]),
                             hide_index=True, width="stretch")
            if pode_editar and st.button("Apagar deck", key=f"apagar_{c.deck['id']}", icon=":material/delete:"):
                apagar_deck(banco, c.deck["id"])
                avisar_depois("success", f"Deck \"{c.deck['nome']}\" apagado.")
                st.rerun()

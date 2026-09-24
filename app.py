"""Juiz Riftbound: interface de chat (etapa 6).

Rodar (a partir da raiz do projeto, com o índice já criado):
    streamlit run app.py
"""

import uuid
from dataclasses import asdict

import streamlit as st

from juiz import config
from juiz.apresentacao import CREDITOS, ROTULOS, linkar_citacoes, plural, procedencia
from juiz.erros import CotaEsgotada
from juiz.registro import registrar_avaliacao, registrar_erro, registrar_resposta

st.set_page_config(page_title="Juiz Riftbound", page_icon="⚖️", layout="centered")

EXEMPLOS = [
    "Posso usar Emboscada pra jogar uma unidade na minha base?",
    "O Guardian Angel salva minha unidade do Smite?",
    "Se counterarem minha carta, eu recebo a mana de volta?",
    "Quantos pontos preciso pra ganhar?",
]


@st.cache_resource(show_spinner="Carregando as regras e o índice de busca...")
def carregar_juiz():
    """Carrega o juiz uma vez só e reaproveita entre perguntas e visitantes."""
    from juiz.responder import Juiz

    return Juiz.padrao()


def obter_juiz():
    # Os testes automáticos colocam aqui um juiz "de mentira", pra não chamar a API.
    return st.session_state.get("juiz_de_teste") or carregar_juiz()


# ---------------------------------------------------------------------------
# Mensagens
# ---------------------------------------------------------------------------

def montar_mensagem(resposta, id_: str) -> dict:
    versao = procedencia()["crd_versao"] or "1.4"
    return {
        "id": id_,
        "papel": "assistant",
        "texto": linkar_citacoes(resposta.texto, resposta.fontes, resposta.regras, versao),
        "original": resposta.texto,  # sem links, pra mandar como histórico nas próximas perguntas
        "tipo": resposta.tipo,
        "encontrou": resposta.encontrou,
        "fontes": [asdict(f) for f in resposta.fontes],
        "nota": resposta.nota_busca,
        "uso": resposta.uso,
        "termos": resposta.termos,
        "busca": resposta.modelo_busca,
    }


def historico_da_conversa() -> list[tuple[str, str]]:
    """Pares (pergunta, resposta) já respondidos nesta conversa, pro juiz entender continuações."""
    pares, pergunta = [], None
    for msg in st.session_state.mensagens:
        if msg["papel"] == "user":
            pergunta = msg["texto"]
        elif pergunta is not None:
            pares.append((pergunta, msg["original"]))
            pergunta = None
    return pares


def avaliar(id_: str) -> None:
    valor = st.session_state.get(f"avaliacao_{id_}")
    if valor is not None:
        registrar_avaliacao(id_, gostou=valor == 1)


def mostrar_fonte(f: dict, detalhes: bool) -> None:
    titulo = (f["resumo"] or f["titulo"]).replace("[", "\\[").replace("]", "\\]")
    nota = f" · similaridade {f['nota']:.2f}" if detalhes and f["nota"] is not None else ""
    st.markdown(f"**[F{f['numero']}]** {ROTULOS[f['tipo']]} · [{titulo}]({f['url']}){nota}")


def mostrar_resposta(msg: dict, detalhes: bool) -> None:
    # unsafe_allow_html: as citações são <sup> com link; o texto do LLM já passou por html.escape.
    st.markdown(msg["texto"], unsafe_allow_html=True)
    if msg.get("busca") and msg["busca"] != config.MODELO_EMBEDDINGS:
        st.caption(f"🔁 Busca feita com o modelo reserva ({msg['busca']}), que roda neste computador: "
                   "a busca principal (Gemini) está indisponível agora.")
    citadas = [f for f in msg["fontes"] if f["citada"]]
    outras = [f for f in msg["fontes"] if not f["citada"]]

    if any(f["citacao_pendente"] for f in citadas):
        st.info("Uma das fontes usadas avisa que o Core Rules ainda não confirma totalmente esta "
                "interpretação. Numa partida oficial, confirme com o juiz do evento.", icon="⚠️")

    if msg["fontes"]:
        contagem = [plural(len(citadas), "citada", "citadas")]
        if outras:
            contagem.append(plural(len(outras), "também consultada", "também consultadas"))
        with st.expander(f"Fontes ({', '.join(contagem)})"):
            for f in citadas:
                mostrar_fonte(f, detalhes)
            if outras:
                st.caption("Também consultadas, mas não citadas na resposta:")
                for f in outras:
                    mostrar_fonte(f, detalhes)

    if detalhes:
        partes = [f"tipo: {msg.get('tipo')}", f"busca: {msg.get('busca')}", f"similaridade do 1º resultado: {msg['nota']}"]
        if msg["uso"]:
            partes.append(f"modelo: {msg['uso'].get('modelo')}")
            partes.append(f"tokens: {msg['uso'].get('tokens_entrada')} de entrada, {msg['uso'].get('tokens_saida')} de saída")
        else:
            partes.append("LLM não chamado (nenhuma fonte parecida o bastante)")
        if msg["termos"]:
            partes.append("glossário: " + ", ".join(f"{pt} → {en}" for pt, en in msg["termos"]))
        st.caption(" · ".join(partes))

    if msg["fontes"]:
        st.feedback("thumbs", key=f"avaliacao_{msg['id']}", on_change=avaliar, args=(msg["id"],))


# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### ⚖️ Juiz Riftbound")
    st.markdown("Tira dúvidas de regras do **Riftbound TCG** em português, sempre citando "
                "a regra ou a página usada. Projeto pessoal e de portfólio.")
    p = procedencia()
    st.markdown(f"**Versões das fontes**\n- FAQ: {p['faq_data']} (commit `{p['faq_commit']}`)\n"
                f"- Core Rules: v{p['crd_versao']} ({p['crd_nome']})")
    detalhes = st.toggle("Mostrar detalhes da busca", help="Similaridade das fontes, modelo usado e tokens gastos.")
    if st.button("Nova conversa", icon=":material/refresh:", width="stretch"):
        st.session_state.mensagens = []
        st.session_state.pop("exemplo", None)
        st.rerun()
    with st.expander("Como funciona"):
        st.markdown(
            "1. A pergunta é comparada com ~500 trechos do FAQ e do Core Rules usando "
            "**embeddings** (vetores que representam o sentido do texto).\n"
            "2. Os 5 trechos mais parecidos, o texto oficial das regras citadas e o texto das "
            "cartas mencionadas vão para um **LLM** (Gemini), com instruções pra responder só com "
            "base nessas fontes.\n"
            "3. Se nada parecido o bastante for encontrado, o juiz diz que não encontrou, em vez de inventar."
        )
    st.markdown(CREDITOS)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

st.title("⚖️ Juiz Riftbound")
st.caption("Pergunte em português. As respostas vêm do Riftbound FAQ e do Core Rules oficial, com a fonte de cada "
           "afirmação. O juiz lembra da conversa: dá pra perguntar \"e se for durante um showdown?\" depois de uma resposta.")

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

for msg in st.session_state.mensagens:
    with st.chat_message(msg["papel"], avatar="⚖️" if msg["papel"] == "assistant" else None):
        if msg["papel"] == "user":
            st.markdown(msg["texto"])
        else:
            mostrar_resposta(msg, detalhes)

pergunta = st.chat_input("Ex.: a Vex atordoa a unidade que acabou de ser jogada?", max_chars=500)
area_de_exemplos = st.empty()  # some assim que a primeira pergunta é feita
if not st.session_state.mensagens:
    with area_de_exemplos.container():
        st.markdown("**Experimente perguntar:**")
        escolha = st.pills("Exemplos", EXEMPLOS, key="exemplo", label_visibility="collapsed")
    pergunta = pergunta or escolha

if pergunta:
    area_de_exemplos.empty()
    historico = historico_da_conversa()  # antes de acrescentar a pergunta nova
    st.session_state.mensagens.append({"papel": "user", "texto": pergunta})
    with st.chat_message("user"):
        st.markdown(pergunta)
    with st.chat_message("assistant", avatar="⚖️"):
        try:
            with st.spinner("Consultando as regras..."):
                resposta = obter_juiz().responder(pergunta, historico=historico)
        except CotaEsgotada:
            registrar_erro(pergunta, CotaEsgotada())
            st.warning(f"{CotaEsgotada.MENSAGEM} Até lá, o juiz não consegue responder.", icon="⏳")
            st.session_state.mensagens.pop()
        except Exception as erro:
            registrar_erro(pergunta, erro)
            dica = f" ({erro})" if isinstance(erro, RuntimeError) else ""
            st.error(f"Não consegui responder agora{dica}. Tente de novo em alguns instantes.")
            st.session_state.mensagens.pop()
        else:
            msg = montar_mensagem(resposta, uuid.uuid4().hex[:8])
            st.session_state.mensagens.append(msg)
            registrar_resposta(msg["id"], resposta)
            mostrar_resposta(msg, detalhes)

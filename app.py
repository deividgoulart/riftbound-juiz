"""Juiz Riftbound: interface de chat (etapa 6).

Rodar (a partir da raiz do projeto):
    streamlit run app.py

Na primeira vez (ou se os dados tiverem mais de um dia), o app baixa e processa o FAQ e o Core Rules
sozinho, com juiz.atualizar. Publicado (com SENHA_DO_APP nos secrets), entra o modo convidado:
veja juiz/limites.py.
"""

import traceback
import uuid
from dataclasses import asdict
from datetime import timedelta

import streamlit as st

from juiz import config
from juiz.ajustes_streamlit import nao_vasculhar_bibliotecas_pesadas
from juiz.apresentacao import CREDITOS, ROTULOS, linkar_citacoes, plural, procedencia
from juiz.erros import CotaEsgotada, explicar_erro
from juiz.limites import ContadorDiario, modo_publico, senha_confere
from juiz.registro import registrar_avaliacao, registrar_erro, registrar_resposta
from juiz.segredos import aplicar_segredos

st.set_page_config(page_title="Juiz Riftbound", page_icon="⚖️", layout="centered")
nao_vasculhar_bibliotecas_pesadas()  # evita o observador de arquivos travar com a transformers


# No Streamlit Cloud, a chave e a senha ficam em st.secrets; o juiz procura no ambiente (como no .env).
PROBLEMA_NOS_SEGREDOS = aplicar_segredos(st.secrets.to_dict)
PUBLICO = modo_publico()

PRIVACIDADE = ("As perguntas são processadas pelo Google Gemini no plano gratuito: o Google pode usá-las pra "
               "melhorar os produtos dele, e pessoas podem revisá-las. Não escreva dados pessoais.")

EXEMPLOS = [
    "Posso usar Emboscada pra jogar uma unidade na minha base?",
    "O Guardian Angel salva minha unidade do Smite?",
    "Se counterarem minha carta, eu recebo a mana de volta?",
    "Quantos pontos preciso pra ganhar?",
]


@st.cache_resource(show_spinner="Preparando as regras... Na primeira vez, o app baixa o FAQ e o Core Rules "
                                "(cerca de 1 minuto).", ttl=timedelta(hours=config.ATUALIZAR_A_CADA_HORAS))
def carregar_juiz():
    """Carrega o juiz uma vez só e reaproveita entre perguntas e visitantes. A cada
    ATUALIZAR_A_CADA_HORAS o cache expira: o app confere se o FAQ ou o CRD mudaram e recarrega."""
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


def obter_juiz():
    # Os testes automáticos colocam aqui um juiz "de mentira", pra não chamar a API.
    return st.session_state.get("juiz_de_teste") or carregar_juiz()


@st.cache_resource
def contador_diario() -> ContadorDiario:
    """Um contador só pra todos os visitantes (o cache_resource é compartilhado entre sessões)."""
    return ContadorDiario(config.LIMITE_DIARIO)


def e_convidado() -> bool:
    return PUBLICO and not st.session_state.get("dono", False)


def motivo_do_bloqueio() -> str | None:
    """Por que o convidado não pode perguntar agora; None se pode."""
    if not e_convidado():
        return None
    if st.session_state.get("perguntas_feitas", 0) >= config.LIMITE_POR_VISITA:
        return (f"Você usou as {config.LIMITE_POR_VISITA} perguntas desta visita. O limite existe pra proteger "
                "a cota gratuita do Gemini, que é dividida entre todos os visitantes.")
    if contador_diario().restantes() == 0:
        return ("O juiz atingiu o limite de perguntas de convidados de hoje, pra proteger a cota gratuita do "
                "Gemini. Volte amanhã!")
    return None


def acesso_com_senha() -> None:
    """Na barra lateral: quem tem a senha usa sem limite."""
    if st.session_state.get("dono"):
        st.success("Uso sem limite liberado.", icon=":material/lock_open:")
        return
    tentativas = st.session_state.get("tentativas_de_senha", 0)
    with st.expander("Tem a senha? Use sem limite"):
        if tentativas >= config.TENTATIVAS_DE_SENHA:
            st.caption("Tentativas esgotadas nesta visita.")
            return
        with st.form("form_senha", clear_on_submit=True, border=False):
            digitada = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                if senha_confere(digitada):
                    st.session_state.dono = True
                    st.rerun()
                st.session_state.tentativas_de_senha = tentativas + 1
                st.error("Senha incorreta.")


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
        st.caption(f"🔁 Busca feita com o modelo reserva ({msg['busca']}), que roda junto com o app: "
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

    # 👍/👎 vai pro registro local (data/logs/). Publicado, o registro fica desligado (privacidade),
    # então o botão também some.
    if msg["fontes"] and not PUBLICO:
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
    if PUBLICO:
        acesso_com_senha()
    st.markdown(f"**Privacidade:** {PRIVACIDADE}")
    st.markdown(CREDITOS)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

st.title("⚖️ Juiz Riftbound")
st.caption("Pergunte em português. As respostas vêm do Riftbound FAQ e do Core Rules oficial, com a fonte de cada "
           "afirmação. O juiz lembra da conversa: dá pra perguntar \"e se for durante um showdown?\" depois de uma resposta.")
if PROBLEMA_NOS_SEGREDOS:
    # Só aparece quando o app publicado está mal configurado. Nunca mostra valores, só nomes.
    st.error(f"**Configuração do app:** {PROBLEMA_NOS_SEGREDOS} (No Streamlit Cloud: Settings > Secrets.)",
             icon=":material/key:")

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

for msg in st.session_state.mensagens:
    with st.chat_message(msg["papel"], avatar="⚖️" if msg["papel"] == "assistant" else None):
        if msg["papel"] == "user":
            st.markdown(msg["texto"])
        else:
            mostrar_resposta(msg, detalhes)

def mostrar_aviso_de_convidado(lugar, bloqueio: str | None) -> None:
    if bloqueio:
        lugar.info(bloqueio, icon=":material/hourglass_top:")
    elif e_convidado():
        restantes = config.LIMITE_POR_VISITA - st.session_state.get("perguntas_feitas", 0)
        lugar.caption(f"Modo convidado: {plural(restantes, 'pergunta restante', 'perguntas restantes')} nesta "
                      f"visita. {PRIVACIDADE}")


bloqueio = motivo_do_bloqueio()
aviso = st.empty()  # preenchido de novo no fim, depois de contar a pergunta desta rodada
mostrar_aviso_de_convidado(aviso, bloqueio)

pergunta = st.chat_input("Ex.: a Vex atordoa a unidade que acabou de ser jogada?", max_chars=500,
                         disabled=bool(bloqueio))
area_de_exemplos = st.empty()  # some assim que a primeira pergunta é feita
if not st.session_state.mensagens and not bloqueio:
    with area_de_exemplos.container():
        st.markdown("**Experimente perguntar:**")
        escolha = st.pills("Exemplos", EXEMPLOS, key="exemplo", label_visibility="collapsed")
    pergunta = pergunta or escolha

# Convidado: a pergunta é "reservada" no contador do dia antes de chamar o juiz (dois visitantes ao
# mesmo tempo não passam do limite) e devolvida se der erro.
reservou = False
if pergunta and e_convidado():
    reservou = contador_diario().consumir()
    if not reservou:
        pergunta = None
        st.rerun()  # mostra o aviso de limite do dia

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
        except Exception as erro:
            traceback.print_exc()  # o detalhe completo vai pro log do servidor (no Streamlit Cloud: Manage app)
            if reservou:
                contador_diario().devolver()
            if not PUBLICO:
                registrar_erro(pergunta, erro)
            if isinstance(erro, CotaEsgotada):
                st.warning(f"{CotaEsgotada.MENSAGEM} Até lá, o juiz não consegue responder.", icon="⏳")
            else:
                st.error(f"Não consegui responder agora ({explicar_erro(erro)}). Tente de novo em alguns instantes.")
            st.session_state.mensagens.pop()
        else:
            msg = montar_mensagem(resposta, uuid.uuid4().hex[:8])
            st.session_state.mensagens.append(msg)
            st.session_state.perguntas_feitas = st.session_state.get("perguntas_feitas", 0) + 1
            if not PUBLICO:
                registrar_resposta(msg["id"], resposta)
            mostrar_resposta(msg, detalhes)

    if e_convidado():
        novo_bloqueio = motivo_do_bloqueio()
        if novo_bloqueio and not bloqueio:
            st.rerun()  # esta foi a última pergunta permitida: redesenha com a caixa de texto desligada
        mostrar_aviso_de_convidado(aviso, novo_bloqueio)

# Prepara o juiz assim que a página abre (depois de desenhar a tela), e não só na 1ª pergunta.
# Na nuvem, a 1ª vez baixa e processa as fontes: o visitante lê a página enquanto isso.
if "juiz_de_teste" not in st.session_state:
    try:
        carregar_juiz()
    except Exception as erro:
        traceback.print_exc()
        st.error(f"O juiz não conseguiu se preparar ({explicar_erro(erro)}). Recarregue a página em alguns instantes.")

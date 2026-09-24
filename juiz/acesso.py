"""Formulário de senha da barra lateral, usado pelo chat do juiz e pelo deck builder.

A senha fica na sessão (st.session_state.dono): quem entra numa página também está liberado na outra.
"""

import streamlit as st

from juiz import config
from juiz.limites import senha_confere


def acesso_com_senha(convite: str = "Tem a senha? Use sem limite", liberado: str = "Uso sem limite liberado.") -> None:
    """Na barra lateral: quem tem a senha usa sem limite (no juiz) e edita a coleção (no deck builder)."""
    if st.session_state.get("dono"):
        st.success(liberado, icon=":material/lock_open:")
        return
    tentativas = st.session_state.get("tentativas_de_senha", 0)
    with st.expander(convite):
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

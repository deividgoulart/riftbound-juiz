"""Juiz Riftbound: ponto de entrada do app, com duas páginas.

Rodar (a partir da raiz do projeto):
    streamlit run app.py

- paginas/juiz.py: o chat do juiz de regras (fase 1).
- paginas/deck_builder.py: coleção de cartas e decks (fase 2).
"""

import streamlit as st

from juiz.ajustes_streamlit import nao_vasculhar_bibliotecas_pesadas

nao_vasculhar_bibliotecas_pesadas()  # evita o observador de arquivos travar com a transformers

st.navigation([
    st.Page("paginas/juiz.py", title="Juiz de regras", icon="⚖️", default=True),
    st.Page("paginas/deck_builder.py", title="Deck builder", icon="🃏", url_path="deck-builder"),
]).run()

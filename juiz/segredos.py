"""Leitura dos "secrets" do app publicado (etapa 8).

No Streamlit Cloud, a chave de API e a senha ficam em Settings > Secrets, num texto no formato TOML:

    GEMINI_API_KEY = "sua-chave"
    SENHA_DO_APP = "sua-senha"

O juiz procura as chaves no ambiente (como no .env local), então este módulo copia os secrets pro
ambiente. Ele também explica o que está errado quando a chave não aparece, porque um erro de
formato (ex.: a chave sem aspas) faz o Streamlit ignorar TODOS os secrets. Nunca mostra valores:
só nomes.
"""

import os
from collections.abc import Callable

NOMES = ("GEMINI_API_KEY", "GROQ_API_KEY", "SENHA_DO_APP", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")


def _achar(segredos: dict, nome: str):
    """Tolera maiúsculas/minúsculas e um nível de seção ("[geral]" seguido de GEMINI_API_KEY = ...)."""
    for chave, valor in segredos.items():
        if chave.upper() == nome:
            return valor
    for valor in segredos.values():
        if isinstance(valor, dict):
            for chave, sub in valor.items():
                if chave.upper() == nome:
                    return sub
    return None


def aplicar_segredos(ler: Callable[[], dict]) -> str | None:
    """Copia os secrets pro ambiente. `ler` devolve os secrets (no app: st.secrets.to_dict).

    Devolve um aviso pro dono do app quando algo está errado, ou None se está tudo certo
    (ou se não há secrets, que é o normal no seu computador: lá as chaves vêm do .env).
    """
    try:
        segredos = ler()
    except FileNotFoundError as erro:  # é o tipo do erro do Streamlit quando falta ou quebra o arquivo
        if getattr(erro, "error_id", "") == "failed-parsing-secrets-file":
            return ("Os secrets do app não estão num formato válido, então nenhum foi lido. Cada linha deve ser "
                    'NOME = "valor", com o valor entre aspas. Ex.: GEMINI_API_KEY = "sua-chave".')
        return None  # sem secrets: rodando localmente

    for nome in NOMES:
        valor = _achar(segredos, nome)
        if valor is not None and str(valor).strip() and not os.environ.get(nome):
            os.environ[nome] = str(valor).strip()

    if not os.environ.get("GEMINI_API_KEY"):
        valor = _achar(segredos, "GEMINI_API_KEY")
        if valor is not None:
            return "GEMINI_API_KEY está nos secrets, mas vazia: cole a chave entre as aspas."
        return (f"Falta GEMINI_API_KEY nos secrets do app (nomes encontrados: {', '.join(sorted(segredos)) or 'nenhum'}). "
                'Acrescente a linha GEMINI_API_KEY = "sua-chave".')
    return None

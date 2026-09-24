"""Contorno pra um problema do Streamlit com a biblioteca transformers (etapa 8).

O Streamlit tem um "observador" que, depois de cada interação, olha todos os módulos importados pra
saber quais arquivos vigiar. A transformers (usada pela busca reserva, e5-small) registra centenas de
submódulos "preguiçosos": só de perguntar se eles têm um caminho, o Python tenta importá-los. Resultado:
cada interação dispara centenas de importações, o log se enche de erros (ex.: "No module named
'torchvision'") e o app fica lento.

Desligar o observador em .streamlit/config.toml (fileWatcherType = "none") não basta: quando o
navegador reconecta (comum no Streamlit Cloud), o Streamlit religa o observador sem conferir essa
opção. Por isso, aqui o observador passa a ignorar essas bibliotecas, que nunca mudam enquanto o app
roda.
"""

BIBLIOTECAS_IGNORADAS = ("transformers", "torch", "sentence_transformers", "torchvision")


def nao_vasculhar_bibliotecas_pesadas() -> None:
    from streamlit.watcher import local_sources_watcher as observador

    original = observador.get_module_paths
    if getattr(original, "ja_ajustado", False):
        return  # o app.py roda de novo a cada interação; o ajuste só precisa ser feito uma vez

    def get_module_paths(module):
        if getattr(module, "__name__", "").split(".")[0] in BIBLIOTECAS_IGNORADAS:
            return set()
        return original(module)

    get_module_paths.ja_ajustado = True
    observador.get_module_paths = get_module_paths

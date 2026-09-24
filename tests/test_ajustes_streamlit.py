"""Testes do contorno pro observador de arquivos do Streamlit (etapa 8)."""

import types

from streamlit.watcher import local_sources_watcher as observador

from juiz.ajustes_streamlit import nao_vasculhar_bibliotecas_pesadas


class ModuloPreguicoso(types.ModuleType):
    """Imita um submódulo da transformers: perguntar pelo caminho dispara uma importação que falha."""

    def __getattr__(self, nome):
        raise ModuleNotFoundError("No module named 'torchvision'")


def test_observador_ignora_bibliotecas_pesadas_e_continua_vendo_o_resto(monkeypatch):
    monkeypatch.setattr(observador, "get_module_paths", observador.get_module_paths)  # desfeito no fim do teste
    nao_vasculhar_bibliotecas_pesadas()
    nao_vasculhar_bibliotecas_pesadas()  # chamar de novo (a cada interação) não empilha ajustes

    assert observador.get_module_paths(ModuloPreguicoso("transformers.models.zoedepth")) == set()
    import juiz.config

    assert any(p.endswith("config.py") for p in observador.get_module_paths(juiz.config))

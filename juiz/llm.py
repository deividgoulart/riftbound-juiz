"""LLM que escreve a resposta (etapa 5).

Todo LLM daqui tem o mesmo método:
    llm.gerar(instrucoes, mensagem) -> texto da resposta

Pra trocar de LLM (por exemplo, pelo Claude Haiku), basta criar outra classe com o mesmo
método e registrar em LLMS. O resto do juiz não muda.
"""

import os
import time

from juiz import config
from juiz.erros import CotaEsgotada, cota_diaria_esgotada

ERROS_TEMPORARIOS = (429, 500, 503)  # limite do tier grátis, erro interno, modelo sobrecarregado


class LLMGemini:
    """Gemini pela API do Google (usa a mesma GEMINI_API_KEY dos embeddings).

    Tenta o modelo principal e, se ele estiver indisponível, os modelos de reserva, em ordem.
    Um modelo que falhou fica "de castigo" por alguns minutos: nas próximas perguntas o juiz vai
    direto pro próximo da lista, em vez de perder tempo esperando o mesmo modelo de novo.
    """

    TENTATIVAS_POR_MODELO = 2
    PAUSA_SEGUNDOS = 300  # quanto tempo um modelo sobrecarregado fica de fora

    def __init__(self, modelos: list[str] | None = None, nivel_de_raciocinio: str = "LOW"):
        self.modelos = modelos or [config.MODELO_LLM, *config.MODELOS_LLM_RESERVA]
        self.nome = self.modelos[0]
        # Os modelos Gemini 3 "pensam" antes de responder. Pra um juiz de regras, raciocínio
        # baixo já basta e a resposta sai bem mais rápido.
        self.nivel_de_raciocinio = nivel_de_raciocinio
        self._cliente = None
        self.ultimo_uso: dict = {}
        self._pausado_ate: dict[str, float] = {}  # modelo -> até quando fica de fora

    @property
    def cliente(self):
        if self._cliente is None:
            from google import genai

            chave = os.environ.get("GEMINI_API_KEY")
            if not chave:
                raise RuntimeError("Coloque GEMINI_API_KEY no arquivo .env (veja o .env.example) ou, no app publicado, nos secrets do Streamlit Cloud")
            self._cliente = genai.Client(api_key=chave)
        return self._cliente

    def gerar(self, instrucoes: str, mensagem: str, esquema=None) -> str:
        """Gera a resposta. Com `esquema` (um modelo pydantic), a resposta vem em JSON nesse formato."""
        from google.genai import errors, types

        formato_json = {"response_mime_type": "application/json", "response_schema": esquema} if esquema else {}
        configuracao = types.GenerateContentConfig(
            system_instruction=instrucoes,
            thinking_config=types.ThinkingConfig(thinking_level=self.nivel_de_raciocinio),
            max_output_tokens=2048,
            # Não usamos ferramentas (function calling); desligar evita um aviso do SDK.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            **formato_json,
        )
        ultimo_erro = None
        agora = time.monotonic()
        disponiveis = [m for m in self.modelos if self._pausado_ate.get(m, 0) <= agora]
        for modelo in disponiveis or self.modelos:  # se todos estão pausados, tenta todos mesmo assim
            for tentativa in range(self.TENTATIVAS_POR_MODELO):
                try:
                    resposta = self.cliente.models.generate_content(model=modelo, contents=mensagem, config=configuracao)
                except errors.APIError as erro:
                    if erro.code not in ERROS_TEMPORARIOS:
                        raise
                    ultimo_erro = erro
                    if cota_diaria_esgotada(erro):
                        break  # a cota é por modelo: este acabou por hoje, mas o próximo da lista pode ter
                    if tentativa < self.TENTATIVAS_POR_MODELO - 1:
                        time.sleep(2)
                    continue
                uso = resposta.usage_metadata
                self.ultimo_uso = {
                    "modelo": modelo,
                    "tokens_entrada": getattr(uso, "prompt_token_count", None),
                    "tokens_saida": getattr(uso, "candidates_token_count", None),
                    "tokens_raciocinio": getattr(uso, "thoughts_token_count", None),
                }
                return (resposta.text or "").strip()
            # Este modelo continua indisponível: fica de fora por um tempo e passa pro próximo.
            # Cota do dia esgotada: 1 hora de fora (tentar a cada 5 minutos só gastaria tempo).
            pausa = 3600 if cota_diaria_esgotada(ultimo_erro) else self.PAUSA_SEGUNDOS
            self._pausado_ate[modelo] = time.monotonic() + pausa
        if ultimo_erro is not None and cota_diaria_esgotada(ultimo_erro):
            raise CotaEsgotada(", ".join(self.modelos)) from ultimo_erro
        raise ultimo_erro


LLMS = {"gemini": LLMGemini}


def carregar_llm(nome: str = "gemini"):
    return LLMS[nome]()

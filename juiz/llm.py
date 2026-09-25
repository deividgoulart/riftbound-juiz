"""LLM que escreve a resposta (etapa 5).

Todo LLM daqui tem o mesmo método:
    llm.gerar(instrucoes, mensagem) -> texto da resposta

Pra trocar de LLM (por exemplo, pelo Claude Haiku), basta criar outra classe com o mesmo
método e registrar em LLMS. O resto do juiz não muda.
"""

import os
import re
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
                raise RuntimeError("Coloque GEMINI_API_KEY no arquivo .env (veja o .env.example) ou, no app publicado, nos secrets da API (Render)")
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


class ErroGroq(RuntimeError):
    """Erro devolvido pela API do Groq (a mensagem dele nunca traz a chave)."""

    def __init__(self, codigo: int, mensagem: str):
        super().__init__(f"o Groq respondeu com erro {codigo}: {mensagem[:300]}")
        self.codigo = codigo
        # Ex.: "Rate limit reached ... on tokens per day (TPD)". Por dia, esperar não adianta.
        self.por_dia = codigo == 429 and ("per day" in mensagem.lower() or "(tpd)" in mensagem.lower()
                                          or "(rpd)" in mensagem.lower())


class LLMGroq:
    """Reserva de outra empresa (etapa 8): modelos abertos no Groq, pelo plano grátis.

    Entra quando todos os Gemini falham, que é o que acontece no plano grátis do Google em horário
    de pico (erro 503, "high demand"). O Groq tem capacidade própria. O plano grátis é apertado
    (8 mil tokens por minuto e 200 mil por dia: ~1 pergunta por minuto e ~40 por dia), mas como
    reserva basta. A API segue o formato da OpenAI, então basta um POST com httpx.
    """

    URL = "https://api.groq.com/openai/v1/chat/completions"
    ERROS_TEMPORARIOS = (429, 498, 500, 502, 503)  # limite por minuto, capacidade, instabilidade

    def __init__(self, modelo: str | None = None):
        self.modelo = modelo or config.MODELO_GROQ
        self.nome = f"groq/{self.modelo}"
        self.ultimo_uso: dict = {}

    @staticmethod
    def configurado() -> bool:
        return bool(os.environ.get("GROQ_API_KEY"))

    def _maximo_de_saida(self) -> int:
        # O Qwen tem um limite de 1.000 tokens de SAÍDA por minuto no plano grátis, e o Groq recusa o
        # pedido se a saída prevista (calculada a partir deste máximo) passar disso.
        return 1024 if self.modelo.startswith("qwen/") else 2048

    def _raciocinio(self) -> dict:
        """Raciocínio curto e escondido: só a resposta final volta (e gasta menos da cota de tokens)."""
        if self.modelo.startswith("openai/gpt-oss"):
            return {"reasoning_effort": "low", "include_reasoning": False}
        if self.modelo.startswith("qwen/"):
            return {"reasoning_effort": "low", "reasoning_format": "hidden"}
        return {}

    def gerar(self, instrucoes: str, mensagem: str, esquema=None) -> str:
        if esquema is not None:
            raise ValueError("O Groq não é usado pra respostas em JSON (o avaliador usa só o Gemini).")
        import httpx

        chave = os.environ.get("GROQ_API_KEY")
        if not chave:
            raise RuntimeError("Coloque GROQ_API_KEY no .env ou, no app publicado, nos secrets da API (Render)")
        corpo = {
            "model": self.modelo,
            "messages": [{"role": "system", "content": instrucoes}, {"role": "user", "content": mensagem}],
            "max_completion_tokens": self._maximo_de_saida(),
            **self._raciocinio(),
        }
        for tentativa in range(2):
            resposta = httpx.post(self.URL, json=corpo, headers={"Authorization": f"Bearer {chave}"}, timeout=60)
            if resposta.status_code == 200:
                break
            try:
                detalhe = resposta.json().get("error", {}).get("message", "")
            except ValueError:
                detalhe = resposta.text
            erro = ErroGroq(resposta.status_code, detalhe)
            if erro.por_dia:
                raise CotaEsgotada(self.nome) from erro
            if resposta.status_code not in self.ERROS_TEMPORARIOS or tentativa == 1:
                raise erro
            time.sleep(min(float(resposta.headers.get("retry-after") or 2), 10))
        dados = resposta.json()
        uso = dados.get("usage") or {}
        self.ultimo_uso = {"modelo": self.nome, "tokens_entrada": uso.get("prompt_tokens"),
                           "tokens_saida": uso.get("completion_tokens")}
        return (dados["choices"][0]["message"].get("content") or "").strip()


class LLMOllama:
    """LLM que roda no seu computador, pelo Ollama (https://ollama.com): sem cota e sem chave.

    Usado só pra gerar as explicações das cartas em lote (api/gerar_explicacoes.py), sem gastar o Gemini. Os modelos
    que cabem num computador comum escrevem pior em português do que o Gemini, então o juiz do site
    continua no Gemini. Antes: instale o Ollama e baixe o modelo (ex.: ollama pull qwen3:8b).
    """

    URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

    def __init__(self, modelo: str, cliente=None):
        self.modelo = modelo
        self.nome = f"ollama/{modelo}"
        self.ultimo_uso: dict = {}
        self._cliente = cliente

    def gerar(self, instrucoes: str, mensagem: str, esquema=None) -> str:
        import httpx

        cliente = self._cliente or httpx.Client(timeout=600)  # no processador, uma resposta pode levar minutos
        # num_ctx: o padrão do Ollama (~4 mil tokens) corta as fontes sem avisar
        corpo = {"model": self.modelo, "stream": False, "think": False,
                 "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 1500},
                 "messages": [{"role": "system", "content": instrucoes}, {"role": "user", "content": mensagem}]}
        try:
            resposta = cliente.post(f"{self.URL}/api/chat", json=corpo)
        except httpx.ConnectError:
            raise RuntimeError("o Ollama não está rodando (abra o app do Ollama ou rode 'ollama serve')") from None
        if resposta.status_code == 404:
            raise RuntimeError(f"o Ollama não tem o modelo {self.modelo} (rode: ollama pull {self.modelo})")
        resposta.raise_for_status()
        dados = resposta.json()
        self.ultimo_uso = {"modelo": self.nome, "tokens_entrada": dados.get("prompt_eval_count"),
                           "tokens_saida": dados.get("eval_count")}
        return re.sub(r"<think>.*?</think>", "", dados["message"]["content"], flags=re.S).strip()


class LLMComReservas:
    """Tenta cada LLM em ordem (os Gemini e depois o Groq). O juiz não precisa saber quem respondeu.

    Um LLM sem chave configurada é pulado. Se todos falharem, levanta o erro mais útil: um erro
    passageiro (sobrecarga) antes de "cota do dia esgotada", porque tentar de novo pode resolver.
    """

    def __init__(self, llms: list):
        self.llms = llms
        self.nome = llms[0].nome
        self.ultimo_uso: dict = {}

    def gerar(self, instrucoes: str, mensagem: str, esquema=None) -> str:
        erros = []
        for llm in self.llms:
            if not getattr(llm, "configurado", lambda: True)():
                continue
            try:
                texto = llm.gerar(instrucoes, mensagem, esquema)
            except Exception as erro:
                erros.append(erro)
                continue
            if not texto.strip():
                # Acontece com modelos que "pensam" escondido: o raciocínio gasta todo o limite de
                # saída e a resposta vem vazia (visto no Qwen do Groq). Vazio é falha: tenta o próximo.
                erros.append(RuntimeError(f"{llm.nome} devolveu uma resposta vazia"))
                continue
            self.ultimo_uso = dict(llm.ultimo_uso)
            return texto
        passageiros = [e for e in erros if not isinstance(e, CotaEsgotada)]
        raise (passageiros or erros)[0]


LLMS = {"gemini": LLMGemini}


def carregar_llm(nome: str = "gemini"):
    """O LLM do juiz: os Gemini e, se houver GROQ_API_KEY, o Groq como última reserva."""
    if nome != "gemini":
        return LLMS[nome]()
    return LLMComReservas([LLMGemini(), LLMGroq()])

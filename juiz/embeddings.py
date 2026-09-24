"""Modelos de embeddings: transformam texto em vetores de números.

Textos com sentido parecido viram vetores próximos, mesmo em línguas diferentes (modelos
multilíngues). É isso que deixa uma pergunta em português achar um trecho em inglês.

Todos os modelos daqui têm os mesmos dois métodos:
    modelo.documentos(textos, titulos) -> matriz (quantidade de textos x dimensões)
    modelo.perguntas(textos)           -> matriz (quantidade de textos x dimensões)

Por que dois métodos? Os modelos de busca costumam ser treinados com um "aviso" diferente
para pergunta e para documento (o e5 usa "query: " e "passage: "). Usar o aviso certo
melhora a busca.

Os vetores saem normalizados (comprimento 1). Assim, a similaridade de cosseno entre dois
vetores é só o produto escalar entre eles.
"""

import os
import time

import numpy as np

from juiz.erros import CotaEsgotada, cota_diaria_esgotada

# Instrução pro Qwen3: ele funciona melhor quando sabe qual é a tarefa (a documentação
# recomenda escrever a instrução em inglês).
INSTRUCAO_QWEN = (
    "Instruct: Given a player's question about the rules of the Riftbound trading card game, "
    "retrieve rules and rulings that answer it\nQuery:"
)


def _normalizar(matriz: np.ndarray) -> np.ndarray:
    return (matriz / np.linalg.norm(matriz, axis=1, keepdims=True)).astype(np.float32)


class ModeloLocal:
    """Modelo que roda no seu computador, via sentence-transformers (baixado do HuggingFace)."""

    def __init__(self, nome: str, id_hf: str, max_tokens: int = 512,
                 prefixo_pergunta: str = "", prefixo_documento: str = "", instrucao_pergunta: str | None = None):
        self.nome = nome
        self.id = id_hf
        self.max_tokens = max_tokens
        self.prefixo_pergunta = prefixo_pergunta
        self.prefixo_documento = prefixo_documento
        self.instrucao_pergunta = instrucao_pergunta
        self._modelo = None

    @property
    def modelo(self):
        if self._modelo is None:
            # O import fica aqui dentro porque carregar o PyTorch demora uns segundos.
            from sentence_transformers import SentenceTransformer

            self._modelo = SentenceTransformer(self.id, device="cpu")
            self._modelo.max_seq_length = self.max_tokens  # o que passar disso é cortado
        return self._modelo

    def _codificar(self, textos: list[str], **opcoes) -> np.ndarray:
        vetores = self.modelo.encode(
            textos, batch_size=16, normalize_embeddings=True, convert_to_numpy=True,
            show_progress_bar=len(textos) > 50, **opcoes,
        )
        return vetores.astype(np.float32)

    def documentos(self, textos: list[str], titulos: list[str] | None = None) -> np.ndarray:
        return self._codificar([self.prefixo_documento + t for t in textos])

    def perguntas(self, textos: list[str]) -> np.ndarray:
        if self.instrucao_pergunta:
            return self._codificar(textos, prompt=self.instrucao_pergunta)
        return self._codificar([self.prefixo_pergunta + t for t in textos])

    def contar_tokens(self, texto: str) -> int:
        return len(self.modelo.tokenizer(self.prefixo_documento + texto)["input_ids"])


class ModeloGemini:
    """Gemini Embedding 2, pela API do Google (precisa de GEMINI_API_KEY no .env)."""

    LOTE = 20  # textos por requisição (cada trecho tem ~250 tokens)

    def __init__(self, dimensoes: int = 768):
        self.nome = "gemini-2"
        self.id = "gemini-embedding-2"
        self.max_tokens = 8192
        self.dimensoes = dimensoes
        self._cliente = None

    @property
    def cliente(self):
        if self._cliente is None:
            from google import genai

            chave = os.environ.get("GEMINI_API_KEY")
            if not chave:
                raise RuntimeError("Coloque GEMINI_API_KEY no arquivo .env (veja o .env.example)")
            self._cliente = genai.Client(api_key=chave)
        return self._cliente

    def _codificar(self, textos: list[str], tentativas: int = 6, espera: float = 5) -> np.ndarray:
        """Manda os textos pra API. Em erro temporário, tenta de novo esperando cada vez mais."""
        from google.genai import errors, types

        vetores = []
        for inicio in range(0, len(textos), self.LOTE):
            # Cada texto vai num Content separado. Se fossem todos juntos, o gemini-embedding-2
            # devolveria UM vetor só pra tudo.
            conteudos = [types.Content(parts=[types.Part.from_text(text=t)]) for t in textos[inicio:inicio + self.LOTE]]
            for tentativa in range(tentativas):
                try:
                    resposta = self.cliente.models.embed_content(
                        model=self.id, contents=conteudos,
                        config=types.EmbedContentConfig(output_dimensionality=self.dimensoes),
                    )
                    break
                except errors.APIError as erro:
                    if cota_diaria_esgotada(erro):  # esperar minutos não resolve uma cota por dia
                        raise CotaEsgotada(self.id) from erro
                    # 429 = limite por minuto do tier grátis; 5xx = instabilidade. Espera e tenta de novo.
                    if erro.code not in (429, 500, 503) or tentativa == tentativas - 1:
                        raise
                    time.sleep(espera * 2 ** tentativa)
            vetores.extend(e.values for e in resposta.embeddings)
        return _normalizar(np.array(vetores, dtype=np.float32))

    def documentos(self, textos: list[str], titulos: list[str] | None = None) -> np.ndarray:
        # Formato recomendado pela documentação do Gemini Embedding 2 para documentos.
        titulos = titulos or ["none"] * len(textos)
        return self._codificar([f"title: {titulo} | text: {texto}" for titulo, texto in zip(titulos, textos)])

    def perguntas(self, textos: list[str]) -> np.ndarray:
        # Na hora de responder, quem está esperando é o jogador: poucas tentativas e espera curta.
        # Se o Gemini não responder logo, o juiz usa a busca reserva (e5-small).
        return self._codificar([f"task: search result | query: {t}" for t in textos], tentativas=2, espera=1)


# Os modelos comparados na etapa 4. São funções para só carregar o modelo quando for usado.
MODELOS = {
    "e5-small": lambda: ModeloLocal("e5-small", "intfloat/multilingual-e5-small",
                                    prefixo_pergunta="query: ", prefixo_documento="passage: "),
    "e5-base": lambda: ModeloLocal("e5-base", "intfloat/multilingual-e5-base",
                                   prefixo_pergunta="query: ", prefixo_documento="passage: "),
    "qwen3-0.6b": lambda: ModeloLocal("qwen3-0.6b", "Qwen/Qwen3-Embedding-0.6B", max_tokens=1024,
                                      instrucao_pergunta=INSTRUCAO_QWEN),
    "gemini-2": lambda: ModeloGemini(),
}


def carregar_modelo(nome: str):
    if nome not in MODELOS:
        raise ValueError(f"Modelo desconhecido: {nome}. Opções: {', '.join(MODELOS)}")
    return MODELOS[nome]()

"""Configuração central: caminhos, URLs das fontes e variáveis do .env.

Todo módulo que precisa saber onde fica um arquivo importa daqui.
Assim cada caminho é definido num lugar só, e mudar a pasta de dados, por exemplo,
é uma alteração de uma linha.
"""

from pathlib import Path

from dotenv import load_dotenv

# Raiz do projeto: a pasta acima de juiz/
RAIZ = Path(__file__).resolve().parent.parent

# Carrega as chaves do arquivo .env (se existir) como variáveis de ambiente.
load_dotenv(RAIZ / ".env")

# --- Pastas de dados ---
DATA_DIR = RAIZ / "data"
RAW_DIR = DATA_DIR / "raw"  # dados como vieram da fonte
PROCESSED_DIR = DATA_DIR / "processed"  # dados limpos e divididos em trechos (etapa 2 em diante)

INDEX_DIR = DATA_DIR / "index"  # vetores de cada modelo de embeddings (etapa 4)
# Os mesmos vetores, sem o texto, publicados no GitHub pro app na nuvem não gastar a cota (etapa 8)
VETORES_DIR = DATA_DIR / "vetores"
ATUALIZACAO = DATA_DIR / "atualizacao.json"  # quando e o que a última atualização fez (etapa 8)
LOGS_DIR = DATA_DIR / "logs"  # perguntas feitas no app e avaliações 👍/👎 (etapa 6; fora do git)

# Modelo de embeddings escolhido na etapa 4 (notebooks/02_comparar_busca.ipynb):
# acertou as 24 perguntas do gabarito em 1º lugar.
MODELO_EMBEDDINGS = "gemini-2"
# Reserva da busca: roda no computador, sem cota nem internet. Entra quando o Gemini falha
# (cota diária de 1.000 textos esgotada, sobrecarga, sem conexão). Na etapa 4 ele achou a fonte
# certa entre os 5 primeiros em todas as perguntas do gabarito (88% em 1º lugar).
MODELO_EMBEDDINGS_RESERVA = "e5-small"

# --- Resposta (etapa 5) ---
MODELO_LLM = "gemini-3.8-flash"  # escolhido na etapa 5: tier grátis, mesma chave dos embeddings
# No tier grátis, os modelos mais novos às vezes ficam sobrecarregados (erro 503). Quando isso
# acontece, o juiz tenta estes, em ordem (ambos também têm tier grátis).
MODELOS_LLM_RESERVA = ["gemini-3.5-flash", "gemini-3.5-flash-lite"]
# Reserva de outra empresa (etapa 8): quando os três Gemini falham (sobrecarga no plano grátis do
# Google), a resposta vem de um modelo aberto no Groq. Só entra se GROQ_API_KEY estiver configurada.
# Escolhido em 24/09/2026 nas 18 perguntas de comparação: o gpt-oss-120b empatou com o Flash-Lite na
# conclusão (91%) e foi mais rápido; o qwen3.8-27b devolveu 4 respostas vazias (o raciocínio escondido
# gastou o limite de 1.000 tokens de saída por minuto do plano grátis).
MODELO_GROQ = "openai/gpt-oss-120b"
K_TRECHOS = 5  # quantos trechos da busca vão pro LLM
K_TRECHOS_EXPLICACAO = 8  # pedidos de explicação ("como funciona a Chain?") precisam de mais material
MAX_TURNOS_HISTORICO = 3  # quantas perguntas e respostas anteriores o juiz leva em conta
# Nota mínima do 1º resultado da busca. Abaixo dela, o juiz responde "não encontrei" sem chamar o LLM.
# Histórico: a etapa 4 sugeriu 0,70 (o gabarito separava bem as perguntas sem resposta). No uso
# real, perguntas curtas de definição ("o que é open state?") tiveram nota 0,66-0,70 mesmo com a
# regra certa em 1º lugar, e caíram no "não encontrei". Como essas notas se misturam com as das
# perguntas fora do escopo (ex.: "mana burn" = 0,675), nenhum corte separa os dois grupos. Por isso
# o corte agora só barra o que é claramente sem relação; na faixa cinzenta, quem decide é o LLM.
# Cada modelo tem sua própria escala de similaridade, então cada um tem seu corte. No e5-small
# as notas ficam espremidas entre ~0,78 e 0,91 (etapa 4), e as com resposta começaram em 0,82.
LIMIAR_NAO_ENCONTREI = {"gemini-2": 0.60, "e5-small": 0.78}
MAX_REGRAS_CITADAS = 20  # regras do CRD citadas pelo FAQ que entram no contexto (texto oficial)
MAX_CARTAS = 5  # textos de carta que entram no contexto
GLOSSARIO = RAIZ / "juiz" / "glossario.yaml"
DEFINICOES = RAIZ / "juiz" / "definicoes.yaml"  # definições oficiais dos termos técnicos (números de regra)
MAX_DEFINICOES = 6  # quantos termos técnicos ganham a definição oficial no contexto
# Acrescentar os termos do glossário à pergunta ANTES da busca? Medido com o gabarito
# (python -m juiz.avaliar_busca --modelos gemini-2 --glossario): com o Gemini, o hit@1 caiu de
# 100% pra 92%, porque os termos colados no fim ("(Kill, Unit)") distorcem o sentido da pergunta.
# Por isso o glossário fica só na resposta (o LLM recebe os termos oficiais em inglês).
USAR_GLOSSARIO_NA_BUSCA = False

# --- Avaliação ---
# Perguntas-gabarito escritas à mão (versionadas no git, ao contrário de data/).
GABARITO = RAIZ / "avaliacao" / "gabarito.yaml"
RESULTADOS_DIR = RAIZ / "avaliacao" / "resultados"  # tabelas das comparações (versionadas)
# Avaliação das respostas (etapa 7). O avaliador é o Flash-Lite: tem cota diária maior, e a
# concordância dele com uma revisão humana é medida (avaliacao/revisao_humana.csv).
MODELO_AVALIADOR = "gemini-3.5-flash-lite"
# Perguntas da comparação entre LLMs: o 3.8 Flash só tem 20 respostas por dia no tier grátis,
# então a comparação usa 18 perguntas em comum, de todas as categorias.
IDS_COMPARACAO = ["q01", "q04", "q05", "q08", "q12", "q15", "q29", "q18", "q20",
                  "q22", "q30", "q34", "q37", "q40", "q35", "q25", "q27", "q45"]

# --- Fonte 1: FAQ não oficial (riftboundfaq.com) ---
FAQ_REPO_URL = "https://github.com/ChristianIvicevic/riftboundfaq.git"
FAQ_BRANCH = "main"
FAQ_DIR = RAW_DIR / "riftboundfaq"
FAQ_CONTENT_DIR = FAQ_DIR / "content"
FAQ_SOURCES_DIR = FAQ_DIR / "sources"
FAQ_SNAPSHOT = RAW_DIR / "faq_snapshot.json"

# Só baixamos o que interessa (sparse checkout). O repositório tem uns 220 MB
# de PDFs em sources/ que não precisamos aqui.
FAQ_SPARSE_PATHS = [
    "/content/",  # as páginas do FAQ (MDX)
    "/sources/*.json",  # catálogo de cartas, erratas e manifesto de versões do CRD
    "/src/lib/glossary.ts",  # glossário com explicações pra iniciantes (Chain, Priority, Focus...)
    "/LICENSE-CC-BY-SA-4.0",  # licença do conteúdo (precisamos dar crédito)
    "/LICENSE-MIT",  # licença do código do FAQ (o glossário fica no código)
]
FAQ_GLOSSARIO = FAQ_DIR / "src" / "lib" / "glossary.ts"
FAQ_GITHUB_URL = "https://github.com/ChristianIvicevic/riftboundfaq"

FAQ_SITE_URL = "https://www.riftboundfaq.com"
FAQ_AUTOR = 'Christian "Near" Ivicevic'
FAQ_LICENCA = "CC BY-SA 4.0"

# --- Fonte 2: Core Rules Document (CRD) oficial da Riot ---
# A página oficial lista sempre a versão mais atual. O link do PDF muda a cada versão.
CRD_RULES_HUB_URL = "https://playriftbound.com/en-us/rules-hub/"
# v1.4 "Vendetta", atualizada em 16/07/2026 (conferido em 23/09/2026)
CRD_PDF_URL = (
    "https://cmsassets.rgpub.io/sanity/files/dsfx7636/news_live/"
    "e9ac8e3d33e0f78cef296f5945aba7bc1313b086.pdf"
)
# O repositório do FAQ não guarda o CRD estruturado (é gerado no build do site), mas o site
# publica o CRD inteiro em HTML, com uma âncora por regra. Usamos essa página como fonte do
# texto e deixamos o PDF oficial como link. A versão atual vem do rules-manifest.json do FAQ.
CRD_HTML_URL = FAQ_SITE_URL + "/reference/core-rules/{versao}"
CRD_REGRA_URL = CRD_HTML_URL + "#R{regra}"  # ex.: .../core-rules/1.4#R355.9.a
CRD_RAW_DIR = RAW_DIR / "crd"
CRD_SNAPSHOT = RAW_DIR / "crd_snapshot.json"

# --- App publicado (etapa 8) ---
# O app se atualiza sozinho (FAQ, CRD, trechos e índices) quando a última atualização tem mais que isso.
ATUALIZAR_A_CADA_HORAS = 24
# Modo convidado: só vale quando a variável SENHA_DO_APP existe (nos secrets do Streamlit Cloud).
# Protege a cota grátis do Gemini de visitantes; com a senha, o uso não tem limite.
LIMITE_POR_VISITA = 10  # perguntas por visita (sessão do navegador)
LIMITE_DIARIO = 100  # perguntas de convidados por dia, somando todos os visitantes
TENTATIVAS_DE_SENHA = 5  # por visita, pra ninguém ficar chutando senhas

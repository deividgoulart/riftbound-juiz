# Riftbound Juiz

Chatbot que funciona como **juiz de regras do Riftbound TCG** (o card game de League of Legends).
Você pergunta em português, ele responde rápido, cita a regra ou página usada (com link) e diz claramente quando não encontrou a resposta, em vez de inventar.

Por baixo, é um **RAG** (*Retrieval-Augmented Generation*): primeiro o app **busca** os trechos mais relevantes das regras e depois pede pra um LLM **responder usando só esses trechos**.

**Experimente:** [riftbound-juiz.streamlit.app](https://riftbound-juiz.streamlit.app). Sem cadastro, com um limite de perguntas por visita.

> Projeto pessoal e de portfólio de dados. A fase 1 (o juiz) está concluída. A fase 2, um **deck builder**, está em andamento: a 1ª etapa (coleção, importação de decks e o que falta pra montar cada um) já está no app.

## Status

| Etapa | Descrição | Status |
|---|---|---|
| 1 | Estrutura do projeto + download e exploração do FAQ | ✅ concluída |
| 2 | Limpeza dos MDX e divisão em trechos (chunking) | ✅ concluída |
| 2b | Perguntas-gabarito em português (resposta e fonte esperadas) | ✅ concluída |
| 3 | Core Rules Document (CRD) oficial | ✅ concluída |
| 4 | Embeddings multilíngues + índice vetorial | ✅ concluída |
| 5 | LLM + geração da resposta (com glossário PT→EN) | ✅ concluída |
| 6 | Interface de chat em Streamlit | ✅ concluída |
| 7 | Avaliação completa (métricas de busca e de resposta) | ✅ concluída |
| 8 | Atualização automática + publicação | ✅ concluída: [app publicado](https://riftbound-juiz.streamlit.app) |

**Fase 2: deck builder**

| Etapa | Descrição | Status |
|---|---|---|
| 1 | Catálogo de cartas no banco, coleção, importação manual de deck e % de conclusão | ✅ concluída |
| 2 | Decks do meta coletados automaticamente (API do TopDeck.gg) | ✅ concluída |
| 3 | Links, lista de compra e preço das cartas que faltam (Liga Riftbound), juiz falando dos meus decks | ✅ concluída |

## Como funciona

```mermaid
flowchart LR
    subgraph fontes["Fontes (baixadas por juiz.atualizar)"]
        FAQ["Riftbound FAQ<br/>(git, MDX)"]
        CRD["Core Rules<br/>(HTML)"]
    end
    FAQ --> L["Limpeza e divisão<br/>em trechos"]
    CRD --> L
    L --> T[("~500 trechos")]
    T --> E["Embeddings<br/>Gemini (principal)<br/>e5-small (reserva)"]
    E --> I[("Índice NumPy")]
    P["Pergunta em português"] --> B["Busca por<br/>similaridade"]
    I --> B
    B --> C["Contexto: trechos F1..F5<br/>+ regras citadas + cartas<br/>+ definições oficiais"]
    C --> LLM["LLM Gemini<br/>(com reservas)"]
    LLM --> R["Resposta em português<br/>com fontes clicáveis"]
```

Se nada parecido o bastante for encontrado, o juiz diz que não encontrou, sem chamar o LLM.

## Fontes de dados

| Fonte | O que é | Onde |
|---|---|---|
| **Riftbound FAQ** | FAQ não oficial com respostas explicadas e citação de regras, por Christian "Near" Ivicevic | [riftboundfaq.com](https://www.riftboundfaq.com) · [repositório](https://github.com/ChristianIvicevic/riftboundfaq) |
| **Core Rules Document (CRD)** | Regras oficiais da Riot. Versão atual: **v1.4 "Vendetta"**, de 16/07/2026 | [Rules Hub oficial](https://playriftbound.com/en-us/rules-hub/) · [PDF oficial](https://cmsassets.rgpub.io/sanity/files/dsfx7636/news_live/e9ac8e3d33e0f78cef296f5945aba7bc1313b086.pdf) · [versão HTML](https://www.riftboundfaq.com/reference/core-rules/1.4) (de onde o texto é lido) |

**Qual fonte vale mais:** o CRD vale mais que o FAQ não oficial. A exceção é quando um **FAQ oficial da Riot** diz explicitamente que tem precedência num ponto; isso acontece em 3 páginas do FAQ que citam o *Vendetta Rules FAQ*.

Os dados **não ficam no repositório**: são baixados pelos scripts pra `data/raw/` (que está no `.gitignore`).

## Estrutura do projeto

```
riftbound-juiz/
├── app.py                  # entrada do app: menu com as duas páginas
├── paginas/
│   ├── juiz.py             # chat do juiz de regras (etapa 6)
│   └── deck_builder.py     # coleção e decks (fase 2)
├── .streamlit/config.toml  # tema e configurações do Streamlit
├── juiz/                   # código Python do projeto
│   ├── config.py           # caminhos, URLs das fontes, leitura do .env
│   ├── baixar_faq.py       # baixa/atualiza o FAQ (git sparse checkout)
│   ├── limpar_faq.py       # MDX -> trechos limpos com metadados (etapa 2)
│   ├── baixar_crd.py       # baixa o CRD em HTML, na versão que o FAQ marca como atual (etapa 3)
│   ├── limpar_crd.py       # HTML -> regras (pra consulta) e trechos (pra busca) (etapa 3)
│   ├── embeddings.py       # modelos que transformam texto em vetores (etapa 4)
│   ├── indice.py           # cria o índice (NumPy) e faz a busca (etapa 4)
│   ├── avaliar_busca.py    # compara os modelos usando o gabarito (etapa 4)
│   ├── glossario.yaml      # termos em português -> termo oficial em inglês (etapa 5)
│   ├── glossario.py        # acha os termos do glossário na pergunta (etapa 5)
│   ├── cartas.py           # texto oficial das cartas, com errata (etapa 5)
│   ├── llm.py              # LLM (Gemini) com modelos de reserva (etapa 5)
│   ├── responder.py        # o juiz: busca + contexto + instruções + LLM (etapa 5)
│   ├── definicoes.yaml     # termo técnico -> definição oficial (CRD e glossário do FAQ)
│   ├── erros.py            # aviso de cota diária esgotada
│   ├── perguntar.py        # pergunte pelo terminal (etapa 5)
│   ├── apresentacao.py     # citações viram links, créditos (etapa 6)
│   ├── registro.py         # guarda perguntas e 👍/👎 em data/logs/ (etapa 6)
│   ├── avaliar_respostas.py # avalia as respostas: métricas, avaliador LLM e revisão humana (etapa 7)
│   ├── atualizar.py        # baixa e processa FAQ e CRD e atualiza os índices, só o que mudou (etapa 8)
│   ├── limites.py          # modo convidado do app publicado: limites e senha (etapa 8)
│   └── acesso.py           # formulário de senha, usado pelas duas páginas (fase 2)
├── decks/                  # deck builder (fase 2), sem Streamlit: só lógica e banco
│   ├── banco.py            # SQLite local ou Turso (SQLite na nuvem) pela API HTTP
│   ├── catalogo.py         # tabela mestre de cartas (card-catalog.json + runas) e nomes
│   ├── colecao.py          # minha coleção: quantidades, CSV e comandos no terminal
│   ├── importar.py         # lê a lista de deck em texto e confere as regras de construção
│   ├── meus_decks.py       # salva, lista e apaga decks
│   ├── meta.py             # decks de torneio pela API do TopDeck.gg (etapa 2)
│   ├── codigos.py          # código da carta (OGN-042) -> nome, pela galeria oficial da Riot
│   ├── compras.py          # links e lista de compra da Liga Riftbound (etapa 3)
│   ├── precos.py           # preço das cartas que faltam, pelo resumo do marketplace da Liga (etapa 3)
│   └── conclusao.py        # % de conclusão, cartas que faltam e ranking dos decks
├── avaliacao/
│   ├── gabarito.yaml       # perguntas-gabarito com resposta e fonte esperadas (etapa 2b; 45 na etapa 7)
│   ├── revisao_humana.csv  # 12 respostas com a nota de uma pessoa, às cegas (etapa 7)
│   └── resultados/         # resultados das avaliações de busca (etapa 4) e de resposta (etapa 7)
├── notebooks/
│   ├── 01_explorar_faq.ipynb   # exploração dos dados (etapa 1)
│   ├── 02_comparar_busca.ipynb # comparação dos modelos de busca (etapa 4)
│   └── 03_avaliar_respostas.ipynb # qualidade das respostas (etapa 7)
├── data/
│   ├── raw/                # dados como vieram da fonte (não versionado)
│   ├── processed/          # dados limpos e divididos em trechos (não versionado)
│   └── vetores/            # vetores da busca, sem o texto (versionado: o app publicado reaproveita)
├── tests/                  # testes automatizados (python -m pytest)
├── requirements.txt        # dependências do app (o que o Streamlit Cloud instala)
├── requirements-dev.txt    # + notebooks, testes e comparações
├── packages.txt            # pacote do sistema pro Streamlit Cloud (git)
├── pytest.ini              # configuração dos testes
├── .streamlit/secrets.toml.example  # modelo dos secrets do app publicado
└── .env.example            # modelo do arquivo de chaves de API
```

## Como rodar

Requisitos: Python 3.12+ e git.

```powershell
# 1. Criar e ativar o ambiente virtual
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Instalar as dependências (requirements-dev.txt inclui as do app e as de desenvolvimento)
pip install -r requirements-dev.txt

# 3. Baixar o FAQ e o CRD, dividir em trechos e montar os índices, tudo de uma vez.
#    Da 2ª vez em diante, só refaz o que mudou nas fontes.
python -m juiz.atualizar

# 4. Abrir o app no navegador (http://localhost:8501): o chat do juiz e, no menu, o deck builder.
#    Ele também roda o passo 3 sozinho, se os dados não existirem ou tiverem mais de um dia.
streamlit run app.py

# (Deck builder) Coleção pelo terminal, além da tela do app
python -m decks.colecao exportar colecao.csv
python -m decks.colecao importar colecao.csv
python -m decks.colecao importar export_liga.csv --substituir   # coleção = exatamente o arquivo
python -m decks.colecao definir "Jinx, Rebel" 2

# (Deck builder) Decks de torneio do TopDeck.gg (precisa de TOPDECK_API_KEY no .env)
python -m decks.meta --forcar

# (Os passos do juiz.atualizar, um por um, se quiser ver cada parte)
python -m juiz.baixar_faq    # baixa só uns 0,7 MB, em vez dos mais de 200 MB do repositório inteiro
python -m juiz.limpar_faq    # -> data/processed/faq_trechos.jsonl
python -m juiz.baixar_crd
python -m juiz.limpar_crd    # -> data/processed/crd_regras.jsonl e crd_trechos.jsonl
python -m juiz.indice --buscar "posso usar emboscada na base?"

# (Ou perguntar pelo terminal)
python -m juiz.perguntar "o Guardian Angel salva minha unidade do Smite?"
python -m juiz.perguntar "posso usar emboscada na base?" --detalhes   # mostra a busca por dentro

# (Opcional) Refazer a comparação de modelos de busca (baixa uns 1,6 GB de modelos locais na 1ª vez)
python -m juiz.avaliar_busca

# (Opcional) Avaliar as respostas com o gabarito (gasta cota: 1 resposta + 1 nota do avaliador por pergunta)
python -m juiz.avaliar_respostas --modelo gemini-3.5-flash-lite
python -m juiz.avaliar_respostas --modelo gemini-3.8-flash --comparacao   # só 18 perguntas (cota de 20/dia)
python -m juiz.avaliar_respostas --concordancia flash-lite_e5             # revisão humana x avaliador

# Explorar os dados e ver as comparações
jupyter notebook notebooks/

# 5. Rodar os testes
python -m pytest
```

A partir da etapa 4 é preciso uma chave grátis do Gemini: crie em [aistudio.google.com/apikey](https://aistudio.google.com/apikey), copie `.env.example` para `.env` e cole a chave em `GEMINI_API_KEY=`.
O tier grátis tem **cota diária**: 1.000 textos por dia no modelo de embeddings, e cada pergunta usa 1. A cota zera à meia-noite do horário do Pacífico, por volta das 4h ou 5h em Brasília.

## O que a exploração encontrou (etapa 1)

- **63 páginas MDX**: 49 de cartas, 7 de regras gerais, 6 de mecânicas e 1 "sobre o site". São umas 21 mil palavras no total.
- **183 perguntas** (`##`/`###`), todas com âncora, ou seja, com link direto. A maior tem 349 palavras, então cada pergunta cabe inteira num trecho.
- **1.134 citações de 408 regras diferentes** do CRD. É o que liga o FAQ às regras oficiais.
- **34 tipos de componente MDX** pra limpar (regras, cartas, termos, palavras-chave, custos, caixas de exemplo…).
- **7 avisos "Rules citation needed"**: respostas que o CRD ainda não sustenta por completo.

Detalhes e gráficos em [`notebooks/01_explorar_faq.ipynb`](notebooks/01_explorar_faq.ipynb).

## Como o FAQ vira trechos (etapa 2)

[`juiz/limpar_faq.py`](juiz/limpar_faq.py) gera **166 trechos**, um por pergunta (`##`). As subseções `###` entram no trecho da pergunta de cima, porque quase todas são continuação da resposta ("Steps", "Cost Sequence"…).

Os componentes MDX viram texto simples, e o que eles informam vira metadado:

| No MDX | No trecho | Metadado |
|---|---|---|
| `<Rule number="355.9.a" />` | `[CRD 355.9.a]`, só no texto do LLM | `regras` |
| `<Card name="Hextech Ray" />` | `Hextech Ray` | `cartas_mencionadas` |
| `<Term item="resolution">resolves</Term>` | `resolves` | — |
| `<Shield />`, `<QuickDraw />` | `[Shield]`, `[Quick-Draw]` | `palavras_chave` |
| `<Energy value={1} /><Fury />` | `[1][Fury]` (mesma notação do texto das cartas) | — |
| `<Steps><Step>…` | lista numerada `1. …` | — |
| `<Callout title="Example">…` | `Example: …` | `avisos`, `citacao_pendente` |

**Por que cada trecho tem dois textos?** O que é bom pra busca nem sempre é bom pra resposta:
- `texto` não tem números de regra e vai pros **embeddings**, porque números não ajudam a achar o significado da pergunta.
- `texto_com_regras` tem `[CRD 355.9.a]` no fim de cada frase e vai pro **LLM**, pra ele poder citar a regra exata.

Exemplo de trecho (`faq_trechos.jsonl`, resumido):

```json
{
  "id": "faq/general-rules/showdowns#showdown-close",
  "categoria": "general-rules", "pagina": "Showdowns", "carta": null,
  "pergunta": "When does a showdown close?",
  "url": "https://www.riftboundfaq.com/general-rules/showdowns#showdown-close",
  "texto_com_regras": "# Showdowns\n## When does a showdown close?\n\nA showdown closes only after every player passes focus in sequence without playing a spell or activating an ability. [CRD 347.2.a, 348]\n...",
  "regras": ["347.2.a", "348", "323.5", "346", "347.1"],
  "cartas_mencionadas": ["Stalwart Poro", "Ravenbloom Student", "Hextech Ray"],
  "palavras_chave": ["Shield"],
  "citacao_pendente": false,
  "crd_revisado": "1.4"
}
```

## Perguntas-gabarito (etapa 2b)

Pra saber se o juiz acerta, precisamos de perguntas com **resposta conhecida**.
[`avaliacao/gabarito.yaml`](avaliacao/gabarito.yaml) tem **28 perguntas em português**, cada uma com a resposta esperada, os trechos do FAQ onde ela está e as regras do CRD que a sustentam.

| Categoria | Quantas | Pra testar |
|---|---|---|
| Carta | 11 | dúvidas sobre uma carta específica |
| Regra geral | 6 | regras que valem pra qualquer carta (custos, chain, movimento…) |
| Mecânica | 4 | palavras-chave como Deathknell, Flow, Ambush |
| Só CRD | 3 | assuntos que o FAQ não cobre (tamanho do deck, pontos pra vencer, mulligan) |
| Fora do escopo | 4 | meta, preço, carta inventada e outro jogo: o bot deve dizer **"não encontrei"** |

As perguntas variam o **jeito de perguntar**: 11 formais, 10 informais ("se counterarem minha carta, recebo a mana de volta?") e 7 com **termos do jogo em português** ("atordoar", "Emboscada", "fase de compra"). Assim dá pra ver se a busca multilíngue entende o que o jogador quis dizer.

Na etapa 4, o gabarito vai medir **quantas vezes o trecho certo aparece entre os primeiros resultados da busca** (hit@k) pra cada modelo de embeddings.
Na etapa 7 ele cresceu pra **45 perguntas** (veja a seção da etapa 7).
Os testes em `tests/test_gabarito.py` conferem se todo trecho e regra citados existem de verdade, então se o FAQ mudar, o teste avisa.

## Como o CRD vira regras e trechos (etapa 3)

**De onde vem o texto:** o repositório do FAQ não guarda o CRD em formato estruturado (ele é gerado na hora de montar o site). O site, porém, publica o **CRD inteiro em HTML, com uma âncora por regra** (`#R355.9.a`) e as sub-regras aninhadas. Usamos essa página em vez de extrair texto do PDF, que dá muito mais trabalho e é fácil de errar. O **PDF oficial continua sendo a autoridade**: o próprio site avisa que o parsing pode ter erros, então o app sempre mostra o link dele.

**O que sai:**
- `crd_regras.jsonl`: **2.381 registros** (2.332 regras + 49 títulos de seção), um por número. Serve pra **consulta direta** ("qual o texto da 355.9.a?"), por exemplo quando um trecho do FAQ cita uma regra.
- `crd_trechos.jsonl`: **330 trechos** (mediana de 185 palavras), que vão pra **busca**.

**Como os trechos são montados:** o CRD é uma árvore (`355` → `355.9` → `355.9.a` → `355.9.a.1`), e a divisão segue os galhos:
- um galho que cabe em 250 palavras vira um trecho inteiro;
- um galho grande é dividido nos galhos filhos, e a regra "mãe" vai **resumida como contexto** em cada pedaço, porque muitas vezes a filha continua a frase dela ("...meets all of the following requirements:");
- regras pequenas vizinhas são agrupadas, pra não gerar trechos minúsculos;
- cada regra aparece em **exatamente um** trecho, e os testes garantem isso.

**Ponte FAQ ↔ CRD:** as **408 regras citadas pelo FAQ existem no CRD** processado, e as regras esperadas no gabarito também. É isso que vai permitir, na etapa 5, puxar o texto oficial de cada regra que um trecho do FAQ cita.

## Escolhendo o modelo de busca (etapa 4)

Os 496 trechos (166 do FAQ + 330 do CRD) foram transformados em vetores por cada candidato. Depois, cada pergunta do gabarito passou por uma busca, conferindo **em que posição aparece a fonte certa**. Os vetores ficam numa matriz **NumPy**, e a busca é um produto escalar. Com 500 trechos isso leva milissegundos, então não precisa de banco vetorial.

| Modelo | Fonte certa em 1º (hit@1) | Entre os 5 primeiros (hit@5) | Separa perguntas sem resposta? |
|---|---|---|---|
| **Gemini Embedding 2** ✅ escolhido | **100%** | **100%** | sim: notas ≤ 0,675 (sem resposta) × ≥ 0,718 (com resposta) |
| multilingual-e5-small | 88% | 100% | não |
| multilingual-e5-base | 79% | 92% | não |
| BM25 (palavra-chave) | 42% | 58% | — |
| Qwen3-Embedding-0.6B | descartado: levou mais de 20 min pra indexar no processador e usou 3,3 GB de RAM, mais que os 2,7 GB do Streamlit Cloud | | |

**O que os números mostram:**
- **Embeddings multilíngues são indispensáveis:** a busca por palavra-chave falha sempre que a pergunta em português não traz um termo em inglês.
- **A nota do Gemini serve de "termômetro":** um corte perto de **0,70** separou todas as perguntas sem resposta. É um **candidato** pra resposta "não encontrei", que ainda precisa ser confirmado com mais perguntas na etapa 7.
- **Amostra pequena:** são 24 perguntas com resposta, então diferenças de 1 ou 2 perguntas podem ser acaso.

Análise completa, com gráficos: [`notebooks/02_comparar_busca.ipynb`](notebooks/02_comparar_busca.ipynb).
O **e5-small** virou a **busca reserva**: entra automaticamente quando o Gemini falha. Os detalhes estão na seção da etapa 6.

## Como o juiz responde (etapa 5)

```
pergunta ─► glossário (termos PT → EN) ─► busca (Gemini Embedding 2, 5 trechos)
                                               │    └─ falhou (cota/sobrecarga/sem internet)? ─► reserva local (e5-small)
          nota do 1º resultado abaixo do corte da busca usada, e nenhuma carta citada? ──► "Não encontrei" (sem chamar o LLM)
                                               │
          contexto: trechos [F1..F5] + texto das cartas (com errata) + texto oficial das regras citadas pelo FAQ
                                               │
          LLM (Gemini 3.8 Flash → reservas 3.5 Flash / 3.5 Flash-Lite) ─► resposta em PT com [F1] e (CRD 355.9.a)
```

**Decisões, com o motivo:**
- **LLM: Gemini 3.8 Flash.** Tem tier grátis e usa a mesma chave dos embeddings. No tier grátis, os modelos mais novos às vezes ficam **sobrecarregados** (erro 503). Por isso o juiz tem **modelos de reserva** (3.5 Flash e 3.5 Flash-Lite), e um modelo que falhou fica 5 minutos de fora. Com isso, as respostas caíram de 15 a 30 s pra **cerca de 1,5 s** durante uma sobrecarga.
- **O glossário não entra na busca, só na resposta.** Medido com o gabarito, acrescentar os termos em inglês à pergunta **piorou** a busca do Gemini (hit@1 de 100% pra 92%). Os termos colados no fim, como "(Kill, Unit)", distorcem o sentido da pergunta. Na resposta, o glossário serve pra o LLM usar o termo oficial ("atordoar" → Stun).
- **Texto das cartas com errata.** Quando a pergunta cita uma carta, pelo nome completo ou pelo nome do campeão, o texto oficial dela entra no contexto. 9 das 63 erratas ainda não estavam aplicadas no catálogo, e o juiz aplica. Nomes curtos ou comuns, como "Vi" e "Buff", só contam com inicial maiúscula, pra "eu vi" não virar carta.
- **Regras citadas pelo FAQ entram com o texto oficial.** Assim o LLM vê a explicação do FAQ e a regra do CRD lado a lado, e sabe qual vale mais.
- **Instruções com "falsos amigos".** Numa resposta de teste, o LLM disse que Recall "volta pra mão", como no Legends of Runeterra. Em Riftbound, **Recall leva pra base** (CRD 455). As instruções agora trazem a definição oficial dos termos que mudam de sentido entre jogos.
- **Citações no formato `[F1]`.** O texto das cartas usa `[1]` pra custo de energia, e isso não pode ser confundido com a fonte 1.

**Amostra:** [`avaliacao/resultados/respostas_amostra_etapa5.md`](avaliacao/resultados/respostas_amostra_etapa5.md) tem 11 perguntas.
- As 8 com resposta foram respondidas certo e com fonte.
- As 3 fora do escopo (meta, carta inventada, outro jogo) receberam "Não encontrei" em menos de 1 segundo, sem chamar o LLM.
- A avaliação completa, com métricas, é a etapa 7.

## A interface (etapa 6)

`streamlit run app.py` abre um chat no navegador, que também funciona no celular:
- **Resposta com links:** as citações `[F1]` abrem a página do FAQ na pergunta certa, e `(CRD 355.9.a)` abre a regra exata no Core Rules.
- **Fontes:** num painel que abre e fecha, primeiro as citadas e depois as só consultadas, com títulos curtos ("Smite — Can Guardian Angel... save a unit from Smite?").
- **Aviso de cautela** quando uma fonte tem "citação pendente" (o FAQ avisa que o CRD ainda não confirma tudo).
- **👍/👎 em cada resposta.** A pergunta, a resposta e a avaliação ficam em `data/logs/conversas.jsonl`, só na sua máquina e fora do git. As perguntas reais vão alimentar o gabarito da etapa 7.
- **Barra lateral:**
  - versões das fontes (data do FAQ e versão do CRD);
  - "Como funciona", em 3 passos;
  - créditos e licença do FAQ (CC BY-SA 4.0);
  - aviso de que o projeto não é oficial da Riot;
  - opção pra mostrar os detalhes da busca (similaridade, modelo, tokens e termos do glossário).

**Ajustes feitos depois de ver o app funcionando:**
- **Fontes demais:** eram 10 por resposta, e agora são 3 a 5. Só entram as cartas citadas na pergunta e as das páginas do FAQ com nota perto da melhor, e trechos abaixo do corte de 0,70 saem do contexto.
- **Citação misturada:** `[F1, CRD 372]` (fonte e regra no mesmo colchete) passou a ser entendida.
- **Exemplos:** as perguntas de exemplo somem depois da primeira pergunta.

Os testes da interface usam o **AppTest** do Streamlit. Ele roda o app sem navegador, com um juiz "de mentira", e confere o que aparece na tela.

### Ajustes depois do primeiro uso real

As primeiras perguntas feitas no app mostraram três problemas que o gabarito não pegava:

1. **"Não encontrei" em perguntas de definição.** "O que é open state?" e "o que é priority?" receberam "não encontrei", **mesmo com a regra certa em 1º lugar na busca**. Perguntas curtas desse tipo têm nota de 0,66 a 0,70, abaixo do corte de 0,70 que tinha vindo do gabarito, e o gabarito não tinha nenhuma pergunta assim. Como essas notas se misturam com as de perguntas fora do escopo, nenhum corte separa os dois grupos. O corte caiu pra **0,60**, e agora só barra o que é claramente sem relação; na faixa cinzenta, quem decide é o LLM.
2. **Respostas técnicas demais pra quem está aprendendo.** "Me explique as chains" começava com "Depende." e despejava regras. Agora, perguntas de explicação ("o que é", "explique", "não entendi") recebem uma definição simples e um exemplo de jogo. Também entrou uma fonte nova, o **glossário para iniciantes do FAQ**, com 7 termos (Chain, Pending, Finalization, Resolution, Priority, Cleanup e Focus). Na busca, ele aparece em 1º lugar pra "o que é priority?" e "me explique as chains".
3. **Cota diária do tier grátis.** O Gemini Embedding 2 aceita **1.000 textos por dia**, e cada trecho indexado conta como um. Recriar o índice inteiro gastava metade da cota do dia. Duas mudanças:
   - **Indexação incremental:** só os trechos novos ou alterados vão pra API. Acrescentar o glossário custou 7 textos, e não 503.
   - **Aviso claro:** quando a cota acaba, o app avisa que ela só volta no dia seguinte, em vez de ficar tentando.
   - **Busca reserva local:** quando o Gemini falha (cota do dia, sobrecarga ou sem internet), a busca passa pro **multilingual-e5-small**, que roda no computador. Ele achou a fonte certa entre os 5 primeiros em 100% do gabarito da etapa 4.
     - **Corte próprio:** cada modelo tem sua escala de nota, então o corte do "não encontrei" é 0,60 no Gemini e 0,78 no e5-small.
     - **Os dois índices andam juntos:** `python -m juiz.indice` atualiza os dois de uma vez.
     - **Aviso na tela:** quando a resposta usa a reserva, o app mostra uma linha discreta dizendo isso.
     - **Primeiro teste real:** foi com a cota do Gemini esgotada. As 4 perguntas do uso real foram respondidas pela reserva, com a primeira levando ~20 s (carrega o modelo) e as seguintes ~1,5 s.
     - **Custo pra etapa 8:** o app publicado vai precisar do PyTorch pra rodar a reserva.

### Conversa com memória e respostas mais didáticas

O uso real mostrou dois problemas: as respostas eram superficiais e difíceis de entender, e o juiz não lembrava da pergunta anterior. As mudanças:

- **Memória da conversa.** O juiz recebe as últimas 3 trocas, então dá pra perguntar "e se for durante um showdown?". Na busca, uma pergunta de continuação também é procurada junto com a pergunta anterior, porque sozinha ela não diz do que se trata. "Nova conversa" zera tudo. No terminal, `python -m juiz.perguntar --chat` abre o mesmo modo.
- **Dois tipos de resposta.** O juiz reconhece pedidos de explicação ("o que é", "como funciona", "explique", "não entendi"):
  - **Explicação:** estrutura fixa com **Em resumo**, **Passo a passo**, **Exemplo** e **Termos que apareceram**, até ~350 palavras, usando 8 trechos em vez de 5.
  - **Pergunta direta:** "Sim/Não/Depende", o porquê em linguagem simples e um exemplo, se ajudar.
- **Definições oficiais dos termos técnicos.** Pedir que o LLM explicasse os termos teve um efeito colateral: ele passou a **inventar** definições (definiu Open State como "quando os jogadores têm prioridade", mas a regra 309.2 diz "quando não existe Chain"). Agora, quando um termo técnico aparece, o juiz manda junto a **definição oficial**: o texto do Core Rules e do glossário do FAQ, listado em [`juiz/definicoes.yaml`](juiz/definicoes.yaml). A instrução proíbe inventar outras e pede os nomes oficiais: "unidade", nunca "lacaio".
- **Citações discretas.** `[F1][F2][F3]` no meio do texto virou um número pequeno sobrescrito com link, como nota de rodapé. Antes, o texto do LLM passa por *escape* de HTML, pra ele não conseguir injetar código na página.

**Limite do tier grátis que afeta a qualidade:** o Gemini 3.8 Flash e o 3.5 Flash aceitam só **20 respostas por dia cada** no tier grátis. Depois disso, quem responde é o 3.5 Flash-Lite, que é mais fraco.

## Avaliando as respostas (etapa 7)

A etapa 4 mediu só a busca. Aqui medimos a **resposta final**, que é o que o usuário lê.

**O gabarito cresceu de 28 pra 45 perguntas:**
- **9 perguntas reais**, tiradas do uso do app, a maioria sobre *timing* ("se eu jogo uma spell e meu oponente passa, eu tenho que passar também?");
- **6 de definição** ("o que é open state?");
- **2 continuações de conversa**, que só fazem sentido com a pergunta anterior;
- **3 novas fora do escopo**, incluindo perguntas sobre outros jogos.

Nas perguntas de sim ou não, o gabarito também guarda a **conclusão esperada**.

**Três jeitos de medir** ([`juiz/avaliar_respostas.py`](juiz/avaliar_respostas.py)):
1. **Métricas automáticas**, objetivas:
   - o juiz respondeu quando devia e disse "não encontrei" quando devia?
   - a 1ª palavra (Sim/Não/Depende) bate com a esperada?
   - citou a fonte certa?
   - citou alguma regra que não existe?
2. **Avaliador LLM:** o Gemini 3.5 Flash-Lite compara cada resposta com a esperada e dá **correta / parcial / incorreta**, numa resposta em JSON com formato fixo (pydantic).
3. **Revisão humana às cegas:** 12 respostas lidas por uma pessoa, sem ver a nota do avaliador, pra medir **o quanto dá pra confiar nele**.

**Rodada 1, com as duas reservas** (busca e5-small + Gemini 3.5 Flash-Lite, o pior caso do juiz):

| Métrica | Resultado |
|---|---|
| respostas corretas (avaliador) | **89%** (40 de 45) |
| conclusão certa nas perguntas de sim/não | **81%** (17 de 21) |
| citou a fonte certa | **97%** |
| citações inventadas | **0** |
| "não encontrei" por engano | **0** em 38 |
| recusou as perguntas fora do escopo | 6 de 7 |
| tempo por resposta (mediana) | 1,6 s |

**O que a avaliação mostrou:**
- **O erro mais comum é a 1ª palavra.** Às vezes o juiz abre com "Sim" onde o certo é "Não" ou "Depende", mesmo quando a explicação depois está certa.
  - Exemplo: "Posso usar Emboscada pra jogar uma unidade na base?" → "Sim, com o timing normal". O certo é **Não**: o Ambush não vale na base.
  - Pra um iniciante, que muitas vezes lê só o começo, isso é grave.
- **Timing da Chain e da prioridade é o ponto fraco**, tanto na busca quanto na resposta.
- **O avaliador LLM serve como filtro, não como juiz final.** Ele concordou com a revisão humana em 6 de 12 respostas. Nas 6 divergências, o texto das regras deu razão ao avaliador em 3 e ao humano em 2; a última depende do gabarito.
  - Quando o avaliador diz "correta", é confiável: o humano concordou em 6 de 7.
  - Quando aponta problema, vale uma pessoa conferir. Ele cobra detalhes que a pergunta não pediu e deixa passar erros sutis de regra.
- **O corte do "não encontrei" não separa bem no e5-small:** as notas das perguntas fora do escopo se misturam com as das legítimas. O corte de 0,78 ficou como rede de segurança, e quem recusou as perguntas fora do escopo foi o LLM, seguindo as instruções.

### Ajustes a partir do diagnóstico (rodada 2)

1. **Prompt:** Sim/Não/Depende só em pergunta de sim ou não, e a 1ª palavra responde exatamente o que foi perguntado.
   - O exemplo no prompt é genérico, e não uma pergunta do gabarito. Colocar o gabarito no prompt melhoraria o número sem melhorar o juiz.
2. **Definições oficiais do *timing*:**
   - Pass: quem recebe a prioridade e por que a Chain resolve (CRD 337.4 e 339.1);
   - Priority: quando cada jogador recebe a prioridade (CRD 312.2);
   - Finalize: Unit e Gear resolvem na hora (CRD 337.2).
3. **Avaliador:** julga só o que a pergunta pede.
4. **Gabarito da q44** ("deck bom de Jinx"): aceita as regras de construção, desde que o juiz diga antes que estratégia não está nas regras.

| Métrica | Rodada 1 | Rodada 2 |
|---|---|---|
| conclusão certa (sim/não) | 81% | 95%\* |
| citou a fonte certa | 97% | 95% |
| citações inventadas | 0 | 0 |
| "não encontrei" por engano | 0 de 38 | 1 de 38 |
| recusou as fora do escopo | 6 de 7 | 7 de 7 |
| concordância do avaliador com a revisão humana | 50% | 67% |

\* **Uma rodada só engana.** Repetindo 4 vezes as perguntas-problema com o prompt novo:
- a da Emboscada acertou **4 de 4** (corrigida de verdade);
- outras três oscilaram (1 ou 2 de 4), porque o LLM não responde sempre igual.

A melhora real fica entre 81% e 95%. Pra decisões importantes, cada pergunta precisa ser feita várias vezes.

A rodada 2 também revelou um bug na própria métrica: "Não encontrei" contava como a conclusão "não". Ele foi corrigido.

Análise completa, com gráficos, a tabela de divergências e o antes × depois: [`notebooks/03_avaliar_respostas.ipynb`](notebooks/03_avaliar_respostas.ipynb).
**O que ficou de fora:** a comparação com o modelo principal (Gemini 3.8 Flash) e a busca Gemini no gabarito de 45 perguntas. O tier grátis do 3.8 Flash dá só 20 respostas por dia, e a cota e a sobrecarga não deixaram rodar. A avaliação foi encerrada com o Flash-Lite, o pior caso do juiz. A etapa 8 ainda comparou o Flash-Lite com os modelos do Groq (veja abaixo).

## Atualização e publicação (etapa 8)

### Atualização automática

`python -m juiz.atualizar` faz o caminho inteiro e só trabalha onde algo mudou:
1. atualiza o FAQ com git e compara o commit;
2. refaz os trechos se o FAQ mudou;
3. baixa o CRD na versão que o FAQ marca como atual, e só reprocessa se o conteúdo mudou;
4. atualiza os dois índices de busca, mandando pro modelo só os trechos novos ou alterados.

O app chama a mesma função quando sobe e depois uma vez por dia. Se a internet falhar, ele segue com os dados que já tem.

### Vetores publicados sem o texto

A pasta `data/` não vai pro GitHub: o texto do Core Rules e das cartas é material da Riot. Por isso, o app publicado **monta os dados sozinho a partir das fontes** ao subir, e isso leva ~25 s.

O problema era a busca: refazer os vetores do Gemini a cada vez que o app sobe gastaria metade da cota diária de embeddings (503 dos 1.000 textos).
- A solução é `data/vetores/`. Ela guarda os vetores com o id e uma "assinatura" (hash) de cada trecho, **sem o texto**, e vai pro GitHub.
- Ao subir, o app reaproveita todo vetor cuja assinatura bate e só manda pro modelo os trechos novos.
- Numa simulação do zero (sem `data/`, sem `.env`), o app baixou tudo e reaproveitou os 503 vetores, com **0 textos enviados à API**.

Depois de rodar `juiz.atualizar` com fontes novas, faça commit de `data/vetores/` pro app publicado aproveitar.

### Quando o Gemini está sobrecarregado: Groq e plano B

Publicado, o app falhava com frequência: no plano grátis, o Google recusa pedidos em horário de pico (erro 503, "high demand"). Num teste, o 3.8 Flash, o 3.7 Flash, o 3.5 Flash-Lite e o 3.1 Flash-Lite deram 503 ao mesmo tempo, e só o 3.5 Flash respondeu, depois de 27 s.

**Por que não um LLM rodando no próprio servidor:** o servidor grátis tem 2 processadores, sem placa de vídeo. Um modelo que cabe na memória levaria de 1 a 2 minutos por resposta e erraria mais que o Gemini. Servidores grátis com mais memória também não têm placa de vídeo, então o problema de velocidade continua.

**Duas camadas de proteção:**
1. **Groq como reserva de outra empresa.** Quando os três Gemini falham, a resposta vem de um modelo aberto no Groq (`config.MODELO_GROQ`), que tem capacidade própria.
   - Plano grátis: ~1 pergunta por minuto e ~40 por dia. Como reserva, basta.
   - Só entra se `GROQ_API_KEY` estiver no `.env` ou nos secrets.
   - **Qual modelo:** os dois modelos grátis do Groq foram comparados com o Flash-Lite nas 18 perguntas de `config.IDS_COMPARACAO`, com a mesma busca (e5-small):

     | | Gemini 3.5 Flash-Lite | **Groq gpt-oss-120b** ✅ | Groq qwen3.8-27b |
     |---|---|---|---|
     | conclusão (Sim/Não/Depende) certa | 91% (10/11) | **91% (10/11)** | 64% (7/11) |
     | citou a fonte certa | 93% | 87% | 73% |
     | citações inventadas | 0 | 0 | 0 |
     | respostas vazias | 0 | 0 | **4 de 17** |
     | tempo (mediana) | 2,8 s | **1,7 s** | 3,4 s |

   - O Qwen tem um limite de 1.000 tokens de **saída** por minuto no plano grátis. O raciocínio escondido gastava esse limite inteiro, e a resposta vinha vazia.
   - Pior: o avaliador (Flash-Lite) deu "correta" pras 4 respostas vazias. Agora a avaliação dá "incorreta" pra resposta vazia sem nem chamar o avaliador, e o app trata resposta vazia como falha e passa pra próxima reserva.

2. **Plano B sem LLM.** Se nenhum LLM responder, o app mostra os 3 trechos das regras que a busca achou, em inglês e com link, e explica o motivo. A busca funciona mesmo sem o Gemini, graças ao e5-small.
   - Essa resposta não conta no limite do convidado.

### Proteção: modo convidado + senha

A chave de API fica nos *secrets* do Streamlit Cloud e roda só no servidor; o visitante nunca a vê. O risco real é outro: alguém gastar a cota **grátis** do dia e o app parar até o dia seguinte. Com o projeto do Google **sem faturamento ativado**, o custo máximo continua zero.

| Quem | O que pode |
|---|---|
| **Convidado** | 10 perguntas por visita e 100 por dia, somando todos os visitantes (`config.LIMITE_POR_VISITA` e `LIMITE_DIARIO`) |
| **Com a senha** | uso sem limite (5 tentativas por visita, comparação em tempo constante) |

O modo convidado só liga quando `SENHA_DO_APP` existe. No seu computador, sem ela, não há limite.

Limitações conhecidas:
- recarregar a página zera o limite da visita; quem protege a cota de verdade é o limite diário;
- o contador diário fica na memória do servidor e zera se o app reiniciar.

**Privacidade:** no plano gratuito, o Google pode usar as perguntas pra melhorar os produtos dele, e pessoas podem revisá-las. O app avisa isso na tela. No app publicado, o registro das conversas em arquivo fica desligado.

### Como publicar no Streamlit Community Cloud (grátis)

1. **Confira que o projeto do Google está sem faturamento:** em [aistudio.google.com](https://aistudio.google.com), a chave deve estar no plano gratuito. Assim, o pior caso é o app parar por cota, sem cobrança.
2. **Suba o código pro GitHub**, incluindo `data/vetores/`, `requirements.txt` e `packages.txt`.
3. Entre em [share.streamlit.io](https://share.streamlit.io) com a conta do GitHub e clique em **Create app**, depois em **Deploy a public app from GitHub**:
   - Repository: `deividgoulart/riftbound-juiz`
   - Branch: `main`
   - Main file path: `app.py`
4. Em **Advanced settings**:
   - Python **3.12**.
   - Em **Secrets**, cole o conteúdo de [`.streamlit/secrets.toml.example`](.streamlit/secrets.toml.example), preenchendo as chaves do Gemini e do Groq, uma senha só sua e, pro deck builder, as duas variáveis do Turso (veja a seção da fase 2).
5. **Deploy.**
   - A 1ª instalação demora uns minutos, por causa do PyTorch.
   - A 1ª pergunta demora ~1 minuto: o app baixa o FAQ, o CRD e o modelo da busca reserva.
   - Se a instalação falhar, veja o log: o `requirements.txt` usa o índice do PyTorch só pra CPU, que é bem menor.

Recursos do plano grátis: até 2,7 GB de memória. O app usa ~1 GB, a maior parte com o PyTorch da busca reserva. Sem visitas por 12 horas, o app "dorme" e acorda no próximo acesso.

## Deck builder (fase 2)

A página **Deck builder** (no menu do app) responde à pergunta "quais decks eu consigo montar com as cartas que tenho?".

### Etapa 1: coleção, importação de decks e conclusão

- **Minha coleção:** uma tabela com as 935 cartas (as 929 do catálogo do FAQ + 6 runas básicas), com busca pelo nome ou pelo campeão, filtros por tipo e domínio e uma coluna de quantidade editável. A tabela só é gravada no botão **Salvar**, e não a cada número digitado. Dá pra importar e exportar em CSV (colunas `carta` e `quantidade`, com vírgula ou ponto e vírgula, como o Excel em português salva).
- **Exportação da Liga Riftbound:** o CSV de coleção que a [Liga Riftbound](https://ligariftbound.com.br) exporta entra direto. O nome vem da coluna `Card (EN)`, e as várias linhas da mesma carta (uma por qualidade, idioma ou foil) somam. Com a opção **substituir a coleção inteira**, a coleção passa a ser exatamente a do arquivo, então uma carta vendida some daqui também. Numa coleção real de 81 linhas, as 70 cartas foram reconhecidas, inclusive "Shen - Kinkou", "Jayce - Defender of Tomorrow" e "Kayle, Justified (Overnumbered)".
- **Importar um deck:** cole a lista exportada por um site de decks. Aceita `3 Carta`, `3x Carta` e `Carta x3`, com ou sem cabeçalhos de seção (`Legend:`, `Main Deck:`, `Runes:`, `Sideboard:`… ou em português). Sem cabeçalho, a seção vem do tipo da carta.
- **Porcentagem de conclusão:** conta cópias. Com 1 de 3 Jinx, Rebel, faltam 2. Cópias a mais não passam de 100%, o sideboard fica de fora por padrão e as runas básicas podem contar como "tenho" (quase todo jogador tem as de um deck inicial). Os decks aparecem do mais fácil pro mais difícil de montar, e cada um mostra a tabela do que falta.

**Decisões, com o motivo:**
- **Por que Streamlit, e não um site "normal":** o disco apagado a cada reinício não é problema só do Streamlit: as hospedagens grátis de sites fazem o mesmo, e o banco na nuvem seria necessário de qualquer jeito. O Streamlit mantém o projeto numa linguagem só (Python, como o juiz) e já está publicado, com senha e secrets. O preço é o visual mais limitado. Pra não ficar preso a ele, **toda a lógica fica em `decks/`, sem Streamlit** (um teste confere isso): trocar a tela por um site no futuro não mexe no banco, na importação nem nas contas.
- **Nomes das cartas:** o catálogo tem só o título das lendas ("Loose Cannon", com a tag Jinx), mas os sites escrevem "Jinx, Loose Cannon" ou "Jinx - Loose Cannon". Os dois viram apelidos da lenda. Caixa, acento, apóstrofo curvo e um código de coleção no fim (`(OGN-202)`) também não atrapalham.
- **Nome não reconhecido não é adivinhado:** o app mostra as cartas parecidas ("quis dizer Jinx, Rebel?") e não salva até a lista ser corrigida (ou até você pedir pra salvar sem elas). Trocar uma carta por outra "parecida" daria uma conta de conclusão errada.
- **Regras de construção só avisam:** o app confere a lista com o Core Rules (CRD 103.2: 1 lenda, deck principal com pelo menos 40 cartas contando o campeão escolhido, até 3 cópias por nome, 12 runas), mas salva mesmo assim, porque um deck em construção pode estar incompleto de propósito.
- **Cada deck guarda a origem** (link, data, torneio e colocação). Na importação manual, só o nome e o link são usados; os outros campos já estão prontos pros decks do meta da próxima etapa.

### Onde a coleção fica: Turso (SQLite na nuvem)

As tabelas (`cartas`, `colecao`, `decks`, `deck_cartas`) são SQLite. Com `TURSO_DATABASE_URL` e `TURSO_AUTH_TOKEN` no `.env` ou nos secrets, elas ficam no [Turso](https://turso.tech), um SQLite na nuvem com plano grátis. Sem as duas variáveis, ficam em `data/decks.sqlite`, no seu computador (fora do git).

- **Por que um banco na nuvem:** o disco do Streamlit Cloud é apagado a cada reinício do app, e a coleção sumiria junto.
- **Por que falar com o Turso pela API HTTP**, e não pelo pacote oficial: o pacote é nativo (Rust) e já teve problema de instalação no Windows. A API é um POST com JSON, e o `httpx` já era dependência do projeto. Cada gravação (ex.: salvar a coleção) vai numa **transação**: ou tudo vale, ou nada.
- **Economia de cota:** o catálogo só é regravado no banco quando muda (o app guarda uma assinatura dele), e a tela de decks faz uma consulta só pra todos os decks.
- **Quem pode editar:** no app publicado, o visitante só vê a coleção e os decks; salvar, importar e apagar pedem a mesma senha do juiz. Se o Turso não estiver configurado no app publicado, a página avisa que o que for salvo vai sumir.

**Como configurar no app publicado:**
1. Crie uma conta grátis em [turso.tech](https://turso.tech) e um banco (`turso db create riftbound-decks`).
2. Pegue a URL (`turso db show riftbound-decks --url`) e crie um token (`turso db tokens create riftbound-decks`).
3. Cole os dois nos secrets do Streamlit Cloud como `TURSO_DATABASE_URL` e `TURSO_AUTH_TOKEN`. Pra usar o mesmo banco no seu computador, cole também no `.env`.

**Testes:** o banco local roda em memória, e o Turso é testado com um servidor falso que confere o JSON enviado e a leitura da resposta. A conexão com um banco Turso de verdade ainda precisa ser conferida depois de criar o banco (passos acima).

### Etapa 2: decks do meta

A aba **Decks do meta** mostra os decks que ficaram entre os 8 primeiros em torneios de Riftbound dos últimos 30 dias, do mais fácil pro mais difícil de montar com a sua coleção, com filtro por lenda e link pro torneio.

- **Fonte: a API oficial do TopDeck.gg**, que é grátis (com uma chave gratuita) e traz os torneios com as listas dos jogadores. O riftools.app, a primeira ideia, não tem API, e não deu pra conferir os termos de uso dele; ler o HTML de um site pode quebrar a qualquer mudança.
- **Atualização:** o app coleta sozinho quando a última coleta tem mais de 7 dias; quem tem a senha também pode clicar em **Atualizar agora**. Pelo terminal: `python -m decks.meta --forcar`. Cada coleta **substitui** os decks do meta anteriores, numa transação só; os decks que você importou não mudam. Uma coleta vazia não apaga nada.
- **Filtros:** só torneios com pelo menos 8 jogadores e só o top 8 de cada um (`config.META_MIN_JOGADORES` e `META_TOP_POR_TORNEIO`). A página mostra os 20 decks mais fáceis de montar.
- **Cartas pelo código:** a API manda o código de cada carta (ex.: OGN-042), e o app acha a carta por ele; o nome fica de reserva (veja abaixo). Um deck com carta não reconhecida fica de fora, em vez de entrar com a conta errada, e o nome aparece no relatório da coleta.
- **Privacidade:** o nome dos jogadores não é guardado; só o torneio, a data, a colocação e o link.
- **Como ligar:** crie uma chave grátis na sua conta do [TopDeck.gg](https://topdeck.gg) e ponha em `TOPDECK_API_KEY`, no `.env` e nos secrets do app publicado.

### Código da carta × nome

Nas importações, o **código** (OGN-042, VEN-R04) é a forma mais segura de saber qual é a carta: não depende de como o nome foi escrito ("Jinx - Loose Cannon", "Kayle, Justified (Overnumbered)"). A API do TopDeck.gg manda o código, e o CSV da Liga também (colunas `Edicao (Sigla)` e `Card #`). Então o app tenta o código primeiro e o nome depois.

A **coleção e os decks continuam guardados pelo nome**: um deck pede "Jinx, Rebel", e qualquer impressão serve. A normal, a foil, a de arte alternativa (OGN-202a) e a overnumbered têm códigos diferentes e o mesmo nome.

- **De onde vêm os códigos:** o catálogo do FAQ não tem. Eles vêm da [galeria de cartas oficial da Riot](https://riftbound.leagueoflegends.com/en-us/card-gallery/), baixada uma vez por semana pra `data/raw/galeria_cartas.json` ([`decks/codigos.py`](decks/codigos.py)). Nos campeões, a galeria dá só "Jinx" como nome; o nome completo vem do texto de acessibilidade da imagem ("Riftbound Unit: Jinx, Rebel. ...").
- **Conferido com dados reais:** as 1.189 impressões da galeria ganharam código, e as 81 linhas do CSV da Liga deram a mesma carta pelo código e pelo nome.
- **Se a galeria falhar** (fora do ar ou mudou de formato), tudo continua funcionando pelo nome, como antes.

**Limite conhecido:** a galeria da Riot, a documentação e a API do TopDeck.gg não abriam no ambiente onde o código foi escrito. O formato das respostas foi conferido no código de um projeto aberto que usa a API em produção, e os testes usam um servidor falso nesse formato. A primeira coleta real mostra no relatório quantos decks entraram e quais cartas não foram reconhecidas.

### Etapa 3: comprar o que falta e o juiz falando dos meus decks

**Comprar o que falta (Liga Riftbound).** Em cada deck, a tabela do que falta ganhou:
- **link pra carta na Liga**: com o código da carta, o link vai direto na impressão certa (`Jinx - Loose Cannon (251)`, coleção OGN), no mesmo formato da Liga; sem o código, vai pelo nome;
- **lista de compra** no formato "3 Nome", pra copiar (ou baixar em .txt) e colar na [Compra por Lista da Liga](https://www.ligariftbound.com.br/?view=cards/lista), que monta o carrinho mais barato entre as lojas. É o "carrinho geral" que o plano pedia;
- **menor preço e custo estimado pra completar**, com o botão **Buscar preços na Liga** (só com a senha).

**De onde vem o preço.** A página de cada carta na Liga mostra o "Preço Médio de Venda no Marketplace": menor, médio e maior preço, separados em Normal e Foil, em texto. É isso que o app lê ([`decks/precos.py`](decks/precos.py)). O formato foi conferido numa página real salva em 25/09/2026, e o teste usa esse trecho (`tests/dados/liga_precos.html`).
- Os preços de cada loja aparecem como **imagens embaralhadas**, ou seja, a Liga não quer que sejam lidos por robôs. Eles ficam de fora.
- Pra não sobrecarregar o site: só as cartas que faltam, só quando alguém clica, **um pedido por segundo**, e o preço fica guardado por uma semana. Se a Liga recusar os pedidos (403 ou 429), a busca para na hora.
- O custo usa o menor preço entre normal e foil, porque a foil também serve pro deck.
- A MYP Cards ficou de fora: o formato da busca dela não foi encontrado.

**O juiz falando dos meus decks.** No chat, a barra lateral tem **Deck em foco**, com os decks do deck builder (os seus primeiro, depois os do meta). Com um deck escolhido, o juiz recebe a lista e o texto oficial de cada carta como mais uma fonte, então dá pra perguntar "quais cartas do meu deck dão Stun?" ou "o que acontece se eu jogar a Jinx, Rebel com o Super Mega Death Rocket!?". Com deck em foco, o atalho do "não encontrei" (busca fraca) não vale, porque a resposta pode estar nas cartas do deck.

**Limite conhecido:** a Liga é bloqueada no ambiente onde o código foi escrito. O leitor de preço foi testado com a página real salva, mas a busca de verdade só roda no seu computador ou no app publicado.

### Próximos passos

O plano da fase 2, com o que já foi feito:

1. ✅ **Cadastro da minha coleção** de cartas, usando o `card-catalog.json` do repositório do FAQ como tabela mestre.
2. ✅ **Decks do meta já prontos no app**, coletados automaticamente uma vez por semana pela API do TopDeck.gg, com origem (link), data, torneio e colocação.
3. ✅ **Importação manual** de um deck específico, colando a lista no formato de texto que os sites exportam.
4. ✅ Para cada deck, **porcentagem de conclusão e cartas que faltam** (deck menos coleção), com banco **SQLite** (Turso na nuvem).
5. **Sugestão de decks**: comparar a coleção com os decks do meta e ordenar do mais fácil pro mais difícil de montar. A ordenação por porcentagem e cartas faltando já existe; falta incluir o custo pra completar, quando tiver preço.
6. ✅ Para cada carta que falta, **link direto** na [Liga Riftbound](https://ligariftbound.com.br) e a lista pra **Compra por Lista** (o carrinho geral). A [MYP Cards](https://mypcards.com/riftbound) ficou de fora (formato da busca desconhecido).
7. ✅ **Preço das cartas que faltam**, pelo resumo do marketplace da Liga.
8. ✅ **Aba nova no Streamlit** pro deck builder, e o juiz responde dúvidas sobre as cartas dos meus decks (Deck em foco).

## Créditos e licenças

- **Código deste projeto:** [MIT](LICENSE).
- **Conteúdo do Riftbound FAQ:** © Christian "Near" Ivicevic, sob [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). O app mostra crédito e link pra fonte original em cada resposta que usa esse conteúdo. Os trechos do FAQ que aparecem no notebook e no app continuam sob CC BY-SA 4.0.
- **Core Rules Document:** © Riot Games. O texto é lido da versão HTML publicada pelo Riftbound FAQ, gerada a partir do PDF oficial. Em caso de divergência, o PDF oficial vale.

### Aviso legal

Riftbound e todo o conteúdo relacionado são propriedade intelectual da Riot Games, Inc.
Este projeto é não oficial e não é afiliado nem endossado pela Riot Games. Foi criado sob a política ["Legal Jibber Jabber"](https://www.riotgames.com/en/legal) da Riot Games.

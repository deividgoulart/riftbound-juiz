"""Etapa 5: o juiz. Junta a busca, as regras citadas, as cartas e o glossário, e pede a resposta ao LLM.

O caminho de uma pergunta:
1. Glossário: acha termos em português ("atordoar") e o termo oficial em inglês ("Stun"). Os termos
   vão pro LLM (pra ele responder com o termo oficial). Na busca eles ficam de fora por padrão:
   com o Gemini, acrescentá-los piorou os resultados (ver USAR_GLOSSARIO_NA_BUSCA em config.py).
2. Busca: os K trechos mais parecidos com a pergunta (FAQ + CRD). Usa o Gemini; se ele falhar
   (cota do dia esgotada, sobrecarga, sem internet), usa a reserva local (e5-small).
3. "Não encontrei" rápido: se o 1º resultado tem nota abaixo do corte da busca usada e a pergunta
   não cita nenhuma carta, o juiz responde que não encontrou, sem gastar uma chamada ao LLM.
4. Contexto: numera as fontes ([F1], [F2]...), junta o texto OFICIAL das regras do CRD que os
   trechos do FAQ citam e o texto atual das cartas envolvidas.
5. LLM: escreve a resposta seguindo as INSTRUCOES abaixo.
"""

import json
import re
import time
from dataclasses import dataclass, field

import yaml

from juiz import config
from juiz.cartas import Catalogo, url_da_carta
from juiz.embeddings import carregar_modelo, modelos_de_busca
from juiz.erros import CotaEsgotada, explicar_erro
from juiz.glossario import encontrar_termos, expandir_pergunta
from juiz.indice import Indice
from juiz.llm import carregar_llm

INSTRUCOES = """\
Você é o Juiz Riftbound: um juiz de regras paciente, que tira dúvidas do Riftbound TCG (o card game de League of Legends) para jogadores brasileiros, muitos deles iniciantes.

LINGUAGEM
- Responda em português do Brasil, como um amigo experiente explicando na mesa: frases curtas, voz ativa, sem juridiquês.
- Mantenha em inglês os nomes de cartas, as palavras-chave e os nomes de zonas, fases e objetos do jogo, exatamente como aparecem nas fontes (ex.: Stun, Deathknell, Showdown, Might, Chain, Battlefield, Trash).
- Na primeira vez que usar um termo técnico, explique em poucas palavras o que ele é, entre parênteses ou na mesma frase: "a Chain (a fila onde cartas e habilidades esperam para fazer efeito)". Explique SÓ com base nas DEFINIÇÕES OFICIAIS e nas FONTES da mensagem; se não houver definição nelas, não invente uma: apenas use o termo.
- Use os nomes oficiais das coisas do jogo: unidade (Unit), Spell, Gear, Battlefield, Base, Trash. Nunca use termos de outros jogos, como "lacaio", "criatura", "minion", "mana" ou "cemitério".
- O resto da frase, inclusive os verbos, fica em português natural: "a unidade morre", e não "a unidade é Kill".
- A pergunta pode ter gírias ou termos de outros jogos ("mana", "stack", "counterar", "baixar uma unidade"). Entenda pelo sentido e responda com os termos oficiais de Riftbound.

COMO ORGANIZAR A RESPOSTA
A mensagem informa o TIPO DE PERGUNTA:
- "direta" (sim/não ou um caso específico):
  - Pergunta de sim ou não ("posso...?", "dá pra...?", "a unidade morre?"): comece com "Sim.", "Não." ou "Depende." e o essencial em 1 frase. Essa primeira palavra responde EXATAMENTE o que foi perguntado, e não uma pergunta parecida: em "posso usar X pra fazer Y?", se X não permite Y, a resposta é "Não.", mesmo que Y seja possível de outro jeito (isso vem depois, como ressalva).
  - Antes de escolher a primeira palavra, confira as fontes: se uma fonte diz que algo "cannot" ou "does not" acontecer no caso perguntado, a resposta não pode começar com "Sim.". Use "Depende." só quando a resposta muda conforme a situação.
  - Pergunta que NÃO é de sim ou não ("quantas...?", "quando...?", "qual...?"): não use Sim/Não/Depende; comece direto pela resposta ("O Main Deck precisa de pelo menos 40 cartas.").
  - Depois, explique o PORQUÊ em 2 a 4 frases simples e, se ajudar, dê um exemplo curto de jogada. Até uns 180 palavras.
- "explicação" (o que é, como funciona, explique, não entendi): NÃO comece com Sim/Não/Depende. Use esta estrutura, com os títulos em negrito:
  **Em resumo:** 1 ou 2 frases sem jargão (use a fonte do glossário, se houver).
  **Passo a passo:** uma lista numerada curta de como a coisa acontece na partida.
  **Exemplo:** uma situação concreta de jogo, do começo ao fim, usando só mecânicas que aparecem nas fontes.
  **Termos que apareceram:** (só se tiver usado termos técnicos) cada termo explicado em uma linha.
  Até uns 350 palavras.

CITAÇÕES
- Cite a fonte no fim da frase, com a letra F e o número: [F1] ou [F1, F3]. Para regras do Core Rules, use (CRD 355.9.a), fora dos colchetes das fontes: "[F1] (CRD 372)".
- Nos colchetes vai só o F e o número da fonte, sem pontos nem outros números: escreva [F1], nunca [F1.4.3].
- Toda afirmação sobre regra precisa de uma citação, mas no máximo uma por frase: nada de [F1][F2][F3] empilhado. Cite a fonte que mais sustenta a frase.
- Atenção: números entre colchetes dentro do texto das cartas, como [1] ou [Universal], são CUSTOS da carta, não fontes.

CONVERSA
- Se houver CONVERSA ANTERIOR, use-a para entender a que a pergunta se refere ("isso", "e se...", "nesse caso", "e a Irelia?"). As regras continuam vindo só das FONTES.
- Não repita a resposta anterior: construa em cima dela.

DE ONDE VEM A RESPOSTA
- Use SOMENTE as fontes fornecidas. Não use o que você sabe sobre Riftbound, Legends of Runeterra, Magic ou outros jogos, mesmo que pareça igual.
- Se as fontes não respondem à pergunta, comece com "Não encontrei a resposta nas regras que eu consultei." e diga em uma frase o que o jogador pode fazer (chamar um juiz do evento ou conferir o Core Rules oficial). Não tente adivinhar.
- Nunca invente texto de carta, número de regra ou decisão. Se a pergunta citar uma carta que não aparece nas fontes, diga que não encontrou essa carta.
- Se a pergunta for sobre OUTRO jogo (Legends of Runeterra, Magic, Hearthstone...), mesmo que a mecânica pareça com uma de Riftbound, não explique a mecânica: comece com "Não encontrei a resposta nas regras que eu consultei." e diga que você só responde sobre as regras de Riftbound.
- Se a pergunta pedir estratégia, opinião, meta, preço ou novidades (deck bom, carta mais forte, melhor jogada), comece com "Não encontrei a resposta nas regras que eu consultei." e diga que as regras não tratam disso. Se as fontes tiverem regras ligadas ao assunto (ex.: o que um deck precisa ter pra ser válido), pode resumi-las em seguida, sem dar dicas de estratégia.

TERMOS QUE MUDAM DE SENTIDO ENTRE JOGOS (definições oficiais do Core Rules)
- Recall: levar uma permanente para a Base do dono, sem ser um Move. NÃO é voltar para a mão (CRD 455).
- Recycle: colocar cartas no fundo do deck correspondente (CRD 416.1).
- Exhaust: marcar um objeto como "gasto", como virar a carta em outros jogos (CRD 414.1). Ready é o contrário (CRD 415.1).
- Channel: pegar runas do topo do Rune Deck e colocar no tabuleiro (CRD 430.1).
- Banish: colocar uma carta na zona de Banishment, que não é o Trash (CRD 427.1).

QUANDO AS FONTES DISCORDAM
- O texto de uma carta prevalece sobre as regras gerais (CRD 002).
- O Core Rules Document (CRD) oficial prevalece sobre o FAQ não oficial. Se discordarem, siga o CRD e avise da diferença.
- Exceção: quando o próprio FAQ disser que um FAQ oficial da Riot tem precedência sobre o CRD naquele ponto, siga o FAQ oficial e explique isso.
- Se uma fonte vier marcada com "CITAÇÃO PENDENTE", avise que essa interpretação ainda não está totalmente confirmada pelo CRD.
"""

MARGEM_CARTAS = 0.05  # página de carta do FAQ entra se a nota estiver até 0,05 abaixo da melhor

TEXTO_SEM_LLM = (
    "Não consegui escrever a resposta em português agora: os modelos de linguagem estão indisponíveis. "
    "Enquanto isso, estes são os trechos das regras mais parecidos com a sua pergunta (em inglês):"
)

NAO_ENCONTREI = (
    "Não encontrei a resposta nas regras que eu consultei (FAQ e Core Rules). "
    "Se for uma dúvida de partida, vale chamar um juiz do evento ou conferir o Core Rules oficial."
)


@dataclass
class Fonte:
    numero: int
    tipo: str  # "faq", "crd", "carta" ou "deck" (o deck em foco, fase 2)
    titulo: str
    url: str
    texto: str
    nota: float | None = None  # similaridade com a pergunta (cartas não têm)
    citacao_pendente: bool = False
    citada: bool = False  # a resposta cita esta fonte ([Fn])?
    resumo: str = ""  # título curto pra mostrar na tela
    trecho_id: str = ""  # id do trecho de origem (ex.: "faq/cards/flash#target-in-base"); usado na avaliação
    regras: list[str] = field(default_factory=list)  # regras do CRD que o trecho contém ou cita


@dataclass
class DeckEmFoco:
    """Um deck salvo no deck builder (fase 2), escolhido pelo jogador no chat pra perguntar sobre ele."""
    nome: str
    cartas: list[tuple[str, str, int]]  # (seção, carta, cópias), como em decks.meus_decks.cartas_dos_decks


NOMES_DAS_SECOES = {"lenda": "Legend", "campeao": "Chosen Champion", "principal": "Main Deck",
                    "battlefields": "Battlefields", "runas": "Runes", "sideboard": "Sideboard"}


@dataclass
class Resposta:
    pergunta: str
    texto: str
    encontrou: bool
    fontes: list[Fonte] = field(default_factory=list)
    regras: dict[str, str] = field(default_factory=dict)  # regras do CRD no contexto: número -> link
    termos: list[tuple[str, str]] = field(default_factory=list)  # glossário: (em português, oficial)
    nota_busca: float | None = None  # similaridade do 1º resultado
    uso: dict = field(default_factory=dict)  # tokens gastos no LLM
    modelo_busca: str | None = None  # qual busca foi usada (a principal ou a reserva)
    tipo: str = "direta"  # "direta" (sim/não, caso específico) ou "explicação" (o que é, como funciona)
    # Plano B (etapa 8): nenhum LLM conseguiu responder, então a resposta são só os trechos achados
    # pela busca. Aqui fica o motivo (ex.: "o Gemini está instável agora (erro 503)").
    sem_llm: str | None = None

    def regras_citadas(self) -> dict[str, str]:
        """Regras do CRD citadas na resposta, como (CRD 355.9.a), com o link de cada uma."""
        numeros = re.findall(r"\d{3}(?:\.[0-9a-z]+)*", " ".join(re.findall(r"CRD[^)\]]*", self.texto)))
        return {n: self.regras[n] for n in dict.fromkeys(numeros) if n in self.regras}


def fontes_citadas(texto: str) -> set[int]:
    """Números das fontes citadas como [F1], [F2] ou [F1, F3]. Custos como [1] não contam, nem
    números de regra que o LLM às vezes escreve com F ("F331.2"), que têm 3 dígitos.

    Sufixo inventado depois de uma fonte ("[F1.4.3]", "[F1.94.1]") é ignorado: conta como F1.
    """
    return {int(n) for grupo in re.findall(r"\[([^\]]*)\]", texto)
            for n in re.findall(r"F(\d{1,2})(?!\d)", grupo)}


RE_PEDIDO_DE_EXPLICACAO = re.compile(
    r"\b(o que (é|e|são|sao|significa|quer dizer)|como (funciona|funcionam|é que funciona)"
    r"|explica|explicar|explique|explicação|explicacao|não entendi|nao entendi|não entendo|nao entendo"
    r"|não consigo entender|nao consigo entender|me ajuda a entender|diferença entre|diferenca entre"
    r"|pra que serve|para que serve)(?!\w)",
    re.IGNORECASE,
)


def e_pedido_de_explicacao(pergunta: str) -> bool:
    """"Como funciona a Chain?" pede explicação; "a Chain fecha se a unidade morrer?" é direta."""
    return bool(RE_PEDIDO_DE_EXPLICACAO.search(pergunta))


def sem_citacoes(texto: str) -> str:
    """Tira [F1] e (CRD ...) de uma resposta anterior: aqueles números valiam pras fontes DELA."""
    texto = re.sub(r"\s*\[[^\]]*F\d+[^\]]*\]", "", texto)
    return re.sub(r"\s*\(CRD [^)]*\)", "", texto)


def mesclar(*listas: list[tuple[dict, float]], k: int) -> list[tuple[dict, float]]:
    """Junta resultados de buscas diferentes, sem repetir trecho (fica a maior nota de cada um)."""
    melhores: dict[str, tuple[dict, float]] = {}
    for lista in listas:
        for trecho, nota in lista:
            if trecho["id"] not in melhores or nota > melhores[trecho["id"]][1]:
                melhores[trecho["id"]] = (trecho, nota)
    return sorted(melhores.values(), key=lambda par: -par[1])[:k]


@dataclass
class Busca:
    """Um jeito de buscar: o modelo de embeddings, o índice feito com ele e o corte do "não encontrei".

    O corte é por modelo porque cada modelo tem sua própria escala de similaridade.
    """

    nome: str
    modelo: object
    indice: object
    limiar: float


class Juiz:
    PAUSA_BUSCA_SEGUNDOS = 300  # uma busca que falhou fica de fora por 5 min (1 h se a cota do dia acabou)

    def __init__(self, buscas: list[Busca], llm, regras: dict[str, dict], catalogo: Catalogo,
                 k: int = config.K_TRECHOS, glossario_na_busca: bool = config.USAR_GLOSSARIO_NA_BUSCA,
                 definicoes: list[dict] | None = None, glossario: dict[str, str] | None = None):
        self.buscas = buscas  # em ordem de preferência: a principal primeiro, depois as reservas
        self.llm = llm
        self.regras = regras
        self.catalogo = catalogo
        self.k = k
        self.glossario_na_busca = glossario_na_busca
        self.definicoes = definicoes or []  # juiz/definicoes.yaml
        self.glossario = glossario or {}  # chave -> explicação do glossário do FAQ ("chain" -> "The chain is...")
        self._pausada_ate: dict[str, float] = {}
        self._filhos: dict[str, list[str]] = {}
        for numero, regra in regras.items():
            if regra.get("pai"):
                self._filhos.setdefault(regra["pai"], []).append(numero)

    @classmethod
    def padrao(cls) -> "Juiz":
        """O juiz montado com o que foi escolhido nas etapas anteriores (juiz/config.py)."""
        caminho = config.PROCESSED_DIR / "crd_regras.jsonl"
        regras = {r["numero"]: r for r in map(json.loads, caminho.open(encoding="utf-8"))}
        buscas = [
            Busca(nome, carregar_modelo(nome), Indice.carregar(nome), config.LIMIAR_NAO_ENCONTREI[nome])
            for nome in modelos_de_busca()
            if Indice.existe(nome)  # a reserva só entra se o índice dela já foi criado (e o PyTorch instalado)
        ]
        faq = map(json.loads, (config.PROCESSED_DIR / "faq_trechos.jsonl").open(encoding="utf-8"))
        glossario = {t["ancora"]: t["texto"].split("\n\n", 1)[1] for t in faq if t["categoria"] == "glossario"}
        definicoes = yaml.safe_load(config.DEFINICOES.read_text(encoding="utf-8"))
        return cls(buscas=buscas, llm=carregar_llm(), regras=regras, catalogo=Catalogo.carregar(),
                   definicoes=definicoes, glossario=glossario)

    # --- definições oficiais dos termos técnicos ---

    def _texto_da_regra(self, numero: str) -> str:
        """A regra e suas sub-regras diretas ("Action is functionally short for the following:" + os itens)."""
        partes = [f"{numero}: {self.regras[numero]['texto']}"]
        partes += [f"{f}: {self.regras[f]['texto']}" for f in self._filhos.get(numero, [])]
        return " | ".join(partes)

    def definicoes_relevantes(self, principais: list[str], secundarios: list[str]) -> list[tuple[str, str]]:
        """Definições oficiais dos termos que aparecem nos textos: primeiro os da pergunta, depois os das fontes."""
        escolhidas: list[tuple[str, str]] = []
        for textos in (principais, secundarios):
            texto = " ".join(textos)
            for d in self.definicoes:
                rotulo = " / ".join(d["termos"])
                if any(r == rotulo for r, _ in escolhidas):
                    continue
                if not any(re.search(rf"(?<![\w-]){re.escape(t)}s?(?![\w-])", texto, re.IGNORECASE) for t in d["termos"]):
                    continue
                partes = []
                if d.get("glossario") in self.glossario:
                    partes.append(f"Glossário do FAQ: {self.glossario[d['glossario']]}")
                partes += [self._texto_da_regra(r) for r in d.get("regras", []) if r in self.regras]
                if partes:
                    escolhidas.append((rotulo, " || ".join(partes)))
        return escolhidas[:config.MAX_DEFINICOES]

    # --- busca, com reserva ---

    def buscar(self, consulta: str, k: int | None = None) -> tuple[list[tuple[dict, float]], Busca]:
        """Busca com a principal; se ela falhar (sem cota, sobrecarga, sem internet), usa a reserva."""
        agora = time.monotonic()
        disponiveis = [b for b in self.buscas if self._pausada_ate.get(b.nome, 0) <= agora]
        ultimo_erro = None
        for busca in disponiveis or self.buscas:  # se todas estão pausadas, tenta todas mesmo assim
            try:
                return busca.indice.buscar(consulta, busca.modelo, k=k or self.k), busca
            except Exception as erro:  # a próxima busca da lista resolve
                ultimo_erro = erro
                pausa = 3600 if isinstance(erro, CotaEsgotada) else self.PAUSA_BUSCA_SEGUNDOS
                self._pausada_ate[busca.nome] = time.monotonic() + pausa
        raise ultimo_erro

    # --- montagem do contexto ---

    def _fonte_do_trecho(self, numero: int, trecho: dict, nota: float) -> Fonte:
        if trecho.get("categoria") == "glossario":
            titulo = f"Glossário do FAQ não oficial (explicação para iniciantes): {trecho['pagina']}"
            resumo = f"Glossário — {trecho['pagina']}"
        elif trecho["fonte"] == "faq":
            titulo = f'FAQ não oficial (riftboundfaq.com), página "{trecho["pagina"]}": {trecho["pergunta"]}'
            resumo = f'{trecho["pagina"]} — {trecho["pergunta"]}'
        else:
            local = trecho["subsecao"] or trecho["secao"]
            titulo = f"Core Rules {trecho['versao']} oficial: regra {trecho['numero']} ({local})"
            local_sem_numero = re.sub(r"^\d{3}\. ", "", local)  # "445. Movement" -> "Movement"
            resumo = f"Regra {trecho['numero']} — {local_sem_numero}"
        return Fonte(numero, trecho["fonte"], titulo, trecho["url"], trecho["texto_com_regras"], round(nota, 3),
                     citacao_pendente=bool(trecho.get("citacao_pendente")), resumo=resumo,
                     trecho_id=trecho.get("id", ""), regras=list(trecho.get("regras", [])))

    def montar_contexto(self, pergunta: str, resultados: list[tuple[dict, float]]) -> tuple[list[Fonte], list[str]]:
        """As fontes numeradas e a lista de regras do CRD citadas pelo FAQ (pra incluir o texto oficial)."""
        fontes = [self._fonte_do_trecho(i, t, n) for i, (t, n) in enumerate(resultados, start=1)]

        # Cartas: as citadas na pergunta e as das páginas do FAQ com nota perto da melhor
        # (páginas de outras cartas, com nota bem menor, só poluiriam o contexto).
        melhor = resultados[0][1] if resultados else 0.0
        das_paginas = [t["carta"] for t, n in resultados if t.get("carta") and n >= melhor - MARGEM_CARTAS]
        cartas = [c for c in dict.fromkeys(self.catalogo.encontrar(pergunta) + das_paginas) if c in self.catalogo.cartas]
        for nome in cartas[:config.MAX_CARTAS]:
            fontes.append(Fonte(len(fontes) + 1, "carta", f"Carta {nome} (texto oficial atual)",
                                url_da_carta(nome), self.catalogo.texto(nome), resumo=nome, trecho_id=f"carta/{nome}"))

        # Regras do CRD citadas pelos trechos do FAQ que ainda não estão num trecho do CRD encontrado.
        ja_no_contexto = {r for t, _ in resultados if t["fonte"] == "crd" for r in t["regras"] + t["contexto"]}
        citadas = [r for t, _ in resultados if t["fonte"] == "faq" for r in t["regras"]]
        extras = [r for r in dict.fromkeys(citadas) if r not in ja_no_contexto and r in self.regras]
        return fontes, extras[:config.MAX_REGRAS_CITADAS]

    def fonte_do_deck(self, deck: DeckEmFoco, numero: int) -> Fonte:
        """O deck em foco vira uma fonte: a lista e o texto oficial de cada carta (runas básicas não têm)."""
        linhas = [f"Deck do jogador: {deck.nome}", ""]
        for secao, rotulo in NOMES_DAS_SECOES.items():
            da_secao = [(carta, qtd) for s, carta, qtd in deck.cartas if s == secao]
            if da_secao:
                linhas.append(f"{rotulo}: " + "; ".join(f"{qtd}x {carta}" for carta, qtd in da_secao))
        nomes = [c for c in dict.fromkeys(carta for _, carta, _ in deck.cartas) if c in self.catalogo.cartas]
        linhas += ["", "Texto oficial das cartas do deck:"]
        linhas += [self.catalogo.texto(nome) + "\n" for nome in nomes[:config.MAX_CARTAS_DO_DECK]]
        return Fonte(numero, "deck", f"Deck do jogador: {deck.nome} (lista e texto oficial das cartas)", "",
                     "\n".join(linhas).strip(), resumo=deck.nome, trecho_id=f"deck/{deck.nome}")

    def montar_mensagem(self, pergunta: str, termos: list[tuple[str, str]], fontes: list[Fonte], extras: list[str],
                        tipo: str = "direta", historico: list[tuple[str, str]] | None = None,
                        definicoes: list[tuple[str, str]] | None = None) -> str:
        partes = []
        if historico:
            partes.append("CONVERSA ANTERIOR (da mais antiga pra mais recente; os números de fonte dela não valem mais)")
            for pergunta_antiga, resposta_antiga in historico:
                resumo = sem_citacoes(resposta_antiga)
                resumo = resumo if len(resumo) <= 900 else resumo[:900] + " …"
                partes += [f"Jogador: {pergunta_antiga}", f"Juiz: {resumo}", ""]
        partes += ["PERGUNTA DO JOGADOR", pergunta, "", f"TIPO DE PERGUNTA: {tipo}", ""]
        deck = next((f for f in fontes if f.tipo == "deck"), None)
        if deck:
            partes += [f"DECK EM FOCO: o jogador escolheu o deck \"{deck.resumo}\". Quando a pergunta falar de \"meu deck\" "
                       f"ou das cartas dele, use a lista e o texto das cartas da fonte [F{deck.numero}]. As regras continuam "
                       "vindo das outras fontes.", ""]
        if termos:
            partes.append("TERMOS DO JOGO NA PERGUNTA (como o jogador escreveu -> termo oficial em inglês)")
            partes += [f'- "{pt}" -> {en}' for pt, en in termos]
            partes.append("")
        if definicoes:
            partes.append("DEFINIÇÕES OFICIAIS DOS TERMOS TÉCNICOS (use estas pra explicar os termos; não invente outras)")
            partes += [f"- {rotulo}: {texto}" for rotulo, texto in definicoes]
            partes.append("")
        partes.append("FONTES")
        for f in fontes:
            partes.append(f"[F{f.numero}] {f.titulo}")
            if f.citacao_pendente:
                partes.append("CITAÇÃO PENDENTE: o próprio FAQ avisa que o CRD ainda não sustenta esta resposta por completo.")
            partes += [f.texto, ""]
        if extras:
            partes.append("TEXTO OFICIAL DAS REGRAS DO CORE RULES CITADAS PELAS FONTES DO FAQ")
            partes += [f"{r}: {self.regras[r]['texto']}" for r in extras]
        return "\n".join(partes).strip()

    # --- resposta ---

    def responder(self, pergunta: str, historico: list[tuple[str, str]] | None = None,
                  plano_b: bool = False, deck: DeckEmFoco | None = None) -> Resposta:
        """Responde a pergunta. `historico` = [(pergunta, resposta), ...] da conversa, da mais antiga pra mais recente.

        Com `plano_b`, se nenhum LLM responder, devolve os trechos achados pela busca em vez de levantar
        o erro (o app usa isso; a avaliação não, porque precisa saber que o LLM falhou).

        Com `deck` (um deck salvo no deck builder), a lista e o texto das cartas dele entram como fonte.
        """
        historico = (historico or [])[-config.MAX_TURNOS_HISTORICO:]
        tipo = "explicação" if e_pedido_de_explicacao(pergunta) else "direta"
        k = config.K_TRECHOS_EXPLICACAO if tipo == "explicação" else self.k
        termos = encontrar_termos(pergunta)
        consulta = expandir_pergunta(pergunta) if self.glossario_na_busca else pergunta
        resultados, busca = self.buscar(consulta, k)
        if historico:
            # Pergunta de continuação ("e se for num showdown?") não diz sozinha do que se trata:
            # busca também junto com a pergunta anterior, com o MESMO modelo (as notas são comparáveis).
            try:
                com_contexto = busca.indice.buscar(f"{historico[-1][0]} {consulta}", busca.modelo, k=k)
                resultados = mesclar(resultados, com_contexto, k=k)
            except Exception:
                pass  # a busca só com a pergunta atual já basta
        nota = resultados[0][1] if resultados else 0.0
        resposta = Resposta(pergunta, NAO_ENCONTREI, encontrou=False, termos=termos,
                            nota_busca=round(nota, 3), modelo_busca=busca.nome, tipo=tipo)

        if nota < busca.limiar and not self.catalogo.encontrar(pergunta) and deck is None:
            return resposta  # nada parecido o bastante: "não encontrei" sem chamar o LLM
        # (com um deck em foco, a resposta pode estar nas cartas dele, mesmo com a busca fraca:
        # "quais cartas do meu deck dão Stun?")

        # Trechos abaixo do limiar só atrapalham; o 1º resultado fica sempre.
        resultados = resultados[:1] + [(t, n) for t, n in resultados[1:] if n >= busca.limiar]

        fontes, extras = self.montar_contexto(pergunta, resultados)
        if deck is not None and deck.cartas:
            fontes.append(self.fonte_do_deck(deck, len(fontes) + 1))
        principais = [pergunta] + [en for _, en in termos] + ([historico[-1][0]] if historico else [])
        definicoes = self.definicoes_relevantes(principais, [t.get("texto", "") for t, _ in resultados[:2]])
        mensagem = self.montar_mensagem(pergunta, termos, fontes, extras, tipo=tipo, historico=historico,
                                        definicoes=definicoes)
        try:
            texto = self.llm.gerar(INSTRUCOES, mensagem)
        except Exception as erro:
            if not plano_b:
                raise
            resposta.sem_llm = explicar_erro(erro)
            resposta.texto = TEXTO_SEM_LLM
            resposta.encontrou = True  # a busca achou fontes; só o resumo em português falhou
            resposta.fontes = fontes
            return resposta

        citadas = fontes_citadas(texto)
        for f in fontes:
            f.citada = f.numero in citadas
        # Todas as regras que aparecem no contexto (citadas pelo FAQ ou nos trechos do CRD), pra linkar.
        numeros_crd = [r for t, _ in resultados for r in t["regras"] + t.get("contexto", [])]
        resposta.texto = texto
        resposta.encontrou = not texto.startswith("Não encontrei")
        resposta.fontes = fontes
        resposta.regras = {n: self.regras[n]["url"] for n in numeros_crd if n in self.regras}
        resposta.uso = dict(getattr(self.llm, "ultimo_uso", {}))
        return resposta

"""Códigos das cartas (fase 2): de "OGN-042" pro nome da carta, pela galeria oficial da Riot.

Por que códigos: nas importações, o código identifica a carta sem as variações de escrita do nome
("Jinx - Loose Cannon", "Kayle, Justified (Overnumbered)"). A API do TopDeck.gg manda o código de cada
carta, e o CSV da Liga Riftbound também (colunas "Edicao (Sigla)" e "Card #").

Por que a coleção continua pelo nome: um deck pede "Jinx, Rebel", e qualquer impressão serve. A
normal, a foil, a de arte alternativa (OGN-202a) e a overnumbered (OGN-304*) têm códigos diferentes
e o mesmo nome. Então o código só serve pra achar o nome.

De onde vêm os códigos: o catálogo do FAQ não tem. A galeria oficial (config.GALERIA_URL) é um site
Next.js: o HTML traz um "buildId", e com ele se pede o JSON de dados da página, que tem a lista de
cartas (cada uma com "name" e "publicCode", ex.: "OGN-042/298"). Nos campeões, "name" é só "Jinx";
o nome completo ("Jinx, Rebel") vem do texto de acessibilidade da imagem ("Riftbound Unit: Jinx,
Rebel. ..."). O método foi conferido no script de um projeto aberto que lê a mesma galeria
(riccjohn/riftbound-card-db), e o mapa resultante reconheceu todas as 1.189 impressões e os 81 códigos
de um CSV real da Liga.

Se a galeria falhar (fora do ar ou mudou de formato), tudo continua funcionando pelo nome.
"""

import json
import re
from datetime import datetime, timedelta, timezone

import httpx

from juiz import config

# Navegador comum: a galeria recusa pedidos sem User-Agent.
CABECALHOS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0 Safari/537.36"}
VERSAO_DA_GALERIA = 2  # 2: com o link da imagem de cada carta
_TEXTO_DA_IMAGEM = re.compile(r"^Riftbound [^:]{1,40}:\s*")


def normalizar_codigo(texto: str) -> str:
    """Uma forma só pros códigos das três fontes: "OGN-042/298" (galeria), "OGN-042" (TopDeck) e
    "OGN" + "42" (Liga) viram "OGN-42"; "VEN-R04" vira "VEN-R4"; "OGN-042a" vira "OGN-42a"."""
    base = str(texto).strip().upper().split("/")[0]
    colecao, _, numero = base.partition("-")
    m = re.match(r"^(R?)0*(\d+)(.*)$", numero)
    return f"{colecao}-{m.group(1)}{int(m.group(2))}{m.group(3).lower()}" if m else base


def codigo_base(codigo: str) -> str:
    """Sem o sufixo de variante: "OGN-42a" (arte alternativa) e "OGN-304*" viram "OGN-42" e "OGN-304"."""
    return re.sub(r"[^\d]+$", "", codigo) if re.search(r"\d", codigo) else codigo


def nomes_possiveis(carta: dict) -> list[str]:
    """Nomes pra tentar no catálogo, do mais completo pro mais curto. O texto da imagem começa com o
    nome completo e um ponto ("Dr. Mundo, Expert. My Might..."): tenta cada corte num ". "."""
    texto = carta.get("texto") or ""
    texto = _TEXTO_DA_IMAGEM.sub("", texto, count=1) if _TEXTO_DA_IMAGEM.match(texto) else ""
    cortes = [m.start() for m in re.finditer(r"\.(?:\s|$)", texto)][:4]
    return [texto[:i] for i in cortes if texto[:i].strip()] + [carta["nome"]]


def _achar_cartas(no) -> list[dict]:
    """A lista de cartas dentro do JSON da página (o caminho muda entre versões do site)."""
    melhor: list[dict] = []
    pilha = [no]
    while pilha:
        atual = pilha.pop()
        if isinstance(atual, list):
            if atual and isinstance(atual[0], dict) and "name" in atual[0] and "publicCode" in atual[0] and len(atual) > len(melhor):
                melhor = atual
            pilha.extend(atual)
        elif isinstance(atual, dict):
            pilha.extend(atual.values())
    return melhor


def ler_pagina(dados: dict) -> list[dict]:
    """JSON da galeria -> [{codigo, nome, texto, imagem}]. A imagem é o link da arte da carta no site da Riot."""
    cartas = []
    for c in _achar_cartas(dados.get("pageProps", dados)):
        texto = ((c.get("cardImage") or {}).get("accessibilityText") or "")
        texto = re.sub(r"<[^>]+>", " ", texto).strip()
        if c.get("publicCode") and c.get("name"):
            cartas.append({"codigo": c["publicCode"], "nome": c["name"], "texto": texto,
                           "imagem": (c.get("cardImage") or {}).get("url")})
    return cartas


def baixar_galeria(cliente: httpx.Client | None = None) -> list[dict]:
    cliente = cliente or httpx.Client(timeout=60, headers=CABECALHOS, follow_redirects=True)
    html = cliente.get(config.GALERIA_URL)
    html.raise_for_status()
    achado = re.search(r'"buildId"\s*:\s*"([^"]+)"', html.text)
    if not achado:
        raise RuntimeError("a galeria de cartas mudou de formato (sem buildId)")
    dados = cliente.get(config.GALERIA_DADOS_URL.format(build_id=achado.group(1)))
    dados.raise_for_status()
    cartas = ler_pagina(dados.json())
    if not cartas:
        raise RuntimeError("a galeria de cartas mudou de formato (lista de cartas não encontrada)")
    return cartas


def carregar_galeria(agora: datetime | None = None, baixar=baixar_galeria) -> list[dict]:
    """Galeria salva em data/raw, baixada de novo se tiver mais de uma semana. Se o download falhar,
    usa a salva; sem nenhuma, devolve [] (as cartas são reconhecidas só pelo nome)."""
    agora = agora or datetime.now(timezone.utc)
    salva = json.loads(config.GALERIA_CARTAS.read_text(encoding="utf-8")) if config.GALERIA_CARTAS.exists() else {}
    baixada_em = datetime.fromisoformat(salva["baixada_em"]) if salva.get("baixada_em") else None
    # Galeria salva antes das imagens (versão 1): baixa de novo, pra o site ter a arte das cartas.
    if salva.get("versao", 1) < VERSAO_DA_GALERIA:
        baixada_em = None
    if baixada_em and agora - baixada_em < timedelta(days=config.GALERIA_ATUALIZAR_A_CADA_DIAS):
        return salva["cartas"]
    try:
        cartas = baixar()
    except Exception as erro:  # sem internet, site fora do ar ou mudou de formato
        print(f"Galeria de cartas indisponível ({type(erro).__name__}: {erro}); cartas reconhecidas pelo nome.")
        return salva.get("cartas", [])
    config.GALERIA_CARTAS.parent.mkdir(parents=True, exist_ok=True)
    config.GALERIA_CARTAS.write_text(json.dumps({"versao": VERSAO_DA_GALERIA, "baixada_em": agora.isoformat(timespec="seconds"), "fonte": config.GALERIA_URL,
                                                 "cartas": cartas}, ensure_ascii=False), encoding="utf-8")
    return cartas


def mapa_de_codigos(galeria: list[dict], resolver) -> dict[str, str]:
    """{código normalizado: nome no catálogo}. `resolver` é Catalogo.resolver."""
    mapa = {}
    for carta in galeria:
        nome = next((n for n in map(resolver, nomes_possiveis(carta)) if n), None)
        if nome:
            mapa[normalizar_codigo(carta["codigo"])] = nome
    return mapa


def mapa_de_imagens(galeria: list[dict]) -> dict[str, str]:
    """{código normalizado: link da imagem}."""
    return {normalizar_codigo(c["codigo"]): c["imagem"] for c in galeria if c.get("imagem")}

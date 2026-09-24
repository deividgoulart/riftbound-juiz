"""Registro local das perguntas feitas no app e do 👍/👎 de cada resposta (etapa 6).

Pra que serve: as perguntas de verdade, feitas durante as partidas, são o melhor material pra
ampliar o gabarito na etapa 7. O arquivo fica em data/logs/ (fora do git) e só na sua máquina.
"""

import json
from datetime import datetime, timezone

from juiz import config


def _arquivo():
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return config.LOGS_DIR / "conversas.jsonl"


def _gravar(evento: dict) -> None:
    evento = {"quando": datetime.now(timezone.utc).isoformat(timespec="seconds"), **evento}
    with _arquivo().open("a", encoding="utf-8") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")


def registrar_resposta(id_: str, resposta) -> None:
    _gravar({
        "tipo": "resposta",
        "id": id_,
        "pergunta": resposta.pergunta,
        "resposta": resposta.texto,
        "encontrou": resposta.encontrou,
        "nota_busca": resposta.nota_busca,
        "modelo": resposta.uso.get("modelo"),
        "busca": resposta.modelo_busca,
        "tipo_pergunta": resposta.tipo,
        "fontes": [{"numero": f.numero, "url": f.url, "citada": f.citada} for f in resposta.fontes],
    })


def registrar_avaliacao(id_: str, gostou: bool) -> None:
    _gravar({"tipo": "avaliacao", "id": id_, "gostou": gostou})


def registrar_erro(pergunta: str, erro: Exception) -> None:
    _gravar({"tipo": "erro", "pergunta": pergunta, "erro": f"{type(erro).__name__}: {erro}"})

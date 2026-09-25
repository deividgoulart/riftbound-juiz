"""Proteção do app publicado (etapa 8): modo convidado com limites e senha pra uso sem limite.

Por que limitar, se a chave nunca aparece pro visitante? A chave fica nos "secrets" do servidor,
mas cada pergunta gasta a cota GRÁTIS do Gemini. Sem limite, qualquer pessoa (ou um robô) poderia
gastar a cota do dia e deixar o juiz fora do ar até o dia seguinte. Com o projeto do Google sem
faturamento ativado, o pior caso é esse: o app para, sem custo nenhum.

Como funciona:
- Só vale quando existe a variável SENHA_DO_APP (nos secrets da API publicada). Rodando no seu
  computador, sem ela, não há limite nenhum.
- Convidado: até config.LIMITE_POR_VISITANTE perguntas por dia e config.LIMITE_DIARIO no dia,
  somando todos os visitantes. Quem digita a senha usa sem limite.

Os contadores por visitante, o token do dono e as tentativas de senha ficam em api/acesso.py.
"""

import hmac
import os
import threading
from datetime import date, datetime, timedelta, timezone

# A cota grátis do Gemini zera à meia-noite do horário do Pacífico. Usamos UTC-8 fixo: no horário
# de verão a virada fica 1 hora fora, o que não faz diferença aqui.
FUSO_DA_COTA = timezone(timedelta(hours=-8))


def senha_do_app() -> str:
    return os.environ.get("SENHA_DO_APP", "")


def modo_publico() -> bool:
    """Com senha configurada, o app está publicado: convidados têm limite."""
    return bool(senha_do_app())


def senha_confere(digitada: str) -> bool:
    senha = senha_do_app()
    # compare_digest leva o mesmo tempo com qualquer entrada: não dá pistas de quantas letras acertou.
    return bool(senha) and hmac.compare_digest(digitada.encode("utf-8"), senha.encode("utf-8"))


class ContadorDiario:
    """Perguntas de convidados no dia, somando todos os visitantes."""

    def __init__(self, limite: int, hoje=None):
        self.limite = limite
        self._hoje = hoje or (lambda: datetime.now(FUSO_DA_COTA).date())
        self._dia: date | None = None
        self._usadas = 0
        self._trava = threading.Lock()  # vários visitantes podem perguntar ao mesmo tempo

    def _virar_o_dia(self) -> None:
        hoje = self._hoje()
        if hoje != self._dia:
            self._dia, self._usadas = hoje, 0

    def restantes(self) -> int:
        with self._trava:
            self._virar_o_dia()
            return max(0, self.limite - self._usadas)

    def consumir(self) -> bool:
        """Reserva uma pergunta. False se o limite do dia já acabou."""
        with self._trava:
            self._virar_o_dia()
            if self._usadas >= self.limite:
                return False
            self._usadas += 1
            return True

    def devolver(self) -> None:
        """Se a pergunta deu erro, ela não conta."""
        with self._trava:
            self._usadas = max(0, self._usadas - 1)

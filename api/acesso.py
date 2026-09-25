"""Quem pode o quê na API publicada: o dono (com a senha) e os convidados (com limite de perguntas).

- Sem SENHA_DO_APP no ambiente (rodando no seu computador), todo mundo é dono: sem limite e com edição.
- Com a senha, o site manda a senha uma vez (POST /api/entrar) e recebe um token assinado, que guarda
  no navegador e manda em cada pedido ("Authorization: Bearer <token>"). O token vale
  TOKEN_VALIDO_POR_DIAS e é assinado com a própria senha (HMAC): trocar a senha desconecta todo mundo.
- Convidado: até config.LIMITE_POR_VISITANTE perguntas por dia por visitante (pelo IP) e
  config.LIMITE_DIARIO no dia, somando todos. Só o dono edita a coleção e os decks.

Limitações conhecidas (aceitáveis pra um projeto de portfólio): os contadores ficam na memória do
servidor (zeram se ele reiniciar) e o IP de quem usa a mesma rede é o mesmo. Quem protege a cota do
Gemini de verdade é o limite diário, que vale pra todos.
"""

import hashlib
import hmac
import threading
import time
from datetime import date, datetime

from juiz import config
from juiz.limites import FUSO_DA_COTA, ContadorDiario, modo_publico, senha_confere, senha_do_app

TOKEN_VALIDO_POR_DIAS = 30
JANELA_DAS_TENTATIVAS = 3600  # segundos: TENTATIVAS_DE_SENHA erradas por IP nesse tempo


def _assinatura(validade: str) -> str:
    return hmac.new(senha_do_app().encode("utf-8"), f"dono:{validade}".encode(), hashlib.sha256).hexdigest()


def criar_token(agora: float | None = None) -> str:
    validade = str(int((agora or time.time()) + TOKEN_VALIDO_POR_DIAS * 86400))
    return f"{validade}.{_assinatura(validade)}"


def token_valido(token: str | None, agora: float | None = None) -> bool:
    if not token or not senha_do_app() or "." not in token:
        return False
    validade, assinatura = token.split(".", 1)
    if not validade.isdigit() or int(validade) < (agora or time.time()):
        return False
    return hmac.compare_digest(assinatura, _assinatura(validade))


def e_dono(autorizacao: str | None) -> bool:
    """Sem senha configurada, quem roda a API é o dono. Com senha, precisa do token."""
    if not modo_publico():
        return True
    token = autorizacao.removeprefix("Bearer ").strip() if autorizacao else None
    return token_valido(token)


class TentativasDeSenha:
    """Senhas erradas por IP, pra ninguém ficar chutando."""

    def __init__(self, limite: int | None = None, janela: float = JANELA_DAS_TENTATIVAS):
        self.limite, self.janela = limite or config.TENTATIVAS_DE_SENHA, janela
        self._erros: dict[str, list[float]] = {}
        self._trava = threading.Lock()

    def _recentes(self, ip: str, agora: float) -> list[float]:
        recentes = [t for t in self._erros.get(ip, []) if agora - t < self.janela]
        self._erros[ip] = recentes
        return recentes

    def bloqueado(self, ip: str) -> bool:
        with self._trava:
            return len(self._recentes(ip, time.monotonic())) >= self.limite

    def errou(self, ip: str) -> None:
        with self._trava:
            self._recentes(ip, time.monotonic()).append(time.monotonic())


class ContadorPorVisitante:
    """Perguntas de cada visitante (IP) no dia."""

    def __init__(self, limite: int, hoje=None):
        self.limite = limite
        self._hoje = hoje or (lambda: datetime.now(FUSO_DA_COTA).date())
        self._dia: date | None = None
        self._usadas: dict[str, int] = {}
        self._trava = threading.Lock()

    def _virar_o_dia(self) -> None:
        if self._hoje() != self._dia:
            self._dia, self._usadas = self._hoje(), {}

    def restantes(self, ip: str) -> int:
        with self._trava:
            self._virar_o_dia()
            return max(0, self.limite - self._usadas.get(ip, 0))

    def consumir(self, ip: str) -> bool:
        with self._trava:
            self._virar_o_dia()
            if self._usadas.get(ip, 0) >= self.limite:
                return False
            self._usadas[ip] = self._usadas.get(ip, 0) + 1
            return True

    def devolver(self, ip: str) -> None:
        with self._trava:
            self._usadas[ip] = max(0, self._usadas.get(ip, 0) - 1)


class Convidados:
    """Os dois limites juntos: o do visitante e o do dia (todos os visitantes)."""

    def __init__(self, por_visitante: int | None = None, diario: int | None = None):
        self.por_visitante = ContadorPorVisitante(por_visitante or config.LIMITE_POR_VISITANTE)
        self.diario = ContadorDiario(diario or config.LIMITE_DIARIO)

    def restantes(self, ip: str) -> int:
        return min(self.por_visitante.restantes(ip), self.diario.restantes())

    def motivo_do_bloqueio(self, ip: str) -> str | None:
        if self.por_visitante.restantes(ip) == 0:
            return (f"Você usou as {self.por_visitante.limite} perguntas de hoje. O limite existe pra proteger a cota "
                    "gratuita do Gemini, que é dividida entre todos os visitantes. Volte amanhã!")
        if self.diario.restantes() == 0:
            return ("O juiz atingiu o limite de perguntas de convidados de hoje, pra proteger a cota gratuita do "
                    "Gemini. Volte amanhã!")
        return None

    def reservar(self, ip: str) -> bool:
        """Reserva a pergunta nos dois contadores antes de chamar o juiz (dois visitantes ao mesmo tempo
        não passam do limite). False se algum limite acabou."""
        if not self.por_visitante.consumir(ip):
            return False
        if not self.diario.consumir():
            self.por_visitante.devolver(ip)
            return False
        return True

    def devolver(self, ip: str) -> None:
        """A pergunta deu erro (ou não gastou o LLM): não conta."""
        self.por_visitante.devolver(ip)
        self.diario.devolver()

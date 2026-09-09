"""Rate limiting simples, em memória.

O Render free roda uma única instância, então um dicionário em processo é
suficiente. A contrapartida: o contador zera a cada deploy e a cada cold start
(o serviço hiberna após ~15 min ocioso). Isso ainda barra brute force sustentado
dentro de uma janela quente; para algo mais forte seria preciso Redis + captcha.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


def client_ip(request: Request) -> str:
    """IP do cliente. Atrás do proxy do Render o IP real vem no
    X-Forwarded-For (o primeiro da lista); localmente cai no socket."""
    encaminhado = request.headers.get("x-forwarded-for")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"


class SlidingWindowLimiter:
    """Janela deslizante: no máximo `max_hits` eventos por `window_seconds`
    para cada chave (ex.: um IP)."""

    def __init__(self, max_hits: int, window_seconds: int, *, mensagem: str | None = None):
        self.max_hits = max_hits
        self.window = window_seconds
        self.mensagem = mensagem or "Muitas tentativas. Aguarde um pouco e tente de novo."
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._ultimo_sweep = 0.0

    def _sweep(self, agora: float) -> None:
        """Remove chaves ociosas de tempos em tempos para não vazar memória."""
        if agora - self._ultimo_sweep < 300:
            return
        self._ultimo_sweep = agora
        for chave in list(self._hits):
            dq = self._hits[chave]
            while dq and dq[0] <= agora - self.window:
                dq.popleft()
            if not dq:
                del self._hits[chave]

    def check(self, chave: str) -> None:
        """Levanta 429 se `chave` já estourou a janela. Não registra nada."""
        dq = self._hits.get(chave)
        if not dq:
            return
        agora = time.monotonic()
        while dq and dq[0] <= agora - self.window:
            dq.popleft()
        if len(dq) >= self.max_hits:
            retry = int(dq[0] + self.window - agora) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=self.mensagem,
                headers={"Retry-After": str(max(1, retry))},
            )

    def hit(self, chave: str) -> None:
        """Registra um evento para `chave` e levanta 429 se estourar."""
        self.check(chave)
        agora = time.monotonic()
        self._sweep(agora)
        self._hits[chave].append(agora)


# Limites por IP. No login só as tentativas que FALHAM contam — um usuário
# legítimo (mesmo numa casa com vários logando pelo mesmo IP) nunca é bloqueado;
# brute force online, sim (uma senha exige milhares de palpites).
login_limiter = SlidingWindowLimiter(
    max_hits=15,
    window_seconds=300,
    mensagem="Muitas tentativas de login sem sucesso. Tente novamente em alguns minutos.",
)
register_limiter = SlidingWindowLimiter(
    max_hits=5,
    window_seconds=3600,
    mensagem="Muitos cadastros a partir deste endereço. Tente mais tarde.",
)
# Busca de pessoas: teto na velocidade de varredura da base de usuários.
busca_limiter = SlidingWindowLimiter(
    max_hits=20,
    window_seconds=60,
    mensagem="Muitas buscas seguidas. Aguarde um momento.",
)

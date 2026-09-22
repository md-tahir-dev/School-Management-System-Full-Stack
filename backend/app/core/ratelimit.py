"""Small in-process sliding-window rate limiter.

Per-process only: fine for a single API container. When the API is scaled out (and for the public
test endpoints in Phase 5) swap `_hits` for Redis; the dependency interface stays the same."""

import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Request

from app.core.errors import AppError


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str, limit: int, window_seconds: int) -> int:
        """Records a hit. Returns 0 if allowed, otherwise seconds until the caller may retry."""
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] >= window_seconds:
            q.popleft()
        if len(q) >= limit:
            return max(1, int(window_seconds - (now - q[0])))
        q.append(now)
        return 0

    def reset(self) -> None:
        self._hits.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, limit: int | Callable[[], int], window_seconds: int | Callable[[], int]):
    """FastAPI dependency factory: `dependencies=[Depends(rate_limit("login", 30, 900))]`."""

    async def dependency(request: Request) -> None:
        lim = limit() if callable(limit) else limit
        win = window_seconds() if callable(window_seconds) else window_seconds
        retry_after = limiter.hit(f"{name}:{client_ip(request)}", lim, win)
        if retry_after:
            raise AppError(
                429,
                "rate_limited",
                "Too many requests. Please wait and try again.",
                details={"retry_after_seconds": retry_after},
                headers={"Retry-After": str(retry_after)},
            )

    return dependency

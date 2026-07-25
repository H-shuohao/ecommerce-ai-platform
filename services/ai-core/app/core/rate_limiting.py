import hashlib
import math
import threading
import time
from dataclasses import dataclass

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.observability import request_id_context
from config import settings


@dataclass
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int


@dataclass
class _Window:
    started_at: float
    count: int


class FixedWindowRateLimiter:
    """Small single-process limiter for the current portfolio deployment."""

    def __init__(self) -> None:
        self._windows: dict[str, _Window] = {}
        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> RateLimitDecision:
        current = time.monotonic() if now is None else now
        with self._lock:
            window = self._windows.get(key)
            if window is None or current - window.started_at >= window_seconds:
                window = _Window(started_at=current, count=0)
                self._windows[key] = window

            if window.count >= limit:
                reset_after = max(
                    1,
                    math.ceil(window_seconds - (current - window.started_at)),
                )
                return RateLimitDecision(
                    allowed=False,
                    limit=limit,
                    remaining=0,
                    reset_after_seconds=reset_after,
                )

            window.count += 1
            reset_after = max(
                1,
                math.ceil(window_seconds - (current - window.started_at)),
            )
            return RateLimitDecision(
                allowed=True,
                limit=limit,
                remaining=max(0, limit - window.count),
                reset_after_seconds=reset_after,
            )

    def clear(self) -> None:
        with self._lock:
            self._windows.clear()


rate_limiter = FixedWindowRateLimiter()


def _is_limited_path(path: str) -> bool:
    return path.startswith(("/api/", "/debug/", "/mcp"))


def _client_key(request: Request) -> str:
    api_key = request.headers.get("X-API-Key", "").strip()
    if api_key:
        # Never keep or log the original credential.
        return f"key:{hashlib.sha256(api_key.encode()).hexdigest()}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


def _headers(decision: RateLimitDecision) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": str(decision.remaining),
        "X-RateLimit-Reset": str(decision.reset_after_seconds),
    }


async def enforce_rate_limit(request: Request, call_next):
    if not settings.RATE_LIMIT_ENABLED or not _is_limited_path(request.url.path):
        return await call_next(request)

    decision = rate_limiter.check(
        _client_key(request),
        limit=settings.RATE_LIMIT_REQUESTS,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    headers = _headers(decision)
    if not decision.allowed:
        headers["Retry-After"] = str(decision.reset_after_seconds)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": "请求过于频繁，请稍后重试",
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "请求过于频繁，请稍后重试",
                    "request_id": request_id_context.get(),
                },
            },
            headers=headers,
        )

    response = await call_next(request)
    response.headers.update(headers)
    return response

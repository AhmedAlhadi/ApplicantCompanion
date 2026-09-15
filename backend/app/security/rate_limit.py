"""Simple in-process sliding-window rate limiting (§42).

For multi-instance deployments swap this for a Redis-backed limiter; the
middleware interface stays the same.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..config import get_settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        path = request.url.path
        if path.startswith("/api/") and path not in {"/api/health", "/api/auth/config"}:
            forwarded = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            key = forwarded or (request.client.host if request.client else "unknown")
            now = time.monotonic()
            if path.startswith("/api/coach") and request.method in {"POST", "PUT"}:
                coach_limit = settings.coach_rate_limit_per_minute
                if coach_limit > 0:
                    coach_key = f"coach:{key}"
                    window = self._hits[coach_key]
                    while window and now - window[0] > 60:
                        window.popleft()
                    if len(window) >= coach_limit:
                        return JSONResponse(
                            {"detail": "Coach rate limit exceeded"},
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        )
                    window.append(now)
            limit = settings.rate_limit_per_minute
            if limit > 0:
                window = self._hits[key]
                while window and now - window[0] > 60:
                    window.popleft()
                if len(window) >= limit:
                    return JSONResponse(
                        {"detail": "Rate limit exceeded"},
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    )
                window.append(now)
        return await call_next(request)

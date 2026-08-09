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
        limit = get_settings().rate_limit_per_minute
        if limit > 0 and request.url.path.startswith("/api/"):
            key = request.client.host if request.client else "unknown"
            now = time.monotonic()
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

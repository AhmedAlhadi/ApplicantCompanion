"""Structured logging + request latency middleware (§55)."""
from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='{"ts": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "msg": "%(message)s"}',
    )


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Structured access log with latency; never logs bodies (§55)."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        started = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - started) * 1000
        logging.getLogger("api.access").info(
            '{"request_id": "%s", "method": "%s", "path": "%s", "status": %d, "latency_ms": %.1f}',
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response

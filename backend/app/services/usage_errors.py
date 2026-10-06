"""Structured commercial-limit errors. The backend remains authoritative."""
from __future__ import annotations

from fastapi import HTTPException


class EntitlementError(Exception):
    def __init__(self, code: str, *, status_code: int = 409, message: str = "", **detail):
        self.code = code
        self.status_code = status_code
        self.detail = {"code": code, "message": message, **detail}
        super().__init__(message or code)

    def as_http(self) -> HTTPException:
        return HTTPException(self.status_code, detail=self.detail)

"""Google Identity Services ID-token verification."""
from __future__ import annotations

from fastapi import HTTPException, status

from ..config import get_settings


def verify_google_id_token(id_token_str: str) -> dict:
    settings = get_settings()
    client_id = (settings.google_client_id or "").strip()
    if not client_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google Sign-In is not configured")
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except ImportError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google Sign-In is not available") from exc

    try:
        claims = google_id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            client_id,
            clock_skew_in_seconds=60,
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Google token") from exc
    if not claims.get("email"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google account has no email")
    if claims.get("email_verified") is False:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google email is not verified")
    return claims

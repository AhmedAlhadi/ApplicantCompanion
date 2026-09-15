"""Auth endpoints (§42). Email/password registration is open for the first user
only; Google Sign-In can provision later users. Admins can also create accounts.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import User
from ..schemas.api import AuthConfigResponse, GoogleAuthRequest, LoginRequest, RegisterRequest, TokenResponse
from ..security.auth import (
    audit,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from ..security.google_oauth import verify_google_id_token
from ..services.serializers import to_dict

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public_user(user: User) -> dict:
    return to_dict(user, exclude={"password_hash", "google_sub"})


def _non_deleted_user_count(db: Session) -> int:
    return db.query(User).filter(User.is_deleted == False).count()  # noqa: E712


@router.get("/config", response_model=AuthConfigResponse)
def auth_config(db: Session = Depends(get_db)):
    return AuthConfigResponse(
        google_client_id=get_settings().google_client_id.strip(),
        registration_open=_non_deleted_user_count(db) == 0,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    if _non_deleted_user_count(db) > 0:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is closed; ask an admin")
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        is_admin=True,  # first user owns the workspace
    )
    db.add(user)
    db.flush()
    audit(db, user, "auth.register", "user", user.id, request=request)
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id), user=_public_user(user))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower(), User.is_deleted == False).first()  # noqa: E712
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    audit(db, user, "auth.login", "user", user.id, request=request)
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id), user=_public_user(user))


@router.post("/google", response_model=TokenResponse)
def google_login(payload: GoogleAuthRequest, request: Request, db: Session = Depends(get_db)):
    claims = verify_google_id_token(payload.id_token)
    sub = str(claims["sub"])
    email = str(claims["email"]).lower()
    name = str(claims.get("name") or "")
    picture = str(claims.get("picture") or "") or None

    user = db.query(User).filter(User.google_sub == sub, User.is_deleted == False).first()  # noqa: E712
    created = False
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is not None and user.is_deleted:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
        if user is None:
            user = User(
                email=email,
                password_hash=None,
                full_name=name,
                is_admin=_non_deleted_user_count(db) == 0,
                google_sub=sub,
                avatar_url=picture,
            )
            db.add(user)
            db.flush()
            created = True
        else:
            user.google_sub = sub
            if picture:
                user.avatar_url = picture
            if name and not user.full_name:
                user.full_name = name
    else:
        if picture:
            user.avatar_url = picture
        if name and not user.full_name:
            user.full_name = name

    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    audit(db, user, "auth.google.register" if created else "auth.google.login", "user", user.id, request=request)
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id), user=_public_user(user))


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _public_user(user)

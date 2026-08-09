"""Auth endpoints (§42). Registration is open for the first user only —
afterwards an existing admin must create accounts (single-user-first design)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas.api import LoginRequest, RegisterRequest, TokenResponse
from ..security.auth import (
    audit,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from ..services.serializers import to_dict

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public_user(user: User) -> dict:
    return to_dict(user, exclude={"password_hash"})


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    existing_count = db.query(User).filter(User.is_deleted == False).count()  # noqa: E712
    if existing_count > 0:
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
    audit(db, user, "auth.login", "user", user.id, request=request)
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id), user=_public_user(user))


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _public_user(user)

"""Admin user-management APIs. Account records only — never another user's workspace."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Application, Job, User
from ..schemas.api import AdminUserCreate, AdminUserUpdate
from ..security.auth import audit, hash_password, require_admin
from ..services.serializers import to_dict

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _would_leave_no_active_admin(
    db: Session,
    target: User,
    *,
    is_admin: bool | None = None,
    is_active: bool | None = None,
    deleting: bool = False,
) -> bool:
    remaining = 0
    for u in db.query(User).filter(User.is_deleted == False).all():  # noqa: E712
        admin_flag = u.is_admin
        active_flag = u.is_active
        if u.id == target.id:
            if deleting:
                continue
            if is_admin is not None:
                admin_flag = is_admin
            if is_active is not None:
                active_flag = is_active
        if admin_flag and active_flag:
            remaining += 1
    return remaining < 1


def _admin_user_payload(db: Session, user: User) -> dict:
    data = to_dict(user, exclude={"password_hash", "google_sub"})
    data["has_password"] = bool(user.password_hash)
    data["google_linked"] = bool(user.google_sub)
    data["job_count"] = (
        db.query(Job).filter(Job.user_id == user.id, Job.is_deleted == False).count()  # noqa: E712
    )
    data["application_count"] = (
        db.query(Application)
        .filter(Application.user_id == user.id, Application.is_deleted == False)  # noqa: E712
        .count()
    )
    return data


def _get_managed_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.get("/stats")
def admin_stats(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    del admin
    now = datetime.now(timezone.utc)
    users = db.query(User).filter(User.is_deleted == False).all()  # noqa: E712
    created_this_month = sum(
        1 for u in users if u.created_at and u.created_at.year == now.year and u.created_at.month == now.month
    )
    return {
        "total_users": len(users),
        "active_users": sum(1 for u in users if u.is_active),
        "admin_users": sum(1 for u in users if u.is_admin),
        "created_this_month": created_this_month,
    }


@router.get("/users")
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    del admin
    users = db.query(User).filter(User.is_deleted == False).order_by(User.created_at.asc()).all()  # noqa: E712
    return [_admin_user_payload(db, u) for u in users]


@router.post("/users", status_code=201)
def create_user(payload: AdminUserCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        is_admin=payload.is_admin,
        is_active=True,
    )
    db.add(user)
    db.flush()
    audit(db, admin, "admin.user.create", "user", user.id, {"email": email, "is_admin": payload.is_admin}, request)
    db.commit()
    db.refresh(user)
    return _admin_user_payload(db, user)


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = _get_managed_user(db, user_id)
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if payload.is_active is not None and payload.is_active != user.is_active:
        if user.id == admin.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot change your own active status")
        if _would_leave_no_active_admin(db, user, is_active=payload.is_active):
            raise HTTPException(status.HTTP_409_CONFLICT, "Cannot deactivate the last admin")
        user.is_active = payload.is_active
    if payload.is_admin is not None and payload.is_admin != user.is_admin:
        if user.id == admin.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot change your own admin role")
        if _would_leave_no_active_admin(db, user, is_admin=payload.is_admin):
            raise HTTPException(status.HTTP_409_CONFLICT, "Cannot demote the last admin")
        user.is_admin = payload.is_admin
    audit(
        db,
        admin,
        "admin.user.update",
        "user",
        user.id,
        payload.model_dump(exclude_none=True, exclude={"password"}),
        request,
    )
    db.commit()
    db.refresh(user)
    return _admin_user_payload(db, user)


@router.delete("/users/{user_id}")
def delete_user(user_id: str, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = _get_managed_user(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete your own account")
    if _would_leave_no_active_admin(db, user, deleting=True):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot delete the last admin")
    user.is_deleted = True
    user.is_active = False
    audit(db, admin, "admin.user.delete", "user", user.id, request=request)
    db.commit()
    return {"ok": True}

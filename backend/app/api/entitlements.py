"""Account usage and entitlement summary."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ApplicationPackUnlock, User
from ..security.auth import get_current_user
from ..services.serializers import to_dict
from ..services.usage import UsageService

router = APIRouter(prefix="/api/account", tags=["account"])


@router.get("/usage")
def account_usage(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    summary = UsageService(db).summary(user.id)
    unlocks = (
        db.query(ApplicationPackUnlock)
        .filter(ApplicationPackUnlock.user_id == user.id, ApplicationPackUnlock.state == "active")
        .order_by(ApplicationPackUnlock.created_at.desc())
        .limit(50)
        .all()
    )
    summary["pack_unlocks"] = [to_dict(row) for row in unlocks]
    return summary


@router.get("/entitlements")
def account_entitlements(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return account_usage(db=db, user=user)

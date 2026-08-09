"""Per-user settings with global defaults (§20: configurable threshold/weights)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import UserSetting


def get_user_setting(db: Session, user_id: str, key: str, default: Any) -> Any:
    row = (
        db.query(UserSetting)
        .filter(UserSetting.user_id == user_id, UserSetting.key == key)
        .first()
    )
    if row is None:
        return default
    return row.value.get("value", default)


def set_user_setting(db: Session, user_id: str, key: str, value: Any) -> UserSetting:
    row = (
        db.query(UserSetting)
        .filter(UserSetting.user_id == user_id, UserSetting.key == key)
        .first()
    )
    if row is None:
        row = UserSetting(user_id=user_id, key=key, value={"value": value})
        db.add(row)
    else:
        row.value = {"value": value}
    db.flush()
    return row


def all_user_settings(db: Session, user_id: str) -> dict[str, Any]:
    rows = db.query(UserSetting).filter(UserSetting.user_id == user_id).all()
    return {r.key: r.value.get("value") for r in rows}

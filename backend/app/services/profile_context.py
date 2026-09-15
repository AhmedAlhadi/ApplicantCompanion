"""User-stated profession/sector hints used as context, never as evidence."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models.career import CareerProfile


def profession_context_for(db: Session, user_id: str) -> str:
    profile = db.query(CareerProfile).filter_by(user_id=user_id).first()
    if not profile:
        return ""
    bits: list[str] = []
    profession = (profile.primary_profession or "").strip()
    if profession:
        bits.append(f"primary profession: {profession}")
    sectors = [str(item).strip() for item in (profile.target_sectors or []) if str(item).strip()]
    if sectors:
        bits.append("target sectors: " + ", ".join(sectors))
    if not bits:
        return ""
    return (
        "User-stated profession context (hints only; never invent facts from this): "
        + "; ".join(bits)
    )

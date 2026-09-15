"""First-run onboarding status. Completion is stored in user settings."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Application, CareerProfile, Experience, Job, JobScore, PendingIngestion, User
from ..security.auth import audit, get_current_user
from ..services.settings import get_user_setting, set_user_setting

router = APIRouter(prefix="/api", tags=["onboarding"])

ONBOARDING_KEY = "onboarding_status"
TERMINAL = {"completed", "skipped", "in_progress"}


def _experience_count(db: Session, user_id: str) -> int:
    return (
        db.query(Experience)
        .filter(Experience.user_id == user_id, Experience.is_deleted == False)  # noqa: E712
        .count()
    )


def _resolve_status(db: Session, user: User, experience_count: int) -> str:
    status = get_user_setting(db, user.id, ONBOARDING_KEY, None)
    if status in TERMINAL:
        return status
    if experience_count > 0:
        set_user_setting(db, user.id, ONBOARDING_KEY, "completed")
        db.commit()
        return "completed"
    set_user_setting(db, user.id, ONBOARDING_KEY, "in_progress")
    db.commit()
    return "in_progress"


def _status_payload(db: Session, user: User) -> dict:
    experience_count = _experience_count(db, user.id)
    status = _resolve_status(db, user, experience_count)
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user.id).first()
    pending_count = (
        db.query(PendingIngestion)
        .filter(PendingIngestion.user_id == user.id, PendingIngestion.status == "pending")
        .count()
    )
    jobs = (
        db.query(Job)
        .filter(Job.user_id == user.id, Job.is_deleted == False)  # noqa: E712
        .order_by(Job.created_at.desc())
        .all()
    )
    latest_job = jobs[0] if jobs else None
    latest_app = None
    latest_score = None
    if latest_job:
        latest_app = (
            db.query(Application)
            .filter(
                Application.user_id == user.id,
                Application.job_id == latest_job.id,
                Application.is_deleted == False,  # noqa: E712
            )
            .order_by(Application.created_at.desc())
            .first()
        )
        score = (
            db.query(JobScore)
            .filter(JobScore.job_id == latest_job.id)
            .order_by(JobScore.created_at.desc())
            .first()
        )
        if score:
            latest_score = {
                "overall_score": score.overall_score,
                "threshold": score.threshold,
                "recommendation": score.recommendation,
            }
    return {
        "status": status,
        "has_profile": bool(profile and (profile.full_name or "").strip()),
        "experience_count": experience_count,
        "pending_count": pending_count,
        "job_count": len(jobs),
        "latest_job": (
            {
                "id": latest_job.id,
                "status": latest_job.status,
                "organization_name": latest_job.organization_name,
                "position_title": latest_job.position_title,
            }
            if latest_job
            else None
        ),
        "latest_application": (
            {
                "id": latest_app.id,
                "status": latest_app.status,
                "job_id": latest_app.job_id,
                "fit_score": latest_app.fit_score_snapshot,
            }
            if latest_app
            else None
        ),
        "latest_score": latest_score,
        "profile": (
            {
                "full_name": profile.full_name,
                "headline": profile.headline,
                "summary": profile.summary,
                "email": profile.email,
                "phone": profile.phone,
                "location": profile.location,
                "links": profile.links or {},
                "primary_profession": profile.primary_profession or "",
                "target_sectors": profile.target_sectors or [],
            }
            if profile
            else None
        ),
    }


@router.get("/onboarding")
def get_onboarding(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _status_payload(db, user)


@router.post("/onboarding/complete")
def complete_onboarding(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    set_user_setting(db, user.id, ONBOARDING_KEY, "completed")
    audit(db, user, "onboarding.complete", "user", user.id, request=request)
    db.commit()
    return _status_payload(db, user)


@router.post("/onboarding/skip")
def skip_onboarding(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    set_user_setting(db, user.id, ONBOARDING_KEY, "skipped")
    audit(db, user, "onboarding.skip", "user", user.id, request=request)
    db.commit()
    return _status_payload(db, user)

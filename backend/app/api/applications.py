"""Application endpoints: creation, decision (§20-21), strategy, generation (§49, §52)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..agents.orchestrator import Orchestrator, generation_stages
from ..database import SessionLocal, get_db
from ..models import (
    Application,
    ApplicationStrategy,
    CoverLetter,
    CV,
    DocumentVersion,
    Job,
    JobScore,
    User,
    WorkflowRun,
)
from ..schemas.api import ApplicationCreate, ApplicationUpdate, DecideRequest, GenerateRequest
from ..security.auth import audit, get_current_user
from ..services.serializers import to_dict
from ..services.user_errors import public_error
from ..workers.runner import submit

router = APIRouter(prefix="/api/applications", tags=["applications"])
logger = logging.getLogger(__name__)

BELOW_THRESHOLD_MESSAGE = (
    "Generation is blocked until you approve continuing with a below-threshold fit score. "
    "Your estimated fit is below the configured threshold — approve to generate documents, "
    "or cancel the application."
)


def _get_owned_app(db: Session, app_id: str, user: User) -> Application:
    app = db.get(Application, app_id)
    if app is None or app.user_id != user.id or app.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return app


def _latest_score(db: Session, job_id: str) -> JobScore | None:
    return (
        db.query(JobScore).filter(JobScore.job_id == job_id).order_by(JobScore.created_at.desc()).first()
    )


def _app_payload(db: Session, app: Application) -> dict:
    data = to_dict(app)
    job = db.get(Job, app.job_id)
    data["job"] = {
        "id": job.id,
        "organization_name": job.organization_name,
        "position_title": job.position_title,
        "location": job.location,
        "deadline": job.deadline,
        "status": job.status,
    } if job else None
    score = _latest_score(db, app.job_id)
    data["fit_score"] = score.overall_score if score else None
    cv = db.query(CV).filter(CV.application_id == app.id).first()
    letter = db.query(CoverLetter).filter(CoverLetter.application_id == app.id).first()
    data["cv_id"] = cv.id if cv else None
    data["cover_letter_id"] = letter.id if letter else None
    return data


@router.post("", status_code=201)
def create_application(payload: ApplicationCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, payload.job_id)
    if job is None or job.user_id != user.id or job.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    existing = (
        db.query(Application)
        .filter(Application.job_id == job.id, Application.user_id == user.id, Application.is_deleted == False)  # noqa: E712
        .first()
    )
    if existing:
        return _app_payload(db, existing)
    app = Application(user_id=user.id, job_id=job.id, status="draft")
    score = _latest_score(db, job.id)
    if score:
        app.fit_score_snapshot = score.overall_score
    db.add(app)
    db.flush()
    audit(db, user, "applications.create", "application", app.id, request=request)
    db.commit()
    return _app_payload(db, app)


@router.get("")
def list_applications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    apps = (
        db.query(Application)
        .filter(Application.user_id == user.id, Application.is_deleted == False)  # noqa: E712
        .order_by(Application.created_at.desc())
        .all()
    )
    return [_app_payload(db, a) for a in apps]


@router.get("/{app_id}")
def get_application(app_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    app = _get_owned_app(db, app_id, user)
    return _app_payload(db, app)


@router.put("/{app_id}")
def update_application(app_id: str, payload: ApplicationUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    app = _get_owned_app(db, app_id, user)
    data = payload.model_dump(exclude_none=True)
    if "status" in data and data["status"] not in (
        "draft", "ready", "submitted", "interview", "rejected", "offer", "withdrawn",
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid status")
    for field, value in data.items():
        setattr(app, field, value)
    audit(db, user, "applications.update", "application", app.id, request=request)
    db.commit()
    return _app_payload(db, app)


@router.delete("/{app_id}")
def delete_application(app_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    app = _get_owned_app(db, app_id, user)
    app.is_deleted = True
    audit(db, user, "applications.delete", "application", app.id, request=request)
    db.commit()
    return {"deleted": app_id}


@router.get("/{app_id}/strategy")
def get_strategy(app_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    app = _get_owned_app(db, app_id, user)
    strategy = (
        db.query(ApplicationStrategy).filter(ApplicationStrategy.application_id == app.id).first()
    )
    if strategy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No strategy yet — generate one first")
    return to_dict(strategy)


@router.post("/{app_id}/strategy", status_code=202)
def generate_strategy(app_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    app = _get_owned_app(db, app_id, user)
    run = Orchestrator(db, user).create_run(
        "document_generation",
        generation_stages(strategy_only=True),
        job_id=app.job_id,
        application_id=app.id,
    )
    db.commit()
    submit(_run_strategy_background, app.id, user.id, run.id)
    return {"status": "accepted", "workflow_run_id": run.id}


def _fail_run(db: Session, run_id: str, exc: Exception) -> None:
    run = db.get(WorkflowRun, run_id)
    if run is None:
        return
    message = public_error(exc)[:2000]
    stages = [dict(stage) for stage in run.stages]
    for stage in stages:
        if stage.get("status") == "RUNNING":
            stage["status"] = "FAILED"
            stage["ended_at"] = datetime.now(timezone.utc).isoformat()
            stage["error"] = message[:1000]
    run.stages = stages
    run.status = "FAILED"
    run.error = message


def _run_strategy_background(app_id: str, user_id: str, run_id: str) -> None:
    db = SessionLocal()
    try:
        app = db.get(Application, app_id)
        user = db.get(User, user_id)
        run = db.get(WorkflowRun, run_id)
        if not app or not user or not run:
            raise RuntimeError("strategy entities no longer exist")
        run.status = "RUNNING"
        db.flush()
        Orchestrator(db, user).run_strategy(app, run=run)
    except Exception as exc:
        logger.exception("Strategy generation failed unexpectedly for run %s", run_id)
        db.rollback()
        _fail_run(db, run_id, exc)
        db.commit()
    finally:
        db.close()


def _check_threshold_gate(db: Session, app: Application) -> None:
    """§20-21: below-threshold scores need an explicit user decision (advisory,
    never a hard rejection)."""
    score = _latest_score(db, app.job_id)
    if score and score.overall_score < score.threshold and not app.user_approved:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "BELOW_THRESHOLD",
                "message": BELOW_THRESHOLD_MESSAGE,
                "score": score.overall_score,
                "threshold": score.threshold,
                "actions": ["continue", "cancel", "review_gaps"],
                "gaps": score.gaps,
            },
        )


@router.post("/{app_id}/decide")
def decide(app_id: str, payload: DecideRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    app = _get_owned_app(db, app_id, user)
    if payload.decision == "continue":
        app.user_approved = True
    elif payload.decision == "cancel":
        app.status = "withdrawn"
        app.user_approved = False
    # review_gaps: no state change — the UI shows the gap report
    audit(db, user, "applications.decide", "application", app.id, {"decision": payload.decision}, request)
    db.commit()
    return _app_payload(db, app)


def _run_generation_background(
    app_id: str,
    user_id: str,
    run_id: str,
    gen_cv: bool,
    gen_cl: bool,
    template_key: str | None,
) -> None:
    db = SessionLocal()
    try:
        app = db.get(Application, app_id)
        user = db.get(User, user_id)
        run = db.get(WorkflowRun, run_id)
        if not app or not user or not run:
            raise RuntimeError("generation entities no longer exist")
        run.status = "RUNNING"
        db.flush()
        Orchestrator(db, user).run_generation(
            app,
            generate_cv=gen_cv,
            generate_cover_letter=gen_cl,
            template_key=template_key,
            run=run,
        )
    except Exception as exc:
        logger.exception("Document generation failed unexpectedly for run %s", run_id)
        db.rollback()
        _fail_run(db, run_id, exc)
        db.commit()
    finally:
        db.close()


def _accept_generation(db: Session, app: Application, user: User, gen_cv: bool, gen_cl: bool, template_key: str | None) -> dict:
    run = Orchestrator(db, user).create_run(
        "document_generation",
        generation_stages(generate_cv=gen_cv, generate_cover_letter=gen_cl),
        job_id=app.job_id,
        application_id=app.id,
    )
    db.commit()
    submit(_run_generation_background, app.id, user.id, run.id, gen_cv, gen_cl, template_key)
    return {"status": "accepted", "workflow_run_id": run.id}


@router.post("/{app_id}/generate-cv", status_code=202)
def generate_cv(app_id: str, payload: GenerateRequest | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    app = _get_owned_app(db, app_id, user)
    _check_threshold_gate(db, app)
    return _accept_generation(db, app, user, True, False, payload.template_key if payload else None)


@router.post("/{app_id}/generate-cover-letter", status_code=202)
def generate_cover_letter(app_id: str, payload: GenerateRequest | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    app = _get_owned_app(db, app_id, user)
    _check_threshold_gate(db, app)
    return _accept_generation(db, app, user, False, True, payload.template_key if payload else None)


@router.post("/{app_id}/generate-all", status_code=202)
def generate_all(app_id: str, payload: GenerateRequest | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    app = _get_owned_app(db, app_id, user)
    _check_threshold_gate(db, app)
    return _accept_generation(db, app, user, True, True, payload.template_key if payload else None)


@router.get("/{app_id}/documents")
def list_documents(app_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    app = _get_owned_app(db, app_id, user)
    out = []
    for doc_type, model in (("cv", CV), ("cover_letter", CoverLetter)):
        doc = db.query(model).filter(model.application_id == app.id).first()
        if doc is None:
            continue
        current = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_type == doc_type,
                DocumentVersion.document_id == doc.id,
                DocumentVersion.is_current == True,  # noqa: E712
            )
            .first()
        )
        versions = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_type == doc_type, DocumentVersion.document_id == doc.id)
            .count()
        )
        out.append({
            **to_dict(doc),
            "document_type": doc_type,
            "current_version": to_dict(current) if current else None,
            "version_count": versions,
        })
    return out


@router.get("/{app_id}/workflow")
def get_app_workflow(app_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    app = _get_owned_app(db, app_id, user)
    run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.application_id == app.id)
        .order_by(WorkflowRun.created_at.desc())
        .first()
    )
    if run is None:
        return {"status": "not_started", "stages": []}
    return to_dict(run)

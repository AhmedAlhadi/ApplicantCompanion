"""Job endpoints: creation, analysis workflow, scores, research (§48, §52)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..agents.orchestrator import Orchestrator
from ..database import SessionLocal, get_db
from ..models import (
    HiringContext,
    Job,
    JobRequirement,
    JobScore,
    OrganizationResearch,
    Person,
    RequirementMatch,
    User,
    WorkflowRun,
)
from ..schemas.api import AnalyzeRequest, JobCreate, JobUpdate
from ..security.auth import audit, get_current_user
from ..services.serializers import to_dict
from ..workers.runner import submit

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _get_owned_job(db: Session, job_id: str, user: User) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.user_id != user.id or job.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


def _run_analysis_background(job_id: str, user_id: str, run_id: str, include_research: bool) -> None:
    """Background entrypoint with its own session (§53)."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        user = db.get(User, user_id)
        run = db.get(WorkflowRun, run_id)
        if job and user and run:
            run.status = "RUNNING"
            db.flush()
            Orchestrator(db, user).run_job_analysis(job, include_research=include_research, run=run)
    finally:
        db.close()


@router.post("", status_code=201)
def create_job(payload: JobCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.source_type in ("paste", "url") and not payload.raw_jd_text.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Job description text is required")
    job = Job(
        user_id=user.id,
        organization_name=payload.organization_name,
        position_title=payload.position_title,
        location=payload.location,
        deadline=payload.deadline,
        notes=payload.notes,
        raw_jd_text=payload.raw_jd_text,
        source_url=payload.source_url,
        source_type=payload.source_type,
    )
    db.add(job)
    db.flush()
    audit(db, user, "jobs.create", "job", job.id, request=request)
    db.commit()
    return to_dict(job)


@router.get("")
def list_jobs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    jobs = (
        db.query(Job)
        .filter(Job.user_id == user.id, Job.is_deleted == False)  # noqa: E712
        .order_by(Job.created_at.desc())
        .all()
    )
    out = []
    for job in jobs:
        data = to_dict(job, exclude={"raw_jd_text", "parsed"})
        score = (
            db.query(JobScore)
            .filter(JobScore.job_id == job.id)
            .order_by(JobScore.created_at.desc())
            .first()
        )
        data["fit_score"] = score.overall_score if score else None
        out.append(data)
    return out


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _get_owned_job(db, job_id, user)
    data = to_dict(job)
    score = (
        db.query(JobScore).filter(JobScore.job_id == job.id).order_by(JobScore.created_at.desc()).first()
    )
    data["fit_score"] = score.overall_score if score else None
    return data


@router.put("/{job_id}")
def update_job(job_id: str, payload: JobUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _get_owned_job(db, job_id, user)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(job, field, value)
    audit(db, user, "jobs.update", "job", job.id, request=request)
    db.commit()
    return to_dict(job)


@router.delete("/{job_id}")
def delete_job(job_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _get_owned_job(db, job_id, user)
    job.is_deleted = True
    audit(db, user, "jobs.delete", "job", job.id, request=request)
    db.commit()
    return {"deleted": job_id}


@router.post("/{job_id}/analyze", status_code=202)
def analyze_job(job_id: str, payload: AnalyzeRequest | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Kick off the analysis workflow in the background; poll/SSE for progress."""
    job = _get_owned_job(db, job_id, user)
    include_research = payload.include_research if payload else True
    run = (
        db.query(WorkflowRun)
        .filter(
            WorkflowRun.job_id == job_id,
            WorkflowRun.workflow_type == "job_analysis",
            WorkflowRun.status.in_(("PENDING", "RUNNING")),
        )
        .first()
    )
    if run is None:
        # Create the run row synchronously so clients get its id immediately,
        # then execute in the background (§53).
        from ..agents.orchestrator import ANALYSIS_STAGES

        run = Orchestrator(db, user).create_run("job_analysis", ANALYSIS_STAGES, job_id=job.id)
        job.status = "analyzing"
        db.commit()
        submit(_run_analysis_background, job.id, user.id, run.id, include_research)
    return {"status": "accepted", "workflow_run_id": run.id}


@router.get("/{job_id}/analysis")
def get_analysis(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _get_owned_job(db, job_id, user)
    requirements = (
        db.query(JobRequirement).filter(JobRequirement.job_id == job.id).all()
    )
    matches = db.query(RequirementMatch).filter(RequirementMatch.job_id == job.id).all()
    match_by_req = {m.requirement_id: m for m in matches}
    return {
        "job": to_dict(job),
        "parsed": job.parsed,
        "requirements": [
            {
                **to_dict(r),
                "match": to_dict(match_by_req[r.id]) if r.id in match_by_req else None,
            }
            for r in requirements
        ],
    }


@router.get("/{job_id}/score")
def get_score(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _get_owned_job(db, job_id, user)
    score = (
        db.query(JobScore).filter(JobScore.job_id == job.id).order_by(JobScore.created_at.desc()).first()
    )
    if score is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No score yet — run analysis first")
    return to_dict(score)


@router.get("/{job_id}/research")
def get_research(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _get_owned_job(db, job_id, user)
    research = (
        db.query(OrganizationResearch).filter(OrganizationResearch.job_id == job.id).all()
    )
    hiring = db.query(HiringContext).filter(HiringContext.job_id == job.id).first()
    people = []
    hiring_data = to_dict(hiring) if hiring else None
    if hiring:
        for pid in (hiring.hiring_manager_id, hiring.recruiter_id):
            if pid:
                person = db.get(Person, pid)
                if person:
                    people.append(to_dict(person))
    return {
        "organization_research": [to_dict(r) for r in research],
        "hiring_context": hiring_data,
        "people": people,
    }


@router.get("/{job_id}/workflow")
def get_workflow(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_owned_job(db, job_id, user)
    run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.job_id == job_id)
        .order_by(WorkflowRun.created_at.desc())
        .first()
    )
    if run is None:
        return {"status": "not_started", "stages": []}
    return to_dict(run)

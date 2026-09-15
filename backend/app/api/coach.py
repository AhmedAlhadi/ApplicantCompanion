"""Career Coach REST API — persistent, user-scoped, retrieval-grounded."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..models.coach import CoachConversation, CoachMessage
from ..schemas.api import CoachConversationIn, CoachMessageIn
from ..security.auth import audit, get_current_user
from ..services.coach import conversation_payload, message_payload, run_turn, _owned_application, _owned_job

router = APIRouter(prefix="/api/coach", tags=["coach"])


def _conversation(db: Session, user: User, conversation_id: str) -> CoachConversation:
    conv = (
        db.query(CoachConversation)
        .filter(
            CoachConversation.id == conversation_id,
            CoachConversation.user_id == user.id,
            CoachConversation.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return conv


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(CoachConversation)
        .filter(CoachConversation.user_id == user.id, CoachConversation.is_deleted == False)  # noqa: E712
        .order_by(CoachConversation.updated_at.desc())
        .all()
    )
    return [conversation_payload(row) for row in rows]


@router.post("/conversations")
def create_conversation(
    payload: CoachConversationIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = CoachConversation(
        user_id=user.id,
        title=(payload.title or "").strip(),
        job_id=(_owned_job(db, user.id, payload.job_id).id if _owned_job(db, user.id, payload.job_id) else None),
        application_id=(
            _owned_application(db, user.id, payload.application_id).id
            if _owned_application(db, user.id, payload.application_id)
            else None
        ),
    )
    db.add(conv)
    db.flush()
    audit(db, user, "coach.conversation.create", "coach_conversation", conv.id, request=request)
    db.commit()
    db.refresh(conv)
    return conversation_payload(conv, [])


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = _conversation(db, user, conversation_id)
    messages = (
        db.query(CoachMessage)
        .filter(
            CoachMessage.conversation_id == conv.id,
            CoachMessage.is_deleted == False,  # noqa: E712
        )
        .order_by(CoachMessage.created_at.asc())
        .all()
    )
    return conversation_payload(conv, messages)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = _conversation(db, user, conversation_id)
    conv.is_deleted = True
    db.query(CoachMessage).filter(CoachMessage.conversation_id == conv.id).update({"is_deleted": True})
    audit(db, user, "coach.conversation.delete", "coach_conversation", conv.id, request=request)
    db.commit()
    return {"ok": True}


@router.post("/conversations/{conversation_id}/messages")
def post_message(
    conversation_id: str,
    payload: CoachMessageIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = _conversation(db, user, conversation_id)
    try:
        assistant = run_turn(
            db,
            user,
            conv,
            payload.content,
            job_id=payload.job_id,
            application_id=payload.application_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit(db, user, "coach.message.create", "coach_conversation", conv.id, request=request)
    db.commit()
    return message_payload(assistant)


@router.post("/conversations/{conversation_id}/messages/stream")
def post_message_stream(
    conversation_id: str,
    payload: CoachMessageIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Complete-response SSE contract; token streaming is a later provider follow-up."""
    conv = _conversation(db, user, conversation_id)

    def events():
        try:
            assistant = run_turn(
                db,
                user,
                conv,
                payload.content,
                job_id=payload.job_id,
                application_id=payload.application_id,
            )
            audit(db, user, "coach.message.create", "coach_conversation", conv.id, request=request)
            db.commit()
            yield f"data: {json.dumps(message_payload(assistant))}\n\n"
        except ValueError as exc:
            db.rollback()
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")

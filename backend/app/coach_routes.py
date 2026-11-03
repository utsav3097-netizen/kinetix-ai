"""Authenticated persistent coach transport; all changes require explicit confirmation."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.auth import CurrentUser, Database, prevent_caching
from app.coach_schemas import (
    CoachConfirmationResponse, CoachMessageInput, CoachMessagePage, CoachMessageResponse,
    ConfirmInput, CoachPageQuery,
)
from app.models.athlete import AthleteProfile
from app.services import coach

router = APIRouter(prefix="/api/v1/coach", tags=["coach"], dependencies=[Depends(prevent_caching)])


@router.get("/messages", response_model=CoachMessagePage)
def list_coach_messages(user: CurrentUser, db: Database, query: Annotated[CoachPageQuery, Query()]) -> dict:
    return coach.list_messages(db, user.id, query.conversation_id, query.offset, query.limit)


@router.post("/messages", response_model=CoachMessageResponse, status_code=201)
async def send_coach_message(payload: CoachMessageInput, user: CurrentUser, db: Database) -> dict:
    profile = db.get(AthleteProfile, user.id)
    return await coach.send_message(db, user.id, payload, profile)


@router.post("/messages/{message_id}/confirm", response_model=CoachConfirmationResponse)
def confirm_coach_message(message_id: str, payload: ConfirmInput, user: CurrentUser, db: Database) -> dict:
    # The literal-True body is intentionally required: no implicit or UI-only confirmation.
    return coach.confirm_message(db, user.id, message_id)

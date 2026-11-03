"""Owner-scoped persistent coach orchestration and confirmed domain commands."""
import re
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import as_utc
from app.coach_schemas import (
    CoachAIResponse, CoachMessageInput, CoachProposal, MealUpdateProposal, PlanDraftProposal,
    PlanEditProposal, WorkoutUpdateProposal,
)
from app.config import Settings, settings
from app.models.athlete import AthleteProfile
from app.models.coach import CoachConversation, CoachMessage
from app.models.nutrition import Meal, MealItem, NutritionDay
from app.models.planning import PlanDraft
from app.models.workout import WorkoutExercise, WorkoutSession, WorkoutSet
from app.services import nutrition, plans, workouts
from app.services.ai.providers import AIUnavailable, UNAVAILABLE_REASON, structured_generate
from app.models.identity import utc_now

SAFETY_REPLY = (
    "I can help you adjust training and recovery, but I cannot diagnose pain or injury. "
    "Stop the movement that causes pain, avoid pushing through sharp or worsening symptoms, "
    "and contact a qualified clinician or urgent care for severe pain, deformity, loss of "
    "function, numbness, chest pain, or trouble breathing. If symptoms persist, get medical advice "
    "before resuming training."
)
PAIN_TERMS = re.compile(r"\b(?:pain|painful|injur(?:y|ies|ed)|hurt|swelling|numb(?:ness)?|sharp|tingling|dizzy|fracture|sprain|strain)\b", re.I)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _profile_context(profile: AthleteProfile | None) -> dict:
    if profile is None:
        return {"available": False}
    # Never include full_name, nickname, email, user id, or other account identifiers.
    return {"available": True, "age": profile.age, "biological_sex": profile.biological_sex,
            "height_cm": profile.height_cm, "current_weight_kg": profile.current_weight_kg,
            "body_fat_percentage": profile.body_fat_percentage, "phase": profile.phase,
            "activity_multiplier": profile.activity_multiplier}


def _training_context(db: Session, owner_id: str, today: date) -> tuple[dict, dict]:
    start = today - timedelta(days=13)
    sessions = list(db.scalars(select(WorkoutSession).where(
        WorkoutSession.owner_id == owner_id, WorkoutSession.deleted_at.is_(None),
        WorkoutSession.performed_on.between(start, today),
    ).order_by(WorkoutSession.performed_on.desc(), WorkoutSession.created_at.desc(), WorkoutSession.id.desc()).limit(50)))
    session_ids = [row.id for row in sessions]
    blocks = list(db.scalars(select(WorkoutExercise).where(
        WorkoutExercise.owner_id == owner_id, WorkoutExercise.deleted_at.is_(None),
        WorkoutExercise.session_id.in_(session_ids),
    ).order_by(WorkoutExercise.session_id, WorkoutExercise.ordinal, WorkoutExercise.id))) if session_ids else []
    block_ids = [row.id for row in blocks]
    sets = list(db.scalars(select(WorkoutSet).where(
        WorkoutSet.owner_id == owner_id, WorkoutSet.deleted_at.is_(None),
        WorkoutSet.block_id.in_(block_ids),
    ).order_by(WorkoutSet.session_id, WorkoutSet.block_id, WorkoutSet.ordinal, WorkoutSet.id).limit(500))) if block_ids else []
    blocks_by_session: dict[str, list[dict]] = {}
    sets_by_block: dict[str, list[dict]] = {}
    for row in sets:
        sets_by_block.setdefault(row.block_id, []).append({"ordinal": row.ordinal, "set_type": row.set_type,
            "external_load_kg": row.external_load_kg, "repetitions": row.repetitions,
            "duration_seconds": row.duration_seconds, "rpe": row.rpe, "rir": row.rir,
            "metrics": {key: row.metrics.get(key) for key in ("estimated_1rm_kg", "volume_kg")}})
    for row in blocks:
        blocks_by_session.setdefault(row.session_id, []).append({"id": row.id, "exercise_id": row.exercise_id,
            "name": row.exercise_snapshot.get("name"), "target_min_reps": row.target_min_reps,
            "target_max_reps": row.target_max_reps, "completed": row.completed,
            "sets": sets_by_block.get(row.id, [])[:20]})
    items = []
    for row in sessions:
        items.append({"id": row.id, "title": row.title, "performed_on": row.performed_on.isoformat(),
            "revision": row.revision, "sleep_hours": row.sleep_hours, "soreness": row.soreness,
            "exercises": blocks_by_session.get(row.id, [])[:20]})
    analysis = _jsonable(workouts.analytics(db, owner_id, 2, end_date=today, bounded=True))
    recovery = {"fatigue": analysis.get("fatigue"),
                "recent_soreness": [item["soreness"] for item in items if item["soreness"] is not None][:7],
                "recent_sleep_hours": [item["sleep_hours"] for item in items if item["sleep_hours"] is not None][:7]}
    return {"window_start": start.isoformat(), "window_end": today.isoformat(), "sessions": items}, {
        "personal_records": analysis.get("prs", [])[:50], "recovery_signals": recovery}


def _nutrition_context(db: Session, owner_id: str, today: date) -> dict:
    start = today - timedelta(days=6)
    days = list(db.scalars(select(NutritionDay).where(
        NutritionDay.owner_id == owner_id, NutritionDay.date.between(start, today),
    ).order_by(NutritionDay.date.desc()).limit(7)))
    day_ids = [row.id for row in days]
    meals = list(db.scalars(select(Meal).where(Meal.owner_id == owner_id, Meal.day_id.in_(day_ids), Meal.deleted_at.is_(None))
        .order_by(Meal.day_id, Meal.id))) if day_ids else []
    meal_ids = [row.id for row in meals]
    meal_items = list(db.scalars(select(MealItem).where(MealItem.owner_id == owner_id, MealItem.meal_id.in_(meal_ids), MealItem.deleted_at.is_(None))
        .order_by(MealItem.meal_id, MealItem.ordinal))) if meal_ids else []
    by_meal: dict[str, list[dict]] = {}
    for item in meal_items:
        by_meal.setdefault(item.meal_id, []).append({"food_id": item.food_id, "grams": item.grams,
            "food_name": item.food_snapshot.get("name"), "nutrients": item.nutrients})
    by_day: dict[str, list[dict]] = {}
    for meal in meals:
        by_day.setdefault(meal.day_id, []).append({"id": meal.id, "slot": meal.slot, "title": meal.title,
            "time": meal.time, "items": by_meal.get(meal.id, [])[:50]})
    return {"window_start": start.isoformat(), "window_end": today.isoformat(), "days": [
        {"date": row.date.isoformat(), "training_day": row.training_day, "revision": row.revision,
         "targets": row.targets, "meals": by_day.get(row.id, [])[:20]}
        for row in days]}


def build_context(db: Session, owner_id: str, profile: AthleteProfile | None, conversation_id: str, current_message: str) -> dict:
    today = utc_now().date()
    training, signals = _training_context(db, owner_id, today)
    active = plans.active_version(db, owner_id)
    active_data = None
    if active is not None:
        view = plans.version_view(db, active)
        day = next((item for item in view["data"]["days"] if item["date"] == today.isoformat()), None)
        active_data = {"version_id": view["id"], "version": view["version"], "title": view["title"],
                       "path": view["path"], "starts_on": view["starts_on"], "ends_on": view["ends_on"],
                       "today": {"label": day["label"], "training_day": day["training_day"], "targets": day["targets"]} if day else None}
    history = list(db.scalars(select(CoachMessage).where(
        CoachMessage.owner_id == owner_id, CoachMessage.conversation_id == conversation_id,
    ).order_by(CoachMessage.created_at.desc(), CoachMessage.id.desc()).limit(12)))
    return {"profile": _profile_context(profile), "training_last_14_days": training,
            "personal_records_last_14_days": signals["personal_records"], "recovery_signals": signals["recovery_signals"],
            "nutrition_last_7_days": _nutrition_context(db, owner_id, today), "active_plan": active_data,
            "conversation": [{"role": row.role, "content": row.content[:1000]} for row in reversed(history)],
            "request": current_message[:4000]}


def _prompt(db: Session) -> str:
    try:
        from app.services.admin_policy import load_setting
        configured = load_setting(db, "coach_prompt")
    except Exception:
        if db.in_transaction():
            db.rollback()
        configured = None
    configured_text = configured.strip() if isinstance(configured, str) else ""
    return (configured_text + ("\n\n" if configured_text else "") +
            "You are the KINETIX coach. Give practical, concise, non-diagnostic fitness guidance. "
            "Use only the bounded context supplied. Do not mention or infer a person's name, email, or identity. "
            "Never invent record IDs. For a requested change to a plan, workout, or meal, return exactly one "
            "typed proposal using only the allowed kinds and include exact changed values; otherwise proposal is null. "
            "A proposal is only a preview: never claim it was applied. Do not emit URLs, tools, endpoints, or arbitrary commands. "
            "For pain or injury, advise stopping aggravating movement and professional care; do not diagnose.")


def _is_safety_question(message: str) -> bool:
    return PAIN_TERMS.search(message) is not None


def _message_view(row: CoachMessage) -> dict:
    return {"id": row.id, "role": row.role, "status": row.status, "content": row.content,
            "proposal_state": row.proposal_state, "proposal": row.proposal, "result": row.result,
            "created_at": as_utc(row.created_at), "confirmed_at": as_utc(row.confirmed_at) if row.confirmed_at else None}


def conversation_for(db: Session, owner_id: str, conversation_id: str | None = None, *, create: bool = False) -> CoachConversation | None:
    statement = select(CoachConversation).where(CoachConversation.owner_id == owner_id)
    if conversation_id is not None:
        statement = statement.where(CoachConversation.id == conversation_id)
    conversation = db.scalar(statement)
    if conversation is None and create and conversation_id is None:
        conversation = CoachConversation(owner_id=owner_id)
        db.add(conversation)
        db.flush()
    if conversation is None and conversation_id is not None:
        raise HTTPException(status_code=404, detail="Coach conversation not found")
    return conversation


async def send_message(db: Session, owner_id: str, payload: CoachMessageInput, profile: AthleteProfile | None,
                       provider_settings: Settings = settings) -> dict:
    conversation = conversation_for(db, owner_id, payload.conversation_id, create=True)
    assert conversation is not None
    user_row = CoachMessage(owner_id=owner_id, conversation_id=conversation.id, role="user", status="complete",
                            content=payload.message, proposal_state="none")
    db.add(user_row)
    conversation.updated_at = utc_now()
    db.flush()
    db.commit()
    try:
        if _is_safety_question(payload.message):
            generated = CoachAIResponse(reply=SAFETY_REPLY, proposal=None)
            status = "safety"
        else:
            context = build_context(db, owner_id, profile, conversation.id, payload.message)
            generated = (await structured_generate(CoachAIResponse, _prompt(db), context, settings=provider_settings)).data
            status = "complete"
    except AIUnavailable:
        generated = CoachAIResponse(reply=UNAVAILABLE_REASON, proposal=None)
        status = "unavailable"
    except Exception:
        # Provider and serialization failures are intentionally indistinguishable from unavailability.
        generated = CoachAIResponse(reply=UNAVAILABLE_REASON, proposal=None)
        status = "unavailable"
    proposal = generated.proposal
    assistant = CoachMessage(owner_id=owner_id, conversation_id=conversation.id, role="assistant", status=status,
        content=generated.reply, proposal_state="pending" if proposal is not None else "none",
        proposal=proposal.model_dump(mode="json") if proposal is not None else None)
    db.add(assistant)
    conversation.updated_at = utc_now()
    db.commit()
    return {"conversation_id": conversation.id, "user": _message_view(user_row), "assistant": _message_view(assistant)}


def list_messages(db: Session, owner_id: str, conversation_id: str | None, offset: int, limit: int) -> dict:
    conversation = conversation_for(db, owner_id, conversation_id)
    if conversation is None:
        return {"conversation_id": None, "items": [], "total": 0}
    statement = select(CoachMessage).where(CoachMessage.owner_id == owner_id, CoachMessage.conversation_id == conversation.id)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = list(db.scalars(statement.order_by(CoachMessage.created_at.desc(), CoachMessage.id.desc()).offset(offset).limit(limit)))
    rows.reverse()
    return {"conversation_id": conversation.id, "items": [_message_view(row) for row in rows], "total": total}


def _stale(message: CoachMessage, detail: str, db: Session) -> None:
    message.proposal_state = "expired"
    db.commit()
    raise HTTPException(status_code=409, detail=detail)


def _profile_or_403(db: Session, owner_id: str) -> AthleteProfile:
    profile = db.get(AthleteProfile, owner_id)
    if profile is None:
        raise HTTPException(status_code=403, detail="Complete onboarding before confirming coach changes")
    return profile


def confirm_message(db: Session, owner_id: str, message_id: str) -> dict:
    try:
        message_id = str(UUID(message_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=404, detail="Coach message not found") from None
    message = db.scalar(select(CoachMessage).where(CoachMessage.id == message_id, CoachMessage.owner_id == owner_id,
        CoachMessage.role == "assistant").with_for_update())
    if message is None:
        raise HTTPException(status_code=404, detail="Coach message not found")
    if message.proposal_state == "confirmed":
        return {"message": _message_view(message), "committed": False}
    if message.proposal_state != "pending" or message.proposal is None:
        raise HTTPException(status_code=409, detail="This coach proposal is no longer confirmable")
    try:
        from pydantic import TypeAdapter
        parsed = TypeAdapter(CoachProposal).validate_python(message.proposal)
        profile = _profile_or_403(db, owner_id)
        result: dict
        if isinstance(parsed, PlanDraftProposal):
            result = plans.draft_view(plans.generate_draft(db, profile, parsed.payload))
        elif isinstance(parsed, PlanEditProposal):
            draft = db.scalar(select(PlanDraft).where(PlanDraft.id == parsed.target_id, PlanDraft.owner_id == owner_id))
            if draft is None:
                _stale(message, "The proposed plan draft is no longer available", db)
            result = plans.draft_view(plans.edit_draft(db, profile, parsed.target_id, parsed.payload))
        elif isinstance(parsed, WorkoutUpdateProposal):
            current = workouts.get_session(db, owner_id, parsed.target_id, lock=True)
            if parsed.expected_revision is not None and current.revision != parsed.expected_revision:
                _stale(message, "The workout changed since this proposal; request a fresh proposal", db)
            result = workouts.session_view(db, workouts.update_session(db, owner_id, parsed.target_id, parsed.payload))
        elif isinstance(parsed, MealUpdateProposal):
            current = db.scalar(select(NutritionDay.revision).join(Meal, Meal.day_id == NutritionDay.id).where(
                NutritionDay.owner_id == owner_id, Meal.owner_id == owner_id, Meal.id == parsed.target_id,
                Meal.deleted_at.is_(None)).with_for_update())
            if current is None:
                _stale(message, "The meal is no longer available", db)
            if parsed.expected_revision is not None and current != parsed.expected_revision:
                _stale(message, "The meal changed since this proposal; request a fresh proposal", db)
            result = nutrition.day_view(db, nutrition.update_meal(db, owner_id, parsed.target_id, parsed.payload))
        else:  # pragma: no cover - closed discriminated union
            raise HTTPException(status_code=422, detail="Unsupported coach proposal")
        message.proposal_state = "confirmed"
        message.confirmed_at = utc_now()
        message.result = _jsonable(result)
        db.commit()
        return {"message": _message_view(message), "committed": True}
    except HTTPException:
        if db.in_transaction():
            db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=422, detail="The proposed change could not be applied") from None

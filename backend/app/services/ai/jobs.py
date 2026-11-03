"""Transaction-owned queue commands and validated public views; no workout imports."""
from copy import deepcopy
import json
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_schemas import InsightComparison, InsightView, MealParseInput, ParsedMealDraft, SetInsight
from app.models import AIInsight, AthleteProfile, Food, WorkoutSourceRecord
from app.models.identity import utc_now
from app.reference_service import visible_references


def latest(db: Session, owner_id: str, source_id: str, kind: str) -> AIInsight | None:
    return db.scalar(select(AIInsight).where(AIInsight.owner_id == owner_id,
        AIInsight.source_record_id == source_id, AIInsight.kind == kind).order_by(AIInsight.attempt.desc()).limit(1))


def enqueue_workout(db: Session, owner_id: str, source_id: str, kind: str, context: dict,
                    comparison: dict, *, retry: bool = False) -> AIInsight:
    """Caller holds the workout session lock; attempt zero deduplicates automatic jobs."""
    source = db.scalar(select(WorkoutSourceRecord).where(WorkoutSourceRecord.id == source_id,
        WorkoutSourceRecord.owner_id == owner_id))
    expected = "set" if kind == "set" else "exercise"
    if kind not in {"set", "exercise_block"} or source is None or source.entity_type != expected or source.action == "delete":
        raise HTTPException(404, "Workout source not found")
    previous = latest(db, owner_id, source_id, kind)
    if previous is not None and (not retry or previous.status != "unavailable"):
        return previous
    row = AIInsight(owner_id=owner_id, kind=kind, source_record_id=source_id,
        attempt=previous.attempt + 1 if previous else 0, context=deepcopy(context),
        comparison=InsightComparison.model_validate(comparison).model_dump(), status="pending")
    db.add(row)
    db.flush()
    return row


def enqueue_meal(db: Session, owner_id: str, payload: MealParseInput) -> AIInsight:
    if payload.date > utc_now().date():
        raise HTTPException(422, "Nutrition dates cannot be in the future")
    if db.scalar(select(AthleteProfile.user_id).where(AthleteProfile.user_id == owner_id)) is None:
        raise HTTPException(403, "Complete your athlete profile first")
    if not payload.text.strip() or not payload.title.strip():
        raise HTTPException(422, "Meal description and title must not be blank")
    # A bounded catalog is sufficient for matching, not a license to invent absent foods.
    foods = db.scalars(visible_references(Food, owner_id).order_by(Food.name, Food.id).limit(300))
    context = {"request": payload.model_dump(mode="json"),
               "foods": [{"id": food.id, "name": food.name} for food in foods]}
    row = AIInsight(owner_id=owner_id, kind="meal_parse", status="pending", context=context, attempt=0)
    db.add(row)
    db.flush()
    return row


def get_insight(db: Session, owner_id: str, insight_id: str, kinds: tuple[str, ...]) -> AIInsight:
    try:
        insight_id = str(UUID(insight_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, "AI insight not found") from None
    row = db.scalar(select(AIInsight).where(AIInsight.id == insight_id, AIInsight.owner_id == owner_id,
                                          AIInsight.kind.in_(kinds)))
    if row is None:
        raise HTTPException(404, "AI insight not found")
    return row


def insight_view(row: AIInsight) -> InsightView:
    result = None
    if row.status == "success":
        schema = ParsedMealDraft if row.kind == "meal_parse" else SetInsight
        result = schema.model_validate_json(json.dumps(row.result, allow_nan=False))
    return InsightView(id=row.id, kind=row.kind, status=row.status, result=result,
        comparison=InsightComparison.model_validate(row.comparison) if row.comparison else None,
        reason=row.reason, provider=row.provider, model=row.model, created_at=row.created_at,
        finished_at=row.finished_at, latency_ms=row.latency_ms)

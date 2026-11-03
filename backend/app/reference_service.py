"""Owner-safe reference resolution and mutation shared with future source-record APIs.

Resolve with get_exercise/get_food, then copy needed values into an immutable source
snapshot within the same transaction. Never resolve a client reference via Session.get:
that bypasses both ownership and soft-deletion checks. Reads do not commit transactions.
"""

from typing import TypeVar
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import Exercise, ExerciseMuscle, Food, MuscleGroup
from app.reference_schemas import ExerciseInput, FoodInput

Reference = TypeVar("Reference", Exercise, Food)


def normalize_name(name: str) -> str:
    return " ".join(name.split()).casefold()


def visible_references(model: type[Reference], user_id: str):
    """A scoped SELECT suitable for listing and source-record reference resolution."""
    return select(model).where(model.deleted_at.is_(None), or_(model.owner_id.is_(None), model.owner_id == user_id))


def _get_reference(db: Session, model: type[Reference], user_id: str, reference_id: str, *, for_update: bool) -> Reference:
    try:
        reference_id = str(UUID(reference_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=404, detail="Reference not found") from None
    statement = visible_references(model, user_id).where(model.id == reference_id)
    if model is Exercise:
        statement = statement.options(selectinload(Exercise.muscles))
    if for_update:
        statement = statement.with_for_update()
    record = db.scalar(statement)
    if record is None:
        raise HTTPException(status_code=404, detail="Reference not found")
    return record


def get_exercise(db: Session, user_id: str, exercise_id: str, *, for_update: bool = False) -> Exercise:
    return _get_reference(db, Exercise, user_id, exercise_id, for_update=for_update)


def get_food(db: Session, user_id: str, food_id: str, *, for_update: bool = False) -> Food:
    return _get_reference(db, Food, user_id, food_id, for_update=for_update)


def require_custom_owner(record: Exercise | Food, user_id: str) -> None:
    if record.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Global references cannot be changed through athlete routes")


def apply_exercise(db: Session, record: Exercise, payload: ExerciseInput) -> None:
    """Apply validated values without committing; does not change ownership/seed identity."""
    muscle_ids = {muscle.muscle_id for muscle in payload.muscles}
    known = set(db.scalars(select(MuscleGroup.id).where(MuscleGroup.id.in_(muscle_ids))))
    if known != muscle_ids:
        raise HTTPException(status_code=422, detail="Every muscle_id must identify an existing muscle group")
    for key, value in payload.model_dump(exclude={"muscles"}).items():
        setattr(record, key, value)
    record.name_key = normalize_name(payload.name)
    # Reuse mapped rows to avoid insert-before-delete primary-key conflicts on PUT.
    previous = {muscle.muscle_id: muscle for muscle in record.muscles}
    mappings = []
    for muscle in payload.muscles:
        mapping = previous.get(muscle.muscle_id)
        if mapping is None:
            mapping = ExerciseMuscle(muscle_id=muscle.muscle_id)
        mapping.contribution = muscle.contribution
        mappings.append(mapping)
    record.muscles = mappings


def apply_food(record: Food, payload: FoodInput) -> None:
    """Apply validated per-100g nutrients without changing owner or seed identity."""
    for key, value in payload.model_dump().items():
        setattr(record, key, value)
    record.name_key = normalize_name(payload.name)
    record.basis_grams = 100


def commit_reference(db: Session, record: Exercise | Food) -> None:
    """Translate a race on the database-enforced owner/name key into a stable 409."""
    model = type(record)
    owner_id, name_key, record_id = record.owner_id, record.name_key, record.id
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate = db.scalar(select(model.id).where(model.owner_id == owner_id, model.name_key == name_key))
        if duplicate is not None and duplicate != record_id:
            raise HTTPException(status_code=409, detail="A reference with this name already exists, including deleted references") from None
        raise

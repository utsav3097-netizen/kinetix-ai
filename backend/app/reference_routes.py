"""Onboarded athlete reference libraries; only owner custom records are mutable."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.auth import Database, prevent_caching
from app.models import Exercise, ExerciseMuscle, Food, MuscleGroup
from app.models.identity import utc_now
from app.profile import CompletedProfile
from app.reference_schemas import (
    ExerciseInput, ExercisePage, ExerciseQuery, ExerciseResponse, FoodInput, FoodPage,
    FoodResponse, MuscleGroupResponse, ReferenceQuery,
)
from app.reference_service import (
    apply_exercise, apply_food, commit_reference, get_exercise, get_food,
    normalize_name, require_custom_owner, visible_references,
)

exercise_router = APIRouter(prefix="/api/v1/exercises", tags=["exercises"], dependencies=[Depends(prevent_caching)])
food_router = APIRouter(prefix="/api/v1/nutrition/foods", tags=["foods"], dependencies=[Depends(prevent_caching)])


@exercise_router.get("/muscles", response_model=list[MuscleGroupResponse])
def list_muscles(profile: CompletedProfile, db: Database):
    return db.scalars(select(MuscleGroup).order_by(MuscleGroup.name)).all()


@exercise_router.get("", response_model=ExercisePage)
def list_exercises(profile: CompletedProfile, db: Database, query: Annotated[ExerciseQuery, Query()]):
    statement = visible_references(Exercise, profile.user_id)
    if query.q:
        statement = statement.where(Exercise.name_key.contains(normalize_name(query.q), autoescape=True))
    if query.equipment:
        statement = statement.where(func.lower(Exercise.equipment) == query.equipment.lower())
    if query.muscle:
        statement = statement.where(Exercise.muscles.any(ExerciseMuscle.muscle_id == query.muscle))
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    items = db.scalars(statement.options(selectinload(Exercise.muscles)).order_by(Exercise.name_key, Exercise.id)
                       .offset(query.offset).limit(query.limit)).all()
    return {"items": items, "total": total}


@exercise_router.post("", response_model=ExerciseResponse, status_code=201)
def create_exercise(payload: ExerciseInput, profile: CompletedProfile, db: Database):
    record = Exercise(owner_id=profile.user_id)
    apply_exercise(db, record, payload)
    db.add(record)
    commit_reference(db, record)
    return record


@exercise_router.get("/{exercise_id}", response_model=ExerciseResponse)
def read_exercise(exercise_id: str, profile: CompletedProfile, db: Database):
    return get_exercise(db, profile.user_id, exercise_id)


@exercise_router.put("/{exercise_id}", response_model=ExerciseResponse)
def update_exercise(exercise_id: str, payload: ExerciseInput, profile: CompletedProfile, db: Database):
    record = get_exercise(db, profile.user_id, exercise_id, for_update=True)
    require_custom_owner(record, profile.user_id)
    apply_exercise(db, record, payload)
    commit_reference(db, record)
    return record


@exercise_router.delete("/{exercise_id}", status_code=204)
def delete_exercise(exercise_id: str, profile: CompletedProfile, db: Database):
    record = get_exercise(db, profile.user_id, exercise_id, for_update=True)
    require_custom_owner(record, profile.user_id)
    record.deleted_at = utc_now()
    db.commit()
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@food_router.get("", response_model=FoodPage)
def list_foods(profile: CompletedProfile, db: Database, query: Annotated[ReferenceQuery, Query()]):
    statement = visible_references(Food, profile.user_id)
    if query.q:
        statement = statement.where(Food.name_key.contains(normalize_name(query.q), autoescape=True))
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    items = db.scalars(statement.order_by(Food.name_key, Food.id).offset(query.offset).limit(query.limit)).all()
    return {"items": items, "total": total}


@food_router.post("", response_model=FoodResponse, status_code=201)
def create_food(payload: FoodInput, profile: CompletedProfile, db: Database):
    record = Food(owner_id=profile.user_id)
    apply_food(record, payload)
    db.add(record)
    commit_reference(db, record)
    return record


@food_router.get("/{food_id}", response_model=FoodResponse)
def read_food(food_id: str, profile: CompletedProfile, db: Database):
    return get_food(db, profile.user_id, food_id)


@food_router.put("/{food_id}", response_model=FoodResponse)
def update_food(food_id: str, payload: FoodInput, profile: CompletedProfile, db: Database):
    record = get_food(db, profile.user_id, food_id, for_update=True)
    require_custom_owner(record, profile.user_id)
    apply_food(record, payload)
    commit_reference(db, record)
    return record


@food_router.delete("/{food_id}", status_code=204)
def delete_food(food_id: str, profile: CompletedProfile, db: Database):
    record = get_food(db, profile.user_id, food_id, for_update=True)
    require_custom_owner(record, profile.user_id)
    record.deleted_at = utc_now()
    db.commit()
    return Response(status_code=204, headers={"Cache-Control": "no-store"})

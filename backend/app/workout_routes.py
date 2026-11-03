"""Authenticated workout transport; commands remain reusable outside HTTP."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.auth import Database, prevent_caching
from app.profile import CompletedProfile
from app.services import workouts
from app.workout_schemas import (
    BlockCreate, BlockInput, ExerciseHistoryPage, PageQuery, SessionInput, SessionPage,
    SessionQuery, SessionView, SetInput, SourcePage, WorkoutAnalytics,
)

router = APIRouter(prefix="/api/v1/workouts", tags=["workouts"], dependencies=[Depends(prevent_caching)])


def _saved(db, session):
    # Render while the command's session lock is held, then commit one atomic
    # source/projection transaction. A response never mixes concurrent revisions.
    result = workouts.session_view(db, session)
    db.commit()
    return result


def _deleted(db):
    db.commit()
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("", response_model=SessionPage)
def list_workouts(profile: CompletedProfile, db: Database, query: Annotated[SessionQuery, Query()]):
    return workouts.list_sessions(db, profile.user_id, query)


@router.post("", response_model=SessionView, status_code=201)
def create_workout(payload: SessionInput, profile: CompletedProfile, db: Database):
    return _saved(db, workouts.create_session(db, profile.user_id, payload))


@router.get("/analytics", response_model=WorkoutAnalytics)
def workout_analytics(profile: CompletedProfile, db: Database, weeks: Annotated[int, Query(ge=1, le=4)] = 1):
    return workouts.analytics(db, profile.user_id, weeks)


@router.get("/exercise-history/{exercise_id}", response_model=ExerciseHistoryPage)
def exercise_history(exercise_id: str, profile: CompletedProfile, db: Database, query: Annotated[PageQuery, Query()]):
    return workouts.exercise_history(db, profile.user_id, exercise_id, query)


@router.get("/{session_id}", response_model=SessionView)
def read_workout(session_id: str, profile: CompletedProfile, db: Database):
    return workouts.session_view(db, workouts.get_session(db, profile.user_id, session_id))


@router.put("/{session_id}", response_model=SessionView)
def update_workout(session_id: str, payload: SessionInput, profile: CompletedProfile, db: Database):
    return _saved(db, workouts.update_session(db, profile.user_id, session_id, payload))


@router.delete("/{session_id}", status_code=204)
def delete_workout(session_id: str, profile: CompletedProfile, db: Database):
    workouts.delete_session(db, profile.user_id, session_id)
    return _deleted(db)


@router.get("/{session_id}/history", response_model=SourcePage)
def source_history(session_id: str, profile: CompletedProfile, db: Database, query: Annotated[PageQuery, Query()]):
    return workouts.source_history(db, profile.user_id, session_id, query)


@router.post("/{session_id}/exercises", response_model=SessionView, status_code=201)
def create_exercise(session_id: str, payload: BlockCreate, profile: CompletedProfile, db: Database):
    return _saved(db, workouts.create_block(db, profile.user_id, session_id, payload))


@router.put("/{session_id}/exercises/{block_id}", response_model=SessionView)
def update_exercise(session_id: str, block_id: str, payload: BlockInput, profile: CompletedProfile, db: Database):
    return _saved(db, workouts.update_block(db, profile.user_id, session_id, block_id, payload))


@router.delete("/{session_id}/exercises/{block_id}", status_code=204)
def delete_exercise(session_id: str, block_id: str, profile: CompletedProfile, db: Database):
    workouts.delete_block(db, profile.user_id, session_id, block_id)
    return _deleted(db)


@router.post("/{session_id}/exercises/{block_id}/complete", response_model=SessionView)
def complete_exercise(session_id: str, block_id: str, profile: CompletedProfile, db: Database):
    return _saved(db, workouts.complete_block(db, profile.user_id, session_id, block_id))


@router.post("/{session_id}/exercises/{block_id}/sets", response_model=SessionView, status_code=201)
def create_set(session_id: str, block_id: str, payload: SetInput, profile: CompletedProfile, db: Database):
    return _saved(db, workouts.create_set(db, profile.user_id, session_id, block_id, payload))


@router.put("/{session_id}/exercises/{block_id}/sets/{set_id}", response_model=SessionView)
def update_set(session_id: str, block_id: str, set_id: str, payload: SetInput, profile: CompletedProfile, db: Database):
    return _saved(db, workouts.update_set(db, profile.user_id, session_id, block_id, set_id, payload))


@router.delete("/{session_id}/exercises/{block_id}/sets/{set_id}", status_code=204)
def delete_set(session_id: str, block_id: str, set_id: str, profile: CompletedProfile, db: Database):
    workouts.delete_set(db, profile.user_id, session_id, block_id, set_id)
    return _deleted(db)

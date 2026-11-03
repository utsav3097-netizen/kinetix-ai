"""Owner-scoped AI requests; logging and meal persistence remain separate commands."""
from fastapi import APIRouter, Depends

from app.ai_schemas import InsightView, MealParseInput
from app.auth import Database, prevent_caching
from app.profile import CompletedProfile
from app.services import workouts
from app.services.ai.jobs import enqueue_meal, get_insight, insight_view

router = APIRouter(prefix="/api/v1", tags=["AI insights"], dependencies=[Depends(prevent_caching)])


def _saved(db, row):
    result = insight_view(row)
    db.commit()
    return result


@router.get("/workouts/insights/{insight_id}", response_model=InsightView)
def workout_insight(insight_id: str, profile: CompletedProfile, db: Database):
    return insight_view(get_insight(db, profile.user_id, insight_id, ("set", "exercise_block")))


@router.get("/nutrition/insights/{insight_id}", response_model=InsightView)
def nutrition_insight(insight_id: str, profile: CompletedProfile, db: Database):
    return insight_view(get_insight(db, profile.user_id, insight_id, ("meal_parse",)))


@router.post("/workouts/{session_id}/exercises/{block_id}/sets/{set_id}/analyze", response_model=InsightView, status_code=202)
def analyze_set(session_id: str, block_id: str, set_id: str, profile: CompletedProfile, db: Database):
    return _saved(db, workouts.analyze_set(db, profile.user_id, session_id, block_id, set_id))


@router.post("/workouts/{session_id}/exercises/{block_id}/analyze", response_model=InsightView, status_code=202)
def analyze_block(session_id: str, block_id: str, profile: CompletedProfile, db: Database):
    return _saved(db, workouts.analyze_block(db, profile.user_id, session_id, block_id))


@router.post("/nutrition/parse", response_model=InsightView, status_code=202)
def parse_meal(payload: MealParseInput, profile: CompletedProfile, db: Database):
    return _saved(db, enqueue_meal(db, profile.user_id, payload))

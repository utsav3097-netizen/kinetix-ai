"""Authenticated nutrition transport; commands retain transaction ownership in callers."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.auth import Database, prevent_caching
from app.nutrition_schemas import DayInput, DayView, MealInput, PageQuery, SourcePage, Trends, WaterInput
from app.profile import CompletedProfile
from app.services import nutrition

router = APIRouter(prefix="/api/v1/nutrition", tags=["nutrition"], dependencies=[Depends(prevent_caching)])


def _saved(db, day):
    result = nutrition.day_view(db, day)
    db.commit()
    return result


def _deleted(db):
    db.commit()
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/days/{on_date}", response_model=DayView)
def read_day(on_date: date, profile: CompletedProfile, db: Database):
    return nutrition.read_day(db, profile.user_id, on_date)


@router.put("/days/{on_date}", response_model=DayView)
def update_day(on_date: date, payload: DayInput, profile: CompletedProfile, db: Database):
    return _saved(db, nutrition.update_day(db, profile.user_id, on_date, payload))


@router.post("/days/{on_date}/meals", response_model=DayView, status_code=201)
def create_meal(on_date: date, payload: MealInput, profile: CompletedProfile, db: Database):
    return _saved(db, nutrition.create_meal(db, profile.user_id, on_date, payload))


@router.put("/meals/{meal_id}", response_model=DayView)
def update_meal(meal_id: str, payload: MealInput, profile: CompletedProfile, db: Database):
    return _saved(db, nutrition.update_meal(db, profile.user_id, meal_id, payload))


@router.delete("/meals/{meal_id}", status_code=204)
def delete_meal(meal_id: str, profile: CompletedProfile, db: Database):
    nutrition.delete_meal(db, profile.user_id, meal_id)
    return _deleted(db)


@router.post("/days/{on_date}/water", response_model=DayView, status_code=201)
def create_water(on_date: date, payload: WaterInput, profile: CompletedProfile, db: Database):
    return _saved(db, nutrition.create_water(db, profile.user_id, on_date, payload))


@router.delete("/water/{water_id}", status_code=204)
def delete_water(water_id: str, profile: CompletedProfile, db: Database):
    nutrition.delete_water(db, profile.user_id, water_id)
    return _deleted(db)


@router.get("/days/{on_date}/history", response_model=SourcePage)
def source_history(on_date: date, profile: CompletedProfile, db: Database, query: Annotated[PageQuery, Query()]):
    return nutrition.source_history(db, profile.user_id, on_date, query)


@router.get("/trends", response_model=Trends)
def trends(profile: CompletedProfile, db: Database,
           weeks: Annotated[int | None, Query(ge=1, le=4)] = None, end_date: date | None = None):
    return nutrition.trends(db, profile.user_id, weeks, end_date)

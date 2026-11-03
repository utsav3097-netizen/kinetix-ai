"""Owner-scoped nutrition commands and queries, reusable by confirmed coach actions.

Commands validate, lock, append source evidence and flush, but never commit.
The caller owns the transaction, including rollback on a rejected command.
Historical quantity corrections use the original item snapshot; an explicit food
replacement captures today's visible reference. Targets only change on explicit
PUT day, using the saved energy/weight/phase base rather than the current profile.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from math import fsum
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import AthleteProfile, User, WorkoutSession
from app.models.identity import new_id, utc_now
from app.models.nutrition import Meal, MealItem, NutritionDay, NutritionSourceRecord, WaterEntry
from app.nutrition_schemas import DayInput, FoodSnapshot, ItemView, MealInput, Nutrients, PageQuery, WaterInput, WaterView
from app.reference_service import get_food
from app.services.fitness_algorithms import EnergyInput, MacroInput, MacroTargets, ProteinRange, calculate_energy, phase_macros, protein_adherence_range
from app.services.nutrition_algorithms import NUTRIENT_KEYS, calculate_adherence, scale_snapshot, sum_nutrients


def validate_date(value: date) -> date:
    if value > utc_now().date():
        raise HTTPException(422, "Nutrition dates cannot be in the future")
    return value


def _uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, "Nutrition record not found") from None


def _profile(db: Session, owner_id: str) -> AthleteProfile:
    profile = db.scalar(select(AthleteProfile).where(AthleteProfile.user_id == owner_id))
    if profile is None:
        raise HTTPException(403, "Complete your athlete profile first")
    return profile


def _macros(weight: float, tdee: float, phase: str, training_day: bool) -> dict:
    try:
        return phase_macros(MacroInput(weight_kg=weight, tdee_kcal=tdee, phase=phase, training_day=training_day)).model_dump()
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


def _provisional(db: Session, owner_id: str, on_date: date, training_day: bool | None = None) -> NutritionDay:
    # Local import keeps planning's reusable baseline macro helper acyclic.
    from app.services.plans import active_day
    planned = active_day(db, owner_id, on_date)
    if planned is not None:
        selected = planned["day"]["training_day"] if training_day is None else training_day
        baseline = planned["baseline"]
        return NutritionDay(
            owner_id=owner_id, date=on_date, training_day=selected,
            bodyweight_kg=baseline["bodyweight_kg"], tdee_kcal=baseline["tdee_kcal"], phase=baseline["phase"],
            profile_snapshot={"plan_version_id": planned["version_id"], "plan_target_pair": planned["target_pair"]},
            targets=deepcopy(planned["target_pair"][str(selected).lower()]),
            protein_range_g=protein_adherence_range(baseline["bodyweight_kg"]).model_dump(), revision=0,
        )
    profile = _profile(db, owner_id)
    if training_day is None:
        training_day = db.scalar(select(WorkoutSession.id).where(
            WorkoutSession.owner_id == owner_id, WorkoutSession.performed_on == on_date,
            WorkoutSession.deleted_at.is_(None),
        ).limit(1)) is not None
    inputs = EnergyInput(weight_kg=profile.current_weight_kg, height_cm=profile.height_cm,
                         age=profile.age, biological_sex=profile.biological_sex,
                         activity_multiplier=profile.activity_multiplier)
    try:
        energy = calculate_energy(inputs)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return NutritionDay(
        owner_id=owner_id, date=on_date, training_day=training_day,
        bodyweight_kg=profile.current_weight_kg, tdee_kcal=energy.tdee_kcal, phase=profile.phase,
        profile_snapshot=inputs.model_dump(),
        targets=_macros(profile.current_weight_kg, energy.tdee_kcal, profile.phase, training_day),
        protein_range_g=protein_adherence_range(profile.current_weight_kg).model_dump(), revision=0,
    )


def _day(db: Session, owner_id: str, on_date: date, *, lock: bool = False) -> NutritionDay | None:
    validate_date(on_date)
    conditions = (NutritionDay.owner_id == owner_id, NutritionDay.date == on_date)
    if lock:
        # Also serialize first writes, when no day row exists yet. SQLite's
        # no-op UPDATE takes its write lock before reading current projections.
        if db.get_bind().dialect.name == "sqlite":
            db.execute(update(NutritionDay).where(*conditions).values(revision=NutritionDay.revision)
                       .execution_options(synchronize_session=False))
        else:
            db.scalar(select(User.id).where(User.id == owner_id).with_for_update())
    statement = select(NutritionDay).where(*conditions)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return db.scalar(statement)


def _append(db: Session, day: NutritionDay, entity_type: str, entity_id: str, action: str, payload: dict) -> str:
    day.revision += 1
    record = NutritionSourceRecord(id=new_id(), owner_id=day.owner_id, day_id=day.id, date=day.date,
                                   revision=day.revision, entity_type=entity_type, entity_id=entity_id,
                                   action=action, payload=deepcopy(payload))
    db.add(record)
    db.flush()
    return record.id


def _day_payload(day: NutritionDay) -> dict:
    return {"id": day.id, "date": day.date.isoformat(), "training_day": day.training_day,
            "bodyweight_kg": day.bodyweight_kg, "tdee_kcal": day.tdee_kcal, "phase": day.phase,
            "profile_snapshot": day.profile_snapshot, "targets": day.targets, "protein_range_g": day.protein_range_g}


def _create_day(db: Session, owner_id: str, on_date: date, training_day: bool) -> NutritionDay:
    day = _provisional(db, owner_id, on_date, training_day)
    db.add(day)
    db.flush()
    _append(db, day, "day", day.id, "create", _day_payload(day))
    return day


def _write_day(db: Session, owner_id: str, on_date: date, training_day: bool) -> NutritionDay:
    day = _day(db, owner_id, on_date, lock=True)
    if day is None:
        return _create_day(db, owner_id, on_date, training_day)
    if day.training_day != training_day:
        raise HTTPException(409, "Update the saved day type before logging with a different training_day")
    return day


def update_day(db: Session, owner_id: str, on_date: date, payload: DayInput) -> NutritionDay:
    day = _day(db, owner_id, on_date, lock=True)
    if day is None:
        return _create_day(db, owner_id, on_date, payload.training_day)
    day.training_day = payload.training_day
    pair = day.profile_snapshot.get("plan_target_pair")
    day.targets = deepcopy(pair[str(day.training_day).lower()]) if pair else _macros(day.bodyweight_kg, day.tdee_kcal, day.phase, day.training_day)
    _append(db, day, "day", day.id, "update", _day_payload(day))
    return day


def _items(db: Session, owner_id: str, meal_id: str) -> list[MealItem]:
    return list(db.scalars(select(MealItem).where(MealItem.owner_id == owner_id, MealItem.meal_id == meal_id,
                                                MealItem.deleted_at.is_(None)).order_by(MealItem.ordinal)))


def _prepare_items(db: Session, owner_id: str, payload: MealInput, previous: list[MealItem]) -> list[dict]:
    existing = {row.id: row for row in previous}
    prepared = []
    for item in payload.items:
        old = existing.get(item.item_id) if item.item_id else None
        if item.item_id is not None and old is None:
            raise HTTPException(404, "Meal item not found in this meal")
        if old is not None and old.food_id == item.food_id:
            snapshot = deepcopy(old.food_snapshot)
        else:
            food = get_food(db, owner_id, item.food_id, for_update=True)
            snapshot = FoodSnapshot.model_validate(food, from_attributes=True).model_dump()
        prepared.append({"id": old.id if old else new_id(), "food_id": item.food_id, "grams": item.grams,
                         "food_snapshot": snapshot, "nutrients": scale_snapshot(snapshot, item.grams)})
    return prepared


def _meal_payload(day: NutritionDay, meal_id: str, payload: MealInput, items: list[dict]) -> dict:
    return {"id": meal_id, "date": day.date.isoformat(), "slot": payload.slot, "title": payload.title,
            "time": payload.time, "items": items, "totals": sum_nutrients([item["nutrients"] for item in items])}


def create_meal(db: Session, owner_id: str, on_date: date, payload: MealInput) -> NutritionDay:
    day = _write_day(db, owner_id, on_date, payload.training_day)
    items = _prepare_items(db, owner_id, payload, [])
    meal_id = new_id()
    source_id = _append(db, day, "meal", meal_id, "create", _meal_payload(day, meal_id, payload, items))
    meal = Meal(id=meal_id, owner_id=owner_id, day_id=day.id, slot=payload.slot,
                title=payload.title, time=payload.time, source_record_id=source_id)
    db.add(meal)
    db.flush()
    for ordinal, item in enumerate(items):
        db.add(MealItem(owner_id=owner_id, meal_id=meal_id, ordinal=ordinal, **item))
    db.flush()
    return day


def _entity_day(db: Session, owner_id: str, entity_id: str, model) -> tuple[NutritionDay, Meal | WaterEntry]:
    entity_id = _uuid(entity_id)
    on_date = db.scalar(select(NutritionDay.date).join(model, model.day_id == NutritionDay.id).where(
        NutritionDay.owner_id == owner_id, model.owner_id == owner_id, model.id == entity_id,
        model.deleted_at.is_(None),
    ))
    if on_date is None:
        raise HTTPException(404, "Nutrition record not found")
    day = _day(db, owner_id, on_date, lock=True)
    # Re-read after taking the day lock: a competing command may have deleted it.
    entity = db.scalar(select(model).where(model.id == entity_id, model.owner_id == owner_id,
                       model.day_id == day.id, model.deleted_at.is_(None)).execution_options(populate_existing=True))
    if entity is None:
        raise HTTPException(404, "Nutrition record not found")
    return day, entity


def update_meal(db: Session, owner_id: str, meal_id: str, payload: MealInput) -> NutritionDay:
    day, meal = _entity_day(db, owner_id, meal_id, Meal)
    if day.training_day != payload.training_day:
        raise HTTPException(409, "Update the saved day type before logging with a different training_day")
    previous = _items(db, owner_id, meal.id)
    prepared = _prepare_items(db, owner_id, payload, previous)
    source_id = _append(db, day, "meal", meal.id, "update", _meal_payload(day, meal.id, payload, prepared))
    meal.slot, meal.title, meal.time, meal.source_record_id = payload.slot, payload.title, payload.time, source_id
    existing = {row.id: row for row in previous}
    retained = {item["id"] for item in prepared}
    for row in previous:
        if row.id not in retained:
            row.deleted_at = utc_now()
    for ordinal, item in enumerate(prepared):
        row = existing.get(item["id"])
        if row is None:
            db.add(MealItem(owner_id=owner_id, meal_id=meal.id, ordinal=ordinal, **item))
        else:
            row.ordinal = ordinal
            for key, value in item.items():
                setattr(row, key, value)
    db.flush()
    return day


def _meal_view(day: NutritionDay, meal: Meal, items: list[MealItem]) -> dict:
    views = [ItemView.model_validate(item).model_dump(mode="json") for item in items]
    return {"id": meal.id, "date": day.date.isoformat(), "slot": meal.slot, "title": meal.title, "time": meal.time,
            "items": views, "totals": sum_nutrients([item["nutrients"] for item in views]),
            "source_record_id": meal.source_record_id}


def delete_meal(db: Session, owner_id: str, meal_id: str) -> None:
    day, meal = _entity_day(db, owner_id, meal_id, Meal)
    items = _items(db, owner_id, meal.id)
    source_id = _append(db, day, "meal", meal.id, "delete", _meal_view(day, meal, items))
    meal.source_record_id = source_id
    meal.deleted_at = utc_now()
    for item in items:
        item.deleted_at = meal.deleted_at
    db.flush()


def create_water(db: Session, owner_id: str, on_date: date, payload: WaterInput) -> NutritionDay:
    day = _write_day(db, owner_id, on_date, payload.training_day)
    total = db.scalar(select(func.coalesce(func.sum(WaterEntry.amount_ml), 0)).where(
        WaterEntry.owner_id == owner_id, WaterEntry.day_id == day.id, WaterEntry.deleted_at.is_(None)))
    if total + payload.amount_ml > 20000:
        raise HTTPException(422, "Recorded water cannot exceed 20000 ml per day")
    row = WaterEntry(id=new_id(), owner_id=owner_id, day_id=day.id, amount_ml=payload.amount_ml, created_at=utc_now())
    _append(db, day, "water", row.id, "create", WaterView.model_validate(row).model_dump(mode="json"))
    db.add(row)
    db.flush()
    return day


def delete_water(db: Session, owner_id: str, water_id: str) -> None:
    day, row = _entity_day(db, owner_id, water_id, WaterEntry)
    _append(db, day, "water", row.id, "delete", WaterView.model_validate(row).model_dump(mode="json"))
    row.deleted_at = utc_now()
    db.flush()


def _load_entries(db: Session, owner_id: str, days: list[NutritionDay]) -> tuple[dict, dict, dict]:
    ids = [day.id for day in days if day.id is not None]
    meals, items, water = defaultdict(list), defaultdict(list), defaultdict(list)
    if not ids:
        return meals, items, water
    rows = list(db.scalars(select(Meal).where(Meal.owner_id == owner_id, Meal.day_id.in_(ids),
                        Meal.deleted_at.is_(None)).order_by(Meal.time, Meal.id)))
    for meal in rows:
        meals[meal.day_id].append(meal)
    if rows:
        for item in db.scalars(select(MealItem).where(MealItem.owner_id == owner_id,
                MealItem.meal_id.in_([meal.id for meal in rows]), MealItem.deleted_at.is_(None)).order_by(MealItem.ordinal)):
            items[item.meal_id].append(item)
    for row in db.scalars(select(WaterEntry).where(WaterEntry.owner_id == owner_id, WaterEntry.day_id.in_(ids),
                         WaterEntry.deleted_at.is_(None)).order_by(WaterEntry.created_at, WaterEntry.id)):
        water[row.day_id].append(row)
    return meals, items, water


def _render_day(day: NutritionDay, meals: list[Meal], items: dict, water: list[WaterEntry]) -> dict:
    meal_views = [_meal_view(day, meal, items[meal.id]) for meal in meals]
    totals = sum_nutrients([meal["totals"] for meal in meal_views])
    adherence = calculate_adherence(Nutrients(**totals), MacroTargets(**day.targets), ProteinRange(**day.protein_range_g),
                                   [(meal["time"], meal["totals"]["protein_g"]) for meal in meal_views])
    return {"date": day.date, "training_day": day.training_day, "persisted": day.id is not None,
            "plan_version_id": day.profile_snapshot.get("plan_version_id"),
            "phase": day.phase, "bodyweight_kg": day.bodyweight_kg, "targets": day.targets,
            "protein_range_g": day.protein_range_g, "totals": {**totals, "water_ml": sum(row.amount_ml for row in water)},
            "meals": meal_views, "water_entries": [WaterView.model_validate(row) for row in water],
            "adherence": adherence.model_dump()}


def day_view(db: Session, day: NutritionDay) -> dict:
    meals, items, water = _load_entries(db, day.owner_id, [day])
    return _render_day(day, meals[day.id], items, water[day.id])


def read_day(db: Session, owner_id: str, on_date: date) -> dict:
    day = _day(db, owner_id, on_date)
    return day_view(db, day if day is not None else _provisional(db, owner_id, on_date))


def source_history(db: Session, owner_id: str, on_date: date, query: PageQuery) -> dict:
    validate_date(on_date)
    statement = select(NutritionSourceRecord).where(NutritionSourceRecord.owner_id == owner_id,
                                                  NutritionSourceRecord.date == on_date)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    return {"total": total, "items": list(db.scalars(statement.order_by(NutritionSourceRecord.revision.desc())
            .offset(query.offset).limit(query.limit)))}


def trends(db: Session, owner_id: str, weeks: int | None = None, end_date: date | None = None) -> dict:
    weeks = _profile(db, owner_id).analysis_weeks if weeks is None else weeks
    if isinstance(weeks, bool) or weeks not in (1, 2, 3, 4):
        raise HTTPException(422, "Analysis weeks must be 1, 2, 3, or 4")
    end = validate_date(end_date if end_date is not None else utc_now().date())
    try:
        start = end - timedelta(days=weeks * 7 - 1)
    except OverflowError:
        raise HTTPException(422, "Analysis window precedes the supported calendar") from None
    days = list(db.scalars(select(NutritionDay).where(NutritionDay.owner_id == owner_id,
                        NutritionDay.date >= start, NutritionDay.date <= end)))
    meals, items, water = _load_entries(db, owner_id, days)
    views = {day.date: _render_day(day, meals[day.id], items, water[day.id]) for day in days}
    points, logged = [], []
    for offset in range(weeks * 7):
        on_date = start + timedelta(days=offset)
        view = views.get(on_date)
        has_meals = view is not None and bool(view["meals"])
        if has_meals:
            logged.append(view)
        points.append({"date": on_date, "logged": has_meals,
                       **{key: view["totals"][key] if has_meals else None for key in ("calories_kcal", "protein_g", "carbs_g", "fat_g")},
                       "target_calories_kcal": view["targets"]["calories_kcal"] if has_meals else None,
                       "macro_score": view["adherence"]["macro_score"] if has_meals else None})
    count = len(logged)
    return {"window_start": start, "window_end": end, "logged_days": count, "expected_days": weeks * 7,
            "coverage_percent": count / (weeks * 7) * 100,
            "averages": {key: fsum(view["totals"][key] for view in logged) / count for key in NUTRIENT_KEYS} if count else None,
            "macro_adherence_score": fsum(view["adherence"]["macro_score"] for view in logged) / count if count else None,
            "caloric_drift_kcal": fsum(view["adherence"]["caloric_drift_kcal"] for view in logged) / count if count else None,
            "protein_timing_gap_count": sum(len(view["adherence"]["protein_timing"]["gaps"]) for view in logged),
            "points": points}

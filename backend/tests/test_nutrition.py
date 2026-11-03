"""Nutrition consumer behavior, preserved evidence and ownership boundaries."""
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

PROFILE = {
    "full_name": "Nutrition Athlete", "nickname": "Athlete", "age": 28,
    "biological_sex": "male", "height_cm": 180, "starting_weight_kg": 80,
    "current_weight_kg": 80, "display_unit": "kg", "activity_multiplier": 1.55,
    "phase": "baseline_assessment", "analysis_weeks": 2,
}


def day(days_ago=0):
    return (datetime.now(timezone.utc).date() - timedelta(days=days_ago)).isoformat()


def day_path(days_ago=0):
    return f"/api/v1/nutrition/days/{day(days_ago)}"


def meal_input(foods, **changes):
    return {"training_day": False, "slot": "lunch", "title": "Chicken and rice", "time": "12:00",
            "items": [{"food_id": foods["Chicken breast"], "grams": 200},
                      {"food_id": foods["Cooked rice"], "grams": 100}], **changes}


def edit_input(meal, **changes):
    return {"training_day": False, "slot": meal["slot"], "title": meal["title"], "time": meal["time"],
            "items": [{"item_id": item["id"], "food_id": item["food_id"], "grams": item["grams"]} for item in meal["items"]],
            **changes}


@pytest.fixture
def nutrition(identity):
    from app import nutrition_routes, profile, reference_routes, workout_routes
    from app.seed import seed_reference_data

    identity.app.include_router(profile.router)
    identity.app.include_router(reference_routes.food_router)
    identity.app.include_router(nutrition_routes.router)
    identity.app.include_router(workout_routes.router)
    with identity.sessions.begin() as db:
        seed_reference_data(db)
    with TestClient(identity.app, headers={"Origin": "http://testserver"}) as client:
        owners = []
        for email in ("nutrition.first@example.com", "nutrition.second@example.com"):
            result = client.post("/api/v1/auth/register", json={"email": email, "password": identity.password})
            assert result.status_code == 201
            headers = {"Authorization": "Bearer " + result.json()["access_token"]}
            assert client.put("/api/v1/profile", headers=headers, json=PROFILE).status_code == 200
            owners.append(headers)
        response = client.get("/api/v1/nutrition/foods?limit=100", headers=owners[0])
        assert response.status_code == 200
        foods = {item["name"]: item["id"] for item in response.json()["items"]}
        yield client, owners, foods


def create_meal(client, owner, foods, days_ago=0, **changes):
    response = client.post(day_path(days_ago) + "/meals", headers=owner, json=meal_input(foods, **changes))
    assert response.status_code == 201, response.text
    return response.json()


def test_meal_nutrients_water_and_frozen_snapshots(nutrition, identity):
    from app.models import Food

    client, (owner, _), foods = nutrition
    saved = create_meal(client, owner, foods)
    assert saved["persisted"] is True
    assert saved["protein_range_g"] == {"min": 144, "max": 192}
    assert saved["totals"] == pytest.approx({
        "calories_kcal": 460, "protein_g": 64.7, "carbs_g": 28, "fat_g": 7.5, "fiber_g": .4, "water_ml": 0,
    })
    meal = saved["meals"][0]
    assert meal["items"][0]["nutrients"] == pytest.approx({
        "calories_kcal": 330, "protein_g": 62, "carbs_g": 0, "fat_g": 7.2, "fiber_g": 0,
    })
    response = client.post(day_path() + "/water", headers=owner, json={"training_day": False, "amount_ml": 500})
    assert response.status_code == 201
    assert response.json()["totals"]["water_ml"] == 500
    with identity.sessions.begin() as db:
        food = db.get(Food, foods["Chicken breast"])
        food.name, food.calories, food.protein_g = "Revised chicken", 200, 40
    assert client.put("/api/v1/profile", headers=owner, json={**PROFILE, "phase": "lean_bulking", "age": 35}).status_code == 200
    reloaded = client.get(day_path(), headers=owner).json()
    assert reloaded["meals"] == saved["meals"]
    assert reloaded["targets"] == saved["targets"]
    assert reloaded["phase"] == "baseline_assessment"
    correction = edit_input(meal)
    correction["items"][0]["grams"] = 100
    result = client.put(f"/api/v1/nutrition/meals/{meal['id']}", headers=owner, json=correction)
    assert result.status_code == 200
    corrected = result.json()["meals"][0]
    assert corrected["totals"]["calories_kcal"] == 295
    assert corrected["items"][0]["food_snapshot"]["name"] == "Chicken breast"
    # Omitting item_id explicitly creates a new entry from the current food basis.
    correction["items"][0].pop("item_id")
    result = client.put(f"/api/v1/nutrition/meals/{meal['id']}", headers=owner, json=correction)
    assert result.status_code == 200
    assert result.json()["meals"][0]["totals"]["calories_kcal"] == 330
    assert result.json()["meals"][0]["items"][0]["food_snapshot"]["name"] == "Revised chicken"
    history = client.get(day_path() + "/history?limit=100", headers=owner).json()
    original = next(item for item in history["items"] if item["id"] == meal["source_record_id"])
    assert original["payload"]["items"][0]["food_snapshot"]["calories"] == 165
    assert original["payload"]["totals"]["calories_kcal"] == 460


def test_deleted_food_quantity_correction_and_explicit_replacement(nutrition):
    client, (owner, _), foods = nutrition
    response = client.post("/api/v1/nutrition/foods", headers=owner, json={
        "name": "My protein food", "calories": 100, "protein_g": 25, "carbs_g": 0, "fat_g": 0, "fiber_g": 0,
    })
    assert response.status_code == 201
    food_id = response.json()["id"]
    saved = create_meal(client, owner, foods, items=[{"food_id": food_id, "grams": 100}])
    meal = saved["meals"][0]
    assert client.delete(f"/api/v1/nutrition/foods/{food_id}", headers=owner).status_code == 204
    correction = edit_input(meal)
    correction["items"][0]["grams"] = 200
    response = client.put(f"/api/v1/nutrition/meals/{meal['id']}", headers=owner, json=correction)
    assert response.status_code == 200
    assert response.json()["totals"]["protein_g"] == 50
    assert client.post(day_path() + "/meals", headers=owner, json=meal_input(foods, items=[{"food_id": food_id, "grams": 100}])).status_code == 404
    correction["items"][0]["food_id"] = foods["Cooked rice"]
    response = client.put(f"/api/v1/nutrition/meals/{meal['id']}", headers=owner, json=correction)
    assert response.status_code == 200
    assert response.json()["totals"]["calories_kcal"] == 260
    assert response.json()["meals"][0]["items"][0]["food_snapshot"]["name"] == "Cooked rice"


def test_day_type_recalculates_only_frozen_macro_base(nutrition, identity):
    from app.models import AthleteProfile

    client, (owner, _), foods = nutrition
    assert client.put("/api/v1/profile", headers=owner, json={**PROFILE, "phase": "body_recomposition"}).status_code == 200
    saved = create_meal(client, owner, foods)
    assert saved["targets"]["carb_cycle_factor"] == .9
    assert saved["targets"]["calories_kcal"] == pytest.approx(2628.25)
    user_id = client.get("/api/v1/auth/me", headers=owner).json()["id"]
    with identity.sessions.begin() as db:
        profile = db.get(AthleteProfile, user_id)
        profile.current_weight_kg = 90
        profile.phase = "lean_bulking"
        profile.activity_multiplier = 1.8
    assert client.get(day_path(), headers=owner).json()["targets"] == saved["targets"]
    assert client.post(day_path() + "/water", headers=owner, json={"training_day": True, "amount_ml": 500}).status_code == 409
    assert client.post(day_path() + "/meals", headers=owner, json=meal_input(foods, training_day=True)).status_code == 409
    meal = saved["meals"][0]
    assert client.put(f"/api/v1/nutrition/meals/{meal['id']}", headers=owner, json=edit_input(meal, training_day=True)).status_code == 409
    result = client.put(day_path(), headers=owner, json={"training_day": True})
    assert result.status_code == 200
    changed = result.json()
    assert changed["phase"] == "body_recomposition"
    assert changed["bodyweight_kg"] == 80
    assert changed["targets"]["carb_cycle_factor"] == 1.1
    assert changed["targets"]["calories_kcal"] == pytest.approx(2920.75)
    assert changed["meals"] == saved["meals"]
    history = client.get(day_path() + "/history", headers=owner).json()
    assert history["total"] == 3
    assert history["items"][0]["payload"]["bodyweight_kg"] == 80
    provisional = client.get(day_path(1), headers=owner).json()
    assert provisional["bodyweight_kg"] == 90
    assert provisional["phase"] == "lean_bulking"


def test_get_is_provisional_infers_only_own_workouts_and_does_not_write(nutrition):
    client, (owner, other), _ = nutrition
    response = client.post("/api/v1/workouts", headers=owner, json={
        "title": "Training", "performed_on": day(), "bodyweight_kg": 80,
    })
    assert response.status_code == 201
    view = client.get(day_path(), headers=owner).json()
    assert view["training_day"] is True
    assert view["persisted"] is False
    assert view["adherence"]["macro_score"] is None
    assert view["adherence"]["caloric_drift_kcal"] is None
    assert all(view["adherence"][key]["status"] == "unlogged" for key in ("protein", "calories", "carbs", "fat"))
    assert client.get(day_path() + "/history", headers=owner).json() == {"items": [], "total": 0}
    assert client.get(day_path(), headers=other).json()["training_day"] is False
    # Explicit first-write choice overrides provisional workout inference.
    result = client.put(day_path(), headers=owner, json={"training_day": False})
    assert result.status_code == 200
    assert result.json()["persisted"] is True
    assert result.json()["training_day"] is False
    assert client.get(day_path(), headers=owner).json()["training_day"] is False


@pytest.mark.parametrize("weeks", [1, 2, 3, 4])
def test_selected_windows_keep_missing_and_water_only_days_null(nutrition, weeks):
    client, (owner, _), foods = nutrition
    saved = create_meal(client, owner, foods, days_ago=1)
    create_meal(client, owner, foods, days_ago=28)
    assert client.post(day_path() + "/water", headers=owner, json={"training_day": False, "amount_ml": 500}).status_code == 201
    result = client.get(f"/api/v1/nutrition/trends?weeks={weeks}", headers=owner)
    assert result.status_code == 200
    trend = result.json()
    assert trend["logged_days"] == 1
    assert trend["expected_days"] == len(trend["points"]) == weeks * 7
    assert trend["coverage_percent"] == pytest.approx(100 / (weeks * 7))
    assert trend["window_start"] == day(weeks * 7 - 1)
    assert trend["window_end"] == day()
    assert trend["averages"]["calories_kcal"] == 460
    assert trend["macro_adherence_score"] == saved["adherence"]["macro_score"]
    assert trend["caloric_drift_kcal"] == saved["adherence"]["caloric_drift_kcal"]
    for point in trend["points"]:
        if point["date"] == day(1):
            assert point["logged"] is True
            assert point["calories_kcal"] == 460
            assert point["target_calories_kcal"] == saved["targets"]["calories_kcal"]
        else:
            assert point["logged"] is False
            assert all(value is None for key, value in point.items() if key not in ("date", "logged"))
    assert client.get("/api/v1/nutrition/trends", headers=owner).json()["expected_days"] == 14
    empty = client.get(f"/api/v1/nutrition/trends?weeks=1&end_date={day(40)}", headers=owner).json()
    assert empty["logged_days"] == 0
    assert empty["averages"] is empty["macro_adherence_score"] is empty["caloric_drift_kcal"] is None


def test_trend_averages_each_logged_days_frozen_targets(nutrition):
    client, (owner, _), foods = nutrition
    first = create_meal(client, owner, foods, days_ago=1)
    assert client.put("/api/v1/profile", headers=owner, json={**PROFILE, "phase": "lean_bulking"}).status_code == 200
    second = create_meal(client, owner, foods, items=[{"food_id": foods["Chicken breast"], "grams": 100}])
    trend = client.get("/api/v1/nutrition/trends?weeks=1", headers=owner).json()
    assert trend["logged_days"] == 2
    assert trend["averages"]["calories_kcal"] == 312.5
    assert trend["macro_adherence_score"] == pytest.approx((first["adherence"]["macro_score"] + second["adherence"]["macro_score"]) / 2)
    assert trend["caloric_drift_kcal"] == pytest.approx((first["adherence"]["caloric_drift_kcal"] + second["adherence"]["caloric_drift_kcal"]) / 2)
    assert trend["points"][-2]["target_calories_kcal"] == first["targets"]["calories_kcal"]
    assert trend["points"][-1]["target_calories_kcal"] == second["targets"]["calories_kcal"]


def test_protein_timing_orders_actual_meals_and_flags_only_gaps_over_five_hours(nutrition):
    client, (owner, _), foods = nutrition
    create_meal(client, owner, foods, time="20:01")
    create_meal(client, owner, foods, time="10:00")
    result = create_meal(client, owner, foods, time="15:00")
    assert result["adherence"]["protein_timing"] == {
        "status": "available", "gaps": [{"from_time": "15:00", "to_time": "20:01", "hours": pytest.approx(301 / 60)}],
    }
    trend = client.get("/api/v1/nutrition/trends?weeks=1", headers=owner).json()
    assert trend["protein_timing_gap_count"] == 1


def test_owner_scoping_covers_meals_items_water_foods_history_and_trends(nutrition):
    client, (owner, other), foods = nutrition
    saved = create_meal(client, owner, foods)
    meal = saved["meals"][0]
    response = client.post(day_path() + "/water", headers=owner, json={"training_day": False, "amount_ml": 500})
    water_id = response.json()["water_entries"][0]["id"]
    assert client.put(f"/api/v1/nutrition/meals/{meal['id']}", headers=other, json=edit_input(meal)).status_code == 404
    assert client.delete(f"/api/v1/nutrition/meals/{meal['id']}", headers=other).status_code == 404
    assert client.delete(f"/api/v1/nutrition/water/{water_id}", headers=other).status_code == 404
    assert client.get(day_path(), headers=other).json()["meals"] == []
    assert client.get(day_path() + "/history", headers=other).json()["total"] == 0
    assert client.get("/api/v1/nutrition/trends", headers=other).json()["logged_days"] == 0
    other_meal = create_meal(client, other, foods)["meals"][0]
    foreign_item = edit_input(other_meal)
    foreign_item["items"][0]["item_id"] = meal["items"][0]["id"]
    assert client.put(f"/api/v1/nutrition/meals/{other_meal['id']}", headers=other, json=foreign_item).status_code == 404
    same_owner_other_meal = create_meal(client, owner, foods)["meals"][-1]
    if same_owner_other_meal["id"] == meal["id"]:
        same_owner_other_meal = next(row for row in client.get(day_path(), headers=owner).json()["meals"] if row["id"] != meal["id"])
    own_wrong_item = edit_input(same_owner_other_meal)
    own_wrong_item["items"][0]["item_id"] = meal["items"][0]["id"]
    assert client.put(f"/api/v1/nutrition/meals/{same_owner_other_meal['id']}", headers=owner, json=own_wrong_item).status_code == 404
    private = client.post("/api/v1/nutrition/foods", headers=owner, json={
        "name": "Private food", "calories": 100, "protein_g": 25, "carbs_g": 0, "fat_g": 0, "fiber_g": 0,
    })
    assert private.status_code == 201
    request = meal_input(foods, items=[{"food_id": private.json()["id"], "grams": 100}])
    assert client.post(day_path(1) + "/meals", headers=other, json=request).status_code == 404
    assert client.get(day_path(1), headers=other).json()["persisted"] is False
    assert client.get(day_path(1) + "/history", headers=other).json()["total"] == 0


def test_deletions_retain_immutable_paginated_history(nutrition, identity):
    from app.models import NutritionSourceRecord

    client, (owner, _), foods = nutrition
    saved = create_meal(client, owner, foods)
    meal = saved["meals"][0]
    response = client.post(day_path() + "/water", headers=owner, json={"training_day": False, "amount_ml": 500})
    water_id = response.json()["water_entries"][0]["id"]
    corrected = edit_input(meal, title="Corrected meal")
    corrected["items"] = corrected["items"][:1]
    assert client.put(f"/api/v1/nutrition/meals/{meal['id']}", headers=owner, json=corrected).status_code == 200
    assert client.delete(f"/api/v1/nutrition/meals/{meal['id']}", headers=owner).status_code == 204
    assert client.delete(f"/api/v1/nutrition/water/{water_id}", headers=owner).status_code == 204
    assert client.delete(f"/api/v1/nutrition/meals/{meal['id']}", headers=owner).status_code == 404
    assert client.delete(f"/api/v1/nutrition/water/{water_id}", headers=owner).status_code == 404
    result = client.get(day_path(), headers=owner).json()
    assert result["meals"] == result["water_entries"] == []
    assert result["totals"]["water_ml"] == 0
    assert result["adherence"]["macro_score"] is None
    history = client.get(day_path() + "/history?limit=100", headers=owner).json()
    assert history["total"] == 6
    assert [row["revision"] for row in history["items"]] == [6, 5, 4, 3, 2, 1]
    page = client.get(day_path() + "/history?offset=2&limit=2", headers=owner).json()
    assert page["total"] == 6
    assert page["items"] == history["items"][2:4]
    assert len(history["items"][4]["payload"]["items"]) == 2
    assert len(history["items"][2]["payload"]["items"]) == 1
    for statement in (
        update(NutritionSourceRecord).where(NutritionSourceRecord.id == meal["source_record_id"]).values(action="delete"),
        delete(NutritionSourceRecord).where(NutritionSourceRecord.id == history["items"][0]["id"]),
    ):
        with identity.sessions() as db:
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(statement)
            db.rollback()
    with identity.sessions() as db:
        source = db.get(NutritionSourceRecord, meal["source_record_id"])
        source.action = "delete"
        with pytest.raises(ValueError, match="append-only"):
            db.flush()
        db.rollback()
    assert client.get(day_path() + "/history?limit=100", headers=owner).json() == history


@pytest.mark.parametrize("changes", [
    {"time": "24:00"}, {"time": "1:00"}, {"time": "12:60"}, {"time": "12:00:00"},
    {"title": ""}, {"title": " "}, {"slot": "other"}, {"items": []},
    {"training_day": 1}, {"training_day": "false"}, {"title": "x" * 121},
    {"date": "2020-01-01"},
])
def test_invalid_meal_fields_are_atomic(nutrition, changes):
    client, (owner, _), foods = nutrition
    assert client.post(day_path() + "/meals", headers=owner, json=meal_input(foods, **changes)).status_code == 422
    assert client.get(day_path(), headers=owner).json()["persisted"] is False


@pytest.mark.parametrize("grams", [0, -1, 5000.1, "200", True, None])
def test_invalid_quantities_are_rejected(nutrition, grams):
    client, (owner, _), foods = nutrition
    payload = meal_input(foods, items=[{"food_id": foods["Chicken breast"], "grams": grams}])
    assert client.post(day_path() + "/meals", headers=owner, json=payload).status_code == 422


def test_nonfinite_quantities_are_rejected(nutrition):
    client, (owner, _), foods = nutrition
    content = ('{"training_day":false,"slot":"lunch","title":"Bad","time":"12:00",'
               '"items":[{"food_id":"' + foods["Chicken breast"] + '","grams":1e999}]}')
    assert client.post(day_path() + "/meals", headers={**owner, "Content-Type": "application/json"}, content=content).status_code == 422


@pytest.mark.parametrize("amount", [0, -1, 10001, 1.5, True, "500"])
def test_invalid_water_amounts(nutrition, amount):
    client, (owner, _), _ = nutrition
    assert client.post(day_path() + "/water", headers=owner, json={"training_day": False, "amount_ml": amount}).status_code == 422


def test_water_daily_bound_removal_and_unlogged_adherence(nutrition):
    client, (owner, _), _ = nutrition
    for _ in range(2):
        response = client.post(day_path() + "/water", headers=owner, json={"training_day": False, "amount_ml": 10000})
        assert response.status_code == 201
    saved = response.json()
    assert saved["totals"]["water_ml"] == 20000
    assert saved["adherence"]["macro_score"] is None
    assert client.post(day_path() + "/water", headers=owner, json={"training_day": False, "amount_ml": 1}).status_code == 422
    assert client.get(day_path() + "/history", headers=owner).json()["total"] == 3
    assert client.delete("/api/v1/nutrition/water/" + saved["water_entries"][0]["id"], headers=owner).status_code == 204
    assert client.post(day_path() + "/water", headers=owner, json={"training_day": False, "amount_ml": 500}).json()["totals"]["water_ml"] == 10500


def test_dates_windows_pagination_authentication_and_onboarding(nutrition, identity):
    client, (owner, _), foods = nutrition
    assert client.get(day_path()).status_code == 401
    result = client.post("/api/v1/auth/register", json={"email": "nutrition.incomplete@example.com", "password": identity.password})
    assert result.status_code == 201
    incomplete = {"Authorization": "Bearer " + result.json()["access_token"]}
    assert client.get(day_path(), headers=incomplete).status_code == 403
    for value in (day(-1), "not-a-date", "2025-02-30"):
        path = f"/api/v1/nutrition/days/{value}"
        assert client.get(path, headers=owner).status_code == 422
        assert client.put(path, headers=owner, json={"training_day": False}).status_code == 422
        assert client.post(path + "/meals", headers=owner, json=meal_input(foods)).status_code == 422
        assert client.post(path + "/water", headers=owner, json={"training_day": False, "amount_ml": 500}).status_code == 422
        assert client.get(path + "/history", headers=owner).status_code == 422
    for query in ("weeks=0", "weeks=5", "weeks=1.5", f"end_date={day(-1)}", "end_date=0001-01-01"):
        assert client.get("/api/v1/nutrition/trends?" + query, headers=owner).status_code == 422
    for query in ("limit=0", "limit=101", "offset=-1"):
        assert client.get(day_path() + "/history?" + query, headers=owner).status_code == 422
    assert client.delete("/api/v1/nutrition/meals/not-a-uuid", headers=owner).status_code == 404
    assert client.delete("/api/v1/nutrition/water/" + str(uuid4()), headers=owner).status_code == 404
    saved = create_meal(client, owner, foods)["meals"][0]
    assert client.put("/api/v1/nutrition/meals/" + saved["id"], headers=owner,
                      json=edit_input(saved, date=day(1))).status_code == 422


def test_commands_allow_caller_rollback_without_hidden_commits(nutrition, identity):
    from app.nutrition_schemas import MealInput
    from app.services import nutrition as service

    client, (owner, _), foods = nutrition
    owner_id = client.get("/api/v1/auth/me", headers=owner).json()["id"]
    with identity.sessions() as db:
        saved = service.create_meal(db, owner_id, date.fromisoformat(day()), MealInput(**meal_input(foods)))
        assert service.day_view(db, saved)["totals"]["calories_kcal"] == 460
        db.rollback()
    assert client.get(day_path(), headers=owner).json()["persisted"] is False
    assert client.get(day_path() + "/history", headers=owner).json()["total"] == 0

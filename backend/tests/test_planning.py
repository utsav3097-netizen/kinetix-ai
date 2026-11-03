"""Reports/plans consumer contracts: source bounds, explicit versioning and targets."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

PROFILE = {"full_name": "Plan Athlete", "nickname": "Plan", "age": 28, "biological_sex": "male",
           "height_cm": 180, "starting_weight_kg": 80, "current_weight_kg": 80, "display_unit": "kg",
           "activity_multiplier": 1.55, "phase": "baseline_assessment", "analysis_weeks": 2}


def today():
    return datetime.now(timezone.utc).date()


@pytest.fixture
def planning(identity):
    from app import dashboard_routes, nutrition_routes, planning_routes, profile, reference_routes, workout_routes
    from app.seed import seed_reference_data
    for router in (profile.router, reference_routes.exercise_router, reference_routes.food_router,
                   workout_routes.router, nutrition_routes.router, dashboard_routes.router,
                   planning_routes.report_router, planning_routes.plan_router):
        identity.app.include_router(router)
    with identity.sessions.begin() as db:
        seed_reference_data(db)
    with TestClient(identity.app, headers={"Origin": "http://testserver"}) as client:
        owners = []
        for email in ("plan.first@example.com", "plan.second@example.com"):
            result = client.post("/api/v1/auth/register", json={"email": email, "password": identity.password})
            assert result.status_code == 201
            headers = {"Authorization": "Bearer " + result.json()["access_token"]}
            assert client.put("/api/v1/profile", headers=headers, json=PROFILE).status_code == 200
            owners.append(headers)
        exercises = {row["name"]: row["id"] for row in client.get("/api/v1/exercises?limit=100", headers=owners[0]).json()["items"]}
        foods = {row["name"]: row["id"] for row in client.get("/api/v1/nutrition/foods?limit=100", headers=owners[0]).json()["items"]}
        yield client, owners, exercises, foods


def generate(client, owner, path="recomp", **changes):
    response = client.post("/api/v1/plans/drafts", headers=owner,
                           json={"path": path, "starts_on": today().isoformat(), **changes})
    assert response.status_code == 201, response.text
    return response.json()


def report(client, owner, **changes):
    response = client.post("/api/v1/reports", headers=owner,
                           json={"weeks": 2, "end_date": today().isoformat(), **changes})
    assert response.status_code == 201, response.text
    return response.json()


def accept(client, owner, draft):
    response = client.post(f"/api/v1/plans/drafts/{draft['id']}/accept", headers=owner, json={})
    assert response.status_code == 201, response.text
    return response.json()


def editable(draft):
    return {"title": "Edited targets", "days": [{"date": day["date"], "training_day": day["training_day"], "label": day["label"],
        "protein_g": day["targets"]["protein_g"], "carbs_g": day["targets"]["carbs_g"], "fat_g": day["targets"]["fat_g"],
        "exercises": [{key: exercise[key] for key in ("exercise_id", "sets", "target_min_reps", "target_max_reps",
                      "duration_seconds", "external_load_kg", "rest_seconds")} for exercise in day["exercises"]]}
        for day in draft["data"]["days"]]}


def log_set(client, owner, exercise, on_date, load=10, reps=10):
    session = client.post("/api/v1/workouts", headers=owner, json={"title": "Observed workout", "performed_on": on_date.isoformat(), "bodyweight_kg": 80}).json()
    block = client.post(f"/api/v1/workouts/{session['id']}/exercises", headers=owner,
        json={"exercise_id": exercise, "ordinal": 1, "target_min_reps": 8, "target_max_reps": 10}).json()["exercises"][0]
    base = f"/api/v1/workouts/{session['id']}/exercises/{block['id']}"
    payload = {"ordinal": 1, "set_type": "working", "external_load_kg": load, "repetitions": reps,
               "duration_seconds": None, "rpe": 8, "rir": None, "rest_seconds": 120}
    response = client.post(base + "/sets", headers=owner, json=payload)
    assert response.status_code == 201, response.text
    return base + "/sets/" + response.json()["exercises"][0]["sets"][0]["id"], payload


def test_empty_report_and_conservative_exact_draft(planning):
    client, (owner, _), _, _ = planning
    empty = report(client, owner)
    assert empty["macro_adherence_score"] is None
    assert empty["logged_training_days"] == empty["logged_nutrition_days"] == 0
    assert empty["data"]["strength_curves"] == []
    assert empty["data"]["nutrition"]["expected_days"] == 14
    draft = generate(client, owner)
    assert draft["assessment_required"] is True
    assert len(draft["data"]["days"]) == 7
    for day in draft["data"]["days"]:
        for exercise in day["exercises"]:
            assert exercise["sets"] == 2
            assert exercise["external_load_kg"] == 0
            assert exercise["rest_seconds"] == 120
            assert exercise["observed_velocity_kg_per_week"] is None
            assert exercise["observed_1rm_kg"] is None
            assert exercise["progression"] is None
            assert exercise["duration_seconds"] == (20 if exercise["exercise_snapshot"]["measurement_type"] == "seconds" else None)
    assert client.get("/api/v1/plans/active", headers=owner).json() is None


@pytest.mark.parametrize("path,training_days,phase", [("cutting", 3, "cutting"), ("bulking", 4, "lean_bulking"),
    ("recomp", 3, "body_recomposition"), ("powerbuilding", 4, "baseline_assessment"),
    ("classic_physique", 4, "lean_bulking"), ("athletic_hybrid", 3, "calisthenics_strength")])
def test_paths_phase_formulas_and_real_sample_math(planning, path, training_days, phase):
    from app.services.fitness_algorithms import MacroInput, phase_macros
    client, (owner, _), _, foods = planning
    draft = generate(client, owner, path)
    data = draft["data"]
    assert data["profile_snapshot"]["phase"] == phase
    assert sum(day["training_day"] for day in data["days"]) == training_days
    for day in data["days"]:
        expected = phase_macros(MacroInput(weight_kg=80.0, tdee_kcal=2774.5, phase=phase, training_day=day["training_day"]))
        assert day["targets"] == pytest.approx(expected.model_dump())
        assert len(day["sample_meals"]) == 3
        for nutrient in ("protein_g", "carbs_g", "fat_g"):
            assert day["sample_totals"][nutrient] == pytest.approx(day["targets"][nutrient])
        for meal in day["sample_meals"]:
            for item in meal["items"]:
                assert item["food_id"] in foods.values()
                assert item["grams"] > 0
                assert item["nutrients"]["calories_kcal"] == pytest.approx(item["food_snapshot"]["calories"] * item["grams"] / 100)
                for nutrient in ("protein_g", "carbs_g", "fat_g", "fiber_g"):
                    assert item["nutrients"][nutrient] == pytest.approx(item["food_snapshot"][nutrient] * item["grams"] / 100)
        assert day["sample_totals"]["calories_kcal"] == pytest.approx(sum(meal["totals"]["calories_kcal"] for meal in day["sample_meals"]))


def test_dated_history_uses_existing_progression_and_no_weekly_invention(planning):
    client, (owner, _), exercises, _ = planning
    log_set(client, owner, exercises["Pull-up"], today() - timedelta(days=7))
    log_set(client, owner, exercises["Pull-up"], today())
    draft = generate(client, owner, "athletic_hybrid")
    prescriptions = [exercise for day in draft["data"]["days"] for exercise in day["exercises"] if exercise["exercise_id"] == exercises["Pull-up"]]
    assert len(prescriptions) == 3
    for row in prescriptions:
        assert row["progression"]["state"] == "increase_weight"
        assert row["external_load_kg"] == 12.5
        assert row["effective_load_kg"] == 88.5
        assert row["observed_1rm_kg"] == pytest.approx(86 * (1 + 10 / 30))
        assert row["observed_velocity_kg_per_week"] == 0


def test_report_window_freezes_edits_and_excludes_later_sources(planning, identity):
    from app.models import WeightCheckIn
    client, (owner, _), exercises, foods = planning
    old = today() - timedelta(days=7)
    set_url, payload = log_set(client, owner, exercises["Pull-up"], old)
    log_set(client, owner, exercises["Pull-up"], today(), load=100)
    user_id = client.get("/api/v1/auth/me", headers=owner).json()["id"]
    with identity.sessions.begin() as db:
        db.add(WeightCheckIn(user_id=user_id, measured_on=old, weight_kg=75))
    meal = client.post(f"/api/v1/nutrition/days/{old}/meals", headers=owner, json={"training_day": True,
        "slot": "lunch", "title": "Rice", "time": "12:00", "items": [{"food_id": foods["Cooked rice"], "grams": 100}]}).json()["meals"][0]
    frozen = report(client, owner, weeks=1, end_date=old.isoformat())
    assert frozen["logged_training_days"] == frozen["logged_nutrition_days"] == 1
    assert frozen["data"]["weight_points"] == [{"date": old.isoformat(), "weight_kg": 75}]
    assert len(frozen["data"]["strength_curves"][0]["points"]) == 1
    assert frozen["data"]["total_volume_kg"] == 860
    assert client.put(set_url, headers=owner, json={**payload, "external_load_kg": 20}).status_code == 200
    assert client.delete(f"/api/v1/nutrition/meals/{meal['id']}", headers=owner).status_code == 204
    assert client.get(f"/api/v1/reports/{frozen['id']}", headers=owner).json() == frozen
    revised = report(client, owner, weeks=1, end_date=old.isoformat())
    assert revised["revision"] == 2
    assert revised["data"]["total_volume_kg"] == 960
    assert revised["macro_adherence_score"] is None


@pytest.mark.parametrize("weeks", [1, 2, 3, 4])
def test_request_period_boundary_and_dedup(planning, identity, monkeypatch, weeks):
    from app.models import AthleteProfile
    from app.services import reports
    client, (owner, _), _, _ = planning
    owner_id = client.get("/api/v1/auth/me", headers=owner).json()["id"]
    origin = today() - timedelta(days=weeks * 7)
    with identity.sessions.begin() as db:
        profile = db.get(AthleteProfile, owner_id)
        profile.created_at = datetime.combine(origin, datetime.min.time(), timezone.utc)
        profile.analysis_weeks = weeks
    just_before = datetime.combine(today() - timedelta(days=1), datetime.min.time(), timezone.utc)
    monkeypatch.setattr(reports, "utc_now", lambda: just_before)
    before = client.get("/api/v1/reports", headers=owner).json()
    assert not any(row["kind"] == "analysis" for row in before["items"])
    monkeypatch.setattr(reports, "utc_now", lambda: datetime.now(timezone.utc))
    first = client.get("/api/v1/reports", headers=owner).json()
    second = client.get("/api/v1/reports", headers=owner).json()
    assert first == second
    analysis = next(row for row in first["items"] if row["kind"] == "analysis")
    assert analysis["window_start"] == origin.isoformat()
    assert analysis["window_end"] == (today() - timedelta(days=1)).isoformat()
    assert analysis["expected_days"] == weeks * 7
    assert all(row["window_end"] < today().isoformat() for row in first["items"])


def test_immutable_versions_edits_and_idempotent_accept(planning, identity):
    from app.models import PlanDraft, Report, TrainingPlanVersion
    client, (owner, _), _, _ = planning
    frozen = report(client, owner)
    draft = generate(client, owner)
    version = accept(client, owner, draft)
    assert version["version"] == 1
    assert accept(client, owner, draft)["id"] == version["id"]
    payload = editable(draft)
    payload["days"][0]["carbs_g"] += 25
    edited_response = client.post(f"/api/v1/plans/drafts/{draft['id']}/edit", headers=owner, json=payload)
    assert edited_response.status_code == 201, edited_response.text
    edited = edited_response.json()
    assert edited["based_on_draft_id"] == draft["id"]
    assert edited["parent_version_id"] == version["id"]
    assert client.get(f"/api/v1/plans/drafts/{draft['id']}", headers=owner).json() == draft
    assert client.get("/api/v1/plans/active", headers=owner).json()["id"] == version["id"]
    next_version = accept(client, owner, edited)
    assert next_version["version"] == 2
    assert next_version["data"]["days"][0]["targets"]["calories_kcal"] == pytest.approx(version["data"]["days"][0]["targets"]["calories_kcal"] + 100)
    assert client.get(f"/api/v1/plans/versions/{version['id']}", headers=owner).json() == version
    assert accept(client, owner, draft)["id"] == version["id"]
    assert client.get("/api/v1/plans/active", headers=owner).json()["id"] == next_version["id"]
    for model, record_id in ((Report, frozen["id"]), (PlanDraft, draft["id"]), (TrainingPlanVersion, version["id"])):
        for operation in (update(model).where(model.id == record_id).values(id=model.id), delete(model).where(model.id == record_id)):
            with identity.sessions() as db, pytest.raises(DBAPIError):
                db.execute(operation)
                db.commit()


def test_cross_owner_and_command_validation(planning):
    client, (owner, other), exercises, _ = planning
    frozen = report(client, owner)
    draft = generate(client, owner)
    version = accept(client, owner, draft)
    for url in (f"/api/v1/reports/{frozen['id']}", f"/api/v1/plans/drafts/{draft['id']}", f"/api/v1/plans/versions/{version['id']}"):
        assert client.get(url, headers=other).status_code == 404
        assert client.get(url).status_code == 401
    assert client.post(f"/api/v1/plans/drafts/{draft['id']}/accept", headers=other, json={}).status_code == 404
    assert client.post(f"/api/v1/plans/drafts/{draft['id']}/edit", headers=other, json=editable(draft)).status_code == 404
    assert client.post("/api/v1/plans/drafts", headers=other, json={"path": "cutting", "starts_on": today().isoformat(), "report_id": frozen["id"]}).status_code == 404
    assert client.get("/api/v1/plans/drafts", headers=other).json()["total"] == 0
    bad = editable(draft)
    bad["days"][0]["date"] = (today() + timedelta(days=1)).isoformat()
    assert client.post(f"/api/v1/plans/drafts/{draft['id']}/edit", headers=owner, json=bad).status_code == 422
    bad = editable(draft)
    bad["days"][0]["exercises"][0]["progression"] = {"next_weight_kg": 500}
    assert client.post(f"/api/v1/plans/drafts/{draft['id']}/edit", headers=owner, json=bad).status_code == 422
    bad = editable(draft)
    bad["days"][0]["exercises"][0]["exercise_id"] = exercises["Plank"]
    assert client.post(f"/api/v1/plans/drafts/{draft['id']}/edit", headers=owner, json=bad).status_code == 422
    assert client.post("/api/v1/reports", headers=owner, json={"weeks": 1, "end_date": (today() + timedelta(days=1)).isoformat()}).status_code == 422
    assert client.post("/api/v1/plans/drafts", headers=owner, json={"path": "cutting", "starts_on": (today() - timedelta(days=1)).isoformat()}).status_code == 422


def test_new_days_inherit_exact_targets_old_days_freeze(planning, identity):
    from app.models import AthleteProfile
    client, (owner, other), _, _ = planning
    day_url = f"/api/v1/nutrition/days/{today()}"
    old = client.put(day_url, headers=owner, json={"training_day": False}).json()
    draft = generate(client, owner)
    accept(client, owner, draft)
    assert client.get(day_url, headers=owner).json()["targets"] == old["targets"]
    assert client.get(day_url, headers=owner).json()["plan_version_id"] is None
    second = generate(client, other)
    edited = editable(second)
    edited["days"][0]["carbs_g"] += 20
    response = client.post(f"/api/v1/plans/drafts/{second['id']}/edit", headers=other, json=edited)
    assert response.status_code == 201, response.text
    version = accept(client, other, response.json())
    provisional = client.get(day_url, headers=other).json()
    assert provisional["training_day"] is True
    assert provisional["plan_version_id"] == version["id"]
    assert provisional["targets"] == version["data"]["days"][0]["targets"]
    saved = client.put(day_url, headers=other, json={"training_day": True}).json()
    assert saved["targets"] == provisional["targets"]
    owner_id = client.get("/api/v1/auth/me", headers=other).json()["id"]
    with identity.sessions.begin() as db:
        profile = db.get(AthleteProfile, owner_id)
        profile.current_weight_kg, profile.phase = 90, "cutting"
    switched = client.put(day_url, headers=other, json={"training_day": False}).json()
    assert switched["targets"] == version["data"]["days"][1]["targets"]
    dashboard = client.get("/api/v1/dashboard/targets", headers=other).json()
    assert dashboard["plan_version_id"] == version["id"]
    assert dashboard["macros"] == version["data"]["days"][0]["targets"]


def test_missing_food_prerequisite_never_fabricates_labels(planning, identity):
    from app.models import Food
    client, (owner, _), _, _ = planning
    with identity.sessions.begin() as db:
        for food in db.scalars(select(Food)):
            food.deleted_at = datetime.now(timezone.utc)
    response = client.post("/api/v1/plans/drafts", headers=owner, json={"path": "cutting", "starts_on": today().isoformat()})
    assert response.status_code == 422
    assert "Sample meals" in response.json()["detail"]
    assert client.get("/api/v1/plans/drafts", headers=owner).json()["total"] == 0

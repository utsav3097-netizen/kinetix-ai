"""Catalog isolation, immutable seed identities, and consumer-visible validation."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select


@pytest.fixture
def catalog(identity):
    from app import profile, reference_routes
    from app.seed import seed_reference_data

    identity.app.include_router(profile.router)
    identity.app.include_router(reference_routes.exercise_router)
    identity.app.include_router(reference_routes.food_router)
    with identity.sessions.begin() as db:
        seed_reference_data(db)
    with TestClient(identity.app, headers={"Origin": "http://testserver"}) as client:
        users = []
        for email in ("first@example.com", "second@example.com"):
            response = client.post("/api/v1/auth/register", json={"email": email, "password": identity.password})
            assert response.status_code == 201
            headers = {"Authorization": "Bearer " + response.json()["access_token"]}
            response = client.put("/api/v1/profile", headers=headers, json={
                "full_name": "Athlete", "nickname": "Athlete", "age": 28,
                "biological_sex": "male", "height_cm": 180, "starting_weight_kg": 80,
                "current_weight_kg": 80, "display_unit": "kg", "activity_multiplier": 1.55,
                "phase": "baseline_assessment", "analysis_weeks": 2,
            })
            assert response.status_code == 200
            users.append(headers)
        yield client, users


@pytest.fixture
def custom_payloads():
    return {
        "/api/v1/exercises": {"name": "Private row", "equipment": "Cable", "met": 6,
            "biomechanical_multiplier": 0, "measurement_type": "reps", "classification": "upper_compound",
            "muscles": [{"muscle_id": "lats", "contribution": 1}]},
        "/api/v1/nutrition/foods": {"name": "Private food", "calories": 160,
            "protein_g": 20, "carbs_g": 20, "fat_g": 0, "fiber_g": 0},
    }


@pytest.mark.parametrize("path", ["/api/v1/exercises", "/api/v1/nutrition/foods"])
def test_custom_records_cannot_be_discovered_or_mutated_by_other_owner(catalog, custom_payloads, path):
    client, (owner, other) = catalog
    payload = custom_payloads[path]
    response = client.post(path, headers=owner, json=payload)
    assert response.status_code == 201
    record = response.json()
    assert record["is_custom"] is True
    resource = f"{path}/{record['id']}"
    assert client.get(path + "?q=Private", headers=other).json() == {"items": [], "total": 0}
    for method in ("get", "put", "delete"):
        kwargs = {"json": payload} if method == "put" else {}
        assert getattr(client, method)(resource, headers=other, **kwargs).status_code == 404
    changed = {**payload, "name": payload["name"] + " corrected"}
    assert client.put(resource, headers=owner, json=changed).json()["name"] == changed["name"]
    assert client.get(resource, headers=owner).json()["name"] == changed["name"]
    assert client.delete(resource, headers=owner).status_code == 204
    assert client.get(resource, headers=owner).status_code == 404
    assert client.get(path + "?q=Private", headers=owner).json()["items"] == []


@pytest.mark.parametrize("path", ["/api/v1/exercises", "/api/v1/nutrition/foods"])
def test_global_references_are_read_only_and_names_are_owner_unique(catalog, custom_payloads, path):
    client, (owner, other) = catalog
    global_item = client.get(path + "?limit=1", headers=owner).json()["items"][0]
    resource = f"{path}/{global_item['id']}"
    assert client.get(resource, headers=other).status_code == 200
    assert client.put(resource, headers=owner, json=custom_payloads[path]).status_code == 403
    assert client.delete(resource, headers=owner).status_code == 403
    assert client.post(path, headers=owner, json=custom_payloads[path]).status_code == 201
    duplicate = {**custom_payloads[path], "name": "  " + custom_payloads[path]["name"].upper() + "  "}
    assert client.post(path, headers=owner, json=duplicate).status_code == 409
    assert client.post(path, headers=other, json=duplicate).status_code == 201
    assert client.get(path).status_code == 401
    assert client.get(path + "?limit=101", headers=owner).status_code == 422


def test_catalog_filters_and_invalid_reference_inputs(catalog, custom_payloads):
    client, (owner, _) = catalog
    rows = client.get("/api/v1/exercises?q=pull&muscle=lats&equipment=Pull-up%20bar", headers=owner).json()
    assert [row["name"] for row in rows["items"]] == ["Pull-up"]
    exercise = custom_payloads["/api/v1/exercises"]
    for invalid in ({"biomechanical_multiplier": 1.1}, {"muscles": [{"muscle_id": "unknown", "contribution": 1}]}, {"owner_id": "spoof"}):
        assert client.post("/api/v1/exercises", headers=owner, json={**exercise, **invalid}).status_code == 422
    food = custom_payloads["/api/v1/nutrition/foods"]
    for invalid in ({"fiber_g": 21}, {"protein_g": 90}, {"basis_grams": 50}):
        assert client.post("/api/v1/nutrition/foods", headers=owner, json={**food, **invalid}).status_code == 422


def test_seed_is_idempotent_and_preserves_admin_edits_and_tombstones(identity):
    from app.seed import seed_reference_data, EXERCISES, FOODS, MUSCLES
    from app.models import Exercise, Food, MuscleGroup

    with identity.sessions.begin() as db:
        assert seed_reference_data(db) == {"muscles": len(MUSCLES), "exercises": len(EXERCISES), "foods": len(FOODS)}
        pull = db.scalar(select(Exercise).where(Exercise.seed_key == "pull-up"))
        dip = db.scalar(select(Exercise).where(Exercise.seed_key == "dip"))
        push = db.scalar(select(Exercise).where(Exercise.seed_key == "push-up"))
        assert (pull.biomechanical_multiplier, dip.biomechanical_multiplier, push.biomechanical_multiplier) == (.95, .95, .65)
        pull.name, pull.name_key = "Renamed pull", "renamed pull"
        dip.deleted_at = datetime.now(timezone.utc)
        food = db.scalar(select(Food).where(Food.seed_key == "banana"))
        food.calories = 90
    with identity.sessions.begin() as db:
        assert seed_reference_data(db) == {"muscles": 0, "exercises": 0, "foods": 0}
        assert db.scalar(select(func.count()).select_from(Exercise)) == len(EXERCISES)
        assert db.scalar(select(func.count()).select_from(Food)) == len(FOODS)
        assert db.scalar(select(func.count()).select_from(MuscleGroup)) == len(MUSCLES)
        assert db.scalar(select(Exercise).where(Exercise.seed_key == "pull-up")).name == "Renamed pull"
        assert db.scalar(select(Exercise).where(Exercise.seed_key == "dip")).deleted_at is not None
        assert db.scalar(select(Food).where(Food.seed_key == "banana")).calories == 90


def test_label_energy_is_preserved_without_assuming_digestible_carbs(catalog):
    client, (owner, _) = catalog
    response = client.post("/api/v1/nutrition/foods", headers=owner, json={
        "name": "Sugar-free confectionery", "calories": 240,
        "protein_g": 0, "carbs_g": 100, "fat_g": 0, "fiber_g": 0,
    })
    assert response.status_code == 201
    saved = client.get("/api/v1/nutrition/foods/" + response.json()["id"], headers=owner).json()
    assert saved["calories"] == 240
    assert saved["carbs_g"] == 100

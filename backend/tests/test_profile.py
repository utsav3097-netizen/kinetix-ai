"""Profile tests reuse the migrated, temporary identity database fixtures."""

from datetime import datetime, timezone

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def profile_client(identity, monkeypatch):
    from app import profile

    monkeypatch.setattr(profile, "utc_now", lambda: datetime(2026, 5, 1, 12, tzinfo=timezone.utc))
    identity.app.include_router(profile.router)

    @identity.app.get("/test/planning")
    def planning(athlete=Depends(profile.require_profile)):
        assert isinstance(athlete, identity.models.AthleteProfile)
        return {"user_id": athlete.user_id, "biological_sex": athlete.biological_sex}

    with TestClient(identity.app, headers={"Origin": "http://testserver"}) as client:
        yield client


@pytest.fixture
def profile_data():
    return {
        "full_name": "  Ada Athlete  ",
        "nickname": "  Ada  ",
        "age": 28,
        "biological_sex": "female",
        "height_cm": 170,
        "starting_weight_kg": 75,
        "current_weight_kg": 70,
        "body_fat_percentage": 22,
        "display_unit": "kg",
        "activity_multiplier": 1.6,
        "phase": "baseline_assessment",
        "analysis_weeks": 2,
    }


def register(client, identity, email="athlete@example.com"):
    response = client.post("/api/v1/auth/register", json={"email": email, "password": identity.password})
    assert response.status_code == 201
    data = response.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data["user"]["id"]


@pytest.fixture
def athlete(profile_client, identity):
    return register(profile_client, identity)


def save(client, athlete, data):
    return client.put("/api/v1/profile", headers=athlete[0], json=data)


def history(client, athlete, query=""):
    return client.get(f"/api/v1/profile/check-ins{query}", headers=athlete[0])


def check_in(client, athlete, day, weight):
    return client.post("/api/v1/profile/check-ins", headers=athlete[0], json={"measured_on": day, "weight_kg": weight})


def test_authentication_and_onboarding_gate(profile_client, athlete, profile_data):
    for method, path, payload in (
        ("get", "/api/v1/profile", None),
        ("put", "/api/v1/profile", profile_data),
        ("get", "/api/v1/profile/check-ins", None),
        ("post", "/api/v1/profile/check-ins", {"measured_on": "2026-05-01", "weight_kg": 70}),
        ("get", "/test/planning", None),
    ):
        response = profile_client.request(method, path, json=payload)
        assert response.status_code == 401
    response = profile_client.get("/api/v1/profile", headers=athlete[0])
    assert response.json() == {"onboarding_complete": False, "profile": None}
    assert response.headers["cache-control"] == "no-store"
    for response in (
        history(profile_client, athlete),
        check_in(profile_client, athlete, "2026-05-01", 70),
        profile_client.get("/test/planning", headers=athlete[0]),
    ):
        assert response.status_code == 403
        assert response.json()["detail"] == "Complete onboarding before tracking or planning"
    assert save(profile_client, athlete, profile_data).status_code == 200
    response = profile_client.get("/test/planning", headers=athlete[0])
    assert response.json() == {"user_id": athlete[1], "biological_sex": "female"}


def test_complete_profile_seeds_only_real_current_measurement(profile_client, athlete, profile_data, identity):
    response = save(profile_client, athlete, profile_data)
    assert response.status_code == 200
    data = response.json()
    assert data["onboarding_complete"] is True
    profile = data["profile"]
    assert profile["user_id"] == athlete[1]
    assert profile["full_name"] == "Ada Athlete"
    assert profile["nickname"] == "Ada"
    assert profile["starting_weight_kg"] == 75
    assert profile["current_weight_kg"] == 70
    assert profile["created_at"] and profile["updated_at"]
    assert set(profile) == set(profile_data) | {"user_id", "created_at", "updated_at"}
    items = history(profile_client, athlete).json()
    assert items["total"] == 1
    assert items["items"][0]["measured_on"] == "2026-05-01"
    assert items["items"][0]["weight_kg"] == 70
    assert set(items["items"][0]) == {"id", "measured_on", "weight_kg"}
    assert save(profile_client, athlete, profile_data).status_code == 200
    assert history(profile_client, athlete).json() == items
    with identity.sessions() as db:
        assert db.scalar(select(func.count()).select_from(identity.models.AthleteProfile)) == 1
        assert db.scalar(select(func.count()).select_from(identity.models.WeightCheckIn)) == 1


@pytest.mark.parametrize("field", [
    "full_name", "nickname", "age", "biological_sex", "height_cm", "starting_weight_kg",
    "current_weight_kg", "display_unit", "activity_multiplier", "phase", "analysis_weeks",
])
def test_missing_required_field_never_persists_partial_profile(profile_client, athlete, profile_data, identity, field):
    del profile_data[field]
    assert save(profile_client, athlete, profile_data).status_code == 422
    assert profile_client.get("/api/v1/profile", headers=athlete[0]).json()["onboarding_complete"] is False
    with identity.sessions() as db:
        assert db.scalar(select(func.count()).select_from(identity.models.AthleteProfile)) == 0
        assert db.scalar(select(func.count()).select_from(identity.models.WeightCheckIn)) == 0


@pytest.mark.parametrize(("field", "value"), [
    ("full_name", "   "), ("full_name", "a" * 121), ("nickname", "\t"), ("nickname", "n" * 41),
    ("age", 12), ("age", 101), ("age", 28.0), ("age", "28"), ("age", True),
    ("biological_sex", None), ("biological_sex", "unknown"),
    ("height_cm", 49.99), ("height_cm", 250.01), ("height_cm", "170"), ("height_cm", True),
    ("starting_weight_kg", 19.99), ("starting_weight_kg", 500.01),
    ("current_weight_kg", 19.99), ("current_weight_kg", 500.01), ("current_weight_kg", "70"),
    ("body_fat_percentage", 0.99), ("body_fat_percentage", 75.01), ("body_fat_percentage", False),
    ("display_unit", "stone"), ("activity_multiplier", 1.19), ("activity_multiplier", 2.41),
    ("phase", "bulking"), ("phase", "calisthenics"),
    ("analysis_weeks", 0), ("analysis_weeks", 5), ("analysis_weeks", 1.0), ("analysis_weeks", True), ("analysis_weeks", "2"),
    ("user_id", "00000000-0000-0000-0000-000000000000"), ("role", "admin"),
])
def test_profile_rejects_invalid_fields(profile_client, athlete, profile_data, field, value):
    profile_data[field] = value
    assert save(profile_client, athlete, profile_data).status_code == 422


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("field", ["height_cm", "starting_weight_kg", "current_weight_kg", "body_fat_percentage", "activity_multiplier"])
def test_profile_schema_rejects_nonfinite_numbers(identity, profile_data, field, number):
    from app.profile import ProfileInput
    from pydantic import ValidationError

    profile_data[field] = float(number)
    with pytest.raises(ValidationError):
        ProfileInput.model_validate(profile_data)


@pytest.mark.parametrize("upper", [False, True])
def test_numeric_and_name_boundaries_are_inclusive(profile_client, athlete, profile_data, upper):
    profile_data.update({
        "full_name": "a" * (120 if upper else 1), "nickname": "n" * (40 if upper else 1),
        "age": 100 if upper else 13, "height_cm": 250 if upper else 50,
        "starting_weight_kg": 500 if upper else 20, "current_weight_kg": 500 if upper else 20,
        "body_fat_percentage": 75 if upper else 1, "activity_multiplier": 2.4 if upper else 1.2,
        "analysis_weeks": 4 if upper else 1,
    })
    assert save(profile_client, athlete, profile_data).status_code == 200


@pytest.mark.parametrize("phase", ["baseline_assessment", "cutting", "lean_bulking", "body_recomposition", "calisthenics_strength"])
@pytest.mark.parametrize("weeks", [1, 2, 3, 4])
def test_all_supported_phases_and_windows(profile_client, athlete, profile_data, phase, weeks):
    profile_data.update(phase=phase, analysis_weeks=weeks, biological_sex="male", display_unit="lb")
    del profile_data["body_fat_percentage"]
    response = save(profile_client, athlete, profile_data)
    assert response.status_code == 200
    assert response.json()["profile"]["body_fat_percentage"] is None


def test_failed_profile_edit_is_atomic_and_history_immutable(profile_client, athlete, profile_data):
    before = save(profile_client, athlete, profile_data).json()
    measurements = history(profile_client, athlete).json()
    assert save(profile_client, athlete, {**profile_data, "nickname": "Changed", "age": 12}).status_code == 422
    assert save(profile_client, athlete, {**profile_data, "nickname": "Changed", "current_weight_kg": 71}).status_code == 422
    assert profile_client.get("/api/v1/profile", headers=athlete[0]).json() == before
    assert history(profile_client, athlete).json() == measurements
    assert save(profile_client, athlete, {**profile_data, "nickname": "Changed", "starting_weight_kg": 76}).status_code == 200
    assert history(profile_client, athlete).json() == measurements


def test_only_latest_measured_day_changes_current_weight(profile_client, athlete, profile_data):
    assert save(profile_client, athlete, profile_data).status_code == 200
    assert check_in(profile_client, athlete, "2026-04-29", 74).status_code == 201
    assert profile_client.get("/api/v1/profile", headers=athlete[0]).json()["profile"]["current_weight_kg"] == 70
    assert check_in(profile_client, athlete, "2026-05-03", 69).status_code == 201
    assert check_in(profile_client, athlete, "2026-05-02", 69.5).status_code == 201
    current = profile_client.get("/api/v1/profile", headers=athlete[0]).json()["profile"]
    assert current["current_weight_kg"] == 69
    assert current["starting_weight_kg"] == 75
    assert check_in(profile_client, athlete, "2026-05-03", 65).status_code == 409
    assert check_in(profile_client, athlete, "2026-05-01", 65).status_code == 409
    assert save(profile_client, athlete, profile_data).status_code == 422
    assert save(profile_client, athlete, {**profile_data, "current_weight_kg": 69}).status_code == 200
    page = history(profile_client, athlete, "?offset=1&limit=2").json()
    assert page["total"] == 4
    assert [item["measured_on"] for item in page["items"]] == ["2026-05-02", "2026-05-01"]
    assert history(profile_client, athlete, "?offset=100").json() == {"items": [], "total": 4}


def test_other_owner_cannot_discover_or_mutate_profile_or_history(profile_client, athlete, profile_data, identity):
    save(profile_client, athlete, profile_data)
    first_history = history(profile_client, athlete).json()
    second = register(profile_client, identity, "second@example.com")
    assert profile_client.get("/api/v1/profile", headers=second[0]).json() == {"onboarding_complete": False, "profile": None}
    assert history(profile_client, second).status_code == 403
    assert save(profile_client, second, {**profile_data, "current_weight_kg": 90}).status_code == 200
    assert history(profile_client, second).json()["items"][0]["weight_kg"] == 90
    assert check_in(profile_client, second, "2026-05-02", 89).status_code == 201
    assert history(profile_client, athlete).json() == first_history
    assert history(profile_client, second, f"?user_id={athlete[1]}").status_code == 422
    assert save(profile_client, second, {**profile_data, "user_id": athlete[1]}).status_code == 422
    assert profile_client.post("/api/v1/profile/check-ins", headers=second[0], json={"user_id": athlete[1], "measured_on": "2026-05-03", "weight_kg": 50}).status_code == 422
    assert profile_client.get("/test/planning", headers=second[0]).json()["user_id"] == second[1]


@pytest.mark.parametrize("query", ["?offset=-1", "?limit=0", "?limit=101", "?offset=abc", "?limit=1.5", "?role=admin"])
def test_history_pagination_is_bounded(profile_client, athlete, profile_data, query):
    save(profile_client, athlete, profile_data)
    assert history(profile_client, athlete, query).status_code == 422


@pytest.mark.parametrize(("field", "value"), [
    ("measured_on", "2026-02-30"), ("measured_on", "20260502"), ("measured_on", "2026-05-02T00:00:00Z"),
    ("measured_on", 1777680000), ("measured_on", None), ("weight_kg", 19.99),
    ("weight_kg", 500.01), ("weight_kg", "70"), ("weight_kg", True), ("role", "admin"),
])
def test_check_in_payload_is_strict(profile_client, athlete, profile_data, field, value):
    save(profile_client, athlete, profile_data)
    payload = {"measured_on": "2026-05-02", "weight_kg": 70, field: value}
    assert profile_client.post("/api/v1/profile/check-ins", headers=athlete[0], json=payload).status_code == 422
    assert history(profile_client, athlete).json()["total"] == 1


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_check_in_schema_rejects_nonfinite_weight(identity, number):
    from app.profile import CheckInInput
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CheckInInput.model_validate({"measured_on": "2026-05-02", "weight_kg": number})


def test_migrated_constraints_and_owner_cascades(profile_client, athlete, profile_data, identity):
    save(profile_client, athlete, profile_data)
    with identity.sessions() as db:
        db.add(identity.models.WeightCheckIn(user_id=athlete[1], measured_on=datetime(2026, 5, 1).date(), weight_kg=70))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        profile = db.get(identity.models.AthleteProfile, athlete[1])
        profile.biological_sex = "unknown"
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.execute(delete(identity.models.User).where(identity.models.User.id == athlete[1]))
        db.commit()
        assert db.scalar(select(func.count()).select_from(identity.models.AthleteProfile)) == 0
        assert db.scalar(select(func.count()).select_from(identity.models.WeightCheckIn)) == 0

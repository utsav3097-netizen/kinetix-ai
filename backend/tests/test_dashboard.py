"""Targets use the authenticated owner's current persisted profile, never demo data."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def dashboard_client(identity):
    from app import dashboard_routes, profile

    identity.app.include_router(profile.router)
    identity.app.include_router(dashboard_routes.router)
    with TestClient(identity.app, headers={"Origin": "http://testserver"}) as client:
        yield client


@pytest.fixture
def target_profile():
    return {
        "full_name": "Athlete Example",
        "nickname": "Athlete",
        "age": 30,
        "biological_sex": "male",
        "height_cm": 180,
        "starting_weight_kg": 85,
        "current_weight_kg": 80,
        "body_fat_percentage": None,
        "display_unit": "kg",
        "activity_multiplier": 1.6,
        "phase": "body_recomposition",
        "analysis_weeks": 2,
    }


def register(client, identity, email="target-athlete@example.com"):
    response = client.post("/api/v1/auth/register", json={"email": email, "password": identity.password})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def save_profile(client, headers, payload):
    response = client.put("/api/v1/profile", headers=headers, json=payload)
    assert response.status_code == 200


def test_dashboard_requires_authentication_and_completed_profile(dashboard_client, identity):
    assert dashboard_client.get("/api/v1/dashboard/targets").status_code == 401
    headers = register(dashboard_client, identity)
    response = dashboard_client.get("/api/v1/dashboard/targets", headers=headers)
    assert response.status_code == 403
    assert "Complete onboarding" in response.json()["detail"]


def test_targets_return_exact_contract_and_recomp_training_rest_energy(dashboard_client, identity, target_profile):
    headers = register(dashboard_client, identity)
    save_profile(dashboard_client, headers, target_profile)
    training = dashboard_client.get("/api/v1/dashboard/targets?training_day=true", headers=headers)
    rest = dashboard_client.get("/api/v1/dashboard/targets?training_day=false", headers=headers)
    assert training.status_code == rest.status_code == 200
    assert training.headers["cache-control"] == "no-store"
    data, rest_data = training.json(), rest.json()
    assert set(data) == {"bmr_kcal", "tdee_kcal", "phase", "training_day", "macros", "protein_range_g", "disclaimer", "plan_version_id"}
    assert data["bmr_kcal"] == 1780
    assert data["tdee_kcal"] == pytest.approx(2848)
    assert data["phase"] == "body_recomposition"
    assert data["training_day"] is True
    assert rest_data["training_day"] is False
    assert data["protein_range_g"] == {"min": 144, "max": 192}
    assert set(data["macros"]) == {"calories_kcal", "base_calories_kcal", "protein_g", "carbs_g", "fat_g", "carb_cycle_factor"}
    assert data["macros"]["base_calories_kcal"] == rest_data["macros"]["base_calories_kcal"] == pytest.approx(2848)
    assert data["macros"]["protein_g"] == pytest.approx(184)
    assert data["macros"]["fat_g"] == 64
    assert data["macros"]["carbs_g"] == pytest.approx(384 * 1.1)
    assert rest_data["macros"]["carbs_g"] == pytest.approx(384 * 0.9)
    assert data["macros"]["calories_kcal"] == pytest.approx(1312 + 1536 * 1.1)
    assert rest_data["macros"]["calories_kcal"] == pytest.approx(1312 + 1536 * 0.9)
    assert "not medical advice" in data["disclaimer"]


def test_targets_are_owner_scoped_and_follow_latest_weight(dashboard_client, identity, target_profile):
    first = register(dashboard_client, identity)
    save_profile(dashboard_client, first, target_profile)
    second = register(dashboard_client, identity, "second-target-athlete@example.com")
    other_profile = {**target_profile, "biological_sex": "female", "current_weight_kg": 60, "phase": "cutting"}
    save_profile(dashboard_client, second, other_profile)
    second_result = dashboard_client.get("/api/v1/dashboard/targets", headers=second).json()
    assert second_result["bmr_kcal"] == 1414
    assert second_result["macros"]["protein_g"] == pytest.approx(132)
    assert second_result["phase"] == "cutting"
    check_in = dashboard_client.post("/api/v1/profile/check-ins", headers=first, json={"measured_on": "2099-01-01", "weight_kg": 82})
    assert check_in.status_code == 201
    first_result = dashboard_client.get("/api/v1/dashboard/targets", headers=first).json()
    assert first_result["bmr_kcal"] == 1800
    assert first_result["macros"]["protein_g"] == pytest.approx(188.6)
    assert first_result["protein_range_g"]["min"] == pytest.approx(147.6)
    assert dashboard_client.get("/api/v1/dashboard/targets", headers=second).json() == second_result


def test_targets_report_invalid_allocations_without_fabricated_fallback(dashboard_client, identity, target_profile):
    headers = register(dashboard_client, identity)
    save_profile(dashboard_client, headers, {
        **target_profile,
        "biological_sex": "female",
        "age": 100,
        "height_cm": 100,
        "current_weight_kg": 100,
        "activity_multiplier": 1.2,
        "phase": "cutting",
    })
    response = dashboard_client.get("/api/v1/dashboard/targets", headers=headers)
    assert response.status_code == 422
    assert "carbohydrate calories must remain positive" in response.json()["detail"]
    assert "macros" not in response.json()


def test_targets_validate_training_day_query(dashboard_client, identity, target_profile):
    headers = register(dashboard_client, identity)
    save_profile(dashboard_client, headers, target_profile)
    assert dashboard_client.get("/api/v1/dashboard/targets?training_day=unknown", headers=headers).status_code == 422

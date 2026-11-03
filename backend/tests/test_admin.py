"""Consumer-facing administration authorization, policy, audit, and announcements behavior."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from app.models.admin import AuditRecord

def bearer(response):
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin_api(identity):
    # Feature-owned models are imported explicitly until the parent integrates model exports.
    from app import admin_routes, profile
    from app.models.admin import AuditRecord
    from app.seed import seed_reference_data

    identity.app.include_router(admin_routes.admin_router)
    identity.app.include_router(admin_routes.announcement_router)
    identity.app.include_router(profile.router)
    with identity.sessions.begin() as db:
        seed_reference_data(db)
    return identity


def test_every_admin_endpoint_requires_persisted_admin_role(admin_api):
    from fastapi.testclient import TestClient

    with TestClient(admin_api.app, headers={"Origin": "http://testserver"}) as client:
        athlete = client.post("/api/v1/auth/register", json={"email": "athlete-admin-test@example.com", "password": admin_api.password})
        headers = bearer(athlete)
        for path in ("/api/v1/admin/settings", "/api/v1/admin/exercises", "/api/v1/admin/foods", "/api/v1/admin/analytics", "/api/v1/admin/audit"):
            assert client.get(path, headers=headers).status_code == 403
            assert client.get(path).status_code == 401


def test_admin_can_manage_references_settings_announcements_and_audit(admin_api):
    from fastapi.testclient import TestClient

    with TestClient(admin_api.app, headers={"Origin": "http://testserver"}) as client:
        admin = client.post("/api/v1/auth/register", json={"email": "bootstrap.admin@example.com", "password": admin_api.password})
        headers = bearer(admin)
        exercise = client.post("/api/v1/admin/exercises", headers=headers, json={
            "name": "Admin row", "equipment": "barbell", "met": 6.0, "biomechanical_multiplier": 0.4,
            "classification": "upper_compound", "measurement_type": "reps", "muscles": [{"muscle_id": "lats", "contribution": 1.0}],
        })
        assert exercise.status_code == 201
        exercise_id = exercise.json()["id"]
        assert client.delete(f"/api/v1/admin/exercises/{exercise_id}", headers=headers).status_code == 204
        setting = client.put("/api/v1/admin/settings/progression_policy", headers=headers, json={"value": {
            "upper_increment_kg": 3.0, "lower_increment_kg": 6.0, "deload_multiplier": 0.85,
        }})
        assert setting.status_code == 200
        assert setting.json()["value"]["upper_increment_kg"] == 3.0
        invalid = client.put("/api/v1/admin/settings/progression_policy", headers=headers, json={"value": {"upper_increment_kg": 0, "lower_increment_kg": 6.0, "deload_multiplier": 0.85}})
        assert invalid.status_code == 422
        announcement = client.post("/api/v1/admin/announcements", headers=headers, json={
            "title": "Maintenance", "body": "The service will be briefly unavailable.",
            "starts_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            "ends_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        })
        assert announcement.status_code == 201
        assert client.get("/api/v1/announcements", headers=headers).json()["items"][0]["title"] == "Maintenance"
        audit = client.get("/api/v1/admin/audit", headers=headers)
        assert audit.status_code == 200
        assert {row["resource_type"] for row in audit.json()["items"]} >= {"exercise", "system_setting", "announcement"}
        with admin_api.sessions() as db:
            assert db.scalar(select(func.count()).select_from(AuditRecord)) >= 3

from fastapi.testclient import TestClient


def test_liveness_does_not_require_database_or_start_ai_worker(monkeypatch):
    from app import main

    worker_started = []

    async def tracked_worker(*args, **kwargs):
        worker_started.append(True)

    def unavailable_database():
        raise AssertionError("liveness must not request a database session")

    monkeypatch.setattr(main.settings, "run_ai_worker", False)
    monkeypatch.setattr(main, "run_worker", tracked_worker)
    monkeypatch.setitem(main.app.dependency_overrides, main.get_db, unavailable_database)

    with TestClient(main.app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert worker_started == []

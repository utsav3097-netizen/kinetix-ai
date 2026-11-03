"""Consumer-facing persistence, privacy, safety, and unavailable boundaries for coach."""
import pytest
from fastapi.testclient import TestClient

def register(client, identity, email):
    response = client.post("/api/v1/auth/register", json={"email": email, "password": identity.password})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def coach_app(identity):
    # Keep feature model registration explicit until the parent exports it from app.models.
    from app.models import coach as _coach_models  # noqa: F401
    from app.coach_routes import router

    identity.app.include_router(router)
    return identity


@pytest.mark.parametrize("message", ["What should I do about knee pain?", "I was injured yesterday"])
def test_injury_question_has_non_diagnostic_boundary(coach_app, message, monkeypatch):
    from app.services import coach

    client = TestClient(coach_app.app, base_url="http://testserver", headers={"Origin": "http://testserver"})
    headers = register(client, coach_app, "safety@example.com")

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("injury boundary must not call the provider")

    monkeypatch.setattr(coach, "structured_generate", fail_if_called)
    response = client.post("/api/v1/coach/messages", headers=headers, json={"message": message})
    assert response.status_code == 201
    assistant = response.json()["assistant"]
    assert assistant["status"] == "safety"
    assert "cannot diagnose" in assistant["content"]
    assert assistant["proposal"] is None


def test_history_is_persistent_and_private_and_unavailable_is_explicit(coach_app, monkeypatch):
    from app.services import coach
    from app.services.ai.providers import AIUnavailable

    client = TestClient(coach_app.app, base_url="http://testserver", headers={"Origin": "http://testserver"})
    first_headers = register(client, coach_app, "first@example.com")
    second_headers = register(client, coach_app, "second@example.com")

    async def unavailable(*args, **kwargs):
        raise AIUnavailable()

    monkeypatch.setattr(coach, "structured_generate", unavailable)
    sent = client.post("/api/v1/coach/messages", headers=first_headers, json={"message": "How should I recover?"})
    assert sent.status_code == 201
    conversation_id = sent.json()["conversation_id"]
    assert sent.json()["assistant"]["status"] == "unavailable"
    assert "unchanged" in sent.json()["assistant"]["content"]
    reloaded = client.get("/api/v1/coach/messages", headers=first_headers)
    assert reloaded.status_code == 200
    assert [row["role"] for row in reloaded.json()["items"]] == ["user", "assistant"]
    assert client.get(f"/api/v1/coach/messages?conversation_id={conversation_id}", headers=second_headers).status_code == 404


def test_provider_response_is_bounded_and_proposals_are_not_auto_committed(coach_app, monkeypatch):
    from app.coach_schemas import CoachAIResponse
    from app.services import coach
    from app.services.ai.providers import Generated

    client = TestClient(coach_app.app, base_url="http://testserver", headers={"Origin": "http://testserver"})
    headers = register(client, coach_app, "proposal@example.com")
    async def proposed(*args, **kwargs):
        return Generated(data=CoachAIResponse(reply="Review this exact change before saving.", proposal=None), provider="test", model="test", latency_ms=1)


    monkeypatch.setattr(coach, "structured_generate", proposed)
    response = client.post("/api/v1/coach/messages", headers=headers, json={"message": "Give me a plan suggestion"})
    assert response.status_code == 201
    assert response.json()["assistant"]["proposal_state"] == "none"
    # A malformed provider payload cannot be accepted by the response contract.
    with pytest.raises(Exception):
        CoachAIResponse.model_validate({"reply": "ok", "unexpected": "command"})

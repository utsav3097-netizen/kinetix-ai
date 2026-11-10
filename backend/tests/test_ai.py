"""AI failures never alter logs; structured drafts retain ambiguity and ownership."""
import asyncio
from datetime import timedelta
import json

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from test_workouts import workouts, create_workout, add_block, add_set, block_path, set_input, day


def commentary(action="hold", **changes):
    return {"summary": "Recorded effort supports the displayed decision.", "form_cue": "Keep the movement comfortable and controlled.",
            "tempo_cue": "Lower smoothly without rushing.", "next_action": action,
            "disclaimer": "General AI-generated guidance, not medical advice.", **changes}


def envelope(data, provider="gemini"):
    text = json.dumps(data)
    if provider == "gemini":
        return {"status": "completed", "steps": [{"type": "thought", "content": [{"type": "text", "text": "private reasoning"}]},
                {"type": "model_output", "content": [{"type": "text", "text": text}]}]}
    return {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}


@pytest.fixture
def ai(workouts, identity):
    from app import ai_routes, nutrition_routes, reference_routes
    identity.app.include_router(ai_routes.router)
    identity.app.include_router(nutrition_routes.router)
    identity.app.include_router(reference_routes.food_router)
    return workouts


def test_invalid_primary_progression_uses_validated_fallback(identity):
    from app.ai_schemas import SetInsight
    from app.services.ai.providers import structured_generate
    from app.services.ai.worker import validate_workout
    settings = identity.settings.model_copy(update={"gemini_api_key": SecretStr("test-primary"), "openai_api_key": SecretStr("test-fallback")})
    context = {"progression": {"state": "hold"}}
    def respond(request):
        if request.url.host == "generativelanguage.googleapis.com":
            return httpx.Response(200, json=envelope(commentary("increase_weight")))
        return httpx.Response(200, json=envelope(commentary(), "openai"))
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await structured_generate(SetInsight, "Training", context, settings=settings, client=client,
                                             validate=lambda data: validate_workout(data, context))
    result = asyncio.run(run())
    assert result.provider == "openai"
    assert result.data.next_action == "hold"
    assert "private reasoning" not in result.data.model_dump_json()


@pytest.mark.parametrize("failure", ["http", "timeout", "malformed", "extra", "wrong_state", "numeric", "oversized"])
def test_failed_outputs_never_become_insights(identity, failure):
    from app.ai_schemas import SetInsight
    from app.services.ai.providers import AIUnavailable, structured_generate
    from app.services.ai.worker import validate_workout
    settings = identity.settings.model_copy(update={"gemini_api_key": SecretStr("secret-canary"), "openai_api_key": None})
    context = {"progression": {"state": "hold"}}
    def respond(request):
        if failure == "http": return httpx.Response(429, text="secret-canary provider diagnostic")
        if failure == "timeout": raise httpx.ReadTimeout("secret-canary", request=request)
        if failure == "malformed": return httpx.Response(200, json={"status": "completed", "steps": []})
        data = commentary()
        if failure == "extra": data["recommended_weight"] = 1000
        if failure == "wrong_state": data["next_action"] = "increase_weight"
        if failure == "numeric": data["summary"] = "Lift 1000 kg now."
        if failure == "oversized": data["summary"] = "x" * 601
        return httpx.Response(200, json=envelope(data))
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await structured_generate(SetInsight, "Training", context, settings=settings, client=client,
                                             validate=lambda data: validate_workout(data, context))
    with pytest.raises(AIUnavailable) as error:
        asyncio.run(run())
    assert "secret-canary" not in str(error.value)


def test_queue_no_key_is_terminal_and_preserves_metrics(ai, identity):
    from app.services.ai.worker import process_one
    client, (owner, other), exercises = ai
    session = create_workout(client, owner)
    block = add_block(client, owner, session, exercises["Pull-up"])
    saved = add_set(client, owner, session, block)
    row = saved["exercises"][0]["sets"][0]
    url = "/api/v1/workouts/insights/" + row["insight_id"]
    pending = client.get(url, headers=owner).json()
    assert pending["status"] == "pending"
    assert pending["comparison"]["volume_kg"] == 688
    assert pending["comparison"]["volume_change_kg"] is None
    assert client.get(url, headers=other).status_code == 404
    assert client.get(url.replace("workouts", "nutrition"), headers=owner).status_code == 404
    assert client.get(url).status_code == 401
    assert client.post(block_path(session, block)+"/sets/"+row["id"]+"/analyze", headers=other).status_code == 404
    settings = identity.settings.model_copy(update={"gemini_api_key": None, "openai_api_key": None})
    assert asyncio.run(process_one(identity.sessions, settings))
    unavailable = client.get(url, headers=owner).json()
    assert unavailable["status"] == "unavailable" and unavailable["result"] is None
    assert unavailable["comparison"] == pending["comparison"]
    assert client.get('/api/v1/workouts/'+session['id'], headers=owner).json()["exercises"][0]["sets"][0]["metrics"] == row["metrics"]
    retry = client.post(block_path(session, block)+"/sets/"+row["id"]+"/analyze", headers=owner)
    assert retry.status_code == 202 and retry.json()["id"] != row["insight_id"]
    assert client.get(url, headers=owner).json()["status"] == "unavailable"


def test_comparison_remains_frozen_after_source_correction(ai, identity):
    client, (owner, _), exercises = ai
    previous = create_workout(client, owner, performed_on=day(1))
    before_block = add_block(client, owner, previous, exercises["Pull-up"])
    add_set(client, owner, previous, before_block)
    current = create_workout(client, owner)
    block = add_block(client, owner, current, exercises["Pull-up"])
    saved = add_set(client, owner, current, block, repetitions=10)
    row = saved["exercises"][0]["sets"][0]
    url = '/api/v1/workouts/insights/'+row['insight_id']
    comparison = client.get(url, headers=owner).json()["comparison"]
    assert comparison["volume_change_kg"] == 172
    assert comparison["one_rm_change_kg"] == pytest.approx(86*2/30)
    client.post(block_path(current, block)+"/complete", headers=owner)
    changed = client.put(block_path(current, block)+"/sets/"+row["id"], headers=owner, json=set_input(repetitions=9)).json()
    assert changed["exercises"][0]["completed"] is False
    assert changed["exercises"][0]["insight_id"] is None
    assert changed["exercises"][0]["sets"][0]["insight_id"] != row["insight_id"]
    assert client.get(url, headers=owner).json()["comparison"] == comparison


def test_interrupted_lease_is_not_billed_again(ai, identity):
    from app.models import AIInsight
    from app.models.identity import utc_now
    from app.services.ai.worker import claim_next
    client, (owner, _), exercises = ai
    session = create_workout(client, owner)
    block = add_block(client, owner, session, exercises["Pull-up"])
    saved = add_set(client, owner, session, block)
    job_id = saved["exercises"][0]["sets"][0]["insight_id"]
    assert claim_next(identity.sessions)[0] == job_id
    assert claim_next(identity.sessions) is None
    with identity.sessions.begin() as db:
        db.get(AIInsight, job_id).lease_expires_at = utc_now()-timedelta(seconds=1)
    assert claim_next(identity.sessions) is None
    result = client.get('/api/v1/workouts/insights/'+job_id, headers=owner).json()
    assert result["status"] == "unavailable" and "interrupted" in result["reason"]

def test_cancelling_inflight_worker_finalizes_claim_immediately(ai, identity, monkeypatch):
    from app.models import AIInsight
    from app.services.ai import worker

    client, (owner, _), exercises = ai
    session = create_workout(client, owner)
    block = add_block(client, owner, session, exercises["Pull-up"])
    saved = add_set(client, owner, session, block)
    job_id = saved["exercises"][0]["sets"][0]["insight_id"]
    provider_started = asyncio.Event()

    async def wait_for_shutdown(*args, **kwargs):
        provider_started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(worker, "structured_generate", wait_for_shutdown)

    async def cancel_worker():
        task = asyncio.create_task(worker.process_one(identity.sessions, identity.settings))
        await asyncio.wait_for(provider_started.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_worker())
    with identity.sessions() as db:
        job = db.get(AIInsight, job_id)
        assert job.status == "unavailable"
        assert "interrupted" in job.reason
        assert job.claim_token is None and job.lease_expires_at is None


def test_parser_keeps_portions_and_unknown_food_unresolved_without_saving(ai, identity):
    from app.services.ai.worker import process_one
    client, (owner, other), _ = ai
    foods = {food['name']: food['id'] for food in client.get('/api/v1/nutrition/foods?limit=100',headers=owner).json()['items']}
    payload = {"text":"3 eggs, 100g oats, 1 scoop mystery", "date":day(), "training_day":False,
               "slot":"breakfast", "title":"Parsed breakfast", "time":"08:00"}
    response = client.post('/api/v1/nutrition/parse', headers=owner, json=payload)
    assert response.status_code == 202
    job_id = response.json()['id']
    url = '/api/v1/nutrition/insights/'+job_id
    assert client.get(url,headers=other).status_code == 404
    extraction = {"items":[
        {"label":"Eggs","source_text":"3 eggs","food_id":foods['Egg'],"grams":150},
        {"label":"Oats","source_text":"100g oats","food_id":foods['Oats'],"grams":100},
        {"label":"Mystery","source_text":"1 scoop mystery","food_id":"unknown","grams":30}]}
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=envelope(extraction)))) as transport:
            return await process_one(identity.sessions, identity.settings.model_copy(update={"gemini_api_key":SecretStr('test'),"openai_api_key":None}),client=transport)
    assert asyncio.run(run())
    result = client.get(url,headers=owner).json()
    assert result['status']=='success',result
    draft = result['result']
    assert [item['resolution'] for item in draft['items']]==['unresolved','resolved','unresolved']
    assert draft['items'][0]['grams'] is None
    assert draft['items'][2]['food_id'] is None and draft['items'][2]['nutrients'] is None
    assert draft['totals']['calories_kcal']==389
    assert draft['totals']['protein_g']==16.9
    day_view = client.get('/api/v1/nutrition/days/'+day(),headers=owner).json()
    assert day_view['persisted'] is False and day_view['meals']==[]


@pytest.mark.parametrize(('text','proposed','expected'), [('0.2kg oats',200,200),('100g oats',100,100),('100g oats',150,None),('1 scoop oats',30,None),('-100g oats',100,None),('100-200g oats',200,None),('2 x 100g oats',200,None),('about 100g oats',100,None)])
def test_only_unambiguous_metric_evidence_produces_grams(text,proposed,expected):
    from app.services.ai.meals import evidence_grams
    assert evidence_grams(text,proposed)==expected

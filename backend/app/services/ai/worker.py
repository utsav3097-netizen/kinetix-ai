"""Single-deployment durable queue worker with transactional claims and bounded leases."""
import asyncio
from datetime import timedelta
import json
import re
from time import monotonic

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.ai_schemas import ExtractedMeal, SetInsight
from app.config import Settings
from app.models import AIInsight
from app.models.identity import new_id, utc_now
from app.services.ai.meals import MEAL_PROMPT, build_draft, validate_extraction
from app.services.ai.providers import AIUnavailable, UNAVAILABLE_REASON, structured_generate

WORKOUT_PROMPT = """Provide short non-medical training commentary based only on this recorded snapshot.
The comparison and deterministic progression are authoritative. next_action MUST equal
progression.state. Never prescribe a different load, repetitions, volume or progression.
Use qualitative prose only: no numbers or numerical quantities in any text field; numerical
facts are displayed separately by the application. Do not claim you observed the athlete's
technique. form_cue and tempo_cue are general optional practice cues, not a diagnosis.
The disclaimer must identify this as general AI-generated guidance, not medical advice.
Do not infer injury, pain, health conditions, or unrecorded training history."""
NUMERIC_PROSE = re.compile(r"\d|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|percent)\b", re.IGNORECASE)


def validate_workout(data: SetInsight, context: dict) -> None:
    if data.next_action != context["progression"]["state"]:
        raise ValueError("AI cannot change deterministic progression")
    for value in (data.summary, data.form_cue, data.tempo_cue, data.disclaimer):
        if NUMERIC_PROSE.search(value):
            raise ValueError("Numerical facts belong to deterministic metrics")
    if "medical" not in data.disclaimer.casefold() or "ai" not in data.disclaimer.casefold():
        raise ValueError("AI guidance requires its safety disclosure")


def claim_next(sessions) -> tuple[str, str] | None:
    now = utc_now()
    with sessions() as db:
        # An interrupted billed call is terminal, never silently retried on restart.
        db.execute(update(AIInsight).where(AIInsight.status == "pending", AIInsight.claim_token.is_not(None),
            AIInsight.lease_expires_at <= now).values(status="unavailable", finished_at=now,
                reason="AI analysis was interrupted. You can explicitly request another analysis.", claim_token=None, lease_expires_at=None))
        candidate = db.scalar(select(AIInsight.id).where(AIInsight.status == "pending",
            AIInsight.claim_token.is_(None)).order_by(AIInsight.created_at, AIInsight.id).limit(1))
        if candidate is None:
            db.commit()
            return None
        token = new_id()
        claimed = db.execute(update(AIInsight).where(AIInsight.id == candidate, AIInsight.status == "pending",
            AIInsight.claim_token.is_(None)).values(claim_token=token, started_at=now,
                lease_expires_at=now + timedelta(seconds=210)))
        db.commit()
        return (candidate, token) if claimed.rowcount == 1 else None


def _finish(sessions, job_id: str, token: str, **values) -> None:
    with sessions() as db:
        db.execute(update(AIInsight).where(AIInsight.id == job_id, AIInsight.status == "pending",
            AIInsight.claim_token == token).values(**values, finished_at=utc_now(), claim_token=None, lease_expires_at=None))
        db.commit()


async def process_one(sessions, settings: Settings, *, client=None) -> bool:
    claimed = claim_next(sessions)
    if claimed is None:
        return False
    job_id, token = claimed
    started = monotonic()
    try:
        with sessions() as db:
            job = db.scalar(select(AIInsight).where(AIInsight.id == job_id, AIInsight.claim_token == token))
            kind, owner_id, context = job.kind, job.owner_id, job.context
        if kind == "meal_parse":
            provider_context = {"text": context["request"]["text"], "foods": context["foods"]}
            generated = await structured_generate(ExtractedMeal, MEAL_PROMPT, provider_context, settings=settings,
                client=client, validate=lambda data: validate_extraction(data, provider_context["text"]))
            with sessions() as db:
                result = build_draft(db, owner_id, context, generated.data)
        else:
            generated = await structured_generate(SetInsight, WORKOUT_PROMPT, context, settings=settings,
                client=client, validate=lambda data: validate_workout(data, context))
            result = generated.data
        # Validate one final time before serialization; never persist provider envelopes.
        validated = type(result).model_validate_json(result.model_dump_json())
        _finish(sessions, job_id, token, status="success", result=validated.model_dump(mode="json"),
                reason=None, provider=generated.provider, model=generated.model, latency_ms=generated.latency_ms)
    except asyncio.CancelledError:
        _finish(sessions, job_id, token, status="unavailable", reason="AI analysis was interrupted. You can explicitly request another analysis.",
                latency_ms=round((monotonic() - started) * 1000))
        raise
    except Exception:
        # Malformed local/provider content also fails closed without sensitive diagnostics.
        _finish(sessions, job_id, token, status="unavailable", reason=UNAVAILABLE_REASON,
                latency_ms=round((monotonic() - started) * 1000))
    return True


async def run_worker(sessions, settings: Settings) -> None:
    while True:
        try:
            worked = await process_one(sessions, settings)
        except SQLAlchemyError:
            # Startup before migrations or a transient DB outage must not kill logging.
            worked = False
        await asyncio.sleep(0.05 if worked else 1.0)

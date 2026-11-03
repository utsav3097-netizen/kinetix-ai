"""Owner-scoped workout commands and queries.

Commands validate and flush within the caller's transaction; callers commit only
when the complete command succeeds. Future confirmed coach actions reuse these
functions rather than writing projections or the source journal directly.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.models import MuscleGroup
from app.models.identity import new_id, utc_now
from app.models.workout import WorkoutExercise, WorkoutSession, WorkoutSet, WorkoutSourceRecord
from app.reference_service import get_exercise
from app.services.admin_policy import progression_policy
from app.services.ai.context import capture_context
from app.services.ai.jobs import enqueue_workout, latest
from app.services.fitness_algorithms import (
    EffectiveLoadInput, FatigueInput, OneRepMaxInput, ProgressionInput, ProgressionPolicy, ProgressionResult,
    ProgressionSet, effective_load, estimate_one_rep_max, fatigue_index, recommend_progression, weekly_volume_landmark,
)
from app.workout_schemas import BlockCreate, BlockInput, PageQuery, SessionInput, SessionQuery, SetInput, SetView


def _uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, "Workout record not found") from None


def get_session(db: Session, owner_id: str, session_id: str, *, lock: bool = False, include_deleted: bool = False) -> WorkoutSession:
    session_id = _uuid(session_id)
    conditions = [WorkoutSession.id == session_id, WorkoutSession.owner_id == owner_id]
    if not include_deleted:
        conditions.append(WorkoutSession.deleted_at.is_(None))
    # SQLite ignores SELECT FOR UPDATE. Acquire its write lock before reading the
    # mutable session, so revision allocation and bodyweight checks serialize too.
    if lock and db.get_bind().dialect.name == "sqlite":
        db.execute(update(WorkoutSession).where(*conditions).values(revision=WorkoutSession.revision).execution_options(synchronize_session=False))
    statement = select(WorkoutSession).where(*conditions)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    session = db.scalar(statement)
    if session is None:
        raise HTTPException(404, "Workout session not found")
    return session


def _block(db: Session, session: WorkoutSession, block_id: str) -> WorkoutExercise:
    block = db.scalar(select(WorkoutExercise).where(
        WorkoutExercise.id == _uuid(block_id), WorkoutExercise.session_id == session.id,
        WorkoutExercise.owner_id == session.owner_id, WorkoutExercise.deleted_at.is_(None),
    ))
    if block is None:
        raise HTTPException(404, "Workout exercise not found")
    return block


def _set(db: Session, session: WorkoutSession, block: WorkoutExercise, set_id: str) -> WorkoutSet:
    row = db.scalar(select(WorkoutSet).where(
        WorkoutSet.id == _uuid(set_id), WorkoutSet.block_id == block.id,
        WorkoutSet.session_id == session.id, WorkoutSet.owner_id == session.owner_id,
        WorkoutSet.deleted_at.is_(None),
    ))
    if row is None:
        raise HTTPException(404, "Workout set not found")
    return row


def _blocks(db: Session, session: WorkoutSession) -> list[WorkoutExercise]:
    return list(db.scalars(select(WorkoutExercise).where(
        WorkoutExercise.session_id == session.id, WorkoutExercise.owner_id == session.owner_id,
        WorkoutExercise.deleted_at.is_(None),
    ).order_by(WorkoutExercise.ordinal, WorkoutExercise.id)))


def _sets(db: Session, session: WorkoutSession, block: WorkoutExercise) -> list[WorkoutSet]:
    return list(db.scalars(select(WorkoutSet).where(
        WorkoutSet.session_id == session.id, WorkoutSet.block_id == block.id,
        WorkoutSet.owner_id == session.owner_id, WorkoutSet.deleted_at.is_(None),
    ).order_by(WorkoutSet.ordinal, WorkoutSet.id)))


def _unique_ordinal(db: Session, session: WorkoutSession, model, parent_id: str, ordinal: int, own_id: str | None = None) -> None:
    parent_column = model.session_id if model is WorkoutExercise else model.block_id
    statement = select(model.id).where(parent_column == parent_id, model.owner_id == session.owner_id,
                                       model.deleted_at.is_(None), model.ordinal == ordinal)
    if own_id:
        statement = statement.where(model.id != own_id)
    if db.scalar(statement) is not None:
        raise HTTPException(409, "Ordinal already exists among active siblings")


def _append(db: Session, session: WorkoutSession, entity_type: str, entity_id: str, action: str, payload: dict, *, source_id: str | None = None) -> str:
    session.revision += 1
    source = WorkoutSourceRecord(
        id=source_id or new_id(), owner_id=session.owner_id, session_id=session.id,
        revision=session.revision, entity_type=entity_type, entity_id=entity_id,
        action=action, payload=deepcopy(payload),
    )
    db.add(source)
    db.flush()
    return source.id


def _session_payload(session: WorkoutSession) -> dict:
    return {"id": session.id, **SessionInput.model_validate(session).model_dump(mode="json")}


def _block_payload(block: WorkoutExercise) -> dict:
    return {"id": block.id, "session_id": block.session_id, "exercise_id": block.exercise_id,
            "exercise_snapshot": deepcopy(block.exercise_snapshot), "ordinal": block.ordinal,
            "target_min_reps": block.target_min_reps, "target_max_reps": block.target_max_reps,
            "completed": block.completed}


def set_view(row: WorkoutSet, db: Session | None = None) -> dict:
    result = SetView.model_validate(row).model_dump(mode="json")
    if db is not None:
        insight = latest(db, row.owner_id, row.source_record_id, "set")
        result["insight_id"] = insight.id if insight else None
    return result


def _block_source(db: Session, session: WorkoutSession, block: WorkoutExercise) -> WorkoutSourceRecord | None:
    return db.scalar(select(WorkoutSourceRecord).where(WorkoutSourceRecord.owner_id == session.owner_id,
        WorkoutSourceRecord.session_id == session.id, WorkoutSourceRecord.entity_id == block.id,
        WorkoutSourceRecord.entity_type == "exercise").order_by(WorkoutSourceRecord.revision.desc()).limit(1))


def _queue_analysis(db: Session, session: WorkoutSession, block: WorkoutExercise,
                    row: WorkoutSet | None = None, *, retry: bool = False):
    rows = _sets(db, session, block)
    progression = block_progression(db, session, block, rows).model_dump()
    context, comparison = capture_context(db, session, block, rows, progression, selected=row)
    source = row.source_record_id if row else _block_source(db, session, block).id
    return enqueue_workout(db, session.owner_id, source, "set" if row else "exercise_block",
                           context, comparison, retry=retry)


def _reopen(db: Session, session: WorkoutSession, block: WorkoutExercise) -> None:
    if block.completed:
        block.completed = False
        _append(db, session, "exercise", block.id, "update", _block_payload(block))


def analyze_set(db: Session, owner_id: str, session_id: str, block_id: str, set_id: str):
    session = get_session(db, owner_id, session_id, lock=True)
    block = _block(db, session, block_id)
    return _queue_analysis(db, session, block, _set(db, session, block, set_id), retry=True)


def analyze_block(db: Session, owner_id: str, session_id: str, block_id: str):
    session = get_session(db, owner_id, session_id, lock=True)
    block = _block(db, session, block_id)
    if not block.completed:
        raise HTTPException(409, "Complete the exercise block before requesting analysis")
    return _queue_analysis(db, session, block, retry=True)


def create_session(db: Session, owner_id: str, payload: SessionInput) -> WorkoutSession:
    session = WorkoutSession(owner_id=owner_id, **payload.model_dump())
    db.add(session)
    db.flush()
    _append(db, session, "session", session.id, "create", _session_payload(session))
    return session


def update_session(db: Session, owner_id: str, session_id: str, payload: SessionInput) -> WorkoutSession:
    session = get_session(db, owner_id, session_id, lock=True)
    # Even deleted sets retain the bodyweight snapshot and prohibit rewriting it.
    if payload.bodyweight_kg != session.bodyweight_kg and db.scalar(select(WorkoutSet.id).where(
        WorkoutSet.session_id == session.id, WorkoutSet.owner_id == owner_id,
    ).limit(1)) is not None:
        raise HTTPException(422, "Session bodyweight cannot change once sets have been recorded")
    for key, value in payload.model_dump().items():
        setattr(session, key, value)
    _append(db, session, "session", session.id, "update", _session_payload(session))
    return session


def create_block(db: Session, owner_id: str, session_id: str, payload: BlockCreate) -> WorkoutSession:
    session = get_session(db, owner_id, session_id, lock=True)
    _unique_ordinal(db, session, WorkoutExercise, session.id, payload.ordinal)
    exercise = get_exercise(db, owner_id, payload.exercise_id, for_update=True)
    snapshot = {key: getattr(exercise, key) for key in ("name", "equipment", "biomechanical_multiplier", "classification", "measurement_type")}
    snapshot["muscles"] = [{"muscle_id": muscle.muscle_id, "contribution": muscle.contribution} for muscle in exercise.muscles]
    block = WorkoutExercise(owner_id=owner_id, session_id=session.id, exercise_id=exercise.id,
                            exercise_snapshot=snapshot, **payload.model_dump(exclude={"exercise_id"}))
    db.add(block)
    db.flush()
    _append(db, session, "exercise", block.id, "create", _block_payload(block))
    return session


def update_block(db: Session, owner_id: str, session_id: str, block_id: str, payload: BlockInput) -> WorkoutSession:
    session = get_session(db, owner_id, session_id, lock=True)
    block = _block(db, session, block_id)
    _unique_ordinal(db, session, WorkoutExercise, session.id, payload.ordinal, block.id)
    for key, value in payload.model_dump().items():
        setattr(block, key, value)
    block.completed = False
    _append(db, session, "exercise", block.id, "update", _block_payload(block))
    return session


def complete_block(db: Session, owner_id: str, session_id: str, block_id: str) -> WorkoutSession:
    session = get_session(db, owner_id, session_id, lock=True)
    block = _block(db, session, block_id)
    if block.completed:
        _queue_analysis(db, session, block)
        return session
    block.completed = True
    payload = _block_payload(block)
    payload["progression"] = block_progression(db, session, block, _sets(db, session, block)).model_dump()
    _append(db, session, "exercise", block.id, "complete", payload)
    _queue_analysis(db, session, block)
    return session


def _metrics(session: WorkoutSession, block: WorkoutExercise, payload: SetInput) -> dict:
    timed = block.exercise_snapshot["measurement_type"] == "seconds"
    if timed != (payload.duration_seconds is not None):
        raise HTTPException(422, "Set measurement must match the exercise snapshot (repetitions or seconds)")
    load = effective_load(EffectiveLoadInput(bodyweight_kg=session.bodyweight_kg,
        biomechanical_multiplier=block.exercise_snapshot["biomechanical_multiplier"], external_load_kg=payload.external_load_kg))
    metrics = {"effective_load_kg": load, "volume_kg": None if timed else load * payload.repetitions,
               "estimated_1rm_kg": None, "one_rm_formula": None, "estimate_unavailable_reason": None}
    if timed:
        metrics["estimate_unavailable_reason"] = "Timed exercises do not have a rep-based 1RM or volume estimate."
    elif payload.repetitions == 0 or payload.repetitions >= 37:
        metrics["estimate_unavailable_reason"] = "1RM estimation requires between 1 and 36 repetitions."
    elif load <= 0:
        metrics["estimate_unavailable_reason"] = "1RM estimation requires positive effective load."
    else:
        estimate = estimate_one_rep_max(OneRepMaxInput(load_kg=load, reps=payload.repetitions))
        metrics.update(estimated_1rm_kg=estimate.estimate_kg, one_rm_formula=estimate.formula)
    return metrics


def create_set(db: Session, owner_id: str, session_id: str, block_id: str, payload: SetInput) -> WorkoutSession:
    session = get_session(db, owner_id, session_id, lock=True)
    block = _block(db, session, block_id)
    _unique_ordinal(db, session, WorkoutSet, block.id, payload.ordinal)
    _reopen(db, session, block)
    row = WorkoutSet(id=new_id(), owner_id=owner_id, session_id=session.id, block_id=block.id,
        source_record_id=new_id(), bodyweight_kg=session.bodyweight_kg,
        metrics=_metrics(session, block, payload), **payload.model_dump())
    source_payload = {**set_view(row), "session_id": session.id, "block_id": block.id}
    _append(db, session, "set", row.id, "create", source_payload, source_id=row.source_record_id)
    db.add(row)
    db.flush()
    _queue_analysis(db, session, block, row)
    return session


def update_set(db: Session, owner_id: str, session_id: str, block_id: str, set_id: str, payload: SetInput) -> WorkoutSession:
    session = get_session(db, owner_id, session_id, lock=True)
    block = _block(db, session, block_id)
    row = _set(db, session, block, set_id)
    _unique_ordinal(db, session, WorkoutSet, block.id, payload.ordinal, row.id)
    metrics = _metrics(session, block, payload)
    _reopen(db, session, block)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.metrics = metrics
    source_id = new_id()
    source_payload = {**set_view(row), "source_record_id": source_id, "session_id": session.id, "block_id": block.id}
    _append(db, session, "set", row.id, "update", source_payload, source_id=source_id)
    row.source_record_id = source_id
    db.flush()
    _queue_analysis(db, session, block, row)
    return session


def _delete_set(db: Session, session: WorkoutSession, row: WorkoutSet) -> None:
    source_id = new_id()
    payload = {**set_view(row), "source_record_id": source_id, "session_id": session.id, "block_id": row.block_id}
    _append(db, session, "set", row.id, "delete", payload, source_id=source_id)
    row.source_record_id = source_id
    row.deleted_at = utc_now()
    db.flush()


def delete_set(db: Session, owner_id: str, session_id: str, block_id: str, set_id: str) -> None:
    session = get_session(db, owner_id, session_id, lock=True)
    block = _block(db, session, block_id)
    _delete_set(db, session, _set(db, session, block, set_id))
    _reopen(db, session, block)


def _delete_block(db: Session, session: WorkoutSession, block: WorkoutExercise) -> None:
    for row in _sets(db, session, block):
        _delete_set(db, session, row)
    block.deleted_at = utc_now()
    _append(db, session, "exercise", block.id, "delete", _block_payload(block))


def delete_block(db: Session, owner_id: str, session_id: str, block_id: str) -> None:
    session = get_session(db, owner_id, session_id, lock=True)
    _delete_block(db, session, _block(db, session, block_id))


def delete_session(db: Session, owner_id: str, session_id: str) -> None:
    session = get_session(db, owner_id, session_id, lock=True)
    for block in _blocks(db, session):
        _delete_block(db, session, block)
    session.deleted_at = utc_now()
    _append(db, session, "session", session.id, "delete", _session_payload(session))


def _active_sets(owner_id: str):
    return select(WorkoutSet, WorkoutExercise, WorkoutSession).join(
        WorkoutExercise, and_(WorkoutSet.block_id == WorkoutExercise.id, WorkoutSet.session_id == WorkoutExercise.session_id),
    ).join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id).where(
        WorkoutSet.owner_id == owner_id, WorkoutExercise.owner_id == owner_id, WorkoutSession.owner_id == owner_id,
        WorkoutSet.deleted_at.is_(None), WorkoutExercise.deleted_at.is_(None), WorkoutSession.deleted_at.is_(None),
    )


def block_progression(db: Session, session: WorkoutSession, block: WorkoutExercise, rows: list[WorkoutSet]) -> ProgressionResult:
    working = [row for row in rows if row.set_type == "working"]
    loads = {row.external_load_kg for row in working}
    current_load = working[0].external_load_kg if len(loads) == 1 else 0.0

    def insufficient(reason: str) -> ProgressionResult:
        return ProgressionResult(state="insufficient_data", next_weight_kg=current_load,
                                 target_reps=block.target_min_reps, reason=reason)

    if block.exercise_snapshot["measurement_type"] != "reps":
        return insufficient("Rep-based progression does not apply to timed exercises.")
    if len(loads) > 1:
        return insufficient("Comparable external loads are required; mixed working-set loads do not define a current load. No next load is recommended.")
    if any(row.repetitions is None or row.repetitions >= 37 for row in working):
        return insufficient("Rep-based progression requires working sets with fewer than 37 repetitions.")
    # Nearest earlier logged session, including deterministic creation ordering
    # for multiple sessions on the same day; never another block in this session.
    previous_session = db.scalar(select(WorkoutSession).join(
        WorkoutExercise, WorkoutExercise.session_id == WorkoutSession.id,
    ).where(
        WorkoutSession.owner_id == session.owner_id, WorkoutExercise.owner_id == session.owner_id,
        WorkoutSession.deleted_at.is_(None), WorkoutExercise.deleted_at.is_(None),
        WorkoutExercise.exercise_id == block.exercise_id, WorkoutSession.id != session.id,
        or_(WorkoutSession.performed_on < session.performed_on,
            and_(WorkoutSession.performed_on == session.performed_on, WorkoutSession.created_at < session.created_at)),
    ).order_by(WorkoutSession.performed_on.desc(), WorkoutSession.created_at.desc(), WorkoutSession.id.desc()).limit(1))
    previous = None
    if previous_session is not None:
        previous_rows = list(db.scalars(select(WorkoutSet).join(WorkoutExercise, WorkoutSet.block_id == WorkoutExercise.id).where(
            WorkoutSet.owner_id == session.owner_id, WorkoutExercise.owner_id == session.owner_id,
            WorkoutSet.session_id == previous_session.id, WorkoutExercise.session_id == previous_session.id,
            WorkoutExercise.exercise_id == block.exercise_id, WorkoutSet.set_type == "working",
            WorkoutSet.deleted_at.is_(None), WorkoutExercise.deleted_at.is_(None),
        ).order_by(WorkoutExercise.ordinal, WorkoutSet.ordinal)))
        if previous_rows:
            if len({row.external_load_kg for row in previous_rows}) > 1:
                return insufficient("Previous working sets need comparable external loads; the nearest earlier session has mixed loads.")
            if any(row.repetitions is None or row.repetitions >= 37 for row in previous_rows):
                return insufficient("The nearest earlier session does not have comparable rep-based working sets.")
            previous = [ProgressionSet(reps=row.repetitions, rpe=row.rpe, rir=row.rir) for row in previous_rows]
    return recommend_progression(ProgressionInput(
        current_weight_kg=current_load, target_min_reps=block.target_min_reps, target_max_reps=block.target_max_reps,
        classification=block.exercise_snapshot["classification"],
        working_sets=[ProgressionSet(reps=row.repetitions, rpe=row.rpe, rir=row.rir) for row in working],
        previous_working_sets=previous,
        policy=ProgressionPolicy.model_validate(progression_policy(db)),
    ))


def _volume(row: WorkoutSet) -> float:
    return (row.metrics["volume_kg"] or 0.0) if row.set_type != "warmup" else 0.0


def session_view(db: Session, session: WorkoutSession) -> dict:
    blocks = []
    total_volume = 0.0
    set_count = 0
    for block in _blocks(db, session):
        rows = _sets(db, session, block)
        total_volume += sum(_volume(row) for row in rows)
        set_count += len(rows)
        source = _block_source(db, session, block) if block.completed else None
        insight = latest(db, session.owner_id, source.id, "exercise_block") if source else None
        blocks.append({key: value for key, value in _block_payload(block).items() if key != "session_id"} | {
            "sets": [set_view(row, db) for row in rows], "progression": block_progression(db, session, block, rows),
            "insight_id": insight.id if insight else None,
        })
    return {**_session_payload(session), "total_volume_kg": total_volume, "exercise_count": len(blocks),
            "set_count": set_count, "revision": session.revision, "exercises": blocks}


def list_sessions(db: Session, owner_id: str, query: SessionQuery) -> dict:
    statement = select(WorkoutSession).where(WorkoutSession.owner_id == owner_id, WorkoutSession.deleted_at.is_(None))
    if query.from_date:
        statement = statement.where(WorkoutSession.performed_on >= query.from_date)
    if query.to_date:
        statement = statement.where(WorkoutSession.performed_on <= query.to_date)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    sessions = list(db.scalars(statement.order_by(WorkoutSession.performed_on.desc(), WorkoutSession.created_at.desc(), WorkoutSession.id.desc()).offset(query.offset).limit(query.limit)))
    ids = [session.id for session in sessions]
    counts = dict(db.execute(select(WorkoutExercise.session_id, func.count()).where(
        WorkoutExercise.owner_id == owner_id, WorkoutExercise.session_id.in_(ids), WorkoutExercise.deleted_at.is_(None),
    ).group_by(WorkoutExercise.session_id)).all())
    volumes = defaultdict(float)
    set_counts = defaultdict(int)
    for row, _, session in db.execute(_active_sets(owner_id).where(WorkoutSession.id.in_(ids))):
        volumes[session.id] += _volume(row)
        set_counts[session.id] += 1
    return {"total": total, "items": [{"id": session.id, "title": session.title, "performed_on": session.performed_on,
        "bodyweight_kg": session.bodyweight_kg, "revision": session.revision, "exercise_count": counts.get(session.id, 0),
        "set_count": set_counts[session.id], "total_volume_kg": volumes[session.id]} for session in sessions]}


def source_history(db: Session, owner_id: str, session_id: str, query: PageQuery) -> dict:
    session = get_session(db, owner_id, session_id, include_deleted=True)
    statement = select(WorkoutSourceRecord).where(WorkoutSourceRecord.owner_id == owner_id, WorkoutSourceRecord.session_id == session.id)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    return {"total": total, "items": list(db.scalars(statement.order_by(WorkoutSourceRecord.revision.desc()).offset(query.offset).limit(query.limit)))}


def exercise_history(db: Session, owner_id: str, exercise_id: str, query: PageQuery) -> dict:
    exercise_id = _uuid(exercise_id)
    logged = db.scalar(select(WorkoutExercise.id).join(
        WorkoutSession, WorkoutExercise.session_id == WorkoutSession.id,
    ).where(WorkoutExercise.owner_id == owner_id, WorkoutSession.owner_id == owner_id,
            WorkoutExercise.exercise_id == exercise_id).limit(1))
    if logged is None:
        get_exercise(db, owner_id, exercise_id)
    statement = _active_sets(owner_id).where(WorkoutExercise.exercise_id == exercise_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.execute(statement.order_by(WorkoutSession.performed_on.desc(), WorkoutSession.created_at.desc(), WorkoutSession.id.desc(), WorkoutExercise.ordinal, WorkoutSet.ordinal).offset(query.offset).limit(query.limit))
    return {"total": total, "items": [{"session_id": session.id, "performed_on": session.performed_on, "set": set_view(row, db)} for row, _, session in rows]}


def analytics(db: Session, owner_id: str, weeks: int, *, end_date: date | None = None, bounded: bool = False) -> dict:
    today = end_date if end_date is not None else utc_now().date()
    start = today - timedelta(days=weeks * 7 - 1)
    sessions = list(db.scalars(select(WorkoutSession).where(
        WorkoutSession.owner_id == owner_id, WorkoutSession.deleted_at.is_(None),
        WorkoutSession.performed_on >= start, WorkoutSession.performed_on <= today,
    ).order_by(WorkoutSession.performed_on.desc(), WorkoutSession.created_at.desc(), WorkoutSession.id.desc())))
    muscle_names = dict(db.execute(select(MuscleGroup.id, MuscleGroup.name)).all())
    credits = defaultdict(float)
    muscle_volume = defaultdict(float)
    daily = {}
    prs = {}
    total_volume = 0.0
    efforts = []
    has_sets = False
    # Ordinary analytics retain all-time PRs; report snapshots restrict every row.
    statement = _active_sets(owner_id)
    if bounded:
        statement = statement.where(WorkoutSession.performed_on >= start, WorkoutSession.performed_on <= today)
    for row, block, session in db.execute(statement.order_by(WorkoutSession.performed_on, WorkoutSession.created_at, WorkoutSet.id)):
        if row.set_type == "warmup":
            continue
        estimate = row.metrics["estimated_1rm_kg"]
        name = block.exercise_snapshot["name"]
        if estimate is not None and (block.exercise_id not in prs or estimate > prs[block.exercise_id]["estimated_1rm_kg"]):
            prs[block.exercise_id] = {"exercise_id": block.exercise_id, "name": name,
                "estimated_1rm_kg": estimate, "performed_on": session.performed_on}
        if not start <= session.performed_on <= today:
            continue
        has_sets = True
        volume = _volume(row)
        total_volume += volume
        if row.set_type == "working":
            effort = row.rpe if row.rpe is not None else (10 - row.rir if row.rir is not None else None)
            if effort is not None:
                efforts.append(effort)
        hard = (row.repetitions is not None and row.repetitions > 0) or (row.duration_seconds is not None and row.duration_seconds > 0)
        for muscle in block.exercise_snapshot["muscles"]:
            muscle_id = muscle["muscle_id"]
            if hard:
                credits[muscle_id] += muscle["contribution"]
            muscle_volume[muscle_id] += volume * muscle["contribution"]
        key = (block.exercise_id, session.performed_on)
        point = daily.setdefault(key, {"name": name, "estimate": None, "volume": 0.0})
        point["volume"] += volume
        if estimate is not None:
            point["estimate"] = max(point["estimate"] or estimate, estimate)
    muscles = []
    for muscle_id in sorted(credits.keys() | muscle_volume.keys()):
        weekly = credits[muscle_id] / weeks
        landmark = weekly_volume_landmark(float(weekly))
        muscles.append({"id": muscle_id, "name": muscle_names.get(muscle_id, muscle_id), "hard_sets": credits[muscle_id],
            "weekly_hard_sets": weekly, "volume_kg": muscle_volume[muscle_id], "landmark": landmark.landmark, "recovery_warning": landmark.recovery_warning})
    curves = {}
    for (exercise_id, day), point in sorted(daily.items()):
        if point["estimate"] is None:
            continue
        curve = curves.setdefault(exercise_id, {"exercise_id": exercise_id, "name": point["name"], "points": []})
        curve["points"].append({"date": day, "estimated_1rm_kg": point["estimate"], "volume_kg": point["volume"]})
    fatigue = fatigue_index(FatigueInput(
        effort_rpe=sum(efforts) / len(efforts) if efforts else None,
        weekly_hard_sets=float(max(credits.values(), default=0.0) / weeks) if has_sets else None,
        sleep_hours=next((session.sleep_hours for session in sessions if session.sleep_hours is not None), None),
        soreness=next((session.soreness for session in sessions if session.soreness is not None), None),
    ))
    return {"weeks": weeks, "total_sessions": len(sessions), "total_volume_kg": total_volume, "muscles": muscles,
            "strength_curves": sorted(curves.values(), key=lambda item: (item["name"], item["exercise_id"])),
            "prs": sorted(prs.values(), key=lambda item: (-item["estimated_1rm_kg"], item["exercise_id"]))[:100], "fatigue": fatigue}

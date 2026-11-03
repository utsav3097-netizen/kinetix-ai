"""Capture deterministic comparisons and minimal training context at enqueue time."""
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import WorkoutExercise, WorkoutSession, WorkoutSet


def _set_data(row: WorkoutSet) -> dict:
    return {key: getattr(row, key) for key in ("ordinal", "set_type", "external_load_kg", "repetitions",
        "duration_seconds", "rpe", "rir", "rest_seconds", "bodyweight_kg", "metrics")}


def capture_context(db: Session, session: WorkoutSession, block: WorkoutExercise,
                    rows: list[WorkoutSet], progression: dict, selected: WorkoutSet | None = None) -> tuple[dict, dict]:
    previous_session = db.scalar(select(WorkoutSession).join(WorkoutExercise, WorkoutExercise.session_id == WorkoutSession.id).where(
        WorkoutSession.owner_id == session.owner_id, WorkoutExercise.owner_id == session.owner_id,
        WorkoutSession.deleted_at.is_(None), WorkoutExercise.deleted_at.is_(None),
        WorkoutExercise.exercise_id == block.exercise_id, WorkoutSession.id != session.id,
        or_(WorkoutSession.performed_on < session.performed_on,
            and_(WorkoutSession.performed_on == session.performed_on, WorkoutSession.created_at < session.created_at)),
    ).order_by(WorkoutSession.performed_on.desc(), WorkoutSession.created_at.desc(), WorkoutSession.id.desc()).limit(1))
    previous_rows = []
    if previous_session is not None:
        previous_block = db.scalar(select(WorkoutExercise).where(WorkoutExercise.owner_id == session.owner_id,
            WorkoutExercise.session_id == previous_session.id, WorkoutExercise.exercise_id == block.exercise_id,
            WorkoutExercise.deleted_at.is_(None)).order_by(WorkoutExercise.ordinal, WorkoutExercise.id).limit(1))
        if previous_block is not None:
            previous_rows = list(db.scalars(select(WorkoutSet).where(WorkoutSet.owner_id == session.owner_id,
                WorkoutSet.session_id == previous_session.id, WorkoutSet.block_id == previous_block.id,
                WorkoutSet.deleted_at.is_(None)).order_by(WorkoutSet.ordinal)))
    if selected is not None:
        previous = next((row for row in previous_rows if row.ordinal == selected.ordinal and row.set_type == selected.set_type), None)
        current_max = selected.metrics.get("estimated_1rm_kg")
        current_volume = selected.metrics.get("volume_kg")
        previous_max = previous.metrics.get("estimated_1rm_kg") if previous else None
        previous_volume = previous.metrics.get("volume_kg") if previous else None
        basis = "Same exercise, set ordinal and set type in the first block of the nearest earlier logged session."
        if previous is None:
            basis += " No comparable previous set is recorded."
    else:
        def totals(values):
            counted = [row for row in values if row.set_type != "warmup"]
            estimates = [row.metrics["estimated_1rm_kg"] for row in counted if row.metrics.get("estimated_1rm_kg") is not None]
            volumes = [row.metrics["volume_kg"] for row in counted if row.metrics.get("volume_kg") is not None]
            return max(estimates) if estimates else None, sum(volumes) if volumes else None
        current_max, current_volume = totals(rows)
        previous_max, previous_volume = totals(previous_rows)
        basis = "Non-warmup block volume and best estimated rep-based maximum versus the first same-exercise block in the nearest earlier logged session."
        if not previous_rows:
            basis += " No previous block with sets is recorded."
    comparison = {"estimated_1rm_kg": current_max, "previous_estimated_1rm_kg": previous_max,
        "one_rm_change_kg": current_max - previous_max if current_max is not None and previous_max is not None else None,
        "volume_kg": current_volume, "previous_volume_kg": previous_volume,
        "volume_change_kg": current_volume - previous_volume if current_volume is not None and previous_volume is not None else None,
        "comparison_basis": basis}
    context = {"exercise": {key: block.exercise_snapshot[key] for key in ("name", "equipment", "classification", "measurement_type")},
        "sets": [_set_data(selected)] if selected else [_set_data(row) for row in rows],
        "previous_sets": [_set_data(row) for row in previous_rows[:12]],
        "progression": progression, "comparison": comparison}
    return context, comparison

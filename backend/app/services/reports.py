"""Request-materialized period reports and explicitly requested immutable snapshots."""
from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update

from app.models import AthleteProfile, NutritionSourceRecord, Report, User, WeightCheckIn, WorkoutSession, WorkoutSourceRecord
from app.models.identity import utc_now
from app.planning_schemas import ReportData
from app.services import nutrition, workouts


def lock_owner(db, owner_id):
    # Serialize first creation as well as revision/version allocation on SQLite.
    if db.get_bind().dialect.name == "sqlite":
        db.execute(update(User).where(User.id == owner_id).values(id=User.id).execution_options(synchronize_session=False))
    else:
        db.scalar(select(User.id).where(User.id == owner_id).with_for_update())


def owned(db, model, owner_id, record_id):
    try:
        record_id = str(UUID(record_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, "Record not found") from None
    row = db.scalar(select(model).where(model.id == record_id, model.owner_id == owner_id))
    if row is None:
        raise HTTPException(404, "Record not found")
    return row


def summary(row):
    trend = row.data["nutrition"]
    return {"id": row.id, "kind": row.kind, "window_start": row.window_start, "window_end": row.window_end,
            "created_at": row.created_at, "revision": row.revision,
            "macro_adherence_score": trend["macro_adherence_score"],
            "logged_training_days": row.data["logged_training_days"], "logged_nutrition_days": trend["logged_days"],
            "expected_days": trend["expected_days"]}


def view(row):
    return {**summary(row), "data": row.data}


def _create(db, profile, kind, start, end):
    owner_id = profile.user_id
    weeks = ((end - start).days + 1) // 7
    stats = workouts.analytics(db, owner_id, weeks, end_date=end, bounded=True)
    trend = nutrition.trends(db, owner_id, weeks, end)
    sessions = list(db.scalars(select(WorkoutSession).where(
        WorkoutSession.owner_id == owner_id, WorkoutSession.deleted_at.is_(None),
        WorkoutSession.performed_on >= start, WorkoutSession.performed_on <= end)))
    observed = list(db.execute(workouts._active_sets(owner_id).where(
        WorkoutSession.performed_on >= start, WorkoutSession.performed_on <= end)))
    training_days = len({session.performed_on for row, _, session in observed if row.set_type != "warmup"})
    weights = list(db.scalars(select(WeightCheckIn).where(WeightCheckIn.user_id == owner_id,
        WeightCheckIn.measured_on >= start, WeightCheckIn.measured_on <= end).order_by(WeightCheckIn.measured_on)))
    source_ids = list(db.scalars(select(WorkoutSourceRecord.id).where(
        WorkoutSourceRecord.owner_id == owner_id, WorkoutSourceRecord.session_id.in_([row.id for row in sessions]))))
    source_ids += list(db.scalars(select(NutritionSourceRecord.id).where(NutritionSourceRecord.owner_id == owner_id,
        NutritionSourceRecord.date >= start, NutritionSourceRecord.date <= end)))
    source_ids += [row.id for row in weights]
    data = ReportData(
        **{key: stats[key] for key in ("total_sessions", "total_volume_kg", "muscles", "strength_curves", "fatigue")},
        weight_points=[{"date": row.measured_on, "weight_kg": row.weight_kg} for row in weights],
        nutrition=trend, source_record_ids=sorted(source_ids), history_sufficient=training_days >= 2,
        explanation=f"{training_days} observed training days and {trend['logged_days']} meal-logged days out of {weeks * 7}. "
                    "Missing nutrition days are unknown, not zero scores. Weight points are dated check-ins only. "
                    "Muscle landmarks use weekly-average set credits. Reports are frozen snapshots materialized on request, not background scheduled jobs. "
                    "Exercise progression still requires comparable working history on distinct dates.",
    ).model_dump(mode="json")
    data["logged_training_days"] = training_days
    revision = (db.scalar(select(func.max(Report.revision)).where(Report.owner_id == owner_id,
                Report.kind == kind, Report.window_start == start, Report.window_end == end)) or 0) + 1
    row = Report(owner_id=owner_id, kind=kind, window_start=start, window_end=end, revision=revision, data=data)
    db.add(row)
    db.flush()
    return row


def create_snapshot(db, profile, payload):
    end = nutrition.validate_date(payload.end_date)
    try:
        start = end - timedelta(days=payload.weeks * 7 - 1)
    except OverflowError:
        raise HTTPException(422, "Report window precedes the supported calendar") from None
    lock_owner(db, profile.user_id)
    return _create(db, profile, "snapshot", start, end)


def materialize_due(db, profile):
    today = utc_now().date()
    origin = profile.created_at.date()
    previous_sunday = today - timedelta(days=today.weekday() + 1)
    periods = []
    if previous_sunday >= origin:
        periods.append(("weekly", previous_sunday - timedelta(days=6), previous_sunday))
    duration = 7 * profile.analysis_weeks
    completed = (today - origin).days // duration
    if completed > 0:
        start = origin + timedelta(days=(completed - 1) * duration)
        periods.append(("analysis", start, start + timedelta(days=duration - 1)))
    if not periods:
        return
    lock_owner(db, profile.user_id)
    for kind, start, end in periods:
        exists = db.scalar(select(Report.id).where(Report.owner_id == profile.user_id,
            Report.kind == kind, Report.window_start == start, Report.window_end == end))
        if exists is None:
            _create(db, profile, kind, start, end)


def list_reports(db, profile, query):
    materialize_due(db, profile)
    statement = select(Report).where(Report.owner_id == profile.user_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(statement.order_by(Report.created_at.desc(), Report.id.desc()).offset(query.offset).limit(query.limit))
    return {"items": [summary(row) for row in rows], "total": total}

"""Current workout projections backed by an append-only source journal."""
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, Uuid, event, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.identity import new_id, utc_now


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"
    __table_args__ = (
        CheckConstraint("bodyweight_kg BETWEEN 20 AND 500", name="ck_workout_weight"),
        CheckConstraint("revision >= 0", name="ck_workout_revision"),
        Index("ix_workout_owner_date", "owner_id", "performed_on"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    performed_on: Mapped[date] = mapped_column(Date, nullable=False)
    bodyweight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    sleep_hours: Mapped[float | None] = mapped_column(Float)
    soreness: Mapped[float | None] = mapped_column(Float)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class WorkoutExercise(Base):
    __tablename__ = "workout_exercises"
    __table_args__ = (
        CheckConstraint("ordinal >= 1", name="ck_workout_exercise_ordinal"),
        CheckConstraint("target_min_reps >= 1 AND target_max_reps >= target_min_reps", name="ck_workout_rep_range"),
        Index("uq_workout_exercise_ordinal", "session_id", "ordinal", unique=True, sqlite_where=text("deleted_at IS NULL"), postgresql_where=text("deleted_at IS NULL")),
        Index("ix_workout_exercise_owner_reference", "owner_id", "exercise_id"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    session_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("workout_sessions.id", ondelete="RESTRICT"), nullable=False)
    exercise_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("exercises.id", ondelete="RESTRICT"), nullable=False)
    exercise_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    target_min_reps: Mapped[int] = mapped_column(Integer, nullable=False)
    target_max_reps: Mapped[int] = mapped_column(Integer, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkoutSourceRecord(Base):
    __tablename__ = "workout_source_records"
    __table_args__ = (
        UniqueConstraint("session_id", "revision", name="uq_workout_source_revision"),
        CheckConstraint("revision >= 1", name="ck_workout_source_revision"),
        CheckConstraint("entity_type IN ('session', 'exercise', 'set')", name="ck_workout_source_entity"),
        CheckConstraint("action IN ('create', 'update', 'delete', 'complete')", name="ck_workout_source_action"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    session_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("workout_sessions.id", ondelete="RESTRICT"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(12), nullable=False)
    entity_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    action: Mapped[str] = mapped_column(String(12), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class WorkoutSet(Base):
    __tablename__ = "workout_sets"
    __table_args__ = (
        CheckConstraint("ordinal >= 1", name="ck_workout_set_ordinal"),
        CheckConstraint("set_type IN ('warmup', 'working', 'drop_set', 'failure')", name="ck_workout_set_type"),
        CheckConstraint("external_load_kg BETWEEN 0 AND 1000", name="ck_workout_set_load"),
        CheckConstraint("(repetitions IS NOT NULL AND repetitions BETWEEN 0 AND 1000 AND duration_seconds IS NULL) OR (repetitions IS NULL AND duration_seconds IS NOT NULL AND duration_seconds BETWEEN 1 AND 7200)", name="ck_workout_set_measurement"),
        Index("uq_workout_set_ordinal", "block_id", "ordinal", unique=True, sqlite_where=text("deleted_at IS NULL"), postgresql_where=text("deleted_at IS NULL")),
        Index("ix_workout_set_session", "owner_id", "session_id"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    session_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("workout_sessions.id", ondelete="RESTRICT"), nullable=False)
    block_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("workout_exercises.id", ondelete="RESTRICT"), nullable=False)
    source_record_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("workout_source_records.id", ondelete="RESTRICT"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    set_type: Mapped[str] = mapped_column(String(12), nullable=False)
    external_load_kg: Mapped[float] = mapped_column(Float, nullable=False)
    repetitions: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    rpe: Mapped[float | None] = mapped_column(Float)
    rir: Mapped[float | None] = mapped_column(Float)
    rest_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    bodyweight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


@event.listens_for(WorkoutSourceRecord, "before_update")
@event.listens_for(WorkoutSourceRecord, "before_delete")
def reject_source_mutation(mapper, connection, target):
    raise ValueError("Workout source records are append-only")

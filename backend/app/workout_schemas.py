"""Validated workout inputs and authoritative response shapes."""
from datetime import date, datetime, timezone
from math import isclose
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.services.fitness_algorithms import FatigueResult, ProgressionResult


class WorkoutModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, from_attributes=True)


class SessionInput(WorkoutModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    performed_on: date
    bodyweight_kg: float = Field(ge=20, le=500)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    soreness: float | None = Field(default=None, ge=0, le=10)

    @model_validator(mode="after")
    def logged_date(self) -> Self:
        if self.performed_on > datetime.now(timezone.utc).date():
            raise ValueError("Workout date cannot be in the future")
        return self


class BlockInput(WorkoutModel):
    ordinal: int = Field(ge=1, strict=True)
    target_min_reps: int = Field(ge=1, strict=True)
    target_max_reps: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def ordered_range(self) -> Self:
        if self.target_max_reps < self.target_min_reps:
            raise ValueError("Maximum target reps cannot be below minimum target reps")
        return self


class BlockCreate(BlockInput):
    exercise_id: str


class SetInput(WorkoutModel):
    ordinal: int = Field(ge=1, strict=True)
    set_type: Literal["warmup", "working", "drop_set", "failure"]
    external_load_kg: float = Field(ge=0, le=1000)
    repetitions: int | None = Field(default=None, ge=0, le=1000, strict=True)
    duration_seconds: int | None = Field(default=None, ge=1, le=7200, strict=True)
    rpe: float | None = Field(default=None, ge=1, le=10)
    rir: float | None = Field(default=None, ge=0, le=9)
    rest_seconds: int = Field(ge=0, le=7200, strict=True)

    @model_validator(mode="after")
    def measurement_and_effort(self) -> Self:
        if (self.repetitions is None) == (self.duration_seconds is None):
            raise ValueError("Supply repetitions or duration_seconds, never both")
        if self.rpe is not None and self.rir is not None and not isclose(self.rpe, 10 - self.rir, rel_tol=0, abs_tol=1e-9):
            raise ValueError("RPE and RIR must agree: RPE = 10 - RIR")
        return self


class SetMetrics(WorkoutModel):
    effective_load_kg: float
    volume_kg: float | None
    estimated_1rm_kg: float | None
    one_rm_formula: Literal["epley", "brzycki"] | None
    estimate_unavailable_reason: str | None


class SetView(SetInput):
    id: str
    source_record_id: str
    bodyweight_kg: float
    metrics: SetMetrics
    insight_id: str | None = None


class MuscleSnapshot(WorkoutModel):
    muscle_id: str
    contribution: float


class ExerciseSnapshot(WorkoutModel):
    name: str
    equipment: str
    biomechanical_multiplier: float
    classification: Literal["upper_compound", "lower_compound", "isolation"]
    measurement_type: Literal["reps", "seconds"]
    muscles: list[MuscleSnapshot]


class BlockView(BlockInput):
    id: str
    exercise_id: str
    exercise_snapshot: ExerciseSnapshot
    completed: bool
    sets: list[SetView]
    progression: ProgressionResult
    insight_id: str | None = None


class SessionSummary(WorkoutModel):
    id: str
    title: str
    performed_on: date
    bodyweight_kg: float
    total_volume_kg: float
    exercise_count: int
    set_count: int
    revision: int


class SessionView(SessionSummary):
    sleep_hours: float | None
    soreness: float | None
    exercises: list[BlockView]


class SessionPage(WorkoutModel):
    items: list[SessionSummary]
    total: int


class PageQuery(WorkoutModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class SessionQuery(PageQuery):
    from_date: date | None = None
    to_date: date | None = None

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("from_date must not follow to_date")
        return self


class SourceView(WorkoutModel):
    id: str
    revision: int
    entity_type: str
    entity_id: str
    action: str
    payload: dict[str, Any]
    created_at: datetime


class SourcePage(WorkoutModel):
    items: list[SourceView]
    total: int


class ExerciseHistoryItem(WorkoutModel):
    session_id: str
    performed_on: date
    set: SetView


class ExerciseHistoryPage(WorkoutModel):
    items: list[ExerciseHistoryItem]
    total: int


class MuscleVolume(WorkoutModel):
    id: str
    name: str
    hard_sets: float
    weekly_hard_sets: float
    volume_kg: float
    landmark: str
    recovery_warning: bool


class StrengthPoint(WorkoutModel):
    date: date
    estimated_1rm_kg: float
    volume_kg: float


class StrengthCurve(WorkoutModel):
    exercise_id: str
    name: str
    points: list[StrengthPoint]


class PersonalRecord(WorkoutModel):
    exercise_id: str
    name: str
    estimated_1rm_kg: float
    performed_on: date


class WorkoutAnalytics(WorkoutModel):
    weeks: int
    total_sessions: int
    total_volume_kg: float
    muscles: list[MuscleVolume]
    strength_curves: list[StrengthCurve]
    prs: list[PersonalRecord]
    fatigue: FatigueResult

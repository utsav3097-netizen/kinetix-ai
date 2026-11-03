"""Only user-editable prescriptions enter commands; evidence is server-owned."""
from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.nutrition_schemas import FoodSnapshot, Nutrients, Slot, Trends
from app.services.fitness_algorithms import FatigueResult, MacroTargets, Phase, ProgressionResult
from app.workout_schemas import ExerciseSnapshot, MuscleVolume, StrengthCurve

Path = Literal["cutting", "bulking", "recomp", "powerbuilding", "classic_physique", "athletic_hybrid"]


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class ReportInput(Command):
    weeks: int = Field(ge=1, le=4, strict=True)
    end_date: date


class DraftInput(Command):
    path: Path
    starts_on: date
    report_id: str | None = None

    @field_validator("report_id")
    @classmethod
    def valid_id(cls, value):
        return str(UUID(value)) if value is not None else None


class ExerciseEdit(Command):
    exercise_id: str
    sets: int = Field(ge=1, le=20, strict=True)
    target_min_reps: int | None = Field(default=None, ge=1, le=36, strict=True)
    target_max_reps: int | None = Field(default=None, ge=1, le=36, strict=True)
    duration_seconds: int | None = Field(default=None, ge=1, le=3600, strict=True)
    external_load_kg: float = Field(ge=0, le=1000)
    rest_seconds: int = Field(ge=0, le=1800, strict=True)

    @field_validator("exercise_id")
    @classmethod
    def valid_id(cls, value):
        return str(UUID(value))

    @model_validator(mode="after")
    def measurement(self) -> Self:
        if self.duration_seconds is not None:
            if self.target_min_reps is not None or self.target_max_reps is not None:
                raise ValueError("Timed prescriptions cannot include repetitions")
        elif self.target_min_reps is None or self.target_max_reps is None or self.target_min_reps > self.target_max_reps:
            raise ValueError("Repetition prescriptions need an ordered min/max range")
        return self


class DayEdit(Command):
    date: date
    training_day: bool = Field(strict=True)
    label: str = Field(min_length=1, max_length=120)
    exercises: list[ExerciseEdit] = Field(max_length=20)
    protein_g: float = Field(gt=0, le=1200)
    carbs_g: float = Field(gt=0, le=4000)
    fat_g: float = Field(gt=0, le=600)

    @model_validator(mode="after")
    def workout(self) -> Self:
        if self.training_day != bool(self.exercises):
            raise ValueError("Training days require exercises; rest days cannot prescribe exercises")
        ids = [row.exercise_id for row in self.exercises]
        if len(set(ids)) != len(ids):
            raise ValueError("An exercise may appear only once per day")
        return self


class PlanEditInput(Command):
    title: str = Field(min_length=1, max_length=120)
    days: list[DayEdit] = Field(min_length=7, max_length=7)


class AcceptInput(Command):
    pass


class WeightPoint(BaseModel):
    date: date
    weight_kg: float


class ReportData(BaseModel):
    total_sessions: int
    total_volume_kg: float
    muscles: list[MuscleVolume]
    strength_curves: list[StrengthCurve]
    weight_points: list[WeightPoint]
    nutrition: Trends
    fatigue: FatigueResult
    source_record_ids: list[str]
    history_sufficient: bool
    explanation: str


class ReportSummary(BaseModel):
    id: str
    kind: Literal["weekly", "analysis", "snapshot"]
    window_start: date
    window_end: date
    created_at: datetime
    revision: int
    macro_adherence_score: float | None
    logged_training_days: int
    logged_nutrition_days: int
    expected_days: int


class ReportView(ReportSummary):
    data: ReportData


class ReportPage(BaseModel):
    items: list[ReportSummary]
    total: int


class PathOption(BaseModel):
    id: Path
    title: str
    phase: Phase
    description: str
    evidence: str
    assessment_required: bool


class PathPage(BaseModel):
    items: list[PathOption]
    history_sufficient: bool
    report_id: str | None


class SampleItem(BaseModel):
    food_id: str
    grams: float
    food_snapshot: FoodSnapshot
    nutrients: Nutrients


class SampleMeal(BaseModel):
    slot: Slot
    title: str
    items: list[SampleItem]
    totals: Nutrients


class PlanExercise(BaseModel):
    exercise_id: str
    exercise_snapshot: ExerciseSnapshot
    sets: int
    target_min_reps: int | None
    target_max_reps: int | None
    duration_seconds: int | None
    external_load_kg: float
    effective_load_kg: float
    rest_seconds: int
    progression: ProgressionResult | None
    observed_1rm_kg: float | None
    observed_velocity_kg_per_week: float | None
    rationale: str


class PlanDay(BaseModel):
    date: date
    training_day: bool
    label: str
    exercises: list[PlanExercise]
    targets: MacroTargets
    sample_meals: list[SampleMeal]
    sample_totals: Nutrients


class ProfileSnapshot(BaseModel):
    bodyweight_kg: float
    tdee_kcal: float
    phase: Phase


class PlanEvidence(BaseModel):
    report_id: str | None
    training_days: int
    notes: list[str]


class PlanData(BaseModel):
    path: Path
    title: str
    assessment_required: bool
    explanation: str
    profile_snapshot: ProfileSnapshot
    evidence: PlanEvidence
    days: list[PlanDay]


class DraftSummary(BaseModel):
    id: str
    path: Path
    title: str
    starts_on: date
    ends_on: date
    assessment_required: bool
    created_at: datetime
    parent_version_id: str | None
    based_on_draft_id: str | None


class DraftView(DraftSummary):
    data: PlanData


class DraftPage(BaseModel):
    items: list[DraftSummary]
    total: int


class VersionSummary(BaseModel):
    id: str
    version: int
    draft_id: str
    accepted_at: datetime
    title: str
    path: Path
    starts_on: date
    ends_on: date


class VersionView(VersionSummary):
    data: PlanData


class VersionPage(BaseModel):
    items: list[VersionSummary]
    total: int

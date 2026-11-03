"""Validated nutrition commands and public deterministic views."""
from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.fitness_algorithms import MacroTargets, Phase, ProteinRange

Slot = Literal["breakfast", "pre_workout", "post_workout", "lunch", "dinner", "snacks"]
Status = Literal["below", "within", "above", "unlogged"]
NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Score = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False)


class DayInput(Command):
    training_day: bool


class ItemInput(Command):
    food_id: str
    grams: float = Field(gt=0, le=5000)
    item_id: str | None = None

    @field_validator("food_id", "item_id")
    @classmethod
    def valid_id(cls, value: str | None) -> str | None:
        return str(UUID(value)) if value is not None else None


class MealInput(DayInput):
    slot: Slot
    title: str = Field(min_length=1, max_length=120)
    time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    items: list[ItemInput] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_items(self) -> Self:
        ids = [item.item_id for item in self.items if item.item_id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("An existing meal item may appear only once")
        return self


class WaterInput(DayInput):
    amount_ml: int = Field(ge=1, le=10000)


class PageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class Nutrients(BaseModel):
    calories_kcal: NonNegative
    protein_g: NonNegative
    carbs_g: NonNegative
    fat_g: NonNegative
    fiber_g: NonNegative


class FoodSnapshot(BaseModel):
    name: str
    basis_grams: Literal[100]
    calories: NonNegative
    protein_g: NonNegative
    carbs_g: NonNegative
    fat_g: NonNegative
    fiber_g: NonNegative


class ItemView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    food_id: str
    grams: float
    food_snapshot: FoodSnapshot
    nutrients: Nutrients


class MealView(BaseModel):
    id: str
    date: date
    slot: Slot
    title: str
    time: str
    items: list[ItemView]
    totals: Nutrients
    source_record_id: str


class WaterView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    amount_ml: int
    created_at: datetime


class ProteinAdherence(BaseModel):
    actual_g: NonNegative
    min_g: NonNegative
    max_g: NonNegative
    status: Status
    score: Score | None


class TargetAdherence(BaseModel):
    actual: NonNegative
    target: NonNegative
    status: Status
    score: Score | None


class ProteinGap(BaseModel):
    from_time: str
    to_time: str
    hours: NonNegative


class ProteinTiming(BaseModel):
    status: Literal["available", "insufficient_data"]
    gaps: list[ProteinGap]


class Adherence(BaseModel):
    macro_score: Score | None
    protein: ProteinAdherence
    calories: TargetAdherence
    carbs: TargetAdherence
    fat: TargetAdherence
    caloric_drift_kcal: float | None
    protein_timing: ProteinTiming


class DayTotals(Nutrients):
    water_ml: int


class DayView(BaseModel):
    date: date
    training_day: bool
    persisted: bool
    plan_version_id: str | None = None
    phase: Phase
    bodyweight_kg: float
    targets: MacroTargets
    protein_range_g: ProteinRange
    totals: DayTotals
    meals: list[MealView]
    water_entries: list[WaterView]
    adherence: Adherence


class SourceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    revision: int
    entity_type: Literal["day", "meal", "water"]
    entity_id: str
    action: Literal["create", "update", "delete"]
    payload: dict
    created_at: datetime


class SourcePage(BaseModel):
    items: list[SourceView]
    total: int


class TrendPoint(BaseModel):
    date: date
    logged: bool
    calories_kcal: NonNegative | None
    target_calories_kcal: NonNegative | None
    protein_g: NonNegative | None
    carbs_g: NonNegative | None
    fat_g: NonNegative | None
    macro_score: Score | None


class Trends(BaseModel):
    window_start: date
    window_end: date
    logged_days: int
    expected_days: int
    coverage_percent: Score
    averages: Nutrients | None
    macro_adherence_score: Score | None
    caloric_drift_kcal: float | None
    protein_timing_gap_count: int
    points: list[TrendPoint]

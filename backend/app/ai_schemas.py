"""Strict provider outputs and owner-scoped asynchronous AI response contracts."""
from datetime import date as Date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.nutrition_schemas import FoodSnapshot, Nutrients, Slot

Text = Annotated[str, Field(min_length=1, max_length=600)]
Number = Annotated[float, Field(allow_inf_nan=False)]


class Structured(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class SetInsight(Structured):
    summary: Text
    form_cue: Text
    tempo_cue: Text
    next_action: Literal["increase_weight", "increase_reps", "deload", "hold", "insufficient_data"]
    disclaimer: Text


class ExtractedItem(Structured):
    label: Annotated[str, Field(min_length=1, max_length=200)]
    source_text: Annotated[str, Field(min_length=1, max_length=2000)]
    food_id: Annotated[str, Field(min_length=1, max_length=36)] | None
    grams: Annotated[float, Field(gt=0, le=5000)] | None


class ExtractedMeal(Structured):
    items: list[ExtractedItem] = Field(min_length=1, max_length=50)


class MealParseInput(Structured):
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    date: Date = Field(strict=False)
    training_day: bool
    slot: Slot
    title: Annotated[str, Field(min_length=1, max_length=120)]
    time: Annotated[str, Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]


class ParsedItem(Structured):
    label: Annotated[str, Field(min_length=1, max_length=200)]
    food_id: str | None
    grams: Annotated[float, Field(gt=0, le=5000)] | None
    food_snapshot: FoodSnapshot | None
    nutrients: Nutrients | None
    resolution: Literal["resolved", "unresolved"]
    reason: Text | None


class ParsedMealDraft(Structured):
    date: Date
    training_day: bool
    title: Annotated[str, Field(min_length=1, max_length=120)]
    slot: Slot
    time: Annotated[str, Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")]
    items: list[ParsedItem] = Field(min_length=1, max_length=50)
    totals: Nutrients


class InsightComparison(Structured):
    estimated_1rm_kg: Number | None
    previous_estimated_1rm_kg: Number | None
    one_rm_change_kg: Number | None
    volume_kg: Number | None
    previous_volume_kg: Number | None
    volume_change_kg: Number | None
    comparison_basis: Text


class InsightView(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: str
    kind: Literal["set", "exercise_block", "meal_parse"]
    status: Literal["pending", "success", "unavailable"]
    result: SetInsight | ParsedMealDraft | None
    comparison: InsightComparison | None
    reason: str | None
    provider: str | None
    model: str | None
    created_at: datetime
    finished_at: datetime | None
    latency_ms: int | None

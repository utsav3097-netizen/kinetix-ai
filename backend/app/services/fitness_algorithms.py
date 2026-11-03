"""Authoritative, deterministic fitness estimates; no persistence or AI dependencies.

Policy defaults not specified by the source formulas: baseline/calisthenics use
maintenance energy, 2 g/kg protein and .8 g/kg fat; recomp uses .8 g/kg fat.
Fatigue is a non-medical heuristic, not a validated diagnosis: effort maps RPE
1..10 to 0..1, volume saturates at 22 weekly hard sets, sleep deficit maps 8..0
hours to 0..1, and soreness maps 0..10 to 0..1. Available signals alone are
weighted .35/.30/.20/.15 and normalized. Missing signals are always disclosed.
"""

from math import isclose
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
HardSets = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
Phase = Literal["baseline_assessment", "cutting", "lean_bulking", "body_recomposition", "calisthenics_strength"]
Classification = Literal["upper_compound", "lower_compound", "isolation"]


class AlgorithmModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class EnergyInput(AlgorithmModel):
    weight_kg: float = Field(ge=20, le=500)
    height_cm: float = Field(ge=50, le=250)
    age: int = Field(ge=13, le=100)
    biological_sex: Literal["male", "female"]
    # Match the existing profile contract, including high-activity athletes.
    activity_multiplier: float = Field(ge=1.2, le=2.4)


class EnergyResult(AlgorithmModel):
    bmr_kcal: Positive
    tdee_kcal: Positive


def calculate_energy(data: EnergyInput) -> EnergyResult:
    offset = 5 if data.biological_sex == "male" else -161
    bmr = 10 * data.weight_kg + 6.25 * data.height_cm - 5 * data.age + offset
    return EnergyResult(bmr_kcal=bmr, tdee_kcal=bmr * data.activity_multiplier)


class MacroInput(AlgorithmModel):
    weight_kg: Positive
    tdee_kcal: Positive
    phase: Phase
    training_day: bool = True


class MacroTargets(AlgorithmModel):
    calories_kcal: Positive
    base_calories_kcal: Positive
    protein_g: Positive
    carbs_g: Positive
    fat_g: Positive
    carb_cycle_factor: Positive


def phase_macros(data: MacroInput) -> MacroTargets:
    base = data.tdee_kcal
    protein_factor, fat_factor, cycle = 2.0, 0.8, 1.0
    if data.phase == "cutting":
        base -= 500
        protein_factor = 2.2
    elif data.phase == "lean_bulking":
        base += 350
        fat_factor = 1.0
    elif data.phase == "body_recomposition":
        protein_factor = 2.3
        cycle = 1.1 if data.training_day else 0.9
    protein = protein_factor * data.weight_kg
    fat = fat_factor * data.weight_kg
    remaining = base - 4 * protein - 9 * fat
    if remaining <= 0:
        raise ValueError("Macro allocation must leave positive carbohydrate calories")
    carbs = remaining / 4 * cycle
    return MacroTargets(
        calories_kcal=4 * protein + 9 * fat + 4 * carbs,
        base_calories_kcal=base,
        protein_g=protein,
        carbs_g=carbs,
        fat_g=fat,
        carb_cycle_factor=cycle,
    )


class ProteinRange(AlgorithmModel):
    min: Positive
    max: Positive


_positive = TypeAdapter(Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)])
_nonnegative = TypeAdapter(Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)])
_hard_sets = TypeAdapter(HardSets)


def protein_adherence_range(weight_kg: float) -> ProteinRange:
    weight = _positive.validate_python(weight_kg)
    return ProteinRange(min=1.8 * weight, max=2.4 * weight)


class EffectiveLoadInput(AlgorithmModel):
    bodyweight_kg: Positive
    biomechanical_multiplier: float = Field(ge=0, le=1)
    external_load_kg: NonNegative = 0.0


def effective_load(data: EffectiveLoadInput) -> float:
    return _nonnegative.validate_python(data.bodyweight_kg * data.biomechanical_multiplier + data.external_load_kg)


class OneRepMaxInput(AlgorithmModel):
    load_kg: Positive
    reps: int = Field(ge=1, lt=37)


class OneRepMaxResult(AlgorithmModel):
    estimate_kg: Positive
    formula: Literal["epley", "brzycki"]


def estimate_one_rep_max(data: OneRepMaxInput) -> OneRepMaxResult:
    if data.reps <= 10:
        return OneRepMaxResult(estimate_kg=data.load_kg * (1 + data.reps / 30), formula="epley")
    return OneRepMaxResult(estimate_kg=data.load_kg * (36 / (37 - data.reps)), formula="brzycki")


class ProgressionSet(AlgorithmModel):
    reps: int = Field(ge=0)
    rpe: float | None = Field(default=None, ge=1, le=10)
    rir: float | None = Field(default=None, ge=0, le=9)

    @model_validator(mode="after")
    def consistent_effort(self) -> Self:
        if self.rpe is not None and self.rir is not None and not isclose(self.rpe, 10 - self.rir, rel_tol=0, abs_tol=1e-9):
            raise ValueError("RPE and RIR must agree: RPE = 10 - RIR")
        return self

    @property
    def effort_rpe(self) -> float | None:
        return self.rpe if self.rpe is not None else (10 - self.rir if self.rir is not None else None)


class ProgressionPolicy(AlgorithmModel):
    upper_increment_kg: Positive = 2.5
    lower_increment_kg: Positive = 5.0
    deload_multiplier: float = Field(default=0.9, gt=0, lt=1)


class ProgressionInput(AlgorithmModel):
    # For bodyweight movements this is external load, not effective bodyweight.
    current_weight_kg: NonNegative
    target_min_reps: int = Field(ge=1)
    target_max_reps: int = Field(ge=1)
    classification: Classification
    working_sets: list[ProgressionSet]
    previous_working_sets: list[ProgressionSet] | None = None
    policy: ProgressionPolicy = Field(default_factory=ProgressionPolicy)

    @model_validator(mode="after")
    def ordered_range(self) -> Self:
        if self.target_max_reps < self.target_min_reps:
            raise ValueError("Maximum target reps cannot be below minimum target reps")
        return self


class ProgressionResult(AlgorithmModel):
    state: Literal["increase_weight", "increase_reps", "deload", "hold", "insufficient_data"]
    next_weight_kg: NonNegative
    target_reps: int = Field(ge=1)
    reason: str
    recovery_check: bool = False


def recommend_progression(data: ProgressionInput) -> ProgressionResult:
    def result(state: str, reason: str, *, weight: float | None = None, reps: int | None = None, recovery: bool = False) -> ProgressionResult:
        return ProgressionResult(
            state=state,
            next_weight_kg=data.current_weight_kg if weight is None else weight,
            target_reps=data.target_min_reps if reps is None else reps,
            reason=reason,
            recovery_check=recovery,
        )

    if not data.working_sets or any(item.effort_rpe is None for item in data.working_sets):
        return result("insufficient_data", "Working sets and RPE or RIR for every set are required; no effort is inferred.")
    if data.previous_working_sets and any(item.effort_rpe is None for item in data.previous_working_sets):
        return result("insufficient_data", "The supplied previous session has missing effort; provide RPE or RIR for every working set.")
    failed_current = any(item.reps < data.target_min_reps for item in data.working_sets)
    failed_previous = bool(data.previous_working_sets) and any(item.reps < data.target_min_reps for item in data.previous_working_sets)
    if failed_current and failed_previous:
        return result("deload", "Minimum reps were missed in two consecutive sessions; reduce load and check recovery.", weight=data.current_weight_kg * data.policy.deload_multiplier, recovery=True)
    if all(item.reps >= data.target_max_reps and item.effort_rpe <= 8 for item in data.working_sets):
        increment = data.policy.lower_increment_kg if data.classification == "lower_compound" else data.policy.upper_increment_kg
        return result("increase_weight", "All working sets reached the top of the rep range at RPE 8 or below.", weight=data.current_weight_kg + increment)
    if not failed_current and any(item.effort_rpe >= 9.5 for item in data.working_sets):
        return result("increase_reps", "Every set met the minimum and at least one reached RPE 9.5–10; hold load and target one rep above the weakest completed set.", reps=min(item.reps for item in data.working_sets) + 1)
    return result("hold", "The supplied working sets do not meet a load increase, rep increase, or two-session deload rule.")


class VolumeLandmark(AlgorithmModel):
    hard_sets: HardSets
    landmark: Literal["below_maintenance", "MV", "maintenance", "MEV", "building", "MAV", "high", "MRV"]
    recovery_warning: bool
    explanation: str


def weekly_volume_landmark(hard_sets: float) -> VolumeLandmark:
    count = _hard_sets.validate_python(hard_sets)
    if count < 6:
        landmark, explanation = "below_maintenance", "Below the 6-set maintenance landmark."
    elif count == 6:
        landmark, explanation = "MV", "Maintenance volume: 6 hard sets per week."
    elif count < 8:
        landmark, explanation = "maintenance", "Between MV and MEV; no additional threshold is inferred."
    elif count <= 10:
        landmark, explanation = "MEV", "Minimum effective volume: 8–10 hard sets per week."
    elif count < 12:
        landmark, explanation = "building", "Between MEV and MAV; no additional threshold is inferred."
    elif count <= 20:
        landmark, explanation = "MAV", "Maximum adaptive volume: 12–20 hard sets per week."
    elif count <= 22:
        landmark, explanation = "high", "Above MAV but not above the 22-set recovery-warning threshold."
    else:
        landmark, explanation = "MRV", "Above 22 hard sets: elevated overtraining risk; review recovery. This is not a diagnosis."
    return VolumeLandmark(hard_sets=count, landmark=landmark, recovery_warning=count > 22, explanation=explanation)


FatigueSignal = Literal["effort_rpe", "weekly_hard_sets", "sleep_hours", "soreness"]


class FatigueInput(AlgorithmModel):
    effort_rpe: float | None = Field(default=None, ge=1, le=10)
    weekly_hard_sets: HardSets | None = None
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    soreness: float | None = Field(default=None, ge=0, le=10)


class FatigueResult(AlgorithmModel):
    state: Literal["available", "unavailable"]
    score: float | None = Field(default=None, ge=0, le=100)
    missing_inputs: list[FatigueSignal]
    components: dict[FatigueSignal, Annotated[float, Field(ge=0, le=1)]]
    disclaimer: str


def fatigue_index(data: FatigueInput) -> FatigueResult:
    weights = {"effort_rpe": 0.35, "weekly_hard_sets": 0.30, "sleep_hours": 0.20, "soreness": 0.15}
    components = {}
    if data.effort_rpe is not None:
        components["effort_rpe"] = (data.effort_rpe - 1) / 9
    if data.weekly_hard_sets is not None:
        components["weekly_hard_sets"] = min(data.weekly_hard_sets, 22) / 22
    if data.sleep_hours is not None:
        components["sleep_hours"] = max(0.0, (8 - data.sleep_hours) / 8)
    if data.soreness is not None:
        components["soreness"] = data.soreness / 10
    missing = [name for name in weights if name not in components]
    score = None
    if components:
        score = min(100.0, max(0.0, 100 * sum(weights[name] * value for name, value in components.items()) / sum(weights[name] for name in components)))
    return FatigueResult(
        state="available" if components else "unavailable",
        score=score,
        missing_inputs=missing,
        components=components,
        disclaimer="Non-medical policy estimate, not a diagnosis. Missing signals are excluded, not assumed to be zero.",
    )

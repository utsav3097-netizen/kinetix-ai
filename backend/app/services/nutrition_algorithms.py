"""Pure recorded-intake signals, not medical assessments.

Protein scores use the inclusive 1.8–2.4 g/kg range. Energy, carbohydrate,
and fat status use an inclusive ±10% band; their score decreases linearly
with absolute relative target error. The macro score equally weights all four.
No meals means unknown adherence, not a claim of zero intake. Timing considers
only consecutive recorded protein meals and never invents an overnight gap.
"""
from collections.abc import Sequence
from math import fsum

from app.nutrition_schemas import Adherence, Nutrients, ProteinAdherence, ProteinGap, ProteinTiming, TargetAdherence
from app.services.fitness_algorithms import MacroTargets, ProteinRange

NUTRIENT_KEYS = ("calories_kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")


def sum_nutrients(values: Sequence[dict]) -> dict:
    return {key: fsum(value[key] for value in values) for key in NUTRIENT_KEYS}


def scale_snapshot(snapshot: dict, grams: float) -> dict:
    factor = grams / snapshot["basis_grams"]
    return {key: snapshot["calories" if key == "calories_kcal" else key] * factor for key in NUTRIENT_KEYS}


def _target(actual: float, target: float, logged: bool) -> TargetAdherence:
    status = "unlogged" if not logged else "below" if actual < target * .9 else "above" if actual > target * 1.1 else "within"
    return TargetAdherence(actual=actual, target=target, status=status,
                           score=max(0.0, min(100.0, 100 * (1 - abs(actual - target) / target))) if logged else None)


def protein_timing(meals: Sequence[tuple[str, float]]) -> ProteinTiming:
    times = sorted(time for time, protein_g in meals if protein_g > 0)
    gaps = []
    for start, end in zip(times, times[1:]):
        start_minutes = int(start[:2]) * 60 + int(start[3:])
        end_minutes = int(end[:2]) * 60 + int(end[3:])
        if end_minutes - start_minutes > 300:
            gaps.append(ProteinGap(from_time=start, to_time=end, hours=(end_minutes - start_minutes) / 60))
    return ProteinTiming(status="available" if len(times) >= 2 else "insufficient_data", gaps=gaps)


def calculate_adherence(totals: Nutrients, targets: MacroTargets, protein_range: ProteinRange,
                        meals: Sequence[tuple[str, float]]) -> Adherence:
    logged = bool(meals)
    actual = totals.protein_g
    status, score = "unlogged", None
    if logged:
        if actual < protein_range.min:
            status, score = "below", 100 * actual / protein_range.min
        elif actual > protein_range.max:
            status, score = "above", 100 * protein_range.max / actual
        else:
            status, score = "within", 100.0
    protein = ProteinAdherence(actual_g=actual, min_g=protein_range.min, max_g=protein_range.max, status=status, score=score)
    calories = _target(totals.calories_kcal, targets.calories_kcal, logged)
    carbs = _target(totals.carbs_g, targets.carbs_g, logged)
    fat = _target(totals.fat_g, targets.fat_g, logged)
    return Adherence(
        macro_score=fsum((protein.score, calories.score, carbs.score, fat.score)) / 4 if logged else None,
        protein=protein, calories=calories, carbs=carbs, fat=fat,
        caloric_drift_kcal=totals.calories_kcal - targets.calories_kcal if logged else None,
        protein_timing=protein_timing(meals),
    )

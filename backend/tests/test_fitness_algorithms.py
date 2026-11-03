"""Pure deterministic policy tests; no model providers or workout history required."""

import pytest
from pydantic import ValidationError

from app.services.fitness_algorithms import (
    EffectiveLoadInput,
    EnergyInput,
    FatigueInput,
    MacroInput,
    OneRepMaxInput,
    ProgressionInput,
    ProgressionPolicy,
    ProgressionSet,
    calculate_energy,
    effective_load,
    estimate_one_rep_max,
    fatigue_index,
    phase_macros,
    protein_adherence_range,
    recommend_progression,
    weekly_volume_landmark,
)


@pytest.mark.parametrize("sex,bmr", [("male", 1780), ("female", 1614)])
def test_mifflin_sex_specific_bmr_and_tdee(sex, bmr):
    result = calculate_energy(EnergyInput(weight_kg=80, height_cm=180, age=30, biological_sex=sex, activity_multiplier=1.6))
    assert result.bmr_kcal == bmr
    assert result.tdee_kcal == pytest.approx(bmr * 1.6)


@pytest.mark.parametrize("sex", [None, "unspecified"])
def test_bmr_rejects_unspecified_sex(sex):
    with pytest.raises(ValidationError):
        EnergyInput(weight_kg=80, height_cm=180, age=30, biological_sex=sex, activity_multiplier=1.6)


def test_bmr_requires_sex_and_rejects_nonpositive_result():
    with pytest.raises(ValidationError):
        EnergyInput(weight_kg=80, height_cm=180, age=30, activity_multiplier=1.6)
    with pytest.raises(ValidationError):
        calculate_energy(EnergyInput(weight_kg=20, height_cm=50, age=100, biological_sex="female", activity_multiplier=1.2))


@pytest.mark.parametrize("phase,base,protein,fat", [
    ("cutting", 2000, 176, 64),
    ("lean_bulking", 2850, 160, 80),
    ("baseline_assessment", 2500, 160, 64),
    ("calisthenics_strength", 2500, 160, 64),
])
def test_phase_macro_policy(phase, base, protein, fat):
    result = phase_macros(MacroInput(weight_kg=80, tdee_kcal=2500, phase=phase))
    assert result.base_calories_kcal == base
    assert result.calories_kcal == pytest.approx(base)
    assert result.protein_g == pytest.approx(protein)
    assert result.fat_g == pytest.approx(fat)
    assert result.carbs_g == pytest.approx((base - 4 * protein - 9 * fat) / 4)
    assert result.carb_cycle_factor == 1


@pytest.mark.parametrize("training_day,factor", [(True, 1.1), (False, 0.9)])
def test_recomp_cycles_only_remaining_carbs(training_day, factor):
    result = phase_macros(MacroInput(weight_kg=80, tdee_kcal=2500, phase="body_recomposition", training_day=training_day))
    assert result.base_calories_kcal == 2500
    assert result.protein_g == pytest.approx(184)
    assert result.fat_g == 64
    assert result.carbs_g == pytest.approx(297 * factor)
    assert result.carb_cycle_factor == factor
    assert result.calories_kcal == pytest.approx(1312 + 1188 * factor)
    assert result.calories_kcal == pytest.approx(4 * result.protein_g + 4 * result.carbs_g + 9 * result.fat_g)


@pytest.mark.parametrize("tdee", [2099, 2100])
def test_macro_allocation_rejects_negative_and_zero_carb_calories(tdee):
    with pytest.raises(ValueError, match="positive carbohydrate"):
        phase_macros(MacroInput(weight_kg=100, tdee_kcal=tdee, phase="cutting"))


def test_protein_adherence_range_uses_actual_weight():
    result = protein_adherence_range(80)
    assert result.min == 144
    assert result.max == 192
    with pytest.raises(ValidationError):
        protein_adherence_range(0)


@pytest.mark.parametrize("multiplier,external,expected", [
    (0.95, 20, 96),
    (0.65, 0, 52),
    (0.0, 15, 15),
    (1.0, 0, 80),
])
def test_bodyweight_effective_load_uses_single_fraction(multiplier, external, expected):
    assert effective_load(EffectiveLoadInput(bodyweight_kg=80, biomechanical_multiplier=multiplier, external_load_kg=external)) == expected


def test_effective_load_rejects_duplicate_multiplier():
    with pytest.raises(ValidationError):
        EffectiveLoadInput(bodyweight_kg=80, biomechanical_multiplier=0.95, bodyweight_multiplier=0.95)


@pytest.mark.parametrize("reps,formula,expected", [
    (1, "epley", 60 * (1 + 1 / 30)),
    (10, "epley", 80),
    (11, "brzycki", 60 * 36 / 26),
    (36, "brzycki", 2160),
])
def test_hybrid_one_rep_max_branch_boundaries(reps, formula, expected):
    result = estimate_one_rep_max(OneRepMaxInput(load_kg=60, reps=reps))
    assert result.formula == formula
    assert result.estimate_kg == pytest.approx(expected)


@pytest.mark.parametrize("reps", [0, 37, 40, 1.5, True])
def test_one_rep_max_rejects_invalid_repetitions(reps):
    with pytest.raises(ValidationError):
        OneRepMaxInput(load_kg=60, reps=reps)


def progression(sets, **overrides):
    values = dict(current_weight_kg=50, target_min_reps=8, target_max_reps=12, classification="upper_compound", working_sets=sets)
    values.update(overrides)
    return recommend_progression(ProgressionInput(**values))


@pytest.mark.parametrize("classification,next_weight", [("upper_compound", 52.5), ("lower_compound", 55), ("isolation", 52.5)])
def test_all_sets_at_top_low_effort_increases_classified_load(classification, next_weight):
    result = progression([ProgressionSet(reps=12, rpe=8), ProgressionSet(reps=13, rpe=7.5)], classification=classification)
    assert result.state == "increase_weight"
    assert result.next_weight_kg == next_weight
    assert result.target_reps == 8
    assert not result.recovery_check


def test_rir_is_equivalent_to_rpe_and_matching_pairs_are_allowed():
    result = progression([ProgressionSet(reps=12, rir=2), ProgressionSet(reps=12, rpe=7, rir=3)], current_weight_kg=0)
    assert result.state == "increase_weight"
    assert result.next_weight_kg == 2.5  # External load, never bodyweight plus 2.5.
    with pytest.raises(ValidationError, match="RPE and RIR must agree"):
        ProgressionSet(reps=12, rpe=8, rir=3)


@pytest.mark.parametrize("effort", [9.5, 10])
def test_all_sets_meet_minimum_and_any_high_effort_adds_one_target_rep(effort):
    result = progression([ProgressionSet(reps=8, rpe=7), ProgressionSet(reps=10, rpe=effort)])
    assert result.state == "increase_reps"
    assert result.next_weight_kg == 50
    assert result.target_reps == 9


def test_two_consecutive_failures_deload_before_other_rules():
    result = progression(
        [ProgressionSet(reps=12, rpe=7), ProgressionSet(reps=7, rpe=10)],
        previous_working_sets=[ProgressionSet(reps=7, rir=0)],
    )
    assert result.state == "deload"
    assert result.next_weight_kg == 45
    assert result.target_reps == 8
    assert result.recovery_check


@pytest.mark.parametrize("sets,previous", [
    ([ProgressionSet(reps=7, rpe=10)], None),  # No fabricated prior failure.
    ([ProgressionSet(reps=7, rpe=10)], [ProgressionSet(reps=8, rpe=10)]),
    ([ProgressionSet(reps=12, rpe=8.5)], None),
    ([ProgressionSet(reps=11, rpe=7)], None),
    ([ProgressionSet(reps=8, rpe=9.4)], None),
    ([ProgressionSet(reps=7, rpe=7), ProgressionSet(reps=12, rpe=10)], []),
])
def test_progression_holds_when_no_exact_rule_applies(sets, previous):
    result = progression(sets, previous_working_sets=previous)
    assert result.state == "hold"
    assert result.next_weight_kg == 50
    assert result.target_reps == 8
    assert not result.recovery_check


@pytest.mark.parametrize("sets,previous", [
    ([], None),
    ([ProgressionSet(reps=12)], None),
    ([ProgressionSet(reps=12, rpe=8), ProgressionSet(reps=12)], None),
    ([ProgressionSet(reps=7, rpe=10)], [ProgressionSet(reps=7)]),
])
def test_missing_effort_or_working_sets_never_guesses(sets, previous):
    result = progression(sets, previous_working_sets=previous)
    assert result.state == "insufficient_data"
    assert result.next_weight_kg == 50
    assert not result.recovery_check


def test_previous_failure_does_not_override_current_success():
    result = progression([ProgressionSet(reps=12, rpe=8)], previous_working_sets=[ProgressionSet(reps=7, rpe=10)])
    assert result.state == "increase_weight"


def test_configurable_progression_policy_controls_all_adjustments():
    policy = ProgressionPolicy(upper_increment_kg=1, lower_increment_kg=3, deload_multiplier=0.85)
    sets = [ProgressionSet(reps=12, rpe=8)]
    assert progression(sets, policy=policy).next_weight_kg == 51
    assert progression(sets, policy=policy, classification="lower_compound").next_weight_kg == 53
    failed = [ProgressionSet(reps=7, rpe=10)]
    assert progression(failed, policy=policy, previous_working_sets=failed).next_weight_kg == 42.5


@pytest.mark.parametrize("overrides", [
    {"target_min_reps": 0}, {"target_min_reps": 13}, {"target_max_reps": 0},
    {"target_min_reps": True}, {"current_weight_kg": -1}, {"classification": "unknown"},
])
def test_progression_rejects_invalid_targets(overrides):
    with pytest.raises(ValidationError):
        progression([ProgressionSet(reps=12, rpe=8)], **overrides)


@pytest.mark.parametrize("sets,landmark,warning", [
    (0, "below_maintenance", False), (5, "below_maintenance", False),
    (6, "MV", False), (7, "maintenance", False), (8, "MEV", False),
    (10, "MEV", False), (11, "building", False), (12, "MAV", False),
    (20, "MAV", False), (21, "high", False), (22, "high", False), (23, "MRV", True),
])
def test_weekly_volume_landmarks_preserve_exact_thresholds_and_gaps(sets, landmark, warning):
    result = weekly_volume_landmark(sets)
    assert result.hard_sets == sets
    assert result.landmark == landmark
    assert result.recovery_warning is warning
    assert result.explanation


@pytest.mark.parametrize("credits,landmark", [(6.5, "maintenance"), (10.5, "building"), (20.5, "high"), (22.1, "MRV")])
def test_fractional_muscle_volume_credits_preserve_gap_boundaries(credits, landmark):
    result = weekly_volume_landmark(credits)
    assert result.hard_sets == credits
    assert result.landmark == landmark
    assert result.recovery_warning is (credits > 22)


def test_fatigue_accepts_fractional_muscle_volume_credits():
    result = fatigue_index(FatigueInput(weekly_hard_sets=5.5))
    assert result.score == pytest.approx(25)
    assert result.components == {"weekly_hard_sets": 0.25}


@pytest.mark.parametrize("sets", [-1, True, float("inf"), float("nan")])
def test_volume_rejects_invalid_set_counts(sets):
    with pytest.raises(ValidationError):
        weekly_volume_landmark(sets)


def test_fatigue_without_signals_is_unavailable_not_zero():
    result = fatigue_index(FatigueInput())
    assert result.state == "unavailable"
    assert result.score is None
    assert result.components == {}
    assert result.missing_inputs == ["effort_rpe", "weekly_hard_sets", "sleep_hours", "soreness"]
    assert "not a diagnosis" in result.disclaimer


def test_fatigue_renormalizes_only_available_signals():
    result = fatigue_index(FatigueInput(effort_rpe=10, sleep_hours=8))
    assert result.state == "available"
    assert result.score == pytest.approx(100 * 0.35 / 0.55)
    assert result.components == {"effort_rpe": 1, "sleep_hours": 0}
    assert result.missing_inputs == ["weekly_hard_sets", "soreness"]


@pytest.mark.parametrize("inputs,expected", [
    (dict(effort_rpe=1, weekly_hard_sets=0, sleep_hours=24, soreness=0), 0),
    (dict(effort_rpe=10, weekly_hard_sets=50, sleep_hours=0, soreness=10), 100),
    (dict(effort_rpe=5.5, weekly_hard_sets=11, sleep_hours=4, soreness=5), 50),
])
def test_fatigue_scaling_and_saturation(inputs, expected):
    result = fatigue_index(FatigueInput(**inputs))
    assert result.score == pytest.approx(expected)
    assert result.missing_inputs == []


VALID_ENERGY = dict(weight_kg=80, height_cm=180, age=30, biological_sex="male", activity_multiplier=1.6)
VALID_MACRO = dict(weight_kg=80, tdee_kcal=2500, phase="cutting")
VALID_LOAD = dict(bodyweight_kg=80, biomechanical_multiplier=0.95, external_load_kg=20)


@pytest.mark.parametrize("model,valid,field", [
    (EnergyInput, VALID_ENERGY, "weight_kg"),
    (EnergyInput, VALID_ENERGY, "height_cm"),
    (EnergyInput, VALID_ENERGY, "age"),
    (EnergyInput, VALID_ENERGY, "activity_multiplier"),
    (MacroInput, VALID_MACRO, "weight_kg"),
    (MacroInput, VALID_MACRO, "tdee_kcal"),
    (EffectiveLoadInput, VALID_LOAD, "bodyweight_kg"),
    (EffectiveLoadInput, VALID_LOAD, "biomechanical_multiplier"),
    (EffectiveLoadInput, VALID_LOAD, "external_load_kg"),
    (OneRepMaxInput, dict(load_kg=60, reps=8), "load_kg"),
    (ProgressionSet, dict(reps=8), "rpe"),
    (ProgressionSet, dict(reps=8), "rir"),
    (ProgressionPolicy, {}, "upper_increment_kg"),
    (ProgressionPolicy, {}, "lower_increment_kg"),
    (ProgressionPolicy, {}, "deload_multiplier"),
    (FatigueInput, {}, "effort_rpe"),
    (FatigueInput, {}, "weekly_hard_sets"),
    (FatigueInput, {}, "sleep_hours"),
    (FatigueInput, {}, "soreness"),
])
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_numeric_inputs_must_be_finite(model, valid, field, invalid):
    with pytest.raises(ValidationError):
        model(**{**valid, field: invalid})


@pytest.mark.parametrize("model,valid,field,invalid", [
    (EnergyInput, VALID_ENERGY, "weight_kg", 19),
    (EnergyInput, VALID_ENERGY, "weight_kg", 501),
    (EnergyInput, VALID_ENERGY, "height_cm", 49),
    (EnergyInput, VALID_ENERGY, "height_cm", 251),
    (EnergyInput, VALID_ENERGY, "age", 12),
    (EnergyInput, VALID_ENERGY, "age", 101),
    (EnergyInput, VALID_ENERGY, "activity_multiplier", 1.1),
    (EnergyInput, VALID_ENERGY, "activity_multiplier", 2.5),
    (MacroInput, VALID_MACRO, "weight_kg", 0),
    (MacroInput, VALID_MACRO, "tdee_kcal", 0),
    (EffectiveLoadInput, VALID_LOAD, "bodyweight_kg", 0),
    (EffectiveLoadInput, VALID_LOAD, "biomechanical_multiplier", -0.01),
    (EffectiveLoadInput, VALID_LOAD, "biomechanical_multiplier", 1.01),
    (EffectiveLoadInput, VALID_LOAD, "external_load_kg", -1),
    (OneRepMaxInput, dict(load_kg=60, reps=8), "load_kg", 0),
    (ProgressionSet, dict(reps=8), "reps", -1),
    (ProgressionSet, dict(reps=8), "rpe", 0.9),
    (ProgressionSet, dict(reps=8), "rpe", 10.1),
    (ProgressionSet, dict(reps=8), "rir", -0.1),
    (ProgressionSet, dict(reps=8), "rir", 9.1),
    (ProgressionPolicy, {}, "upper_increment_kg", 0),
    (ProgressionPolicy, {}, "lower_increment_kg", -1),
    (ProgressionPolicy, {}, "deload_multiplier", 0),
    (ProgressionPolicy, {}, "deload_multiplier", 1),
    (FatigueInput, {}, "effort_rpe", 0),
    (FatigueInput, {}, "effort_rpe", 11),
    (FatigueInput, {}, "weekly_hard_sets", -1),
    (FatigueInput, {}, "sleep_hours", -1),
    (FatigueInput, {}, "sleep_hours", 25),
    (FatigueInput, {}, "soreness", -1),
    (FatigueInput, {}, "soreness", 11),
])
def test_numeric_input_boundaries(model, valid, field, invalid):
    with pytest.raises(ValidationError):
        model(**{**valid, field: invalid})


def test_overflow_cannot_escape_as_infinite_output():
    with pytest.raises(ValidationError):
        effective_load(EffectiveLoadInput(bodyweight_kg=1e308, biomechanical_multiplier=1, external_load_kg=1e308))
    with pytest.raises(ValidationError):
        estimate_one_rep_max(OneRepMaxInput(load_kg=1e308, reps=36))
    with pytest.raises(ValidationError):
        protein_adherence_range(1e308)


def test_high_effort_rep_target_never_drops_below_completed_sets():
    result = progression(
        [ProgressionSet(reps=10, rpe=10), ProgressionSet(reps=11, rpe=9.5)],
        target_min_reps=6,
        target_max_reps=10,
    )
    assert result.state == "increase_reps"
    assert result.target_reps == 11
    assert result.next_weight_kg == 50

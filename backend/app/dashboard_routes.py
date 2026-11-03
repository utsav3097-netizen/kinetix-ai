"""Owner-scoped dashboard targets derived only from the completed profile."""

from fastapi import APIRouter, Depends, HTTPException

from app.auth import Database, prevent_caching
from app.models.identity import utc_now
from app.profile import CompletedProfile
from app.services import plans, reports
from app.services.fitness_algorithms import (
    EnergyInput,
    EnergyResult,
    MacroInput,
    MacroTargets,
    Phase,
    ProteinRange,
    calculate_energy,
    phase_macros,
    protein_adherence_range,
)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"], dependencies=[Depends(prevent_caching)])


class TargetsResponse(EnergyResult):
    phase: Phase
    training_day: bool
    macros: MacroTargets
    protein_range_g: ProteinRange
    disclaimer: str
    plan_version_id: str | None = None


@router.get("/targets", response_model=TargetsResponse)
def get_targets(profile: CompletedProfile, db: Database, training_day: bool | None = None) -> TargetsResponse:
    reports.materialize_due(db, profile)
    planned = plans.active_day(db, profile.user_id, utc_now().date())
    training_day = planned["day"]["training_day"] if training_day is None and planned else (True if training_day is None else training_day)
    try:
        energy = calculate_energy(EnergyInput(
            weight_kg=profile.current_weight_kg,
            height_cm=profile.height_cm,
            age=profile.age,
            biological_sex=profile.biological_sex,
            activity_multiplier=profile.activity_multiplier,
        ))
        macros = phase_macros(MacroInput(
            weight_kg=profile.current_weight_kg,
            tdee_kcal=energy.tdee_kcal,
            phase=profile.phase,
            training_day=training_day,
        ))
        protein_range = protein_adherence_range(profile.current_weight_kg)
    except ValueError:
        raise HTTPException(status_code=422, detail="Profile values cannot produce valid energy and macro targets. Review your profile and phase; carbohydrate calories must remain positive.") from None
    if planned:
        macros = MacroTargets(**planned["target_pair"][str(training_day).lower()])
        protein_range = protein_adherence_range(planned["baseline"]["bodyweight_kg"])
    db.commit()
    return TargetsResponse(
        **energy.model_dump(),
        phase=planned["baseline"]["phase"] if planned else profile.phase,
        training_day=training_day,
        macros=macros,
        protein_range_g=protein_range,
        plan_version_id=planned["version_id"] if planned else None,
        disclaimer="Deterministic estimates, not medical advice. Accepted plan targets apply when today is covered; otherwise profile formulas apply. Reports materialize on request after completed periods. Baseline/calisthenics use maintenance energy, 2 g/kg protein and 0.8 g/kg fat; recomp cycles carbohydrate calories only. No AI is used.",
    )

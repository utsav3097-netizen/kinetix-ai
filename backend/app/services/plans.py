"""Deterministic seven-day prescriptions; commands flush and caller commits."""
from collections import defaultdict
from copy import deepcopy
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.models import ActiveTrainingPlan, Exercise, PlanDraft, Report, TrainingPlanVersion, WorkoutSession
from app.models.identity import utc_now
from app.planning_schemas import PlanData
from app.reference_service import get_exercise
from app.services import workouts
from app.services.fitness_algorithms import EffectiveLoadInput, EnergyInput, calculate_energy, effective_load
from app.services.nutrition import _macros
from app.services.plan_meals import MealExamples
from app.services.reports import lock_owner, owned

PATHS = {
    "cutting": ("Cutting", "cutting", "Three full-body days with a 500 kcal energy deficit and 2.2 g/kg protein."),
    "bulking": ("Lean bulking", "lean_bulking", "Four upper/lower days with a 350 kcal surplus; observed loads, not promised muscle gain."),
    "recomp": ("Post-cut / recomposition", "body_recomposition", "Three full-body days, 2.3 g/kg protein and training/rest carbohydrate cycling."),
    "powerbuilding": ("Powerbuilding", "baseline_assessment", "Four strength-and-assistance days at maintenance energy; strength targets follow observed rep ranges."),
    "classic_physique": ("Classic physique hypertrophy", "lean_bulking", "Four upper/lower hypertrophy days and a 350 kcal surplus; no body-shape or vascularity guarantees."),
    "athletic_hybrid": ("Athletic hybrid / calisthenics", "calisthenics_strength", "Three bodyweight, lower-body and core days at maintenance energy, with capability-dependent assessment."),
}
ASSESSMENT = "Conservative unloaded technique assessment: no added load, two comfortable sets of 3–5 reps or a 20-second hold. Skip unfamiliar or painful movements; bodyweight ability is not assumed."
INSTRUCTIONS = "Warm up separately with comfortable unloaded movement; prescribed sets are working sets. Repeat the same load until new observations justify a change. Sample meals are gram-based examples, not a claim of nutritional completeness; label calories can differ from 4/4/9 target calories."


def _history(db, owner_id, start, end):
    rows = list(db.execute(workouts._active_sets(owner_id).where(
        WorkoutSession.performed_on >= start, WorkoutSession.performed_on <= end
    ).order_by(WorkoutSession.performed_on, WorkoutSession.created_at, WorkoutSession.id)))
    grouped = defaultdict(list)
    dates = set()
    for row, block, session in rows:
        if row.set_type == "working":
            grouped[block.exercise_id].append((row, block, session))
            dates.add(session.performed_on)
    return grouped, len(dates)


def path_options(db, profile):
    end = utc_now().date()
    grouped, count = _history(db, profile.user_id, end - timedelta(days=profile.analysis_weeks * 7 - 1), end)
    report = db.scalar(select(Report).where(Report.owner_id == profile.user_id).order_by(Report.created_at.desc(), Report.id.desc()).limit(1))
    nutrition_days = report.data["nutrition"]["logged_days"] if report else None
    available = list(db.scalars(select(Exercise).where(Exercise.deleted_at.is_(None),
        or_(Exercise.owner_id.is_(None), Exercise.owner_id == profile.user_id), Exercise.id.in_(grouped))))
    enough = any(_prescription(db, exercise, grouped[exercise.id], profile.current_weight_kg, count)["progression"] is not None
                 for exercise in available)
    evidence = f"{count} working-set training dates and {len(grouped)} logged movements in the current {profile.analysis_weeks}-week window. "
    evidence += f"Latest frozen report has {nutrition_days} nutrition days. " if report else "No frozen nutrition report yet. "
    evidence += "Each exercise still needs comparable working sets on two dates; otherwise it receives an unloaded assessment."
    return {"items": [{"id": key, "title": value[0], "phase": value[1], "description": value[2],
            "evidence": evidence, "assessment_required": not enough} for key, value in PATHS.items()],
            "history_sufficient": enough, "report_id": report.id if report else None}


def _snapshot(exercise):
    return {key: getattr(exercise, key) for key in ("name", "equipment", "biomechanical_multiplier", "classification", "measurement_type")} | {
        "muscles": [{"muscle_id": row.muscle_id, "contribution": row.contribution} for row in exercise.muscles]}


def _prescription(db, exercise, history, weight, training_days):
    snapshot = _snapshot(exercise)
    timed = exercise.measurement_type == "seconds"
    comparable = [(row, block, session) for row, block, session in history if block.exercise_snapshot == snapshot]
    progression = None
    observed = None
    velocity = None
    latest = comparable[-1] if comparable else None
    dates = {session.performed_on for _, _, session in comparable}
    if latest and len(dates) >= 2 and training_days >= 2 and not timed:
        _, block, session = latest
        current = [row for row, saved_block, saved_session in comparable if saved_session.id == session.id and saved_block.id == block.id]
        progression = workouts.block_progression(db, session, block, current)
        # block_progression can advance from one block alone: planning additionally
        # requires a prior dated comparable, effort-bearing working observation.
        prior = [row for row, _, previous in comparable if previous.performed_on < session.performed_on]
        if not prior or any(row.repetitions is None or not 1 <= row.repetitions < 37 or (row.rpe is None and row.rir is None) for row in prior):
            progression = None
        elif len({row.external_load_kg for row in prior if row.session_id == prior[-1].session_id}) != 1:
            progression = None
    sufficient = progression is not None and progression.state != "insufficient_data"
    points = {}
    for row, _, session in comparable:
        value = row.metrics.get("estimated_1rm_kg")
        if value is not None:
            points[session.performed_on] = max(points.get(session.performed_on, value), value)
    if len(points) >= 2:
        ordered = sorted(points)
        observed = points[ordered[-1]]
        velocity = (points[ordered[-1]] - points[ordered[0]]) / ((ordered[-1] - ordered[0]).days / 7)
    load = progression.next_weight_kg if sufficient else 0.0
    return {"exercise_id": exercise.id, "exercise_snapshot": snapshot,
        "sets": min(len(current), 20) if sufficient else 2,
        "target_min_reps": (block.target_min_reps if sufficient else 3) if not timed else None,
        "target_max_reps": (block.target_max_reps if sufficient else 5) if not timed else None,
        "duration_seconds": 20 if timed else None, "external_load_kg": load,
        "effective_load_kg": effective_load(EffectiveLoadInput(bodyweight_kg=weight, biomechanical_multiplier=exercise.biomechanical_multiplier, external_load_kg=load)),
        "rest_seconds": 180 if sufficient and exercise.classification != "isolation" else 120,
        "progression": progression.model_dump() if sufficient else None,
        "observed_1rm_kg": observed, "observed_velocity_kg_per_week": velocity,
        "rationale": progression.reason if sufficient else ASSESSMENT}


def _schedule(path, exercises, history):
    # Familiar references precede basic seed movements; never synthesize IDs.
    basics = {key: index for index, key in enumerate(("push-up", "squat", "plank", "barbell-row", "lunge", "bench-press", "overhead-press"))}
    ordered = sorted(exercises, key=lambda row: (row.id not in history, basics.get(row.seed_key, 100), row.name, row.id))
    upper = [row for row in ordered if row.classification == "upper_compound"]
    lower = [row for row in ordered if row.classification == "lower_compound"]
    core = [row for row in ordered if row.classification == "isolation"]
    bodyweight = [row for row in upper if row.biomechanical_multiplier > 0]
    if not upper or not lower:
        raise HTTPException(422, "Planning requires available upper- and lower-body exercises. Add suitable reference movements first.")
    if path == "athletic_hybrid" and (not bodyweight or not core):
        raise HTTPException(422, "Athletic planning requires available bodyweight and core exercises.")
    if path in ("cutting", "recomp"):
        group = upper[:2] + lower[:1] + core[:1]
        return {offset: ("Full body", group) for offset in (0, 2, 4)}
    if path == "athletic_hybrid":
        group = bodyweight[:2] + lower[:1] + core[:1]
        return {offset: ("Bodyweight + lower / core", group) for offset in (0, 2, 4)}
    if path == "powerbuilding":
        return {0: ("Upper strength + assistance", upper[:2] + core[:1]),
                1: ("Lower strength + assistance", lower[:2] + core[:1]),
                3: ("Upper assistance + strength", list(reversed(upper[:2])) + core[:1]),
                4: ("Lower assistance + strength", list(reversed(lower[:2])) + core[:1])}
    prefix = "Hypertrophy " if path == "classic_physique" else ""
    return {0: (prefix + "Upper", upper[:3]), 1: (prefix + "Lower", lower[:2] + core[:1]),
            3: (prefix + "Upper", upper[:3]), 4: (prefix + "Lower", lower[:2] + core[:1])}


def _save_draft(db, owner_id, data, *, based_on=None, parent=None):
    row = PlanDraft(owner_id=owner_id, data=PlanData.model_validate(data).model_dump(mode="json"),
                    based_on_draft_id=based_on, parent_version_id=parent)
    db.add(row)
    db.flush()
    return row


def generate_draft(db, profile, payload):
    today = utc_now().date()
    if payload.starts_on < today:
        raise HTTPException(422, "Plan start cannot precede today")
    try:
        payload.starts_on + timedelta(days=6)
    except OverflowError:
        raise HTTPException(422, "Plan dates exceed the supported calendar") from None
    report = owned(db, Report, profile.user_id, payload.report_id) if payload.report_id else None
    end = report.window_end if report else today
    start = report.window_start if report else end - timedelta(days=profile.analysis_weeks * 7 - 1)
    history, training_days = _history(db, profile.user_id, start, end)
    exercises = list(db.scalars(select(Exercise).where(Exercise.deleted_at.is_(None),
        or_(Exercise.owner_id.is_(None), Exercise.owner_id == profile.user_id))))
    schedule = _schedule(payload.path, exercises, history)
    prescribed = {exercise.id: _prescription(db, exercise, history.get(exercise.id, []), profile.current_weight_kg, training_days)
                  for _, group in schedule.values() for exercise in group}
    assessment = any(row["progression"] is None for row in prescribed.values())
    title, phase, description = PATHS[payload.path]
    energy = calculate_energy(EnergyInput(weight_kg=profile.current_weight_kg, height_cm=profile.height_cm,
        age=profile.age, biological_sex=profile.biological_sex, activity_multiplier=profile.activity_multiplier))
    meals = MealExamples(db, profile.user_id)
    days = []
    for offset in range(7):
        label, group = schedule.get(offset, ("Rest / comfortable recovery", []))
        targets = _macros(profile.current_weight_kg, energy.tdee_kcal, phase, bool(group))
        samples, totals = meals.for_targets(targets)
        days.append({"date": payload.starts_on + timedelta(days=offset), "training_day": bool(group), "label": label,
            "exercises": [prescribed[row.id] for row in group], "targets": targets, "sample_meals": samples, "sample_totals": totals})
    active = db.get(ActiveTrainingPlan, profile.user_id)
    return _save_draft(db, profile.user_id, {"path": payload.path, "title": title + (" — assessment" if assessment else ""),
        "assessment_required": assessment, "explanation": description + " " + (ASSESSMENT + " " if assessment else "") + INSTRUCTIONS,
        "profile_snapshot": {"bodyweight_kg": profile.current_weight_kg, "tdee_kcal": energy.tdee_kcal, "phase": phase},
        "evidence": {"report_id": report.id if report else None, "training_days": training_days,
                     "notes": [f"Current corrected source records dated {start} through {end}; any linked report remains frozen.",
                               "Observed velocity is a dated first-to-last 1RM difference, not a forecast."] +
                              [f"Working-set source {row.source_record_id}" for rows in history.values() for row, _, _ in rows]},
        "days": days}, parent=active.version_id if active else None)


def edit_draft(db, profile, draft_id, payload):
    original = owned(db, PlanDraft, profile.user_id, draft_id)
    data = deepcopy(original.data)
    if [day.date.isoformat() for day in payload.days] != [day["date"] for day in data["days"]]:
        raise HTTPException(422, "An edited draft must preserve all seven original dates in order")
    data["title"] = payload.title
    data["explanation"] += " This is a manually edited draft; prescriptions are not new observed progression."
    meals = MealExamples(db, profile.user_id)
    weight = data["profile_snapshot"]["bodyweight_kg"]
    days = []
    for day in payload.days:
        exercises = []
        for requested in day.exercises:
            exercise = get_exercise(db, profile.user_id, requested.exercise_id)
            if (exercise.measurement_type == "seconds") != (requested.duration_seconds is not None):
                raise HTTPException(422, "Prescription measurement must match the available exercise")
            values = requested.model_dump()
            values.update(exercise_snapshot=_snapshot(exercise), effective_load_kg=effective_load(EffectiveLoadInput(
                bodyweight_kg=weight, biomechanical_multiplier=exercise.biomechanical_multiplier, external_load_kg=requested.external_load_kg)),
                progression=None, observed_1rm_kg=None, observed_velocity_kg_per_week=None,
                rationale="Manually edited prescription, not an observed progression recommendation. " + (ASSESSMENT if data["assessment_required"] else ""))
            exercises.append(values)
        calories = 4 * day.protein_g + 4 * day.carbs_g + 9 * day.fat_g
        targets = {"protein_g": day.protein_g, "carbs_g": day.carbs_g, "fat_g": day.fat_g,
                   "calories_kcal": calories, "base_calories_kcal": calories, "carb_cycle_factor": 1.0}
        samples, totals = meals.for_targets(targets)
        days.append({"date": day.date, "training_day": day.training_day, "label": day.label, "exercises": exercises,
                     "targets": targets, "sample_meals": samples, "sample_totals": totals})
    data["days"] = days
    parent = db.scalar(select(TrainingPlanVersion.id).where(TrainingPlanVersion.owner_id == profile.user_id,
                                                           TrainingPlanVersion.draft_id == original.id))
    return _save_draft(db, profile.user_id, data, based_on=original.id, parent=parent or original.parent_version_id)


def accept_draft(db, profile, draft_id):
    lock_owner(db, profile.user_id)
    draft = owned(db, PlanDraft, profile.user_id, draft_id)
    existing = db.scalar(select(TrainingPlanVersion).where(TrainingPlanVersion.owner_id == profile.user_id,
                                                         TrainingPlanVersion.draft_id == draft.id))
    if existing is not None:
        return existing
    number = (db.scalar(select(func.max(TrainingPlanVersion.version)).where(TrainingPlanVersion.owner_id == profile.user_id)) or 0) + 1
    version = TrainingPlanVersion(owner_id=profile.user_id, version=number, draft_id=draft.id)
    db.add(version)
    db.flush()
    active = db.get(ActiveTrainingPlan, profile.user_id)
    if active is None:
        db.add(ActiveTrainingPlan(owner_id=profile.user_id, version_id=version.id))
    else:
        active.version_id = version.id
    profile.phase = draft.data["profile_snapshot"]["phase"]
    db.flush()
    return version


def draft_summary(row):
    data = row.data
    return {"id": row.id, "path": data["path"], "title": data["title"], "starts_on": data["days"][0]["date"],
        "ends_on": data["days"][-1]["date"], "assessment_required": data["assessment_required"], "created_at": row.created_at,
        "parent_version_id": row.parent_version_id, "based_on_draft_id": row.based_on_draft_id}


def draft_view(row):
    return {**draft_summary(row), "data": row.data}


def version_view(db, row):
    draft = owned(db, PlanDraft, row.owner_id, row.draft_id)
    data = draft.data
    return {"id": row.id, "version": row.version, "draft_id": row.draft_id, "accepted_at": row.accepted_at,
            "title": data["title"], "path": data["path"], "starts_on": data["days"][0]["date"],
            "ends_on": data["days"][-1]["date"], "data": data}


def list_drafts(db, owner_id, query):
    statement = select(PlanDraft).where(PlanDraft.owner_id == owner_id)
    return {"total": db.scalar(select(func.count()).select_from(statement.subquery())), "items": [draft_summary(row) for row in
        db.scalars(statement.order_by(PlanDraft.created_at.desc(), PlanDraft.id.desc()).offset(query.offset).limit(query.limit))]}


def list_versions(db, owner_id, query):
    statement = select(TrainingPlanVersion).where(TrainingPlanVersion.owner_id == owner_id)
    return {"total": db.scalar(select(func.count()).select_from(statement.subquery())), "items": [version_view(db, row) for row in
        db.scalars(statement.order_by(TrainingPlanVersion.version.desc()).offset(query.offset).limit(query.limit))]}


def active_version(db, owner_id):
    pointer = db.get(ActiveTrainingPlan, owner_id)
    return owned(db, TrainingPlanVersion, owner_id, pointer.version_id) if pointer else None


def active_day(db, owner_id, on_date):
    version = active_version(db, owner_id)
    if version is None:
        return None
    data = owned(db, PlanDraft, owner_id, version.draft_id).data
    day = next((day for day in data["days"] if day["date"] == on_date.isoformat()), None)
    if day is None:
        return None
    # Same-date exact target wins for its prescribed type. Opposite type uses
    # the first accepted day of that type, or the frozen baseline formula.
    baseline = data["profile_snapshot"]
    pair = {}
    for training in (True, False):
        matching = day if day["training_day"] == training else next((row for row in data["days"] if row["training_day"] == training), None)
        pair[str(training).lower()] = deepcopy(matching["targets"] if matching else _macros(
            baseline["bodyweight_kg"], baseline["tdee_kcal"], baseline["phase"], training))
    return {"version_id": version.id, "day": day, "baseline": baseline, "target_pair": pair}

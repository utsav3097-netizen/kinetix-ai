"""Run `python -m app.seed` after migrations to insert missing canonical references.

Seeds are conservative generic defaults, not branded nutrition labels or individualized
biomechanics. Existing records (including tombstones and administrator edits) win.
All additions commit together; unique keys and savepoints also protect concurrent seeds.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Exercise, Food, MuscleGroup
from app.reference_schemas import ExerciseInput, FoodInput
from app.reference_service import apply_exercise, apply_food, normalize_name

MUSCLES = {
    "chest": "Chest", "back": "Back", "lats": "Lats", "upper_back": "Upper back",
    "shoulders": "Shoulders", "anterior_deltoids": "Shoulders — anterior",
    "lateral_deltoids": "Shoulders — lateral", "posterior_deltoids": "Shoulders — posterior",
    "biceps": "Biceps", "triceps": "Triceps", "forearms": "Forearms",
    "quads": "Quadriceps", "hamstrings": "Hamstrings", "glutes": "Glutes",
    "calves": "Calves", "abs": "Core / Abs",
}

# name, equipment, MET, body-mass fraction, classification, measurement, muscle weights.
# Muscle-up=1, hanging leg raise=.35 and plank=.65 are explicit approximate defaults;
# only pull/chin-up/dip=.95 and push-up/diamond push-up=.65 are specified factors.
# MET values and muscle weights are editable generic estimates, not clinical measures.
EXERCISES = {
    "pull-up": ("Pull-up", "Pull-up bar", 8.0, .95, "upper_compound", "reps", {"lats": 1, "back": .8, "biceps": .6, "upper_back": .5, "forearms": .4}),
    "chin-up": ("Chin-up", "Pull-up bar", 8.0, .95, "upper_compound", "reps", {"lats": 1, "back": .8, "biceps": .8, "forearms": .4}),
    "dip": ("Dip", "Parallel bars", 8.0, .95, "upper_compound", "reps", {"chest": 1, "triceps": .8, "anterior_deltoids": .5}),
    "push-up": ("Push-up", "Bodyweight", 8.0, .65, "upper_compound", "reps", {"chest": 1, "triceps": .6, "anterior_deltoids": .5, "abs": .3}),
    "diamond-push-up": ("Diamond Push-up", "Bodyweight", 8.0, .65, "upper_compound", "reps", {"chest": .8, "triceps": 1, "anterior_deltoids": .4, "abs": .3}),
    "muscle-up": ("Muscle-up", "Pull-up bar", 8.0, 1.0, "upper_compound", "reps", {"lats": 1, "back": .8, "chest": .8, "triceps": .8, "biceps": .6}),
    "hanging-leg-raise": ("Hanging Leg Raise", "Pull-up bar", 5.0, .35, "isolation", "reps", {"abs": 1, "forearms": .4}),
    "plank": ("Plank", "Bodyweight", 3.0, .65, "isolation", "seconds", {"abs": 1, "glutes": .3, "shoulders": .3}),
    "squat": ("Squat", "Barbell", 6.0, 0, "lower_compound", "reps", {"quads": 1, "glutes": .8, "hamstrings": .4, "abs": .3}),
    "bench-press": ("Bench press", "Barbell", 6.0, 0, "upper_compound", "reps", {"chest": 1, "triceps": .6, "anterior_deltoids": .5}),
    "deadlift": ("Deadlift", "Barbell", 6.0, 0, "lower_compound", "reps", {"hamstrings": 1, "glutes": 1, "back": .7, "upper_back": .6, "forearms": .4}),
    "barbell-row": ("Barbell row", "Barbell", 6.0, 0, "upper_compound", "reps", {"lats": 1, "upper_back": 1, "back": 1, "posterior_deltoids": .6, "biceps": .5}),
    "overhead-press": ("Overhead press", "Barbell", 6.0, 0, "upper_compound", "reps", {"shoulders": 1, "anterior_deltoids": 1, "lateral_deltoids": .6, "triceps": .6}),
    "lunge": ("Lunge", "Dumbbell", 6.0, 0, "lower_compound", "reps", {"quads": 1, "glutes": .8, "hamstrings": .4, "calves": .3}),
}

# Generic edible food per 100 g: kcal, protein, carbohydrate (including fiber), fat, fiber.
# Chicken is cooked skinless breast; yogurt is plain nonfat; egg is whole edible portion.
FOODS = {
    "chicken-breast": ("Chicken breast", 165, 31, 0, 3.6, 0),
    "cooked-rice": ("Cooked rice", 130, 2.7, 28, .3, .4),
    "oats": ("Oats", 389, 16.9, 66.3, 6.9, 10.6),
    "banana": ("Banana", 89, 1.1, 22.8, .3, 2.6),
    "greek-yogurt": ("Greek yogurt", 59, 10.3, 3.6, .4, 0),
    "egg": ("Egg", 143, 12.6, .7, 9.5, 0),
    "olive-oil": ("Olive oil", 884, 0, 0, 100, 0),
}


def _existing_seed(db: Session, model, key: str, name: str):
    record = db.scalar(select(model).where(model.seed_key == key))
    if record is None:
        record = db.scalar(select(model).where(model.owner_id.is_(None), model.name_key == normalize_name(name)))
        if record is not None and record.seed_key is None:
            # Remember an existing global record even if an admin renames it later.
            record.seed_key = key
    return record


def seed_reference_data(db: Session) -> dict[str, int]:
    """Insert missing canonical rows in the caller's transaction; never commit it."""
    inserted = {"muscles": 0, "exercises": 0, "foods": 0}
    for muscle_id, name in MUSCLES.items():
        if db.get(MuscleGroup, muscle_id) is not None:
            continue
        try:
            with db.begin_nested():
                db.add(MuscleGroup(id=muscle_id, name=name))
                db.flush()
            inserted["muscles"] += 1
        except IntegrityError:
            if db.get(MuscleGroup, muscle_id) is None:
                raise
    for model, seeds, counter in ((Exercise, EXERCISES, "exercises"), (Food, FOODS, "foods")):
        for key, values in seeds.items():
            if _existing_seed(db, model, key, values[0]) is not None:
                continue
            try:
                with db.begin_nested():
                    record = model(owner_id=None, seed_key=key)
                    if model is Exercise:
                        name, equipment, met, fraction, classification, measurement, muscles = values
                        payload = ExerciseInput(
                            name=name, equipment=equipment, met=met, biomechanical_multiplier=fraction,
                            classification=classification, measurement_type=measurement,
                            muscles=[{"muscle_id": muscle, "contribution": contribution} for muscle, contribution in muscles.items()],
                        )
                        apply_exercise(db, record, payload)
                    else:
                        name, calories, protein, carbs, fat, fiber = values
                        apply_food(record, FoodInput(name=name, calories=calories, protein_g=protein,
                                                     carbs_g=carbs, fat_g=fat, fiber_g=fiber))
                    db.add(record)
                    db.flush()
                inserted[counter] += 1
            except IntegrityError:
                if _existing_seed(db, model, key, values[0]) is None:
                    raise
    db.flush()
    return inserted


def main() -> None:
    with SessionLocal.begin() as db:
        counts = seed_reference_data(db)
    print("Reference seed complete: " + ", ".join(f"{count} {kind} added" for kind, count in counts.items()))


if __name__ == "__main__":
    main()

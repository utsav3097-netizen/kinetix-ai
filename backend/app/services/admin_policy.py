"""Validated DB-backed administration policy at service boundaries.

Pure deterministic algorithms continue to own their defaults; callers opt into this
boundary only when a persisted administrator policy is available.
"""
from sqlalchemy.orm import Session

from app.models.admin import SystemSetting

DEFAULT_SETTINGS: dict[str, object] = {
    "coach_prompt": "Provide concise, supportive, non-medical guidance. Deterministic calculations remain authoritative.",
    "meal_prompt": "Extract only foods supported by the supplied catalog. Never invent nutrition facts.",
    "progression_policy": {"upper_increment_kg": 2.5, "lower_increment_kg": 5.0, "deload_multiplier": 0.9},
}


def load_setting(db: Session, key: str) -> object:
    row = db.get(SystemSetting, key)
    return row.value if row is not None else DEFAULT_SETTINGS[key]

def configured_setting(db: Session, key: str) -> object | None:
    row = db.get(SystemSetting, key)
    return row.value if row is not None else None


def progression_policy(db: Session) -> dict[str, float]:
    value = load_setting(db, "progression_policy")
    if db.get(SystemSetting, "progression_policy") is None:
        alias = db.get(SystemSetting, "progression_multipliers")
        if alias is not None:
            value = alias.value
    if not isinstance(value, dict):
        return DEFAULT_SETTINGS["progression_policy"].copy()  # type: ignore[union-attr]
    try:
        result = {name: float(value[name]) for name in ("upper_increment_kg", "lower_increment_kg", "deload_multiplier")}
    except (KeyError, TypeError, ValueError):
        return DEFAULT_SETTINGS["progression_policy"].copy()  # type: ignore[union-attr]
    if not 0.1 <= result["upper_increment_kg"] <= 20 or not 0.1 <= result["lower_increment_kg"] <= 30 or not 0.5 <= result["deload_multiplier"] < 1:
        return DEFAULT_SETTINGS["progression_policy"].copy()  # type: ignore[union-attr]
    return result

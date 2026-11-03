"""Server-authorized administration and public scheduled-announcement APIs."""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentUser, Database, prevent_caching, require_admin
from app.admin_schemas import (
    ExerciseAdminPage, FoodAdminPage, AnalyticsResponse, AnnouncementInput, AnnouncementPage, AnnouncementQuery,
    AnnouncementResponse, AuditPage, AuditQuery, AuditResponse, ReferenceQuery, SettingInput, SettingResponse,
)
from app.services.admin_policy import DEFAULT_SETTINGS, load_setting, progression_policy
from app.models.admin import Announcement, AuditRecord, SystemSetting
from app.models.ai import AIInsight
from app.models.athlete import AthleteProfile
from app.models.identity import User, utc_now
from app.models.nutrition import NutritionDay, NutritionSourceRecord
from app.models.reference import Exercise, Food
from app.models.workout import WorkoutSession, WorkoutSourceRecord
from app.reference_service import apply_exercise, apply_food, normalize_name
from app.reference_schemas import ExerciseInput, ExerciseResponse, FoodInput, FoodResponse

admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(prevent_caching), Depends(require_admin)])
announcement_router = APIRouter(prefix="/api/v1/announcements", tags=["announcements"], dependencies=[Depends(prevent_caching)])



def _setting_value(key: str, value: object) -> object:
    if key in {"coach_prompt", "meal_prompt"}:
        if not isinstance(value, str) or not 20 <= len(value) <= 4000 or any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise HTTPException(422, "Prompt settings must be 20-4000 printable characters")
        return value
    if key in {"progression_policy", "progression_multipliers"}:
        if not isinstance(value, dict) or set(value) != {"upper_increment_kg", "lower_increment_kg", "deload_multiplier"}:
            raise HTTPException(422, "Progression policy requires upper_increment_kg, lower_increment_kg, and deload_multiplier")
        upper, lower, deload = (value.get(name) for name in ("upper_increment_kg", "lower_increment_kg", "deload_multiplier"))
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in (upper, lower, deload)):
            raise HTTPException(422, "Progression policy values must be numbers")
        if not 0.1 <= float(upper) <= 20 or not 0.1 <= float(lower) <= 30 or not 0.5 <= float(deload) < 1:
            raise HTTPException(422, "Progression policy values are outside safe bounds")
        return {"upper_increment_kg": float(upper), "lower_increment_kg": float(lower), "deload_multiplier": float(deload)}
    raise HTTPException(404, "Unknown system setting")




def _snapshot(record) -> dict:
    if isinstance(record, Exercise):
        return {"id": record.id, "name": record.name, "equipment": record.equipment, "met": record.met,
                "biomechanical_multiplier": record.biomechanical_multiplier, "classification": record.classification,
                "measurement_type": record.measurement_type, "muscles": [{"muscle_id": row.muscle_id, "contribution": row.contribution} for row in record.muscles],
                "deleted_at": record.deleted_at.isoformat() if record.deleted_at else None}
    if isinstance(record, Food):
        return {"id": record.id, "name": record.name, "basis_grams": record.basis_grams, "calories": record.calories,
                "protein_g": record.protein_g, "carbs_g": record.carbs_g, "fat_g": record.fat_g, "fiber_g": record.fiber_g,
                "deleted_at": record.deleted_at.isoformat() if record.deleted_at else None}
    if isinstance(record, Announcement):
        return {"id": record.id, "title": record.title, "body": record.body, "starts_at": record.starts_at.isoformat(),
                "ends_at": record.ends_at.isoformat() if record.ends_at else None}
    return {"key": record.key, "value": record.value} if isinstance(record, SystemSetting) else {}


def _audit(db: Session, actor_id: str, action: str, resource_type: str, resource_id: str, before, after) -> None:
    db.add(AuditRecord(actor_id=actor_id, action=action, resource_type=resource_type, resource_id=resource_id,
                       before=before, after=after))


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "The requested global record conflicts with an existing record") from None


def _uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, "Record not found") from None


def _reference_query(model, query: ReferenceQuery):
    statement = select(model)
    if not query.include_deleted:
        statement = statement.where(model.deleted_at.is_(None))
    if query.search:
        needle = f"%{query.search.casefold()}%"
        statement = statement.where(func.lower(model.name).like(needle))
    return statement.order_by(model.name, model.id)


@admin_router.get("/settings", response_model=list[SettingResponse])
def list_settings(db: Database, admin: Annotated[User, Depends(require_admin)]):
    rows = {row.key: row for row in db.scalars(select(SystemSetting).order_by(SystemSetting.key))}
    result = []
    for key, default in DEFAULT_SETTINGS.items():
        row = rows.get(key)
        result.append(row if row else {"key": key, "value": default})
    return result


@admin_router.put("/settings/{key}", response_model=SettingResponse)
def update_setting(key: str, payload: SettingInput, db: Database, admin: Annotated[User, Depends(require_admin)]):
    value = _setting_value(key, payload.value)
    row = db.get(SystemSetting, key)
    before = _snapshot(row) if row else None
    if row is None:
        row = SystemSetting(key=key, value=value, updated_by=admin.id)
        db.add(row)
    else:
        row.value, row.updated_by = value, admin.id
    db.flush()
    _audit(db, admin.id, "update" if before else "create", "system_setting", key, before, {"key": key, "value": value})
    _commit(db)
    return row


@admin_router.get("/exercises", response_model=ExerciseAdminPage)
def list_admin_exercises(db: Database, query: Annotated[ReferenceQuery, Query()]):
    statement = _reference_query(Exercise, query).options(selectinload(Exercise.muscles))
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    return {"items": db.scalars(statement.offset(query.offset).limit(query.limit)).all(), "total": total}

@admin_router.get("/exercises/{exercise_id}", response_model=ExerciseResponse)
def read_admin_exercise(exercise_id: str, db: Database):
    record = db.scalar(select(Exercise).options(selectinload(Exercise.muscles)).where(
        Exercise.id == _uuid(exercise_id), Exercise.owner_id.is_(None)))
    if record is None:
        raise HTTPException(404, "Global exercise not found")
    return record


@admin_router.post("/exercises", response_model=ExerciseResponse, status_code=201)
def create_admin_exercise(payload: ExerciseInput, db: Database, admin: Annotated[User, Depends(require_admin)]):
    record = Exercise(owner_id=None, name=payload.name, name_key=normalize_name(payload.name))
    apply_exercise(db, record, payload)
    db.add(record)
    db.flush()
    _audit(db, admin.id, "create", "exercise", record.id, None, _snapshot(record))
    _commit(db)
    return record


@admin_router.put("/exercises/{exercise_id}", response_model=ExerciseResponse)
def update_admin_exercise(exercise_id: str, payload: ExerciseInput, db: Database, admin: Annotated[User, Depends(require_admin)]):
    record = db.scalar(select(Exercise).options(selectinload(Exercise.muscles)).where(Exercise.id == _uuid(exercise_id), Exercise.owner_id.is_(None)))
    if record is None:
        raise HTTPException(404, "Global exercise not found")
    before = _snapshot(record)
    record.name, record.name_key, record.deleted_at = payload.name, normalize_name(payload.name), None
    apply_exercise(db, record, payload)
    db.flush()
    _audit(db, admin.id, "update", "exercise", record.id, before, _snapshot(record))
    _commit(db)
    return record


@admin_router.delete("/exercises/{exercise_id}", status_code=204)
def delete_admin_exercise(exercise_id: str, db: Database, admin: Annotated[User, Depends(require_admin)]):
    record = db.scalar(select(Exercise).options(selectinload(Exercise.muscles)).where(Exercise.id == _uuid(exercise_id), Exercise.owner_id.is_(None), Exercise.deleted_at.is_(None)))
    if record is None:
        raise HTTPException(404, "Global exercise not found")
    before = _snapshot(record)
    record.deleted_at = utc_now()
    db.flush()
    _audit(db, admin.id, "delete", "exercise", record.id, before, _snapshot(record))
    _commit(db)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@admin_router.get("/foods", response_model=FoodAdminPage)
def list_admin_foods(db: Database, query: Annotated[ReferenceQuery, Query()]):
    statement = _reference_query(Food, query)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    return {"items": db.scalars(statement.offset(query.offset).limit(query.limit)).all(), "total": total}

@admin_router.get("/foods/{food_id}", response_model=FoodResponse)
def read_admin_food(food_id: str, db: Database):
    record = db.scalar(select(Food).where(Food.id == _uuid(food_id), Food.owner_id.is_(None)))
    if record is None:
        raise HTTPException(404, "Global food not found")
    return record


@admin_router.post("/foods", response_model=FoodResponse, status_code=201)
def create_admin_food(payload: FoodInput, db: Database, admin: Annotated[User, Depends(require_admin)]):
    record = Food(owner_id=None, name=payload.name, name_key=normalize_name(payload.name))
    apply_food(record, payload)
    db.add(record)
    db.flush()
    _audit(db, admin.id, "create", "food", record.id, None, _snapshot(record))
    _commit(db)
    return record


@admin_router.put("/foods/{food_id}", response_model=FoodResponse)
def update_admin_food(food_id: str, payload: FoodInput, db: Database, admin: Annotated[User, Depends(require_admin)]):
    record = db.scalar(select(Food).where(Food.id == _uuid(food_id), Food.owner_id.is_(None)))
    if record is None:
        raise HTTPException(404, "Global food not found")
    before = _snapshot(record)
    record.name, record.name_key, record.deleted_at = payload.name, normalize_name(payload.name), None
    apply_food(record, payload)
    db.flush()
    _audit(db, admin.id, "update", "food", record.id, before, _snapshot(record))
    _commit(db)
    return record


@admin_router.delete("/foods/{food_id}", status_code=204)
def delete_admin_food(food_id: str, db: Database, admin: Annotated[User, Depends(require_admin)]):
    record = db.scalar(select(Food).where(Food.id == _uuid(food_id), Food.owner_id.is_(None), Food.deleted_at.is_(None)))
    if record is None:
        raise HTTPException(404, "Global food not found")
    before = _snapshot(record)
    record.deleted_at = utc_now()
    db.flush()
    _audit(db, admin.id, "delete", "food", record.id, before, _snapshot(record))
    _commit(db)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@admin_router.get("/announcements", response_model=AnnouncementPage)
def list_announcements(db: Database, query: Annotated[AnnouncementQuery, Query()]):
    statement = select(Announcement)
    if query.search:
        needle = f"%{query.search.casefold()}%"
        statement = statement.where(or_(func.lower(Announcement.title).like(needle), func.lower(Announcement.body).like(needle)))
    if not query.include_expired:
        statement = statement.where(or_(Announcement.ends_at.is_(None), Announcement.ends_at > utc_now()))
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    return {"items": db.scalars(statement.order_by(Announcement.starts_at.desc(), Announcement.id.desc()).offset(query.offset).limit(query.limit)).all(), "total": total}


@admin_router.post("/announcements", response_model=AnnouncementResponse, status_code=201)
def create_announcement(payload: AnnouncementInput, db: Database, admin: Annotated[User, Depends(require_admin)]):
    record = Announcement(created_by=admin.id, **payload.model_dump())
    db.add(record)
    db.flush()
    _audit(db, admin.id, "create", "announcement", record.id, None, _snapshot(record))
    _commit(db)
    return record


@admin_router.put("/announcements/{announcement_id}", response_model=AnnouncementResponse)
def update_announcement(announcement_id: str, payload: AnnouncementInput, db: Database, admin: Annotated[User, Depends(require_admin)]):
    record = db.get(Announcement, _uuid(announcement_id))
    if record is None:
        raise HTTPException(404, "Announcement not found")
    before = _snapshot(record)
    for key, value in payload.model_dump().items():
        setattr(record, key, value)
    db.flush()
    _audit(db, admin.id, "update", "announcement", record.id, before, _snapshot(record))
    _commit(db)
    return record


@admin_router.delete("/announcements/{announcement_id}", status_code=204)
def delete_announcement(announcement_id: str, db: Database, admin: Annotated[User, Depends(require_admin)]):
    record = db.get(Announcement, _uuid(announcement_id))
    if record is None:
        raise HTTPException(404, "Announcement not found")
    before = _snapshot(record)
    db.delete(record)
    db.flush()
    _audit(db, admin.id, "delete", "announcement", record.id, before, None)
    _commit(db)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@announcement_router.get("", response_model=AnnouncementPage)
def active_announcements(db: Database, user: CurrentUser, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    now = utc_now()
    statement = select(Announcement).where(Announcement.starts_at <= now, or_(Announcement.ends_at.is_(None), Announcement.ends_at > now))
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    return {"items": db.scalars(statement.order_by(Announcement.starts_at.desc(), Announcement.id.desc()).offset(offset).limit(limit)).all(), "total": total}


@admin_router.get("/audit", response_model=AuditPage)
def list_audit(db: Database, query: Annotated[AuditQuery, Query()]):
    statement = select(AuditRecord)
    if query.resource_type:
        statement = statement.where(AuditRecord.resource_type == query.resource_type)
    if query.action:
        statement = statement.where(AuditRecord.action == query.action)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.scalars(statement.order_by(AuditRecord.created_at.desc(), AuditRecord.id.desc()).offset(query.offset).limit(query.limit)).all()
    return {"items": items, "total": total}


@admin_router.get("/analytics", response_model=AnalyticsResponse)
def analytics(db: Database):
    now = utc_now()
    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    admin_users = db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0
    profiles = db.scalar(select(func.count()).select_from(AthleteProfile)) or 0
    workouts = db.scalar(select(func.count()).select_from(WorkoutSession).where(WorkoutSession.deleted_at.is_(None))) or 0
    nutrition = db.scalar(select(func.count()).select_from(NutritionDay)) or 0
    ai_total = db.scalar(select(func.count()).select_from(AIInsight)) or 0
    ai_success = db.scalar(select(func.count()).select_from(AIInsight).where(AIInsight.status == "success")) or 0
    ai_failed = db.scalar(select(func.count()).select_from(AIInsight).where(AIInsight.status == "unavailable")) or 0
    avg_latency = db.scalar(select(func.avg(AIInsight.latency_ms)).where(AIInsight.latency_ms.is_not(None)))
    try:
        db.execute(select(1))
        db_status = "ok"
    except Exception:
        db_status = "unavailable"
    return {"users": {"total": total_users, "admins": admin_users},
            "onboarding": {"completed": profiles, "completion_rate": round(profiles / total_users, 4) if total_users else 0.0},
            "logging": {"workout_sessions": workouts, "nutrition_days": nutrition},
            "ai": {"jobs": ai_total, "success": ai_success, "failure": ai_failed, "success_rate": round(ai_success / ai_total, 4) if ai_total else 0.0, "average_latency_ms": round(float(avg_latency), 2) if avg_latency is not None else None},
            "health": {"database": db_status, "checked_at": now.isoformat()}}


__all__ = ["admin_router", "announcement_router", "load_setting", "progression_policy", "DEFAULT_SETTINGS"]

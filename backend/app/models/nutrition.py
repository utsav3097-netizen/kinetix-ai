"""Nutrition projections backed by an append-only, owner-bound source journal."""
from datetime import date as CalendarDate, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.identity import new_id, utc_now


class NutritionDay(Base):
    __tablename__ = "nutrition_days"
    __table_args__ = (
        UniqueConstraint("owner_id", "date", name="uq_nutrition_owner_date"),
        CheckConstraint("bodyweight_kg BETWEEN 20 AND 500", name="ck_nutrition_weight"),
        CheckConstraint("tdee_kcal > 0", name="ck_nutrition_tdee"),
        CheckConstraint("revision >= 0", name="ck_nutrition_revision"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    date: Mapped[CalendarDate] = mapped_column(Date, nullable=False)
    training_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    bodyweight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    tdee_kcal: Mapped[float] = mapped_column(Float, nullable=False)
    phase: Mapped[str] = mapped_column(String(24), nullable=False)
    profile_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    targets: Mapped[dict] = mapped_column(JSON, nullable=False)
    protein_range_g: Mapped[dict] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class NutritionSourceRecord(Base):
    __tablename__ = "nutrition_source_records"
    __table_args__ = (
        UniqueConstraint("day_id", "revision", name="uq_nutrition_source_revision"),
        CheckConstraint("revision >= 1", name="ck_nutrition_source_revision"),
        CheckConstraint("entity_type IN ('day', 'meal', 'water')", name="ck_nutrition_source_entity"),
        CheckConstraint("action IN ('create', 'update', 'delete')", name="ck_nutrition_source_action"),
        Index("ix_nutrition_source_owner_date", "owner_id", "date"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    day_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("nutrition_days.id", ondelete="RESTRICT"), nullable=False)
    date: Mapped[CalendarDate] = mapped_column(Date, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(12), nullable=False)
    entity_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False)
    action: Mapped[str] = mapped_column(String(12), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class Meal(Base):
    __tablename__ = "nutrition_meals"
    __table_args__ = (
        CheckConstraint("slot IN ('breakfast', 'pre_workout', 'post_workout', 'lunch', 'dinner', 'snacks')", name="ck_nutrition_meal_slot"),
        Index("ix_nutrition_meal_owner_day", "owner_id", "day_id"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    day_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("nutrition_days.id", ondelete="RESTRICT"), nullable=False)
    slot: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    time: Mapped[str] = mapped_column(String(5), nullable=False)
    source_record_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("nutrition_source_records.id", ondelete="RESTRICT"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MealItem(Base):
    __tablename__ = "nutrition_meal_items"
    __table_args__ = (
        CheckConstraint("grams > 0 AND grams <= 5000", name="ck_nutrition_item_grams"),
        Index("ix_nutrition_item_owner_meal", "owner_id", "meal_id"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    meal_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("nutrition_meals.id", ondelete="RESTRICT"), nullable=False)
    food_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("foods.id", ondelete="RESTRICT"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    grams: Mapped[float] = mapped_column(Float, nullable=False)
    food_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    nutrients: Mapped[dict] = mapped_column(JSON, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WaterEntry(Base):
    __tablename__ = "nutrition_water_entries"
    __table_args__ = (
        CheckConstraint("amount_ml BETWEEN 1 AND 10000", name="ck_nutrition_water_amount"),
        Index("ix_nutrition_water_owner_day", "owner_id", "day_id"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    day_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("nutrition_days.id", ondelete="RESTRICT"), nullable=False)
    amount_ml: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


@event.listens_for(NutritionSourceRecord, "before_update")
@event.listens_for(NutritionSourceRecord, "before_delete")
def reject_source_mutation(mapper, connection, target):
    raise ValueError("Nutrition source records are append-only")

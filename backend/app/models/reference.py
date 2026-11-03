"""Soft-deleted reference records; historical source rows must keep their own snapshots."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.identity import new_id, utc_now


class MuscleGroup(Base):
    __tablename__ = "muscle_groups"
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="ck_muscle_name"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)


class ReferenceFields:
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    # RESTRICT prevents removing an owner from accidentally making private data global.
    owner_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_key: Mapped[str] = mapped_column(String(240), nullable=False)
    # Immutable seed identity survives administrator renames and soft deletion.
    seed_key: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    @property
    def is_custom(self) -> bool:
        return self.owner_id is not None


class Exercise(ReferenceFields, Base):
    __tablename__ = "exercises"
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="ck_exercise_name"),
        CheckConstraint("length(name_key) BETWEEN 1 AND 240", name="ck_exercise_name_key"),
        CheckConstraint("seed_key IS NULL OR owner_id IS NULL", name="ck_exercise_seed_global"),
        CheckConstraint("length(trim(equipment)) BETWEEN 1 AND 80", name="ck_exercise_equipment"),
        CheckConstraint("met BETWEEN 0.1 AND 30", name="ck_exercise_met"),
        CheckConstraint("classification IN ('upper_compound', 'lower_compound', 'isolation')", name="ck_exercise_classification"),
        CheckConstraint("biomechanical_multiplier BETWEEN 0 AND 1", name="ck_exercise_biomechanical"),
        CheckConstraint("measurement_type IN ('reps', 'seconds')", name="ck_exercise_measurement_type"),
        Index("uq_exercise_global_name", "name_key", unique=True, sqlite_where=text("owner_id IS NULL"), postgresql_where=text("owner_id IS NULL")),
        Index("uq_exercise_owner_name", "owner_id", "name_key", unique=True, sqlite_where=text("owner_id IS NOT NULL"), postgresql_where=text("owner_id IS NOT NULL")),
    )

    equipment: Mapped[str] = mapped_column(String(80), nullable=False)
    met: Mapped[float] = mapped_column(Float, nullable=False)
    biomechanical_multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    measurement_type: Mapped[str] = mapped_column(String(7), nullable=False, default="reps")
    muscles: Mapped[list["ExerciseMuscle"]] = relationship(cascade="all, delete-orphan", order_by="ExerciseMuscle.muscle_id")


class ExerciseMuscle(Base):
    __tablename__ = "exercise_muscles"
    __table_args__ = (
        CheckConstraint("contribution BETWEEN 0 AND 1", name="ck_exercise_muscle_contribution"),
    )

    exercise_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True)
    muscle_id: Mapped[str] = mapped_column(String(40), ForeignKey("muscle_groups.id", ondelete="RESTRICT"), primary_key=True)
    contribution: Mapped[float] = mapped_column(Float, nullable=False)


class Food(ReferenceFields, Base):
    __tablename__ = "foods"
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="ck_food_name"),
        CheckConstraint("length(name_key) BETWEEN 1 AND 240", name="ck_food_name_key"),
        CheckConstraint("seed_key IS NULL OR owner_id IS NULL", name="ck_food_seed_global"),
        CheckConstraint("basis_grams = 100", name="ck_food_basis"),
        CheckConstraint("calories BETWEEN 0 AND 900", name="ck_food_calories"),
        CheckConstraint("protein_g BETWEEN 0 AND 100", name="ck_food_protein"),
        CheckConstraint("carbs_g BETWEEN 0 AND 100", name="ck_food_carbs"),
        CheckConstraint("fat_g BETWEEN 0 AND 100", name="ck_food_fat"),
        CheckConstraint("fiber_g BETWEEN 0 AND carbs_g", name="ck_food_fiber"),
        CheckConstraint("protein_g + carbs_g + fat_g <= 100", name="ck_food_macro_mass"),
        Index("uq_food_global_name", "name_key", unique=True, sqlite_where=text("owner_id IS NULL"), postgresql_where=text("owner_id IS NULL")),
        Index("uq_food_owner_name", "owner_id", "name_key", unique=True, sqlite_where=text("owner_id IS NOT NULL"), postgresql_where=text("owner_id IS NOT NULL")),
    )

    basis_grams: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    calories: Mapped[float] = mapped_column(Float, nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False)
    fiber_g: Mapped[float] = mapped_column(Float, nullable=False)

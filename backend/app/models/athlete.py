"""Complete owner-bound onboarding and dated body-weight measurements."""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.identity import new_id, utc_now


class AthleteProfile(Base):
    __tablename__ = "athlete_profiles"
    __table_args__ = (
        CheckConstraint("length(trim(full_name)) BETWEEN 1 AND 120", name="ck_profile_full_name"),
        CheckConstraint("length(trim(nickname)) BETWEEN 1 AND 40", name="ck_profile_nickname"),
        CheckConstraint("age BETWEEN 13 AND 100", name="ck_profile_age"),
        CheckConstraint("biological_sex IN ('male', 'female')", name="ck_profile_biological_sex"),
        CheckConstraint("height_cm BETWEEN 50 AND 250", name="ck_profile_height"),
        CheckConstraint("starting_weight_kg BETWEEN 20 AND 500", name="ck_profile_starting_weight"),
        CheckConstraint("current_weight_kg BETWEEN 20 AND 500", name="ck_profile_current_weight"),
        CheckConstraint("body_fat_percentage IS NULL OR body_fat_percentage BETWEEN 1 AND 75", name="ck_profile_body_fat"),
        CheckConstraint("display_unit IN ('kg', 'lb')", name="ck_profile_display_unit"),
        CheckConstraint("activity_multiplier BETWEEN 1.2 AND 2.4", name="ck_profile_activity"),
        CheckConstraint(
            "phase IN ('baseline_assessment', 'cutting', 'lean_bulking', 'body_recomposition', 'calisthenics_strength')",
            name="ck_profile_phase",
        ),
        CheckConstraint("analysis_weeks IN (1, 2, 3, 4)", name="ck_profile_analysis_weeks"),
    )

    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    nickname: Mapped[str] = mapped_column(String(40), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    biological_sex: Mapped[str] = mapped_column(String(6), nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    starting_weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    current_weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    body_fat_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    display_unit: Mapped[str] = mapped_column(String(2), nullable=False)
    activity_multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    phase: Mapped[str] = mapped_column(String(24), nullable=False)
    analysis_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class WeightCheckIn(Base):
    __tablename__ = "weight_check_ins"
    __table_args__ = (
        UniqueConstraint("user_id", "measured_on", name="uq_weight_check_in_owner_day"),
        CheckConstraint("weight_kg BETWEEN 20 AND 500", name="ck_weight_check_in_weight"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("athlete_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    measured_on: Mapped[date] = mapped_column(Date, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)

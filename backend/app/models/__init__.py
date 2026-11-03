"""Import all persisted models here so Alembic can discover their metadata."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.ai import AIInsight
from app.models.athlete import AthleteProfile, WeightCheckIn
from app.models.identity import AuthRateBucket, RefreshSession, RefreshToken, User
from app.models.nutrition import Meal, MealItem, NutritionDay, NutritionSourceRecord, WaterEntry
from app.models.reference import Exercise, ExerciseMuscle, Food, MuscleGroup
from app.models.workout import WorkoutExercise, WorkoutSession, WorkoutSet, WorkoutSourceRecord
from app.models.planning import ActiveTrainingPlan, PlanDraft, Report, TrainingPlanVersion

__all__ = [
    "AIInsight",
    "AthleteProfile", "AuthRateBucket", "Exercise", "ExerciseMuscle", "Food", "MuscleGroup",
    "RefreshSession", "RefreshToken", "SystemSchema", "User", "WeightCheckIn",
    "WorkoutExercise", "WorkoutSession", "WorkoutSet", "WorkoutSourceRecord",
    "Meal", "MealItem", "NutritionDay", "NutritionSourceRecord", "WaterEntry",
    "ActiveTrainingPlan", "PlanDraft", "Report", "TrainingPlanVersion",
]


class SystemSchema(Base):
    __tablename__ = "system_schema"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    component: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

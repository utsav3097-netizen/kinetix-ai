"""Shared validation for athlete custom references, seeding, and future admin CRUD."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Contribution = Annotated[float, Field(ge=0, le=1)]
Nutrient = Annotated[float, Field(ge=0, le=100)]


class ReferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False)

    name: str = Field(min_length=1, max_length=120)


class MuscleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False)

    muscle_id: str = Field(min_length=1, max_length=40)
    contribution: Contribution


class ExerciseInput(ReferenceInput):
    equipment: str = Field(min_length=1, max_length=80)
    met: float = Field(ge=0.1, le=30)
    biomechanical_multiplier: float = Field(ge=0, le=1)
    measurement_type: Literal["reps", "seconds"] = "reps"
    classification: Literal["upper_compound", "lower_compound", "isolation"]
    muscles: list[MuscleInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_muscles(self) -> Self:
        if len({muscle.muscle_id for muscle in self.muscles}) != len(self.muscles):
            raise ValueError("Each muscle may appear only once")
        return self


class FoodInput(ReferenceInput):
    calories: float = Field(ge=0, le=900)
    protein_g: Nutrient
    carbs_g: Nutrient
    fat_g: Nutrient
    fiber_g: Nutrient

    @model_validator(mode="after")
    def consistent_nutrients(self) -> Self:
        if self.protein_g + self.carbs_g + self.fat_g > 100:
            raise ValueError("Protein, carbohydrate and fat cannot total more than 100 g per 100 g")
        if self.fiber_g > self.carbs_g:
            raise ValueError("Fiber cannot exceed total carbohydrate")
        # Preserve label energy: polyols and other components need not follow
        # the simplified 4/4/9 factors used for planning macro targets.
        return self


class MuscleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    muscle_id: str
    contribution: float


class MuscleGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


class ExerciseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str | None
    name: str
    equipment: str
    met: float
    biomechanical_multiplier: float
    measurement_type: Literal["reps", "seconds"]
    classification: Literal["upper_compound", "lower_compound", "isolation"]
    muscles: list[MuscleResponse]
    is_custom: bool


class FoodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str | None
    name: str
    basis_grams: Literal[100]
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    is_custom: bool


class ExercisePage(BaseModel):
    items: list[ExerciseResponse]
    total: int


class FoodPage(BaseModel):
    items: list[FoodResponse]
    total: int


class ReferenceQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    q: str = Field(default="", max_length=120)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class ExerciseQuery(ReferenceQuery):
    muscle: str | None = Field(default=None, min_length=1, max_length=40)
    equipment: str | None = Field(default=None, min_length=1, max_length=80)

"""Atomic onboarding and immutable, owner-scoped weight history."""

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import exists, func, select, update
from sqlalchemy.exc import IntegrityError

from app.auth import CurrentUser, Database, prevent_caching
from app.models import AthleteProfile, User, WeightCheckIn
from app.models.identity import utc_now

router = APIRouter(prefix="/api/v1/profile", tags=["profile"], dependencies=[Depends(prevent_caching)])
Weight = Annotated[float, Field(strict=True, ge=20, le=500, allow_inf_nan=False)]


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False)

    full_name: str = Field(min_length=1, max_length=120)
    nickname: str = Field(min_length=1, max_length=40)
    age: int = Field(ge=13, le=100)
    biological_sex: Literal["male", "female"]
    height_cm: float = Field(ge=50, le=250)
    starting_weight_kg: Weight
    current_weight_kg: Weight
    body_fat_percentage: float | None = Field(default=None, ge=1, le=75)
    display_unit: Literal["kg", "lb"]
    activity_multiplier: float = Field(ge=1.2, le=2.4)
    phase: Literal["baseline_assessment", "cutting", "lean_bulking", "body_recomposition", "calisthenics_strength"]
    analysis_weeks: Literal[1, 2, 3, 4]

    @field_validator("analysis_weeks", mode="before")
    @classmethod
    def strict_analysis_window(cls, value: object) -> object:
        # Literal equality alone would admit True and 1.0 as the integer 1.
        if type(value) is not int:
            raise ValueError("Analysis weeks must be an integer")
        return value


class ProfileResponse(ProfileInput):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    created_at: datetime
    updated_at: datetime


class OnboardingResponse(BaseModel):
    onboarding_complete: bool
    profile: ProfileResponse | None


class CheckInInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    measured_on: date
    weight_kg: Weight

    @field_validator("measured_on", mode="before")
    @classmethod
    def calendar_date(cls, value: object) -> date:
        if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-":
            raise ValueError("Measured date must use YYYY-MM-DD")
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise ValueError("Measured date must be a valid YYYY-MM-DD date") from None
        if parsed.isoformat() != value:
            raise ValueError("Measured date must use YYYY-MM-DD")
        return parsed


class CheckInResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    measured_on: date
    weight_kg: float


class CheckInPage(BaseModel):
    items: list[CheckInResponse]
    total: int


class CheckInPagination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=30, ge=1, le=100)


def require_profile(user: CurrentUser, db: Database) -> AthleteProfile:
    """Gate tracking/planning on the owner's complete, atomically saved profile."""
    profile = db.get(AthleteProfile, user.id)
    if profile is None:
        raise HTTPException(status_code=403, detail="Complete onboarding before tracking or planning")
    return profile


CompletedProfile = Annotated[AthleteProfile, Depends(require_profile)]


def onboarding_response(profile: AthleteProfile | None) -> OnboardingResponse:
    return OnboardingResponse(
        onboarding_complete=profile is not None,
        profile=ProfileResponse.model_validate(profile) if profile is not None else None,
    )


@router.get("", response_model=OnboardingResponse)
def get_profile(user: CurrentUser, db: Database) -> OnboardingResponse:
    return onboarding_response(db.get(AthleteProfile, user.id))


@router.put("", response_model=OnboardingResponse)
def save_profile(payload: ProfileInput, user: CurrentUser, db: Database) -> OnboardingResponse:
    # Serialize first onboarding saves for an owner on PostgreSQL. SQLite's
    # unique primary key also prevents concurrent requests creating two profiles.
    db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    profile = db.get(AthleteProfile, user.id)
    if profile is None:
        profile = AthleteProfile(user_id=user.id, **payload.model_dump())
        db.add(profile)
        try:
            db.flush()
            # Starting weight is an undated baseline, not invented historical
            # evidence. A single current measurement seeds today's UTC record.
            db.add(WeightCheckIn(user_id=user.id, measured_on=utc_now().date(), weight_kg=payload.current_weight_kg))
            db.commit()
        except IntegrityError:
            db.rollback()
            if db.get(AthleteProfile, user.id) is not None:
                raise HTTPException(status_code=409, detail="Profile was already saved; reload before editing") from None
            raise
    else:
        latest = db.scalar(
            select(WeightCheckIn).where(WeightCheckIn.user_id == user.id).order_by(WeightCheckIn.measured_on.desc()).limit(1)
        )
        if latest is None or payload.current_weight_kg != latest.weight_kg:
            raise HTTPException(status_code=422, detail="Current weight must match the latest check-in; add a new weight check-in to change it")
        # Never overwrite measurements or a concurrent newer check-in's weight.
        for field, value in payload.model_dump(exclude={"current_weight_kg"}).items():
            setattr(profile, field, value)
        db.commit()
    db.refresh(profile)
    return onboarding_response(profile)


@router.get("/check-ins", response_model=CheckInPage)
def list_check_ins(profile: CompletedProfile, db: Database, pagination: Annotated[CheckInPagination, Query()]) -> CheckInPage:
    owner_filter = WeightCheckIn.user_id == profile.user_id
    total = db.scalar(select(func.count()).select_from(WeightCheckIn).where(owner_filter))
    items = db.scalars(
        select(WeightCheckIn)
        .where(owner_filter)
        .order_by(WeightCheckIn.measured_on.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    ).all()
    return CheckInPage(items=[CheckInResponse.model_validate(item) for item in items], total=total)


@router.post("/check-ins", response_model=CheckInResponse, status_code=201)
def create_check_in(payload: CheckInInput, profile: CompletedProfile, db: Database) -> CheckInResponse:
    owner_id = profile.user_id
    # Same-owner mutations serialize in PostgreSQL; SQLite serializes writes.
    db.scalar(select(User.id).where(User.id == owner_id).with_for_update())
    check_in = WeightCheckIn(user_id=owner_id, **payload.model_dump())
    db.add(check_in)
    try:
        db.flush()
        # Evaluate against persisted dates, not insertion order or a stale ORM
        # profile, so older/backfilled measurements never replace current weight.
        later_check_in = exists().where(WeightCheckIn.user_id == owner_id, WeightCheckIn.measured_on > payload.measured_on)
        db.execute(
            update(AthleteProfile)
            .where(AthleteProfile.user_id == owner_id, ~later_check_in)
            .values(current_weight_kg=payload.weight_kg, updated_at=utc_now()),
            execution_options={"synchronize_session": False},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate = db.scalar(select(WeightCheckIn.id).where(WeightCheckIn.user_id == owner_id, WeightCheckIn.measured_on == payload.measured_on))
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="A weight check-in already exists for this date") from None
        raise
    return CheckInResponse.model_validate(check_in)

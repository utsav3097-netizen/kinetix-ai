"""Strict transport validation for the administration and announcements APIs."""
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.reference_schemas import ExerciseResponse, FoodResponse


class AdminModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False)


class SettingInput(AdminModel):
    value: Any


class SettingResponse(AdminModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False)
    key: str
    value: Any
    updated_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

class AnnouncementInput(AdminModel):
    model_config = ConfigDict(extra="forbid", strict=False, str_strip_whitespace=True, allow_inf_nan=False)
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    starts_at: AwareDatetime
    ends_at: AwareDatetime | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Announcement times must include a timezone")
        return value

    @model_validator(mode="after")
    def valid_window(self):
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("Announcement end must be after its start")
        return self


class AnnouncementResponse(AdminModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False)
    id: str
    title: str
    body: str
    starts_at: datetime
    ends_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class AnnouncementPage(AdminModel):
    items: list[AnnouncementResponse]
    total: int


class AnnouncementQuery(AdminModel):
    model_config = ConfigDict(extra="forbid", strict=False, str_strip_whitespace=True, allow_inf_nan=False)
    offset: int = Field(default=0, ge=0, le=1_000_000)
    limit: int = Field(default=20, ge=1, le=100)
    search: str | None = Field(default=None, min_length=1, max_length=120)
    include_expired: bool = False


class AuditQuery(AdminModel):
    model_config = ConfigDict(extra="forbid", strict=False, str_strip_whitespace=True, allow_inf_nan=False)
    offset: int = Field(default=0, ge=0, le=1_000_000)
    limit: int = Field(default=50, ge=1, le=100)
    resource_type: str | None = Field(default=None, min_length=1, max_length=40)
    action: str | None = Field(default=None, min_length=1, max_length=24)


class ReferenceQuery(AdminModel):
    model_config = ConfigDict(extra="forbid", strict=False, str_strip_whitespace=True, allow_inf_nan=False)
    offset: int = Field(default=0, ge=0, le=1_000_000)
    limit: int = Field(default=20, ge=1, le=100)
    search: str | None = Field(default=None, min_length=1, max_length=120)
    include_deleted: bool = False


class ExerciseAdminPage(AdminModel):
    items: list[ExerciseResponse]
    total: int


class FoodAdminPage(AdminModel):
    items: list[FoodResponse]
    total: int




class AnalyticsResponse(AdminModel):
    users: dict[str, int | float]
    onboarding: dict[str, int | float]
    logging: dict[str, int | float]
    ai: dict[str, int | float | None]
    health: dict[str, str | int | float]


class AuditResponse(AdminModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False)
    id: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    before: dict | None
    after: dict | None
    created_at: datetime

class AuditPage(AdminModel):
    items: list[AuditResponse]
    total: int

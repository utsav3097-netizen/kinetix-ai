"""Bounded, typed coach transport and provider response contracts."""
from datetime import date, datetime
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.planning_schemas import DraftInput, PlanEditInput
from app.workout_schemas import SessionInput
from app.nutrition_schemas import MealInput


class CoachModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True, allow_inf_nan=False)


class CoachMessageInput(CoachModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None

    @field_validator("conversation_id")
    @classmethod
    def valid_conversation_id(cls, value: str | None) -> str | None:
        return str(UUID(value)) if value is not None else None


class CoachPageQuery(CoachModel):
    model_config = ConfigDict(extra="forbid", strict=False, str_strip_whitespace=True, allow_inf_nan=False)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=30, ge=1, le=100)
    conversation_id: str | None = None

    @field_validator("conversation_id")
    @classmethod
    def valid_conversation_id(cls, value: str | None) -> str | None:
        return str(UUID(value)) if value is not None else None


class ConfirmInput(CoachModel):
    confirm: Literal[True]


class ProposalBase(CoachModel):
    target_id: str | None = None
    summary: str = Field(min_length=1, max_length=500)

    @field_validator("target_id")
    @classmethod
    def valid_target_id(cls, value: str | None) -> str | None:
        return str(UUID(value)) if value is not None else None


class PlanDraftProposal(ProposalBase):
    kind: Literal["plan_draft"]
    target_id: None = None
    payload: DraftInput


class PlanEditProposal(ProposalBase):
    kind: Literal["plan_edit"]
    target_id: str
    expected_revision: int | None = Field(default=None, ge=0, strict=True)
    payload: PlanEditInput


class WorkoutUpdateProposal(ProposalBase):
    kind: Literal["workout_update"]
    target_id: str
    expected_revision: int | None = Field(default=None, ge=0, strict=True)
    payload: SessionInput


class MealUpdateProposal(ProposalBase):
    kind: Literal["meal_update"]
    target_id: str
    expected_revision: int | None = Field(default=None, ge=0, strict=True)
    payload: MealInput


CoachProposal = Annotated[Union[PlanDraftProposal, PlanEditProposal, WorkoutUpdateProposal, MealUpdateProposal], Field(discriminator="kind")]


class CoachAIResponse(CoachModel):
    reply: str = Field(min_length=1, max_length=4000)
    proposal: CoachProposal | None = None


class CoachMessageView(CoachModel):
    id: str
    role: Literal["user", "assistant"]
    status: Literal["complete", "unavailable", "safety"]
    content: str
    proposal_state: Literal["none", "pending", "confirmed", "expired", "rejected"]
    proposal: CoachProposal | None
    result: dict | None
    created_at: datetime
    confirmed_at: datetime | None


class CoachMessagePage(CoachModel):
    conversation_id: str | None
    items: list[CoachMessageView]
    total: int


class CoachMessageResponse(CoachModel):
    conversation_id: str
    user: CoachMessageView
    assistant: CoachMessageView


class CoachConfirmationResponse(CoachModel):
    message: CoachMessageView
    committed: bool

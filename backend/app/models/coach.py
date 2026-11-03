"""Persistent owner-scoped coach conversations and confirmation state."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.identity import new_id, utc_now


class CoachConversation(Base):
    __tablename__ = "coach_conversations"
    __table_args__ = (
        UniqueConstraint("owner_id", name="uq_coach_conversation_owner"),
        Index("ix_coach_conversation_owner", "owner_id"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class CoachMessage(Base):
    __tablename__ = "coach_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_coach_message_role"),
        CheckConstraint("status IN ('complete', 'unavailable', 'safety')", name="ck_coach_message_status"),
        CheckConstraint("proposal_state IN ('none', 'pending', 'confirmed', 'expired', 'rejected')", name="ck_coach_proposal_state"),
        Index("ix_coach_message_owner_created", "owner_id", "created_at", "id"),
        Index("ix_coach_message_conversation_created", "conversation_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("coach_conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="complete")
    content: Mapped[str] = mapped_column(String(6000), nullable=False)
    proposal_state: Mapped[str] = mapped_column(String(12), nullable=False, default="none")
    proposal: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

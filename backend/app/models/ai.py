"""Durable AI jobs; terminal results retain their immutable source and context."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.identity import new_id, utc_now


class AIInsight(Base):
    __tablename__ = "ai_insights"
    __table_args__ = (
        UniqueConstraint("source_record_id", "kind", "attempt", name="uq_ai_source_attempt"),
        CheckConstraint("kind IN ('set', 'exercise_block', 'meal_parse')", name="ck_ai_kind"),
        CheckConstraint("status IN ('pending', 'success', 'unavailable')", name="ck_ai_status"),
        CheckConstraint("attempt >= 0", name="ck_ai_attempt"),
        CheckConstraint("(kind = 'meal_parse' AND source_record_id IS NULL) OR (kind != 'meal_parse' AND source_record_id IS NOT NULL)", name="ck_ai_source"),
        Index("ix_ai_queue", "status", "created_at"),
        Index("ix_ai_owner", "owner_id", "id"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("workout_source_records.id", ondelete="RESTRICT"))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    context: Mapped[dict] = mapped_column(JSON, nullable=False)
    comparison: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(String(240))
    provider: Mapped[str | None] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(120))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

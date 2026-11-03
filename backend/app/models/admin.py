"""Administration policy, scheduled communications, and append-only audit records."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.identity import new_id, utc_now


class SystemSetting(Base):
    """Mutable, validated application policy owned by administrators."""
    __tablename__ = "system_settings"
    __table_args__ = (
        CheckConstraint("length(trim(key)) BETWEEN 1 AND 80", name="ck_system_setting_key"),
    )

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_by: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class Announcement(Base):
    """A public, time-windowed announcement; never stores athlete context."""
    __tablename__ = "announcements"
    __table_args__ = (
        CheckConstraint("length(trim(title)) BETWEEN 1 AND 160", name="ck_announcement_title"),
        CheckConstraint("length(trim(body)) BETWEEN 1 AND 4000", name="ck_announcement_body"),
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="ck_announcement_window"),
        Index("ix_announcements_schedule", "starts_at", "ends_at"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(String(4000), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class AuditRecord(Base):
    """Append-only record of administrator mutations; before/after are immutable snapshots."""
    __tablename__ = "audit_records"
    __table_args__ = (
        Index("ix_audit_records_created", "created_at", "id"),
        Index("ix_audit_records_resource", "resource_type", "resource_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(80), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

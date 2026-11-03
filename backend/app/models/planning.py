"""Frozen report/draft/version content with a separate mutable active pointer."""
from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.identity import new_id, utc_now


class OwnedSnapshot:
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Report(OwnedSnapshot, Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("kind IN ('weekly', 'analysis', 'snapshot')", name="ck_report_kind"),
        CheckConstraint("window_end >= window_start AND revision >= 1", name="ck_report_window"),
        UniqueConstraint("owner_id", "kind", "window_start", "window_end", "revision", name="uq_report_revision"),
        Index("uq_report_period", "owner_id", "kind", "window_start", "window_end", unique=True,
              sqlite_where=text("kind != 'snapshot'"), postgresql_where=text("kind != 'snapshot'")),
    )
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)


class PlanDraft(OwnedSnapshot, Base):
    __tablename__ = "plan_drafts"
    parent_version_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("training_plan_versions.id", ondelete="RESTRICT", use_alter=True, name="fk_draft_parent_version"))
    based_on_draft_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("plan_drafts.id", ondelete="RESTRICT"))
    data: Mapped[dict] = mapped_column(JSON, nullable=False)


class TrainingPlanVersion(Base):
    __tablename__ = "training_plan_versions"
    __table_args__ = (
        UniqueConstraint("owner_id", "version", name="uq_plan_owner_version"),
        UniqueConstraint("draft_id", name="uq_plan_accepted_draft"),
        CheckConstraint("version >= 1", name="ck_plan_version"),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    draft_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("plan_drafts.id", ondelete="RESTRICT"), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ActiveTrainingPlan(Base):
    __tablename__ = "active_training_plans"
    owner_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    version_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("training_plan_versions.id", ondelete="RESTRICT"), nullable=False, unique=True)

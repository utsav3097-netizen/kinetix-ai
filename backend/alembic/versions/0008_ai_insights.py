"""Persist source-linked AI jobs, private inputs, and validated draft results.

Revision ID: 0008_ai_insights
Revises: 0007_food_label_energy
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_ai_insights"
down_revision = "0007_food_label_energy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_insights",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("source_record_id", sa.Uuid(as_uuid=False), sa.ForeignKey("workout_source_records.id", ondelete="RESTRICT")),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("comparison", sa.JSON()),
        sa.Column("result", sa.JSON()),
        sa.Column("reason", sa.String(240)),
        sa.Column("provider", sa.String(20)),
        sa.Column("model", sa.String(120)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("claim_token", sa.Uuid(as_uuid=False)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("source_record_id", "kind", "attempt", name="uq_ai_source_attempt"),
        sa.CheckConstraint("kind IN ('set', 'exercise_block', 'meal_parse')", name="ck_ai_kind"),
        sa.CheckConstraint("status IN ('pending', 'success', 'unavailable')", name="ck_ai_status"),
        sa.CheckConstraint("attempt >= 0", name="ck_ai_attempt"),
        sa.CheckConstraint("(kind = 'meal_parse' AND source_record_id IS NULL) OR (kind != 'meal_parse' AND source_record_id IS NOT NULL)", name="ck_ai_source"),
    )
    op.create_index("ix_ai_queue", "ai_insights", ["status", "created_at"])
    op.create_index("ix_ai_owner", "ai_insights", ["owner_id", "id"])


def downgrade() -> None:
    op.drop_table("ai_insights")

"""Persistent owner-scoped coach conversations and proposals.

Revision ID: 0010_coach
Revises: 0009_reports_plans
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_coach"
down_revision = "0009_reports_plans"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "coach_conversations",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", name="uq_coach_conversation_owner"),
    )
    op.create_index("ix_coach_conversation_owner", "coach_conversations", ["owner_id"])
    op.create_table(
        "coach_messages",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.Uuid(as_uuid=False), sa.ForeignKey("coach_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("content", sa.String(6000), nullable=False),
        sa.Column("proposal_state", sa.String(12), nullable=False),
        sa.Column("proposal", sa.JSON()),
        sa.Column("result", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_coach_message_role"),
        sa.CheckConstraint("status IN ('complete', 'unavailable', 'safety')", name="ck_coach_message_status"),
        sa.CheckConstraint("proposal_state IN ('none', 'pending', 'confirmed', 'expired', 'rejected')", name="ck_coach_proposal_state"),
    )
    op.create_index("ix_coach_message_owner_created", "coach_messages", ["owner_id", "created_at", "id"])
    op.create_index("ix_coach_message_conversation_created", "coach_messages", ["conversation_id", "created_at", "id"])


def downgrade():
    op.drop_index("ix_coach_message_conversation_created", table_name="coach_messages")
    op.drop_index("ix_coach_message_owner_created", table_name="coach_messages")
    op.drop_table("coach_messages")
    op.drop_index("ix_coach_conversation_owner", table_name="coach_conversations")
    op.drop_table("coach_conversations")

"""Create the deployment schema marker.

Revision ID: 0001_foundation
Revises: None
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = op.create_table(
        "system_schema",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("component", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("component"),
    )
    op.bulk_insert(table, [{"id": 1, "component": "kinetix-ai"}])


def downgrade() -> None:
    op.drop_table("system_schema")

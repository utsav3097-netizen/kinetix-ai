"""Immutable reports, draft plans, accepted versions and active pointers.

Revision ID: 0009_reports_plans
Revises: 0008_ai_insights
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_reports_plans"
down_revision = "0008_ai_insights"
branch_labels = None
depends_on = None


def identity():
    return [sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
            sa.Column("owner_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)]


def upgrade():
    op.create_table("reports", *identity(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False), sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False), sa.Column("data", sa.JSON(), nullable=False),
        sa.CheckConstraint("kind IN ('weekly', 'analysis', 'snapshot')", name="ck_report_kind"),
        sa.CheckConstraint("window_end >= window_start AND revision >= 1", name="ck_report_window"),
        sa.UniqueConstraint("owner_id", "kind", "window_start", "window_end", "revision", name="uq_report_revision"))
    op.create_index("ix_reports_owner_id", "reports", ["owner_id"])
    op.create_index("uq_report_period", "reports", ["owner_id", "kind", "window_start", "window_end"], unique=True,
                    sqlite_where=sa.text("kind != 'snapshot'"), postgresql_where=sa.text("kind != 'snapshot'"))
    op.create_table("plan_drafts", *identity(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parent_version_id", sa.Uuid(as_uuid=False)),
        sa.Column("based_on_draft_id", sa.Uuid(as_uuid=False), sa.ForeignKey("plan_drafts.id", ondelete="RESTRICT")),
        sa.Column("data", sa.JSON(), nullable=False))
    op.create_index("ix_plan_drafts_owner_id", "plan_drafts", ["owner_id"])
    op.create_table("training_plan_versions", *identity(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("draft_id", sa.Uuid(as_uuid=False), sa.ForeignKey("plan_drafts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "version", name="uq_plan_owner_version"),
        sa.UniqueConstraint("draft_id", name="uq_plan_accepted_draft"),
        sa.CheckConstraint("version >= 1", name="ck_plan_version"))
    op.create_index("ix_training_plan_versions_owner_id", "training_plan_versions", ["owner_id"])
    with op.batch_alter_table("plan_drafts") as batch:
        batch.create_foreign_key("fk_draft_parent_version", "training_plan_versions", ["parent_version_id"], ["id"], ondelete="RESTRICT")
    op.create_table("active_training_plans",
        sa.Column("owner_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("version_id", sa.Uuid(as_uuid=False), sa.ForeignKey("training_plan_versions.id", ondelete="RESTRICT"), nullable=False, unique=True))
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION reject_planning_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'Reports and plans are immutable'; END; $$ LANGUAGE plpgsql""")
    for table in ("reports", "plan_drafts", "training_plan_versions"):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_planning_mutation()")
        else:
            for action in ("UPDATE", "DELETE"):
                op.execute(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Reports and plans are immutable'); END")


def downgrade():
    for table in ("reports", "plan_drafts", "training_plan_versions"):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"DROP TRIGGER {table}_immutable ON {table}")
        else:
            for action in ("update", "delete"):
                op.execute(f"DROP TRIGGER {table}_no_{action}")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION reject_planning_mutation()")
    op.drop_table("active_training_plans")
    with op.batch_alter_table("plan_drafts") as batch:
        batch.drop_constraint("fk_draft_parent_version", type_="foreignkey")
    op.drop_table("training_plan_versions")
    op.drop_table("plan_drafts")
    op.drop_table("reports")

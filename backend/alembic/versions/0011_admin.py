"""Administration policy, announcements, and append-only audit records.

Revision ID: 0011_admin
Revises: 0010_coach
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_admin"
down_revision = "0010_coach"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(key)) BETWEEN 1 AND 80", name="ck_system_setting_key"),
    )
    op.create_table(
        "announcements",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.String(4000), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(title)) BETWEEN 1 AND 160", name="ck_announcement_title"),
        sa.CheckConstraint("length(trim(body)) BETWEEN 1 AND 4000", name="ck_announcement_body"),
        sa.CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="ck_announcement_window"),
    )
    op.create_index("ix_announcements_schedule", "announcements", ["starts_at", "ends_at"])
    op.create_table(
        "audit_records",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("actor_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("resource_type", sa.String(40), nullable=False),
        sa.Column("resource_id", sa.String(80), nullable=False),
        sa.Column("before", sa.JSON()),
        sa.Column("after", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_records_created", "audit_records", ["created_at", "id"])
    op.create_index("ix_audit_records_resource", "audit_records", ["resource_type", "resource_id", "created_at"])
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION reject_audit_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'Audit records are append-only'; END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER audit_records_immutable BEFORE UPDATE OR DELETE ON audit_records FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()")
    else:
        op.execute("CREATE TRIGGER audit_records_no_update BEFORE UPDATE ON audit_records BEGIN SELECT RAISE(ABORT, 'Audit records are append-only'); END")
        op.execute("CREATE TRIGGER audit_records_no_delete BEFORE DELETE ON audit_records BEGIN SELECT RAISE(ABORT, 'Audit records are append-only'); END")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER audit_records_immutable ON audit_records")
        op.execute("DROP FUNCTION reject_audit_mutation()")
    else:
        op.execute("DROP TRIGGER audit_records_no_update")
        op.execute("DROP TRIGGER audit_records_no_delete")
    op.drop_index("ix_audit_records_resource", table_name="audit_records")
    op.drop_index("ix_audit_records_created", table_name="audit_records")
    op.drop_table("audit_records")
    op.drop_index("ix_announcements_schedule", table_name="announcements")
    op.drop_table("announcements")
    op.drop_table("system_settings")

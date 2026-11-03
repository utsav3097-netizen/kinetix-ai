"""Add complete athlete profiles and immutable owner-scoped weight check-ins.

Revision ID: 0003_athlete
Revises: 0002_identity
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_athlete"
down_revision = "0002_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "athlete_profiles",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("nickname", sa.String(40), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("biological_sex", sa.String(6), nullable=False),
        sa.Column("height_cm", sa.Float(), nullable=False),
        sa.Column("starting_weight_kg", sa.Float(), nullable=False),
        sa.Column("current_weight_kg", sa.Float(), nullable=False),
        sa.Column("body_fat_percentage", sa.Float(), nullable=True),
        sa.Column("display_unit", sa.String(2), nullable=False),
        sa.Column("activity_multiplier", sa.Float(), nullable=False),
        sa.Column("phase", sa.String(24), nullable=False),
        sa.Column("analysis_weeks", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(full_name)) BETWEEN 1 AND 120", name="ck_profile_full_name"),
        sa.CheckConstraint("length(trim(nickname)) BETWEEN 1 AND 40", name="ck_profile_nickname"),
        sa.CheckConstraint("age BETWEEN 13 AND 100", name="ck_profile_age"),
        sa.CheckConstraint("biological_sex IN ('male', 'female')", name="ck_profile_biological_sex"),
        sa.CheckConstraint("height_cm BETWEEN 50 AND 250", name="ck_profile_height"),
        sa.CheckConstraint("starting_weight_kg BETWEEN 20 AND 500", name="ck_profile_starting_weight"),
        sa.CheckConstraint("current_weight_kg BETWEEN 20 AND 500", name="ck_profile_current_weight"),
        sa.CheckConstraint("body_fat_percentage IS NULL OR body_fat_percentage BETWEEN 1 AND 75", name="ck_profile_body_fat"),
        sa.CheckConstraint("display_unit IN ('kg', 'lb')", name="ck_profile_display_unit"),
        sa.CheckConstraint("activity_multiplier BETWEEN 1.2 AND 2.4", name="ck_profile_activity"),
        sa.CheckConstraint(
            "phase IN ('baseline_assessment', 'cutting', 'lean_bulking', 'body_recomposition', 'calisthenics_strength')",
            name="ck_profile_phase",
        ),
        sa.CheckConstraint("analysis_weeks IN (1, 2, 3, 4)", name="ck_profile_analysis_weeks"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "weight_check_ins",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["athlete_profiles.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "measured_on", name="uq_weight_check_in_owner_day"),
        sa.CheckConstraint("weight_kg BETWEEN 20 AND 500", name="ck_weight_check_in_weight"),
    )


def downgrade() -> None:
    op.drop_table("weight_check_ins")
    op.drop_table("athlete_profiles")

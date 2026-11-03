"""Add private/global exercise and normalized food references.

Revision ID: 0004_reference
Revises: 0003_athlete
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_reference"
down_revision = "0003_athlete"
branch_labels = None
depends_on = None


def reference_columns():
    return [
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("name_key", sa.String(240), nullable=False),
        sa.Column("seed_key", sa.String(80), nullable=True, unique=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def reference_constraints(kind):
    return [
        sa.CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name=f"ck_{kind}_name"),
        sa.CheckConstraint("length(name_key) BETWEEN 1 AND 240", name=f"ck_{kind}_name_key"),
        sa.CheckConstraint("seed_key IS NULL OR owner_id IS NULL", name=f"ck_{kind}_seed_global"),
    ]


def upgrade() -> None:
    op.create_table(
        "muscle_groups",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="ck_muscle_name"),
    )
    op.create_table(
        "exercises", *reference_columns(),
        sa.Column("equipment", sa.String(80), nullable=False),
        sa.Column("met", sa.Float(), nullable=False),
        sa.Column("biomechanical_multiplier", sa.Float(), nullable=False),
        sa.Column("measurement_type", sa.String(7), nullable=False),
        sa.Column("classification", sa.String(20), nullable=False),
        *reference_constraints("exercise"),
        sa.CheckConstraint("length(trim(equipment)) BETWEEN 1 AND 80", name="ck_exercise_equipment"),
        sa.CheckConstraint("met BETWEEN 0.1 AND 30", name="ck_exercise_met"),
        sa.CheckConstraint("biomechanical_multiplier BETWEEN 0 AND 1", name="ck_exercise_biomechanical"),
        sa.CheckConstraint("measurement_type IN ('reps', 'seconds')", name="ck_exercise_measurement_type"),
        sa.CheckConstraint("classification IN ('upper_compound', 'lower_compound', 'isolation')", name="ck_exercise_classification"),
    )
    op.create_table(
        "exercise_muscles",
        sa.Column("exercise_id", sa.Uuid(as_uuid=False), sa.ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("muscle_id", sa.String(40), sa.ForeignKey("muscle_groups.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("contribution", sa.Float(), nullable=False),
        sa.CheckConstraint("contribution BETWEEN 0 AND 1", name="ck_exercise_muscle_contribution"),
    )
    op.create_table(
        "foods", *reference_columns(),
        sa.Column("basis_grams", sa.Integer(), nullable=False),
        sa.Column("calories", sa.Float(), nullable=False),
        sa.Column("protein_g", sa.Float(), nullable=False),
        sa.Column("carbs_g", sa.Float(), nullable=False),
        sa.Column("fat_g", sa.Float(), nullable=False),
        sa.Column("fiber_g", sa.Float(), nullable=False),
        *reference_constraints("food"),
        sa.CheckConstraint("basis_grams = 100", name="ck_food_basis"),
        sa.CheckConstraint("calories BETWEEN 0 AND 900", name="ck_food_calories"),
        sa.CheckConstraint("protein_g BETWEEN 0 AND 100", name="ck_food_protein"),
        sa.CheckConstraint("carbs_g BETWEEN 0 AND 100", name="ck_food_carbs"),
        sa.CheckConstraint("fat_g BETWEEN 0 AND 100", name="ck_food_fat"),
        sa.CheckConstraint("fiber_g BETWEEN 0 AND carbs_g", name="ck_food_fiber"),
        sa.CheckConstraint("protein_g + carbs_g + fat_g <= 100", name="ck_food_macro_mass"),
        sa.CheckConstraint(
            "abs(calories - (4*protein_g + 4*carbs_g + 9*fat_g - 2*fiber_g)) <= "
            "CASE WHEN (4*protein_g + 4*carbs_g + 9*fat_g - 2*fiber_g)*0.2 > 20 "
            "THEN (4*protein_g + 4*carbs_g + 9*fat_g - 2*fiber_g)*0.2 ELSE 20 END",
            name="ck_food_energy",
        ),
    )
    # Include tombstones: deleted names remain reserved and cannot be silently reused.
    for table, kind in (("exercises", "exercise"), ("foods", "food")):
        op.create_index(f"uq_{kind}_global_name", table, ["name_key"], unique=True,
                        sqlite_where=sa.text("owner_id IS NULL"), postgresql_where=sa.text("owner_id IS NULL"))
        op.create_index(f"uq_{kind}_owner_name", table, ["owner_id", "name_key"], unique=True,
                        sqlite_where=sa.text("owner_id IS NOT NULL"), postgresql_where=sa.text("owner_id IS NOT NULL"))


def downgrade() -> None:
    op.drop_table("exercise_muscles")
    op.drop_table("exercises")
    op.drop_table("foods")
    op.drop_table("muscle_groups")

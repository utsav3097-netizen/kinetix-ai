"""Preserve label calories independently of simplified planning energy factors.

Revision ID: 0007_food_label_energy
Revises: 0006_nutrition
"""
from alembic import op

revision = "0007_food_label_energy"
down_revision = "0006_nutrition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("foods") as batch:
        batch.drop_constraint("ck_food_energy", type_="check")


def downgrade() -> None:
    # Existing label values must satisfy the old restriction before rollback;
    # never alter user-entered nutrients to force an incompatible downgrade.
    with op.batch_alter_table("foods") as batch:
        batch.create_check_constraint(
            "ck_food_energy",
            "abs(calories - (4*protein_g + 4*carbs_g + 9*fat_g - 2*fiber_g)) <= "
            "CASE WHEN (4*protein_g + 4*carbs_g + 9*fat_g - 2*fiber_g)*0.2 > 20 "
            "THEN (4*protein_g + 4*carbs_g + 9*fat_g - 2*fiber_g)*0.2 ELSE 20 END",
        )

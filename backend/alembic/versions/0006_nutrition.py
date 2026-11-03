"""Add nutrition snapshots, projections and an immutable source journal.

Revision ID: 0006_nutrition
Revises: 0005_workouts
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_nutrition"
down_revision = "0005_workouts"
branch_labels = None
depends_on = None


def identity_columns():
    return [
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    ]


def day_column():
    return sa.Column("day_id", sa.Uuid(as_uuid=False), sa.ForeignKey("nutrition_days.id", ondelete="RESTRICT"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "nutrition_days", *identity_columns(),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("training_day", sa.Boolean(), nullable=False),
        sa.Column("bodyweight_kg", sa.Float(), nullable=False),
        sa.Column("tdee_kcal", sa.Float(), nullable=False),
        sa.Column("phase", sa.String(24), nullable=False),
        sa.Column("profile_snapshot", sa.JSON(), nullable=False),
        sa.Column("targets", sa.JSON(), nullable=False),
        sa.Column("protein_range_g", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.UniqueConstraint("owner_id", "date", name="uq_nutrition_owner_date"),
        sa.CheckConstraint("bodyweight_kg BETWEEN 20 AND 500", name="ck_nutrition_weight"),
        sa.CheckConstraint("tdee_kcal > 0", name="ck_nutrition_tdee"),
        sa.CheckConstraint("revision >= 0", name="ck_nutrition_revision"),
    )
    op.create_table(
        "nutrition_source_records", *identity_columns(), day_column(),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(12), nullable=False),
        sa.Column("entity_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("action", sa.String(12), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("day_id", "revision", name="uq_nutrition_source_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_nutrition_source_revision"),
        sa.CheckConstraint("entity_type IN ('day', 'meal', 'water')", name="ck_nutrition_source_entity"),
        sa.CheckConstraint("action IN ('create', 'update', 'delete')", name="ck_nutrition_source_action"),
    )
    op.create_index("ix_nutrition_source_owner_date", "nutrition_source_records", ["owner_id", "date"])
    op.create_table(
        "nutrition_meals", *identity_columns(), day_column(),
        sa.Column("slot", sa.String(16), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("time", sa.String(5), nullable=False),
        sa.Column("source_record_id", sa.Uuid(as_uuid=False), sa.ForeignKey("nutrition_source_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("slot IN ('breakfast', 'pre_workout', 'post_workout', 'lunch', 'dinner', 'snacks')", name="ck_nutrition_meal_slot"),
    )
    op.create_index("ix_nutrition_meal_owner_day", "nutrition_meals", ["owner_id", "day_id"])
    op.create_table(
        "nutrition_meal_items", *identity_columns(),
        sa.Column("meal_id", sa.Uuid(as_uuid=False), sa.ForeignKey("nutrition_meals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("food_id", sa.Uuid(as_uuid=False), sa.ForeignKey("foods.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("grams", sa.Float(), nullable=False),
        sa.Column("food_snapshot", sa.JSON(), nullable=False),
        sa.Column("nutrients", sa.JSON(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("grams > 0 AND grams <= 5000", name="ck_nutrition_item_grams"),
    )
    op.create_index("ix_nutrition_item_owner_meal", "nutrition_meal_items", ["owner_id", "meal_id"])
    op.create_table(
        "nutrition_water_entries", *identity_columns(), day_column(),
        sa.Column("amount_ml", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount_ml BETWEEN 1 AND 10000", name="ck_nutrition_water_amount"),
    )
    op.create_index("ix_nutrition_water_owner_day", "nutrition_water_entries", ["owner_id", "day_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION reject_nutrition_source_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'Nutrition source records are append-only'; END;
            $$ LANGUAGE plpgsql""")
        op.execute("""CREATE TRIGGER nutrition_source_immutable BEFORE UPDATE OR DELETE
            ON nutrition_source_records FOR EACH ROW EXECUTE FUNCTION reject_nutrition_source_mutation()""")
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(f"""CREATE TRIGGER nutrition_source_no_{action.lower()} BEFORE {action}
                ON nutrition_source_records BEGIN
                SELECT RAISE(ABORT, 'Nutrition source records are append-only'); END""")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER nutrition_source_immutable ON nutrition_source_records")
        op.execute("DROP FUNCTION reject_nutrition_source_mutation()")
    else:
        op.execute("DROP TRIGGER nutrition_source_no_update")
        op.execute("DROP TRIGGER nutrition_source_no_delete")
    op.drop_table("nutrition_water_entries")
    op.drop_table("nutrition_meal_items")
    op.drop_table("nutrition_meals")
    op.drop_table("nutrition_source_records")
    op.drop_table("nutrition_days")

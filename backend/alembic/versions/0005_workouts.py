"""Add workout projections and an immutable source journal.

Revision ID: 0005_workouts
Revises: 0004_reference
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_workouts"
down_revision = "0004_reference"
branch_labels = None
depends_on = None


def identity_columns():
    return [
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=False), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    ]


def session_column():
    return sa.Column("session_id", sa.Uuid(as_uuid=False), sa.ForeignKey("workout_sessions.id", ondelete="RESTRICT"), nullable=False)


def active_ordinal_index(name, table, parent):
    op.create_index(name, table, [parent, "ordinal"], unique=True,
                    sqlite_where=sa.text("deleted_at IS NULL"), postgresql_where=sa.text("deleted_at IS NULL"))


def upgrade() -> None:
    op.create_table(
        "workout_sessions", *identity_columns(),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("performed_on", sa.Date(), nullable=False),
        sa.Column("bodyweight_kg", sa.Float(), nullable=False),
        sa.Column("sleep_hours", sa.Float(), nullable=True),
        sa.Column("soreness", sa.Float(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("bodyweight_kg BETWEEN 20 AND 500", name="ck_workout_weight"),
        sa.CheckConstraint("revision >= 0", name="ck_workout_revision"),
    )
    op.create_index("ix_workout_owner_date", "workout_sessions", ["owner_id", "performed_on"])
    op.create_table(
        "workout_exercises", *identity_columns(), session_column(),
        sa.Column("exercise_id", sa.Uuid(as_uuid=False), sa.ForeignKey("exercises.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("exercise_snapshot", sa.JSON(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("target_min_reps", sa.Integer(), nullable=False),
        sa.Column("target_max_reps", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("ordinal >= 1", name="ck_workout_exercise_ordinal"),
        sa.CheckConstraint("target_min_reps >= 1 AND target_max_reps >= target_min_reps", name="ck_workout_rep_range"),
    )
    active_ordinal_index("uq_workout_exercise_ordinal", "workout_exercises", "session_id")
    op.create_index("ix_workout_exercise_owner_reference", "workout_exercises", ["owner_id", "exercise_id"])
    op.create_table(
        "workout_source_records", *identity_columns(), session_column(),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(12), nullable=False),
        sa.Column("entity_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("action", sa.String(12), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "revision", name="uq_workout_source_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_workout_source_revision"),
        sa.CheckConstraint("entity_type IN ('session', 'exercise', 'set')", name="ck_workout_source_entity"),
        sa.CheckConstraint("action IN ('create', 'update', 'delete', 'complete')", name="ck_workout_source_action"),
    )
    op.create_table(
        "workout_sets", *identity_columns(), session_column(),
        sa.Column("block_id", sa.Uuid(as_uuid=False), sa.ForeignKey("workout_exercises.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_record_id", sa.Uuid(as_uuid=False), sa.ForeignKey("workout_source_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("set_type", sa.String(12), nullable=False),
        sa.Column("external_load_kg", sa.Float(), nullable=False),
        sa.Column("repetitions", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("rpe", sa.Float(), nullable=True),
        sa.Column("rir", sa.Float(), nullable=True),
        sa.Column("rest_seconds", sa.Integer(), nullable=False),
        sa.Column("bodyweight_kg", sa.Float(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("ordinal >= 1", name="ck_workout_set_ordinal"),
        sa.CheckConstraint("set_type IN ('warmup', 'working', 'drop_set', 'failure')", name="ck_workout_set_type"),
        sa.CheckConstraint("external_load_kg BETWEEN 0 AND 1000", name="ck_workout_set_load"),
        sa.CheckConstraint("(repetitions IS NOT NULL AND repetitions BETWEEN 0 AND 1000 AND duration_seconds IS NULL) OR (repetitions IS NULL AND duration_seconds IS NOT NULL AND duration_seconds BETWEEN 1 AND 7200)", name="ck_workout_set_measurement"),
    )
    active_ordinal_index("uq_workout_set_ordinal", "workout_sets", "block_id")
    op.create_index("ix_workout_set_session", "workout_sets", ["owner_id", "session_id"])
    # Protect the source log even against bulk SQL that bypasses ORM listeners.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION reject_workout_source_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'Workout source records are append-only'; END;
            $$ LANGUAGE plpgsql""")
        op.execute("""CREATE TRIGGER workout_source_immutable BEFORE UPDATE OR DELETE
            ON workout_source_records FOR EACH ROW EXECUTE FUNCTION reject_workout_source_mutation()""")
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(f"""CREATE TRIGGER workout_source_no_{action.lower()} BEFORE {action}
                ON workout_source_records BEGIN
                SELECT RAISE(ABORT, 'Workout source records are append-only'); END""")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER workout_source_immutable ON workout_source_records")
        op.execute("DROP FUNCTION reject_workout_source_mutation()")
    else:
        op.execute("DROP TRIGGER workout_source_no_update")
        op.execute("DROP TRIGGER workout_source_no_delete")
    op.drop_table("workout_sets")
    op.drop_table("workout_source_records")
    op.drop_table("workout_exercises")
    op.drop_table("workout_sessions")

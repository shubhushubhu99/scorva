"""create ai operations control center tables

Revision ID: f6a1b2c3d4e5
Revises: e5f6a1b2c3d4
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "f6a1b2c3d4e5"
down_revision = "e5f6a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. ai_model_registry
    if "ai_model_registry" not in existing_tables:
        op.create_table(
            "ai_model_registry",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("provider", sa.String(64), nullable=False),
            sa.Column("model_id", sa.String(128), nullable=False),
            sa.Column("display_name", sa.String(255), nullable=False),
            sa.Column("context_window", sa.Integer(), nullable=True),
            sa.Column("max_tokens", sa.Integer(), nullable=True),
            sa.Column("input_cost", sa.Numeric(12, 6), nullable=True),
            sa.Column("output_cost", sa.Numeric(12, 6), nullable=True),
            sa.Column("capabilities", JSONB(), nullable=True),
            sa.Column("is_available", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_test_status", sa.String(32), nullable=True),
            sa.Column("last_test_latency_ms", sa.Integer(), nullable=True),
            sa.Column("last_test_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("provider", "model_id", name="uq_ai_model_provider_id"),
        )
        op.create_index("ix_ai_model_registry_provider", "ai_model_registry", ["provider"])
        op.create_index("ix_ai_model_registry_model_id", "ai_model_registry", ["model_id"])

    # 2. ai_task_model_assignments
    if "ai_task_model_assignments" not in existing_tables:
        op.create_table(
            "ai_task_model_assignments",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("task_type", sa.String(64), nullable=False, unique=True),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("primary_provider", sa.String(64), nullable=False),
            sa.Column("primary_model", sa.String(128), nullable=False),
            sa.Column("secondary_provider", sa.String(64), nullable=True),
            sa.Column("secondary_model", sa.String(128), nullable=True),
            sa.Column("fallback_models", JSONB(), nullable=True),
            sa.Column("timeout_seconds", sa.Integer(), server_default=sa.text("180"), nullable=False),
            sa.Column("max_retries", sa.Integer(), server_default=sa.text("2"), nullable=False),
            sa.Column("parallel_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_ai_task_assignments_task_type", "ai_task_model_assignments", ["task_type"])

    # 3. ai_execution_records
    if "ai_execution_records" not in existing_tables:
        op.create_table(
            "ai_execution_records",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("evaluation_id", UUID(as_uuid=True), sa.ForeignKey("evaluation_jobs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("submission_id", UUID(as_uuid=True), sa.ForeignKey("submissions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("task_type", sa.String(64), nullable=False),
            sa.Column("primary_provider", sa.String(64), nullable=False),
            sa.Column("primary_model", sa.String(128), nullable=False),
            sa.Column("actual_provider", sa.String(64), nullable=False),
            sa.Column("actual_model", sa.String(128), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("fallback_used", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("fallback_reason", sa.Text(), nullable=True),
            sa.Column("attempt_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
            sa.Column("duration_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("prompt_tokens", sa.Integer(), nullable=True),
            sa.Column("completion_tokens", sa.Integer(), nullable=True),
            sa.Column("total_tokens", sa.Integer(), nullable=True),
            sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=True),
            sa.Column("prompt_preview", sa.Text(), nullable=True),
            sa.Column("output_payload", JSONB(), nullable=True),
            sa.Column("validation_passed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("validation_errors", JSONB(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_ai_exec_records_task_type", "ai_execution_records", ["task_type"])
        op.create_index("ix_ai_exec_records_status", "ai_execution_records", ["status"])
        op.create_index("ix_ai_exec_records_created_at", "ai_execution_records", ["created_at"])
        op.create_index("ix_ai_exec_records_eval_id", "ai_execution_records", ["evaluation_id"])
        op.create_index("ix_ai_exec_records_sub_id", "ai_execution_records", ["submission_id"])

    # 4. ai_model_test_records
    if "ai_model_test_records" not in existing_tables:
        op.create_table(
            "ai_model_test_records",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("provider", sa.String(64), nullable=False),
            sa.Column("model_id", sa.String(128), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("is_structured", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("response_text", sa.Text(), nullable=True),
            sa.Column("structured_output", JSONB(), nullable=True),
            sa.Column("validation_passed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("duration_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("tokens_used", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("tested_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_ai_model_test_records_provider", "ai_model_test_records", ["provider"])
        op.create_index("ix_ai_model_test_records_model_id", "ai_model_test_records", ["model_id"])
        op.create_index("ix_ai_model_test_records_created_at", "ai_model_test_records", ["created_at"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "ai_model_test_records" in existing_tables:
        op.drop_table("ai_model_test_records")
    if "ai_execution_records" in existing_tables:
        op.drop_table("ai_execution_records")
    if "ai_task_model_assignments" in existing_tables:
        op.drop_table("ai_task_model_assignments")
    if "ai_model_registry" in existing_tables:
        op.drop_table("ai_model_registry")

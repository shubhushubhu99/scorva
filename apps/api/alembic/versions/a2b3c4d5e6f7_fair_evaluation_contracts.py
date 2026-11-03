"""create fair evaluation contracts and policy tables

Revision ID: a2b3c4d5e6f7
Revises: f6a1b2c3d4e5
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "a2b3c4d5e6f7"
down_revision = "f6a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. Add policy_version column to evaluation_results if missing
    columns = [c["name"] for c in inspector.get_columns("evaluation_results")]
    if "policy_version" not in columns:
        op.add_column(
            "evaluation_results",
            sa.Column("policy_version", sa.String(32), server_default="1.0.0", nullable=True),
        )

    # 2. evaluation_policy_versions
    if "evaluation_policy_versions" not in existing_tables:
        op.create_table(
            "evaluation_policy_versions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("version", sa.String(32), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("policy_rules", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("version", name="uq_evaluation_policy_versions_version"),
        )
        op.create_index("ix_eval_policy_ver_version", "evaluation_policy_versions", ["version"])

    # 3. evaluation_evidence_records
    if "evaluation_evidence_records" not in existing_tables:
        op.create_table(
            "evaluation_evidence_records",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "evaluation_result_id",
                UUID(as_uuid=True),
                sa.ForeignKey("evaluation_results.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "submission_id",
                UUID(as_uuid=True),
                sa.ForeignKey("submissions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("commit_sha", sa.String(64), nullable=False),
            sa.Column("evidence_type", sa.String(64), nullable=False),
            sa.Column("file_path", sa.String(500), nullable=False),
            sa.Column("start_line", sa.Integer(), nullable=True),
            sa.Column("end_line", sa.Integer(), nullable=True),
            sa.Column("source_excerpt", sa.Text(), nullable=False),
            sa.Column("commit_ref", sa.String(255), nullable=True),
            sa.Column(
                "criterion_id",
                UUID(as_uuid=True),
                sa.ForeignKey("rubric_criteria.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("requirement_id", sa.String(100), nullable=True),
            sa.Column("verification_status", sa.String(32), nullable=False, server_default="VERIFIED"),
            sa.Column("confidence", sa.Numeric(5, 2), nullable=False, server_default="1.00"),
            sa.Column("explanation", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_eval_ev_eval_result_id", "evaluation_evidence_records", ["evaluation_result_id"])
        op.create_index("ix_eval_ev_submission_id", "evaluation_evidence_records", ["submission_id"])
        op.create_index("ix_eval_ev_commit_sha", "evaluation_evidence_records", ["commit_sha"])
        op.create_index("ix_eval_ev_criterion_id", "evaluation_evidence_records", ["criterion_id"])
        op.create_index("ix_eval_ev_status", "evaluation_evidence_records", ["verification_status"])

    # 4. evaluation_deduction_attributions
    if "evaluation_deduction_attributions" not in existing_tables:
        op.create_table(
            "evaluation_deduction_attributions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "evaluation_result_id",
                UUID(as_uuid=True),
                sa.ForeignKey("evaluation_results.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "submission_id",
                UUID(as_uuid=True),
                sa.ForeignKey("submissions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "criterion_id",
                UUID(as_uuid=True),
                sa.ForeignKey("rubric_criteria.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("issue_description", sa.String(500), nullable=False),
            sa.Column("defect_severity", sa.String(32), nullable=False, server_default="MINOR"),
            sa.Column("relevance_explanation", sa.Text(), nullable=False),
            sa.Column("overlap_group_id", sa.String(100), nullable=True),
            sa.Column("is_primary_attribution", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("cross_criterion_justification", sa.Text(), nullable=True),
            sa.Column("deduction_points", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
            sa.Column("proportionality_rationale", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_eval_ded_eval_result_id", "evaluation_deduction_attributions", ["evaluation_result_id"])
        op.create_index("ix_eval_ded_submission_id", "evaluation_deduction_attributions", ["submission_id"])
        op.create_index("ix_eval_ded_criterion_id", "evaluation_deduction_attributions", ["criterion_id"])
        op.create_index("ix_eval_ded_overlap_group_id", "evaluation_deduction_attributions", ["overlap_group_id"])

    # 5. evaluation_criterion_assessments
    if "evaluation_criterion_assessments" not in existing_tables:
        op.create_table(
            "evaluation_criterion_assessments",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "evaluation_result_id",
                UUID(as_uuid=True),
                sa.ForeignKey("evaluation_results.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "submission_id",
                UUID(as_uuid=True),
                sa.ForeignKey("submissions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "criterion_id",
                UUID(as_uuid=True),
                sa.ForeignKey("rubric_criteria.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("policy_version", sa.String(32), nullable=False, server_default="1.0.0"),
            sa.Column("evidence_strength", sa.String(32), nullable=False, server_default="MODERATE"),
            sa.Column("raw_score_before_deductions", sa.Numeric(5, 2), nullable=False),
            sa.Column("total_deductions", sa.Numeric(5, 2), nullable=False, server_default="0.00"),
            sa.Column("final_criterion_score", sa.Numeric(5, 2), nullable=False),
            sa.Column("confidence", sa.Numeric(5, 2), nullable=False, server_default="1.00"),
            sa.Column("positive_findings", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("negative_findings", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("neutral_observations", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("missing_evidence_observations", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("unresolved_questions", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("score_justification", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_eval_crit_assess_eval_result_id", "evaluation_criterion_assessments", ["evaluation_result_id"])
        op.create_index("ix_eval_crit_assess_submission_id", "evaluation_criterion_assessments", ["submission_id"])
        op.create_index("ix_eval_crit_assess_criterion_id", "evaluation_criterion_assessments", ["criterion_id"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "evaluation_criterion_assessments" in existing_tables:
        op.drop_table("evaluation_criterion_assessments")
    if "evaluation_deduction_attributions" in existing_tables:
        op.drop_table("evaluation_deduction_attributions")
    if "evaluation_evidence_records" in existing_tables:
        op.drop_table("evaluation_evidence_records")
    if "evaluation_policy_versions" in existing_tables:
        op.drop_table("evaluation_policy_versions")

    columns = [c["name"] for c in inspector.get_columns("evaluation_results")]
    if "policy_version" in columns:
        op.drop_column("evaluation_results", "policy_version")

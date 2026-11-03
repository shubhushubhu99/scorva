from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from apps.api.core.database import Base

if TYPE_CHECKING:
    from apps.api.modules.organizations.models import Organization
    from apps.api.modules.hackathons.models import Hackathon
    from apps.api.modules.users.models import User


class Team(Base):
    """Subsystem C: Participant teams registered within a hackathon."""
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hackathons.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    join_code: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("hackathon_id", "name", name="uq_teams_hackathon_name"),
    )

    members: Mapped[List["TeamMember"]] = relationship(
        "TeamMember", back_populates="team", cascade="all, delete-orphan"
    )
    submissions: Mapped[List["Submission"]] = relationship(
        "Submission", back_populates="team"
    )


class TeamMember(Base):
    """Subsystem C: Association linking individual participants to a team."""
    __tablename__ = "team_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_in_team: Mapped[str] = mapped_column(
        String(20), nullable=False, default="member"
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
        CheckConstraint(
            "role_in_team IN ('leader', 'member')",
            name="chk_team_members_role",
        ),
    )

    team: Mapped["Team"] = relationship("Team", back_populates="members")


class Submission(Base):
    """Subsystem C: Project submissions submitted to a hackathon by participating teams."""
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hackathons.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    team_name: Mapped[str] = mapped_column(String(150), nullable=False)
    repository_url: Mapped[str] = mapped_column(String(500), nullable=False)
    target_branch: Mapped[str] = mapped_column(
        String(100), nullable=False, default="main"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    repository_owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    repository_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    default_branch: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    verified_commit_sha: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    connection_status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="unverified", default="unverified"
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification_diagnostic: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    verification_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'evaluated', 'flagged', 'withdrawn')",
            name="chk_submissions_status",
        ),
        Index(
            "uq_submissions_hackathon_repo_active",
            "hackathon_id",
            "repository_url",
            unique=True,
            postgresql_where=(deleted_at.is_(None)),
        ),
        Index("idx_submissions_hackathon_status", "hackathon_id", "status"),
        Index("idx_submissions_team", "team_id"),
    )

    team: Mapped["Team"] = relationship("Team", back_populates="submissions")
    snapshots: Mapped[List["SubmissionSnapshot"]] = relationship(
        "SubmissionSnapshot", back_populates="submission"
    )
    evaluation_jobs: Mapped[List["EvaluationJob"]] = relationship(
        "EvaluationJob", back_populates="submission"
    )
    judge_reviews: Mapped[List["JudgeReview"]] = relationship(
        "JudgeReview", back_populates="submission"
    )


class SubmissionSnapshot(Base):
    """
    Subsystem C: Represents an immutable frozen commit SHA captured at evaluation time.
    Evaluations are permanently bound to a snapshot and its effective configuration.
    """
    __tablename__ = "submission_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    tree_sha: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    snapshot_tarball_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    configuration_snapshot: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False
    )
    metadata_: Mapped[Dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "submission_id", "commit_sha", name="uq_submission_snapshots_submission_commit"
        ),
    )

    submission: Mapped["Submission"] = relationship(
        "Submission", back_populates="snapshots"
    )
    evaluation_jobs: Mapped[List["EvaluationJob"]] = relationship(
        "EvaluationJob", back_populates="snapshot"
    )


class Rubric(Base):
    """Subsystem C: Parent rubric configuration for a hackathon."""
    __tablename__ = "rubrics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hackathons.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scoring_mode: Mapped[str] = mapped_column(
        String(30), nullable=False, default="offset_normalized"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("hackathon_id", "name", name="uq_rubrics_hackathon_name"),
        CheckConstraint(
            "scoring_mode IN ('offset_normalized', 'raw_proportional')",
            name="chk_rubrics_scoring_mode",
        ),
    )

    versions: Mapped[List["RubricVersion"]] = relationship(
        "RubricVersion", back_populates="rubric", cascade="all, delete-orphan"
    )


class RubricVersion(Base):
    """Subsystem C: Immutable frozen snapshot of criteria and weights used for evaluation runs."""
    __tablename__ = "rubric_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rubric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubrics.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "rubric_id", "version_number", name="uq_rubric_versions_rubric_version"
        ),
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="chk_rubric_versions_status",
        ),
    )

    rubric: Mapped["Rubric"] = relationship("Rubric", back_populates="versions")
    criteria: Mapped[List["RubricCriterion"]] = relationship(
        "RubricCriterion",
        back_populates="rubric_version",
        cascade="all, delete-orphan",
        order_by="RubricCriterion.order_index",
    )


class RubricCriterion(Base):
    """
    Subsystem C: Individual assessment criterion belonging to a rubric version.
    Protected by PostgreSQL immutability trigger once rubric_version is published.
    """
    __tablename__ = "rubric_criteria"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    min_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )
    max_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("10.00")
    )
    evidence_requirements: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("min_score < max_score", name="chk_rubric_criteria_min_max"),
        CheckConstraint(
            "weight > 0.0000 AND weight <= 1.0000",
            name="chk_rubric_criteria_weight",
        ),
    )

    rubric_version: Mapped["RubricVersion"] = relationship(
        "RubricVersion", back_populates="criteria"
    )


class EvaluationJob(Base):
    """Subsystem C: Asynchronous job tracking evaluation orchestration and worker leasing."""
    __tablename__ = "evaluation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hackathons.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submission_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    current_result_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "evaluation_results.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_evaluation_jobs_current_result_id",
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued"
    )
    current_stage: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    attempts_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    claim_token: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    request_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    reevaluation_of_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    dispatch_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="chk_evaluation_jobs_status",
        ),
        CheckConstraint(
            "current_stage IS NULL OR current_stage IN ("
            "'repo_acquisition', 'safe_extraction', 'evidence_indexing', "
            "'model_evaluation', 'output_validation', 'score_calculation', 'persistence')",
            name="chk_evaluation_jobs_current_stage",
        ),
        Index("idx_eval_jobs_status_heartbeat", "status", "last_heartbeat_at"),
        Index("idx_eval_jobs_org_hack", "organization_id", "hackathon_id"),
        Index(
            "uq_eval_jobs_organization_idempotency_key",
            "organization_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "ix_eval_jobs_reevaluation_of",
            "reevaluation_of_job_id",
            unique=False,
            postgresql_where=text("reevaluation_of_job_id IS NOT NULL"),
        ),
    )

    submission: Mapped["Submission"] = relationship(
        "Submission", back_populates="evaluation_jobs"
    )
    snapshot: Mapped["SubmissionSnapshot"] = relationship(
        "SubmissionSnapshot", back_populates="evaluation_jobs"
    )
    results: Mapped[List["EvaluationResult"]] = relationship(
        "EvaluationResult",
        back_populates="job",
        foreign_keys="EvaluationResult.job_id",
        cascade="all, delete-orphan",
    )
    outbox_entries: Mapped[List["EvaluationJobOutbox"]] = relationship(
        "EvaluationJobOutbox",
        back_populates="job",
        cascade="all, delete-orphan",
    )
    reevaluation_parent: Mapped[Optional["EvaluationJob"]] = relationship(
        "EvaluationJob",
        remote_side="EvaluationJob.id",
        foreign_keys=[reevaluation_of_job_id],
    )


class EvaluationJobOutbox(Base):
    """
    Subsystem C: Transactional Outbox for reliable asynchronous evaluation dispatch.
    Committed atomically with evaluation_jobs in the same database transaction.
    """
    __tablename__ = "evaluation_job_outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    queue_name: Mapped[str] = mapped_column(
        String(50), nullable=False, default="evaluations.default"
    )
    routing_key: Mapped[str] = mapped_column(
        String(50), nullable=False, default="evaluations.default"
    )
    payload: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    relay_claim_token: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    relay_claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    relay_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    claim_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    publish_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    dispatch_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dead_lettered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dead_letter_reason: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'dead_lettered')",
            name="chk_outbox_status",
        ),
        Index(
            "uq_eval_job_outbox_active_dispatch",
            "job_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'processing')"),
        ),
        Index(
            "ix_eval_job_outbox_claimable",
            "status",
            "claim_count",
            "relay_expires_at",
            "id",
            postgresql_where=text("dead_lettered_at IS NULL AND processed_at IS NULL"),
        ),
        Index(
            "ix_eval_job_outbox_quarantine",
            "id",
            postgresql_where=text("status = 'processing' AND claim_count >= 5 AND dead_lettered_at IS NULL"),
        ),
    )

    job: Mapped["EvaluationJob"] = relationship(
        "EvaluationJob", back_populates="outbox_entries"
    )


class EvaluationResult(Base):
    """
    Subsystem C: Authoritative output of an evaluation attempt.
    Preserves full retry history across attempts.
    """
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hackathons.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_jobs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submission_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    model_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    policy_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, default="1.0.0")
    raw_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    normalized_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False
    )
    summary_assessment: Mapped[str] = mapped_column(Text, nullable=False)
    has_insufficient_evidence: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "job_id", "attempt_number", name="uq_evaluation_results_job_attempt"
        ),
    )

    job: Mapped["EvaluationJob"] = relationship(
        "EvaluationJob", back_populates="results", foreign_keys=[job_id]
    )
    criterion_scores: Mapped[List["EvaluationCriterionScore"]] = relationship(
        "EvaluationCriterionScore",
        back_populates="evaluation_result",
        cascade="all, delete-orphan",
    )
    judge_reviews: Mapped[List["JudgeReview"]] = relationship(
        "JudgeReview", back_populates="evaluation_result"
    )
    assessments: Mapped[List["EvaluationCriterionAssessment"]] = relationship(
        "EvaluationCriterionAssessment",
        back_populates="evaluation_result",
        cascade="all, delete-orphan",
    )
    evidence_records: Mapped[List["EvaluationEvidenceRecord"]] = relationship(
        "EvaluationEvidenceRecord",
        back_populates="evaluation_result",
        cascade="all, delete-orphan",
    )
    deductions: Mapped[List["EvaluationDeductionAttribution"]] = relationship(
        "EvaluationDeductionAttribution",
        back_populates="evaluation_result",
        cascade="all, delete-orphan",
    )


class EvaluationCriterionScore(Base):
    """Subsystem C: Criterion-level score and rationale awarded by model for a specific result attempt."""
    __tablename__ = "evaluation_criterion_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    evaluation_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    criterion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_criteria.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    awarded_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False
    )
    normalized_criterion_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False
    )
    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("1.00")
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_status: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "evidence_status IN ('verified', 'partial', 'missing')",
            name="chk_evaluation_criterion_scores_evidence_status",
        ),
    )

    evaluation_result: Mapped["EvaluationResult"] = relationship(
        "EvaluationResult", back_populates="criterion_scores"
    )
    evidence_references: Mapped[List["EvidenceReference"]] = relationship(
        "EvidenceReference",
        back_populates="criterion_score",
        cascade="all, delete-orphan",
    )


class EvidenceReference(Base):
    """Subsystem C: Verifiable line-level citations grounding the score in the snapshot."""
    __tablename__ = "evidence_references"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    criterion_score_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_criterion_scores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    start_line: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_line: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    is_verified_in_repo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    verification_failure_reason: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    criterion_score: Mapped["EvaluationCriterionScore"] = relationship(
        "EvaluationCriterionScore", back_populates="evidence_references"
    )


class JudgeReview(Base):
    """Subsystem C: Independent human judge review, scoring, and feedback record."""
    __tablename__ = "judge_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hackathons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    judge_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    evaluation_result_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_results.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="draft", default="draft"
    )
    score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    original_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    adjusted_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    overall_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "decision IS NULL OR decision IN ('accepted', 'adjusted', 'rejected')",
            name="chk_judge_reviews_decision",
        ),
        CheckConstraint(
            "status IN ('draft', 'submitted')",
            name="chk_judge_reviews_status",
        ),
        UniqueConstraint(
            "submission_id", "judge_user_id",
            name="uq_judge_reviews_submission_judge",
        ),
        Index("ix_judge_reviews_hackathon_status", "hackathon_id", "status"),
        Index("ix_judge_reviews_submission_status", "submission_id", "status"),
    )

    evaluation_result: Mapped[Optional["EvaluationResult"]] = relationship(
        "EvaluationResult", back_populates="judge_reviews"
    )
    submission: Mapped["Submission"] = relationship(
        "Submission", back_populates="judge_reviews"
    )
    rubric_version: Mapped["RubricVersion"] = relationship(
        "RubricVersion"
    )
    judge_user: Mapped["User"] = relationship(
        "User"
    )
    criterion_scores: Mapped[List["JudgeCriterionScore"]] = relationship(
        "JudgeCriterionScore",
        back_populates="judge_review",
        cascade="all, delete-orphan",
    )


class JudgeCriterionScore(Base):
    """Subsystem C: Criterion-level scoring and feedback by human judge."""
    __tablename__ = "judge_criterion_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    judge_review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("judge_reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    criterion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_criteria.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    original_awarded_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    adjusted_awarded_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    judge_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "judge_review_id", "criterion_id",
            name="uq_judge_criterion_scores_review_criterion",
        ),
    )

    judge_review: Mapped["JudgeReview"] = relationship(
        "JudgeReview", back_populates="criterion_scores"
    )
    criterion: Mapped["RubricCriterion"] = relationship(
        "RubricCriterion"
    )


class OrganizationIntegration(Base):
    """
    Subsystem C: Encrypted credential vault storing GitHub tokens and App installations per tenant.
    Tokens are encrypted at rest with AES-256-GCM.
    """
    __tablename__ = "organization_integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, default="github"
    )
    credential_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pat"
    )
    encrypted_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_id: Mapped[str] = mapped_column(
        String(50), nullable=False, default="master_v1"
    )
    token_preview: Mapped[str] = mapped_column(String(20), nullable=False)
    scopes: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
        server_default='["contents:read", "metadata:read"]',
    )
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "credential_type IN ('pat', 'github_app')",
            name="chk_org_integrations_credential_type",
        ),
        Index(
            "uq_org_integrations_org_provider_active",
            "organization_id",
            "provider",
            unique=True,
            postgresql_where=(revoked_at.is_(None)),
        ),
    )


class HackathonJudge(Base):
    """Subsystem C: Event-scoped judge assignments mapping users to specific hackathons."""
    __tablename__ = "hackathon_judges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hackathons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    access_code: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "hackathon_id", "user_id", name="uq_hackathon_judges_hackathon_user"
        ),
    )


class GitHubEvent(Base):
    """
    Subsystem C: Durable repository activity and webhook delivery event store.
    Provides idempotent deduplication, provenance tracking, and project activity timelines.
    """
    __tablename__ = "github_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    delivery_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    action: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    hackathon_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hackathons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    submission_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    repository_owner: Mapped[str] = mapped_column(
        String(150), nullable=False
    )
    repository_name: Mapped[str] = mapped_column(
        String(150), nullable=False
    )
    canonical_repo_id: Mapped[str] = mapped_column(
        String(300), nullable=False, index=True
    )
    ref: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    commit_sha: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    sender_login: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    summary: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    details: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="received", index=True
    )
    diagnostic_code: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('received', 'processed', 'ignored', 'failed')",
            name="chk_github_events_status",
        ),
        Index("ix_github_events_org_hack_sub", "organization_id", "hackathon_id", "submission_id"),
        Index("ix_github_events_repo_timestamp", "canonical_repo_id", "event_timestamp"),
    )


class SubmissionRepoInspection(Base):
    """Subsystem E: Persisted neural repo inspection and judge synthesis results."""
    __tablename__ = "submission_repo_inspections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hackathon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hackathons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inspected_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="completed")
    project_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quick_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    what_is_building: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    innovation_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    tech_stack_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    complexity_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    judge_factors_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    key_highlights: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    potential_red_flags: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    suggested_judge_questions: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    raw_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AIModelRegistryItem(Base):
    """Subsystem E: Persisted AI Model catalog across Pi, Ollama, and external providers."""
    __tablename__ = "ai_model_registry"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    context_window: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    input_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6), nullable=True)
    output_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6), nullable=True)
    capabilities: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_test_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_test_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("provider", "model_id", name="uq_ai_model_provider_id"),
    )


class AITaskModelAssignment(Base):
    """Subsystem E: Task-based AI Model routing policy and fallback configuration."""
    __tablename__ = "ai_task_model_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_type: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    primary_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_model: Mapped[str] = mapped_column(String(128), nullable=False)
    secondary_provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    secondary_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    fallback_models: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=180, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    parallel_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AIExecutionRecord(Base):
    """Subsystem E: Audit log of all model executions, token usage, latencies, and fallbacks."""
    __tablename__ = "ai_execution_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    evaluation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    submission_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    primary_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    primary_model: Mapped[str] = mapped_column(String(128), nullable=False)
    actual_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    actual_model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fallback_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6), nullable=True)
    prompt_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    validation_passed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    validation_errors: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class AIModelTestRecord(Base):
    """Subsystem E: History of ad-hoc administrative model test runs."""
    __tablename__ = "ai_model_test_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    is_structured: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    structured_output: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    validation_passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tested_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


# ==============================================================================
# Phase 1: Fair Evaluation Foundation & Scoring Contracts Models
# ==============================================================================

class EvaluationPolicyVersion(Base):
    """
    Subsystem F: Versioned Fair Evaluation Policy definition.
    Ensures historical evaluations can be traced to the policy in effect at the time.
    """
    __tablename__ = "evaluation_policy_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    policy_rules: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EvaluationEvidenceRecord(Base):
    """
    Subsystem F: Verifiable, line-level evidence grounding for awarded scores and findings.
    Traces finding to commit SHA, file path, line range, and verification status.
    """
    __tablename__ = "evaluation_evidence_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    evaluation_result_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_results.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    start_line: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_line: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    commit_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    criterion_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_criteria.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    requirement_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="VERIFIED", index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("1.00"))
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    evaluation_result: Mapped[Optional["EvaluationResult"]] = relationship(
        "EvaluationResult", back_populates="evidence_records"
    )
    submission: Mapped["Submission"] = relationship("Submission")
    criterion: Mapped[Optional["RubricCriterion"]] = relationship("RubricCriterion")


class EvaluationDeductionAttribution(Base):
    """
    Subsystem F: Explicit score deduction attribution and anti-duplicate penalty tracking.
    Enforces that the same defect cannot trigger multiple deductions across criteria
    unless an independent cross-criterion justification is provided.
    """
    __tablename__ = "evaluation_deduction_attributions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    evaluation_result_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_results.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    criterion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_criteria.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    issue_description: Mapped[str] = mapped_column(String(500), nullable=False)
    defect_severity: Mapped[str] = mapped_column(String(32), nullable=False, default="MINOR")
    relevance_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    overlap_group_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    is_primary_attribution: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cross_criterion_justification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deduction_points: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    proportionality_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    evaluation_result: Mapped[Optional["EvaluationResult"]] = relationship(
        "EvaluationResult", back_populates="deductions"
    )
    submission: Mapped["Submission"] = relationship("Submission")
    criterion: Mapped["RubricCriterion"] = relationship("RubricCriterion")


class EvaluationCriterionAssessment(Base):
    """
    Subsystem F: Structured criterion assessment storing positive/negative findings,
    missing evidence observations, requirement coverage, and score justifications.
    """
    __tablename__ = "evaluation_criterion_assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    evaluation_result_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_results.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    criterion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_criteria.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    evidence_strength: Mapped[str] = mapped_column(String(32), default="MODERATE", nullable=False)
    raw_score_before_deductions: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    total_deductions: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    final_criterion_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("1.00"), nullable=False)
    positive_findings: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    negative_findings: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    neutral_observations: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    missing_evidence_observations: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    unresolved_questions: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    score_justification: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    evaluation_result: Mapped[Optional["EvaluationResult"]] = relationship(
        "EvaluationResult", back_populates="assessments"
    )
    submission: Mapped["Submission"] = relationship("Submission")
    criterion: Mapped["RubricCriterion"] = relationship("RubricCriterion")


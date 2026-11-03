"""
Scorva Fair Evaluation Contracts: Strict Pydantic Data Structures.

Enforces evidence grounding, requirement boundaries, deduction attribution,
and mathematical invariants across automated and human evaluation workflows.
"""

from decimal import Decimal
from enum import Enum
import math
from typing import Any, Dict, List, Literal, Optional, Union
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.api.modules.evaluations.scoring_calculator import assert_not_float, to_decimal


# ==============================================================================
# Enumerations
# ==============================================================================

class VerificationStatus(str, Enum):
    """Rigorous verification status for evidence and requirements."""
    VERIFIED = "VERIFIED"                  # Directly verified against code/tests/manifests
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"  # Partially evidenced; non-trivial gaps remain
    UNVERIFIED = "UNVERIFIED"              # Stated/claimed by team, but no confirming evidence found
    CONTRADICTED = "CONTRADICTED"          # Disproved by code (e.g. claim vs opposite reality)
    NOT_AVAILABLE = "NOT_AVAILABLE"        # Information was not available in captured evidence


class EvidenceType(str, Enum):
    """Source classification of captured repository evidence."""
    SOURCE_CODE = "SOURCE_CODE"
    TEST_SUITE = "TEST_SUITE"
    BUILD_MANIFEST = "BUILD_MANIFEST"
    DOCUMENTATION = "DOCUMENTATION"
    DEMO_ARTIFACT = "DEMO_ARTIFACT"
    RUNTIME_LOG = "RUNTIME_LOG"
    EXTERNAL_API = "EXTERNAL_API"
    CI_WORKFLOW = "CI_WORKFLOW"


class RequirementType(str, Enum):
    """Categorization of problem statement vs team scope requirements."""
    MANDATORY = "MANDATORY"              # Explicit core requirement from the hackathon problem statement
    OPTIONAL = "OPTIONAL"                # Explicitly marked optional / bonus in problem statement
    TEAM_CLAIMED = "TEAM_CLAIMED"        # Pitched or claimed by team, not in problem statement


class DefectSeverity(str, Enum):
    """Severity classification for proposed score deductions."""
    COSMETIC = "COSMETIC"                # Minor style, formatting, or spelling
    MINOR = "MINOR"                      # Non-blocking edge case or minor omission
    MODERATE = "MODERATE"                # Noticeable defect or missing secondary feature
    MAJOR = "MAJOR"                      # Critical functional defect or broken core path
    CRITICAL = "CRITICAL"                # Security vulnerability, fraud, or complete failure


class EvidenceStrength(str, Enum):
    """Overall strength of evidence supporting a criterion assessment."""
    STRONG = "STRONG"                    # Comprehensive code, tests, and manifests present
    MODERATE = "MODERATE"                # Clear code evidence, but sparse tests or documentation
    WEAK = "WEAK"                        # Minimal code evidence; high inference required
    INSUFFICIENT = "INSUFFICIENT"        # Cannot reliably evaluate criterion from provided evidence


# ==============================================================================
# Evidence Contract
# ==============================================================================

class EvidenceContract(BaseModel):
    """
    Cryptographically grounded evidence reference linking findings to actual repository assets.
    Prohibits hallucinated paths and invalid line spans.
    """
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    evidence_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    evidence_type: EvidenceType
    commit_sha: str = Field(..., min_length=7, max_length=64, description="Target commit SHA")
    file_path: str = Field(..., min_length=1, max_length=500, description="Relative file path in repository")
    start_line: Optional[int] = Field(None, ge=1, description="1-indexed starting line number")
    end_line: Optional[int] = Field(None, ge=1, description="1-indexed ending line number")
    source_excerpt: str = Field(..., min_length=1, max_length=5000, description="Exact source code or text excerpt")
    commit_ref: Optional[str] = Field(None, description="Optional commit message or tag")
    criterion_id: Optional[uuid.UUID] = Field(None, description="Target rubric criterion ID")
    requirement_id: Optional[str] = Field(None, description="Associated requirement identifier")
    verification_status: VerificationStatus = VerificationStatus.VERIFIED
    confidence: Decimal = Field(default=Decimal("1.00"), ge=Decimal("0.00"), le=Decimal("1.00"))
    explanation: str = Field(..., min_length=5, description="Why this evidence is relevant to the assessment")

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_decimal_types(cls, v: Any, info: Any) -> Decimal:
        assert_not_float(v, info.field_name)
        if isinstance(v, Decimal):
            return v
        return to_decimal(v, info.field_name)

    @model_validator(mode="after")
    def validate_line_boundaries(self) -> "EvidenceContract":
        if self.start_line is not None and self.end_line is not None:
            if self.start_line > self.end_line:
                raise ValueError(
                    f"start_line ({self.start_line}) cannot be greater than end_line ({self.end_line})."
                )
        return self


# ==============================================================================
# Requirement Contract
# ==============================================================================

class RequirementContract(BaseModel):
    """
    Tracks implementation status of hackathon problem statement and rubric requirements.
    Prevents inventing unstated requirements or penalizing missing optional features.
    """
    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=2, max_length=255)
    description: str = Field(..., min_length=5)
    requirement_type: RequirementType = RequirementType.MANDATORY
    criterion_id: Optional[uuid.UUID] = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    cited_evidence_ids: List[uuid.UUID] = Field(default_factory=list)
    rationale: str = Field(..., min_length=5)


# ==============================================================================
# Deduction Attribution Contract
# ==============================================================================

class DeductionAttributionContract(BaseModel):
    """
    Represents an explicit, justified score deduction.
    Enforces anti-duplicate penalty rules and proportionality constraints.
    """
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    deduction_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    criterion_id: uuid.UUID = Field(..., description="The rubric criterion receiving this deduction")
    issue_description: str = Field(..., min_length=5, max_length=500, description="What exactly is wrong?")
    evidence_ids: List[uuid.UUID] = Field(default_factory=list, description="IDs of evidence grounding this deduction")
    defect_severity: DefectSeverity = DefectSeverity.MINOR
    relevance_explanation: str = Field(..., min_length=5, description="Why this issue specifically affects this criterion")
    overlap_group_id: Optional[str] = Field(
        None,
        description="Root defect identifier to group related impacts and prevent duplicate penalties",
    )
    is_primary_attribution: bool = Field(
        default=True,
        description="Whether this criterion is the primary home for this deduction",
    )
    cross_criterion_justification: Optional[str] = Field(
        None,
        description="Required if is_primary_attribution is False, explaining why an additional deduction is warranted",
    )
    deduction_points: Decimal = Field(
        ...,
        ge=Decimal("0.00"),
        le=Decimal("10.00"),
        description="Points to deduct from criterion raw score",
    )
    proportionality_rationale: str = Field(
        ...,
        min_length=5,
        description="Why the deduction points are proportionate to the defect severity",
    )
    affected_requirement_id: Optional[str] = Field(
        default=None,
        description="Identifier of mandatory requirement directly compromised by this defect",
    )
    impact_explanation: Optional[str] = Field(
        default=None,
        description="Detailed explanation of demonstrated impact on functionality, reliability, or security",
    )
    raw_score_non_overlap_justification: Optional[str] = Field(
        default=None,
        description="Explanation proving why this impact was not already discounted in raw_score_before_deductions",
    )

    @field_validator("deduction_points", mode="before")
    @classmethod
    def validate_decimal_types(cls, v: Any, info: Any) -> Decimal:
        assert_not_float(v, info.field_name)
        if isinstance(v, Decimal):
            return v
        return to_decimal(v, info.field_name)

    @model_validator(mode="after")
    def validate_cross_criterion_rule(self) -> "DeductionAttributionContract":
        if not self.is_primary_attribution:
            if not self.cross_criterion_justification or len(self.cross_criterion_justification.strip()) < 10:
                raise ValueError(
                    f"Non-primary deduction '{self.issue_description}' requires an explicit "
                    f"'cross_criterion_justification' (at least 10 chars) to prevent duplicate penalties."
                )
        return self


# ==============================================================================
# Criterion Assessment Contract
# ==============================================================================

class CriterionAssessmentContract(BaseModel):
    """
    Comprehensive, fair assessment of a single rubric criterion.
    Separates positive observations, negative observations, missing evidence, and deductions.
    """
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    criterion_id: uuid.UUID
    criterion_title: str
    positive_findings: List[str] = Field(default_factory=list, description="Demonstrated positive architectural or functional strengths")
    negative_findings: List[str] = Field(default_factory=list, description="Identified defects, antipatterns, or weaknesses")
    neutral_observations: List[str] = Field(default_factory=list, description="Architectural or context notes without valence")
    missing_evidence_observations: List[str] = Field(default_factory=list, description="Areas where evidence could neither confirm nor deny claims")
    contradictory_evidence_observations: List[str] = Field(default_factory=list, description="Areas where code contradicted documentation")
    requirement_coverage: List[RequirementContract] = Field(default_factory=list)
    evidence_strength: EvidenceStrength = EvidenceStrength.MODERATE
    deductions: List[DeductionAttributionContract] = Field(default_factory=list)
    confidence: Decimal = Field(default=Decimal("1.00"), ge=Decimal("0.00"), le=Decimal("1.00"))
    unresolved_questions: List[str] = Field(default_factory=list)
    raw_score_before_deductions: Decimal = Field(..., ge=Decimal("0.00"), le=Decimal("10.00"))
    total_deductions: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), le=Decimal("10.00"))
    final_criterion_score: Decimal = Field(..., ge=Decimal("0.00"), le=Decimal("10.00"))
    score_justification: str = Field(..., min_length=10, description="Clear, plain-language reasoning for the awarded score")

    @field_validator("confidence", "raw_score_before_deductions", "total_deductions", "final_criterion_score", mode="before")
    @classmethod
    def validate_decimal_types(cls, v: Any, info: Any) -> Decimal:
        assert_not_float(v, info.field_name)
        if isinstance(v, Decimal):
            return v
        return to_decimal(v, info.field_name)

    @model_validator(mode="after")
    def validate_score_arithmetic(self) -> "CriterionAssessmentContract":
        computed_deductions = sum((d.deduction_points for d in self.deductions), Decimal("0.00"))
        # Verify total_deductions matches sum of deductions within 0.01 tolerance
        diff = abs(self.total_deductions - computed_deductions)
        if diff > Decimal("0.01"):
            self.total_deductions = computed_deductions

        expected_final = max(Decimal("0.00"), self.raw_score_before_deductions - self.total_deductions)
        final_diff = abs(self.final_criterion_score - expected_final)
        if final_diff > Decimal("0.01"):
            raise ValueError(
                f"final_criterion_score ({self.final_criterion_score}) does not match "
                f"raw_score ({self.raw_score_before_deductions}) minus deductions ({self.total_deductions}) = {expected_final}"
            )
        return self


# ==============================================================================
# Standardized Evaluation Output Contract
# ==============================================================================

class StandardizedEvaluationOutput(BaseModel):
    """
    Standardized top-level output for Fair Evaluation agents.
    Strictly forbids LLM computation of total weighted score; that remains deterministic.
    """
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    evaluation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    submission_id: uuid.UUID
    repository_commit_sha: str = Field(..., min_length=7, max_length=64)
    rubric_version_id: uuid.UUID
    policy_version: str = Field(default="1.0.0", description="SemVer evaluation policy version")
    criterion_assessments: List[CriterionAssessmentContract] = Field(..., min_length=1)
    evidence_records: List[EvidenceContract] = Field(default_factory=list)
    overall_quick_summary: str = Field(..., min_length=5, description="1-2 plain-language summary sentences")
    overall_detailed_summary: str = Field(..., min_length=15, description="Thorough technical summary breakdown")
    has_insufficient_evidence: bool = Field(default=False)
    unresolved_questions: List[str] = Field(default_factory=list)
    validation_passed: bool = Field(default=True)
    model_metadata: Dict[str, Any] = Field(default_factory=dict)

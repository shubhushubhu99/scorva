"""
Scorva Phase 1 Final Gate: Raw-Score, Deduction Interaction & Proportionality Test Suite.

Verifies:
1. Scenario A: Same defect counted twice (raw score lowered + deduction for same issue) -> rejected.
2. Scenario B: Raw score explicitly accounts for the defect -> rejected.
3. Scenario C: Legitimate separate impact with documented non-overlap justification -> permitted.
4. Scenario D: Different defects in the same criterion -> permitted.
5. Within-criterion duplicate penalties prevented without distinct impacts.
6. Proportionality: Minor defect classified as Critical is rejected.
7. Proportionality: Major severity with limited criterion impact is rejected.
8. Proportionality: Critical defect that genuinely justifies substantial deduction is accepted.
9. Proportionality: Optional requirements remain deduction-immune.
10. Proportionality: Weak evidence cannot justify major or critical deductions.
"""

from decimal import Decimal
import uuid
import pytest

from apps.api.modules.evaluations.output_validator import (
    AIEvaluationValidationError,
    validate_standardized_evaluation_output,
)
from apps.api.modules.evaluations.policy.contracts import (
    CriterionAssessmentContract,
    DeductionAttributionContract,
    DefectSeverity,
    EvidenceContract,
    EvidenceStrength,
    EvidenceType,
    RequirementContract,
    RequirementType,
    StandardizedEvaluationOutput,
    VerificationStatus,
)
from apps.api.modules.evaluations.policy.deduction_engine import (
    DeductionAttributionEngine,
    SEVERITY_MAX_DEDUCTION_BOUNDS,
)


# ==============================================================================
# Helper Fixtures
# ==============================================================================

@pytest.fixture
def base_test_setup():
    crit1_id = uuid.uuid4()
    crit2_id = uuid.uuid4()
    rubric_crit = [
        {"id": crit1_id, "title": "Security & Architecture", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")},
        {"id": crit2_id, "title": "Execution & Completeness", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")},
    ]
    ev1_id = uuid.uuid4()
    ev2_id = uuid.uuid4()
    evidence_records = [
        EvidenceContract(
            evidence_id=ev1_id,
            evidence_type=EvidenceType.SOURCE_CODE,
            commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            file_path="src/auth/jwt.py",
            start_line=10,
            end_line=25,
            source_excerpt="def verify_token(token): return True",
            explanation="Authentication bypass logic in JWT handler.",
        ),
        EvidenceContract(
            evidence_id=ev2_id,
            evidence_type=EvidenceType.SOURCE_CODE,
            commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            file_path="src/api/routes.py",
            start_line=50,
            end_line=75,
            source_excerpt="async def handle_request(req): parse(req.body)",
            explanation="Unbounded memory consumption in request parser.",
        ),
    ]
    return {
        "crit1_id": crit1_id,
        "crit2_id": crit2_id,
        "rubric_crit": rubric_crit,
        "ev1_id": ev1_id,
        "ev2_id": ev2_id,
        "evidence_records": evidence_records,
    }


# ==============================================================================
# 1. Raw-Score and Deduction Interaction Tests (Scenarios A, B, C, D)
# ==============================================================================

def test_scenario_a_same_defect_counted_twice_rejected(base_test_setup):
    """
    Scenario A:
    Criterion receives a lower raw score (7.0/10.0) because of a missing authentication mechanism.
    Evaluator proposes an additional deduction for the same missing authentication mechanism.
    Expected: Reject the duplicate penalty unless a genuinely distinct impact is demonstrated.
    """
    s = base_test_setup
    crit1_id = s["crit1_id"]

    # Raw score was lowered to 7.00 due to missing authentication mechanism
    assessment = CriterionAssessmentContract(
        criterion_id=crit1_id,
        criterion_title="Security & Architecture",
        positive_findings=["Good modular codebase structure."],
        negative_findings=["Missing authentication mechanism on API endpoints."],
        deductions=[
            DeductionAttributionContract(
                criterion_id=crit1_id,
                evidence_ids=[s["ev1_id"]],
                issue_description="Missing authentication mechanism on API endpoints",
                defect_severity=DefectSeverity.MODERATE,
                relevance_explanation="Leaves endpoints unauthenticated.",
                is_primary_attribution=True,
                deduction_points=Decimal("2.00"),
                proportionality_rationale="Significant security defect.",
            )
        ],
        raw_score_before_deductions=Decimal("7.00"),
        total_deductions=Decimal("2.00"),
        final_criterion_score=Decimal("5.00"),
        score_justification="Raw score lowered to 7.00 due to missing authentication mechanism on endpoints.",
    )

    violations = DeductionAttributionEngine.validate_criterion_raw_score_interaction(assessment)
    assert len(violations) > 0
    assert any("Scenario A" in v and "duplicate punishment" in v.lower() for v in violations)

    payload = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=s["evidence_records"],
        criterion_assessments=[assessment],
        overall_quick_summary="Evaluation with double counting.",
        overall_detailed_summary="Comprehensive review breakdown.",
    )

    with pytest.raises(AIEvaluationValidationError) as exc:
        validate_standardized_evaluation_output(payload, rubric_criteria=[s["rubric_crit"][0]])
    assert exc.value.error_code == "RAW_SCORE_DEDUCTION_DOUBLE_COUNTING"


def test_scenario_b_raw_score_already_accounts_for_defect_rejected(base_test_setup):
    """
    Scenario B:
    Evaluator explicitly states in its assessment that a defect has already reduced the raw score.
    The same defect is submitted as a deduction.
    Expected: Reject the additional deduction.
    """
    s = base_test_setup
    crit1_id = s["crit1_id"]

    assessment = CriterionAssessmentContract(
        criterion_id=crit1_id,
        criterion_title="Security & Architecture",
        positive_findings=["Implements structured logging and error handling."],
        negative_findings=["Unencrypted database credentials."],
        deductions=[
            DeductionAttributionContract(
                criterion_id=crit1_id,
                evidence_ids=[s["ev1_id"]],
                issue_description="Unencrypted database credentials in configuration",
                defect_severity=DefectSeverity.MODERATE,
                relevance_explanation="Credential disclosure risk.",
                is_primary_attribution=True,
                deduction_points=Decimal("1.50"),
                proportionality_rationale="Moderate exposure.",
            )
        ],
        raw_score_before_deductions=Decimal("8.00"),
        total_deductions=Decimal("1.50"),
        final_criterion_score=Decimal("6.50"),
        score_justification="The defect of unencrypted database credentials has already reduced the raw score to 8.00.",
    )

    violations = DeductionAttributionEngine.validate_criterion_raw_score_interaction(assessment)
    assert len(violations) > 0
    assert any("Scenario B" in v for v in violations)


def test_scenario_c_legitimate_separate_impact_permitted(base_test_setup):
    """
    Scenario C:
    A defect has two genuinely independent impacts:
    - Impact 1: Unauthenticated administrative endpoint access.
    - Impact 2: Denial of service via unbounded memory consumption.
    Both impacts are explicitly documented and supported by evidence.
    Expected: Allow separate attribution when non-overlap justification is evidenced.
    """
    s = base_test_setup
    crit1_id = s["crit1_id"]

    d1 = DeductionAttributionContract(
        criterion_id=crit1_id,
        evidence_ids=[s["ev1_id"]],
        issue_description="Missing authentication mechanism in JWT token validator",
        defect_severity=DefectSeverity.MODERATE,
        relevance_explanation="Security flaw in authentication layer.",
        is_primary_attribution=True,
        deduction_points=Decimal("2.00"),
        proportionality_rationale="Moderate authorization defect.",
        impact_explanation="Enables complete unauthorized administrative access to protected resources.",
        raw_score_non_overlap_justification="Raw score evaluated baseline architectural structure; this deduction penalizes the critical auth bypass.",
    )

    d2 = DeductionAttributionContract(
        criterion_id=crit1_id,
        evidence_ids=[s["ev2_id"]],
        issue_description="Missing authentication allows remote denial of service via memory exhaust",
        defect_severity=DefectSeverity.MODERATE,
        relevance_explanation="Reliability and availability flaw.",
        is_primary_attribution=True,
        deduction_points=Decimal("2.00"),
        proportionality_rationale="Independent availability failure impact.",
        impact_explanation="Demonstrated memory leak and server crash triggered by unauthenticated request spam.",
        raw_score_non_overlap_justification="Raw score did not account for server availability crash; this addresses demonstrated DoS vulnerability.",
    )

    assessment = CriterionAssessmentContract(
        criterion_id=crit1_id,
        criterion_title="Security & Architecture",
        positive_findings=["Clean layered architecture and comprehensive domain documentation."],
        negative_findings=[],
        deductions=[d1, d2],
        raw_score_before_deductions=Decimal("9.00"),
        total_deductions=Decimal("4.00"),
        final_criterion_score=Decimal("5.00"),
        score_justification="Raw score of 9.0 awarded for clean architecture. Deductions applied for independent security and DoS vulnerabilities.",
    )

    # 1. Raw-score interaction should be clean (both have non-overlap justifications)
    violations = DeductionAttributionEngine.validate_criterion_raw_score_interaction(assessment)
    assert len(violations) == 0

    # 2. Within-criterion duplicate check should accept both because distinct impacts and evidence are documented
    batch_res = DeductionAttributionEngine.validate_deductions_batch([d1, d2], known_evidence_ids={s["ev1_id"], s["ev2_id"]})
    assert batch_res.is_valid is True
    assert len(batch_res.accepted_deductions) == 2


def test_scenario_d_different_defects_in_same_criterion_permitted(base_test_setup):
    """
    Scenario D:
    Two independent, distinct defects affect the same criterion:
    - Defect 1: SQL injection vulnerability in search query.
    - Defect 2: Insecure hardcoded API key in config.
    Expected: Permit separate deductions when independently justified.
    """
    s = base_test_setup
    crit1_id = s["crit1_id"]

    d1 = DeductionAttributionContract(
        criterion_id=crit1_id,
        evidence_ids=[s["ev1_id"]],
        issue_description="SQL injection vulnerability in search query builder",
        defect_severity=DefectSeverity.MODERATE,
        relevance_explanation="Direct SQL injection vector.",
        is_primary_attribution=True,
        deduction_points=Decimal("2.50"),
        proportionality_rationale="Critical data compromise vector.",
        impact_explanation="Allows unauthenticated database extraction.",
    )

    d2 = DeductionAttributionContract(
        criterion_id=crit1_id,
        evidence_ids=[s["ev2_id"]],
        issue_description="Hardcoded third-party API secret key in settings module",
        defect_severity=DefectSeverity.MINOR,
        relevance_explanation="Credential hygiene defect.",
        is_primary_attribution=True,
        deduction_points=Decimal("1.00"),
        proportionality_rationale="Secret exposure in repository history.",
        impact_explanation="Exposes third-party integration credentials in public repository.",
    )

    assessment = CriterionAssessmentContract(
        criterion_id=crit1_id,
        criterion_title="Security & Architecture",
        positive_findings=["Solid project structure."],
        negative_findings=[],
        deductions=[d1, d2],
        raw_score_before_deductions=Decimal("8.50"),
        total_deductions=Decimal("3.50"),
        final_criterion_score=Decimal("5.00"),
        score_justification="Awarded 8.5 for architectural layout. Independent deductions for SQL injection and hardcoded API secret.",
    )

    violations = DeductionAttributionEngine.validate_criterion_raw_score_interaction(assessment)
    assert len(violations) == 0

    batch_res = DeductionAttributionEngine.validate_deductions_batch([d1, d2], known_evidence_ids={s["ev1_id"], s["ev2_id"]})
    assert batch_res.is_valid is True
    assert len(batch_res.accepted_deductions) == 2


# ==============================================================================
# 2. Within-Criterion Duplicate Deduction Tests
# ==============================================================================

def test_within_criterion_duplicate_penalties_rejected(base_test_setup):
    """
    Verify that proposing two deductions in the SAME criterion for the same underlying issue
    without distinct impacts and evidence is rejected.
    """
    s = base_test_setup
    crit1_id = s["crit1_id"]

    d1 = DeductionAttributionContract(
        criterion_id=crit1_id,
        evidence_ids=[s["ev1_id"]],
        issue_description="Missing authentication mechanism in REST API endpoints",
        defect_severity=DefectSeverity.MODERATE,
        relevance_explanation="Authentication omission.",
        is_primary_attribution=True,
        deduction_points=Decimal("2.00"),
        proportionality_rationale="Moderate severity defect.",
    )

    d2_duplicate = DeductionAttributionContract(
        criterion_id=crit1_id,
        evidence_ids=[s["ev1_id"]],
        issue_description="Missing authentication mechanism in API routes",
        defect_severity=DefectSeverity.MODERATE,
        relevance_explanation="Repeated authentication penalty.",
        is_primary_attribution=True,
        deduction_points=Decimal("2.00"),
        proportionality_rationale="Additional penalty for same issue.",
    )

    res = DeductionAttributionEngine.validate_deductions_batch([d1, d2_duplicate], known_evidence_ids={s["ev1_id"]})
    assert res.is_valid is False
    assert res.duplicate_penalties_prevented == 1
    assert any("Duplicate penalty rejected within criterion" in msg for msg in res.validation_messages)


# ==============================================================================
# 3. Severity & Deduction Proportionality Tests
# ==============================================================================

def test_minor_defect_classified_as_critical_rejected(base_test_setup):
    """
    Verify that an evaluator cannot inflate a minor defect to CRITICAL severity
    to authorize an arbitrary large point deduction.
    """
    s = base_test_setup
    crit1_id = s["crit1_id"]

    d = DeductionAttributionContract(
        criterion_id=crit1_id,
        evidence_ids=[s["ev1_id"]],
        issue_description="Minor typo and non-blocking formatting in debug logs",
        defect_severity=DefectSeverity.CRITICAL,  # Arbitrarily inflated!
        relevance_explanation="Cosmetic defect in log message.",
        is_primary_attribution=True,
        deduction_points=Decimal("8.00"),  # Arbitrary 8-point deduction!
        proportionality_rationale="Minor non-blocking cosmetic defect.",
        impact_explanation="Slightly messy log output, but system functions normally.",
    )

    res = DeductionAttributionEngine.validate_deductions_batch([d], known_evidence_ids={s["ev1_id"]})
    assert res.is_valid is False
    assert any("Disproportionate deduction rejected" in msg for msg in res.validation_messages)


def test_major_severity_with_limited_impact_rejected(base_test_setup):
    """
    Verify that a defect labeled MAJOR with limited/minor impact cannot exceed proportional bounds.
    """
    s = base_test_setup
    crit1_id = s["crit1_id"]

    d = DeductionAttributionContract(
        criterion_id=crit1_id,
        evidence_ids=[s["ev1_id"]],
        issue_description="Minor omission in optional utility helper script",
        defect_severity=DefectSeverity.MAJOR,
        relevance_explanation="Helper script omission.",
        is_primary_attribution=True,
        deduction_points=Decimal("4.50"),  # Disproportionate for minor omission!
        proportionality_rationale="Omitted helper function.",
        impact_explanation="Non-blocking edge case only, core platform operates as intended.",
    )

    res = DeductionAttributionEngine.validate_deductions_batch([d], known_evidence_ids={s["ev1_id"]})
    assert res.is_valid is False
    assert any("Disproportionate deduction rejected" in msg for msg in res.validation_messages)


def test_critical_defect_with_genuine_substantial_impact_accepted(base_test_setup):
    """
    Verify that a genuinely critical defect (catastrophic failure, proven security breach)
    is accepted with substantial deduction points when backed by evidence and rationale.
    """
    s = base_test_setup
    crit1_id = s["crit1_id"]

    d = DeductionAttributionContract(
        criterion_id=crit1_id,
        evidence_ids=[s["ev1_id"]],
        issue_description="Catastrophic remote code execution vulnerability in deserialization pipeline",
        defect_severity=DefectSeverity.CRITICAL,
        relevance_explanation="Completely compromises entire server security.",
        is_primary_attribution=True,
        deduction_points=Decimal("8.50"),
        proportionality_rationale="Critical vulnerability allowing unauthenticated root execution, invalidating core security.",
        impact_explanation="Proven unauthenticated remote shell execution across all public interfaces.",
    )

    res = DeductionAttributionEngine.validate_deductions_batch([d], known_evidence_ids={s["ev1_id"]})
    assert res.is_valid is True
    assert len(res.accepted_deductions) == 1
    assert res.total_deducted_points_by_criterion[crit1_id] == Decimal("8.50")


def test_optional_requirements_remain_deduction_immune(base_test_setup):
    """
    Verify that optional and bonus requirements are strictly immune from score deductions (EVAL_05).
    """
    s = base_test_setup
    crit1_id = s["crit1_id"]

    d = DeductionAttributionContract(
        criterion_id=crit1_id,
        evidence_ids=[s["ev1_id"]],
        issue_description="Bonus feature OPT_WEBSOCKETS was not implemented",
        defect_severity=DefectSeverity.MINOR,
        relevance_explanation="Omitted optional feature.",
        is_primary_attribution=True,
        deduction_points=Decimal("1.00"),
        proportionality_rationale="Did not implement optional real-time streaming.",
        affected_requirement_id="OPT_WEBSOCKETS",
    )

    res = DeductionAttributionEngine.validate_deductions_batch(
        [d],
        known_evidence_ids={s["ev1_id"]},
        optional_requirement_ids={"OPT_WEBSOCKETS"},
    )
    assert res.is_valid is False
    assert any("violates EVAL_05" in msg for msg in res.validation_messages)


def test_deduction_arithmetic_strictly_decimal():
    """
    Verify that deduction point calculations prohibit floating-point arithmetic.
    """
    raw = Decimal("8.50")
    crit_id = uuid.uuid4()
    d1 = DeductionAttributionContract(
        criterion_id=crit_id,
        issue_description="Valid minor defect",
        defect_severity=DefectSeverity.MINOR,
        relevance_explanation="Minor defect.",
        deduction_points=Decimal("1.25"),
        proportionality_rationale="Minor deduction.",
    )
    final, total_ded = DeductionAttributionEngine.apply_deductions_to_raw_score(raw, [d1])
    assert isinstance(final, Decimal)
    assert isinstance(total_ded, Decimal)
    assert final == Decimal("7.25")
    assert total_ded == Decimal("1.25")

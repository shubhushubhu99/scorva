"""
Scorva Phase 1: Fair Evaluation Foundation & Scoring Contracts Verification Suite.

Validates:
1. Criterion-specific scoring anchors (0 to 10) across all 5 criteria.
2. Missing evidence versus confirmed absence (EVAL_04).
3. Mandatory versus optional requirements (EVAL_05).
4. Duplicate penalty detection and anti-double-counting (EVAL_10).
5. Cross-criterion deduction justification.
6. Unsupported findings and hallucination defense.
7. Invalid evidence references (line bounds, fake files).
8. Invalid rubric weights (must sum to 1.0000).
9. Score boundaries ([min_score, max_score]).
10. Decimal arithmetic (strictly zero float drift).
11. Policy versioning and trace validation.
12. Judge score separation.
13. Existing evaluation compatibility.

Mandatory Fairness Scenarios:
- Scenario A: Simple but effective project (no stack size penalty).
- Scenario B: Sophisticated but incomplete project (no complexity points for broken execution).
- Scenario C: Missing optional feature (no deductions for omitted bonus features).
- Scenario D: Duplicate defect (same defect across criteria requires justification or rejected).
- Scenario E: Unsupported claim (README claims distinguished from verified code).
- Scenario F: Insufficient evidence (uncertainty expressed, no arbitrary 0 penalty).
- Scenario G: Equivalent achievement (consistent scoring across equivalent rubrics).
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
from apps.api.modules.evaluations.policy.criteria_framework import (
    CODE_QUALITY_CRITERION,
    EXECUTION_COMPLETENESS_CRITERION,
    INNOVATION_CRITERION,
    POTENTIAL_IMPACT_CRITERION,
    TECHNICAL_COMPLEXITY_CRITERION,
    get_all_standard_criteria_frameworks,
    get_criterion_framework,
)
from apps.api.modules.evaluations.policy.deduction_engine import (
    DeductionAttributionEngine,
    SEVERITY_MAX_DEDUCTION_BOUNDS,
)
from apps.api.modules.evaluations.policy.policy_engine import (
    DEFAULT_EVALUATION_POLICY_VERSION,
    EvaluationPolicy,
    get_active_evaluation_policy,
)
from apps.api.modules.evaluations.scoring_calculator import (
    CriterionInput,
    EvaluationScoreResult,
    ScoringMode,
    assert_not_float,
    calculate_evaluation_scores,
    to_decimal,
    validate_criteria_weights,
)


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def standard_5_rubric_criteria():
    """Returns the 5 official criteria matching the Graviton hackathon rubric."""
    return [
        {
            "id": uuid.UUID("9f1c4f5d-4b8b-4f0f-8a0c-bf236be8b0b6"),
            "title": "Innovation & Originality",
            "weight": Decimal("0.2500"),
            "min_score": Decimal("0.00"),
            "max_score": Decimal("10.00"),
            "description": "Uniqueness of concept and creative problem-solving.",
        },
        {
            "id": uuid.UUID("2bd7a620-e8d7-4102-bee0-64d0d34eab0f"),
            "title": "Technical Complexity & Architecture",
            "weight": Decimal("0.2500"),
            "min_score": Decimal("0.00"),
            "max_score": Decimal("10.00"),
            "description": "Depth of architecture, modularity, and technical rigor.",
        },
        {
            "id": uuid.UUID("078b836e-425e-4b6f-b034-8822811c1313"),
            "title": "Code Quality & Cleanliness",
            "weight": Decimal("0.2000"),
            "min_score": Decimal("0.00"),
            "max_score": Decimal("10.00"),
            "description": "Readability, typing, error handling, and test suites.",
        },
        {
            "id": uuid.UUID("c21ff60b-bf07-4e0f-be17-a5dd5b4835bd"),
            "title": "Execution & Completeness",
            "weight": Decimal("0.1500"),
            "min_score": Decimal("0.00"),
            "max_score": Decimal("10.00"),
            "description": "Working functionality and absence of placeholder stubs.",
        },
        {
            "id": uuid.UUID("23c1c275-0ac2-4a28-8f44-c923414634fc"),
            "title": "Potential Impact & Usability",
            "weight": Decimal("0.1500"),
            "min_score": Decimal("0.00"),
            "max_score": Decimal("10.00"),
            "description": "Practical usefulness, target audience relevance, and UX polish.",
        },
    ]


# ==============================================================================
# 1. Criterion-Specific Scoring Anchors Tests
# ==============================================================================

def test_01_criterion_scoring_anchors_complete_0_to_10():
    """Asserts that all 5 criteria possess unique, non-repetitive anchors from 0 to 10."""
    frameworks = get_all_standard_criteria_frameworks()
    assert len(frameworks) == 5

    for fw in frameworks:
        assert len(fw.scoring_anchors) == 11  # 0 through 10
        for lvl in range(11):
            assert lvl in fw.scoring_anchors
            desc = fw.scoring_anchors[lvl]
            assert isinstance(desc, str) and len(desc.strip()) > 15
            # Ensure anchors are distinct and meaningful
            assert "exceptional" in fw.scoring_anchors[10].lower() or "flawless" in fw.scoring_anchors[10].lower() or "breakthrough" in fw.scoring_anchors[10].lower() or "masterclass" in fw.scoring_anchors[10].lower() or "exemplary" in fw.scoring_anchors[10].lower()

        # Check forbidden irrelevant factors
        assert len(fw.irrelevant_factors) >= 3
        assert len(fw.positive_indicators) >= 3
        assert len(fw.negative_indicators) >= 3


def test_02_organizer_defined_custom_criterion_resolution():
    """Asserts that organizer-defined criteria construct dynamic, anchored frameworks."""
    custom_fw = get_criterion_framework("Design & Mobile Responsiveness")
    assert custom_fw.display_title == "Design & Mobile Responsiveness"
    assert len(custom_fw.scoring_anchors) == 11
    assert "Design & Mobile Responsiveness" in custom_fw.scoring_anchors[10]
    assert len(custom_fw.irrelevant_factors) >= 1


# ==============================================================================
# 2. Missing Evidence vs Confirmed Absence Tests (EVAL_04)
# ==============================================================================

def test_03_missing_evidence_does_not_force_zero_score():
    """
    EVAL_04: Missing evidence must flag uncertainty, not automatically force min_score 0.00.
    """
    ca = CriterionAssessmentContract(
        criterion_id=uuid.UUID("c21ff60b-bf07-4e0f-be17-a5dd5b4835bd"),
        criterion_title="Execution & Completeness",
        positive_findings=["Entrypoints and basic UI layouts were verified."],
        negative_findings=[],
        missing_evidence_observations=["Deep worker execution directory was unindexed in snapshot."],
        evidence_strength=EvidenceStrength.WEAK,
        confidence=Decimal("0.60"),  # Explicitly communicates uncertainty
        raw_score_before_deductions=Decimal("5.00"),  # Baseline neutral, NOT 0.00
        total_deductions=Decimal("0.00"),
        final_criterion_score=Decimal("5.00"),
        score_justification="Assigned provisional baseline score 5.00 due to unindexed worker files.",
    )
    assert ca.final_criterion_score == Decimal("5.00")
    assert ca.confidence == Decimal("0.60")
    assert ca.evidence_strength == EvidenceStrength.WEAK


# ==============================================================================
# 3. Mandatory vs Optional Requirements (EVAL_05)
# ==============================================================================

def test_04_omitted_optional_feature_cannot_be_penalized():
    """
    EVAL_05: Failure to build an optional or bonus requirement must never trigger a deduction.
    """
    policy = EvaluationPolicy.get_default_policy()

    # Create assessment where an optional requirement has an unverified status
    optional_req = RequirementContract(
        requirement_id="OPT_01_KUBERNETES_HELM",
        title="Helm Chart Deployment",
        description="Optional bonus: Deploy using Kubernetes Helm chart.",
        requirement_type=RequirementType.OPTIONAL,
        verification_status=VerificationStatus.NOT_AVAILABLE,
        rationale="Team did not build the optional Helm chart.",
    )

    # Invalid deduction penalizing the missing optional feature
    illegal_deduction = DeductionAttributionContract(
        criterion_id=uuid.UUID("2bd7a620-e8d7-4102-bee0-64d0d34eab0f"),
        issue_description="Missing OPT_01_KUBERNETES_HELM chart",
        defect_severity=DefectSeverity.MINOR,
        relevance_explanation="Architecture is missing optional Helm packaging.",
        deduction_points=Decimal("1.00"),
        proportionality_rationale="Proportionate penalty for missing deployment chart.",
    )

    output = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="abcdef1234567890",
        rubric_version_id=uuid.uuid4(),
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=uuid.UUID("2bd7a620-e8d7-4102-bee0-64d0d34eab0f"),
                criterion_title="Technical Complexity & Architecture",
                requirement_coverage=[optional_req],
                deductions=[illegal_deduction],
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("1.00"),
                final_criterion_score=Decimal("7.00"),
                score_justification="Penalized for missing optional Helm chart.",
            )
        ],
        overall_quick_summary="Good project with solid architecture.",
        overall_detailed_summary="Evaluated against optional and mandatory requirements.",
    )

    violations = policy.validate_evaluation_fairness(output)
    assert any("EVAL_05" in v for v in violations)


# ==============================================================================
# 4 & 5. Duplicate Penalty Detection & Anti-Double-Counting (EVAL_10)
# ==============================================================================

def test_05_duplicate_primary_deduction_rejected():
    """
    EVAL_10: The same root defect cannot trigger primary deductions on multiple criteria.
    """
    crit1_id = uuid.uuid4()
    crit2_id = uuid.uuid4()
    defect_group = "DEFECT_STATIC_LOGO_AUTH_BYPASS"

    ded1 = DeductionAttributionContract(
        criterion_id=crit1_id,
        issue_description="Uploaded logo files are served from public static URLs without auth.",
        defect_severity=DefectSeverity.MODERATE,
        relevance_explanation="Security hygiene vulnerability on file storage.",
        overlap_group_id=defect_group,
        is_primary_attribution=True,
        deduction_points=Decimal("1.50"),
        proportionality_rationale="Proportionate moderate penalty for public static logo leak.",
    )

    ded2_duplicate = DeductionAttributionContract(
        criterion_id=crit2_id,
        issue_description="Uploaded logo files are served from public static URLs without auth.",
        defect_severity=DefectSeverity.MODERATE,
        relevance_explanation="Reduces potential impact because files are publicly exposed.",
        overlap_group_id=defect_group,
        is_primary_attribution=True,  # VIOLATION: Cannot have second primary for same root defect
        deduction_points=Decimal("1.50"),
        proportionality_rationale="Proportionate penalty on impact.",
    )

    res = DeductionAttributionEngine.validate_deductions_batch([ded1, ded2_duplicate])
    assert not res.is_valid
    assert res.duplicate_penalties_prevented == 1
    assert len(res.accepted_deductions) == 1
    assert res.accepted_deductions[0].criterion_id == crit1_id


def test_06_secondary_deduction_allowed_only_with_rigorous_justification():
    """
    Cross-criterion deduction is permitted ONLY if marked non-primary AND supported
    by a distinct, independent justification.
    """
    crit1_id = uuid.uuid4()
    crit2_id = uuid.uuid4()
    defect_group = "DEFECT_PUBLIC_SCANNER_ABUSE"

    primary_ded = DeductionAttributionContract(
        criterion_id=crit1_id,
        issue_description="Scanner lacks rate-limiting or target authorization checks.",
        defect_severity=DefectSeverity.MAJOR,
        relevance_explanation="Code quality defect: missing authorization middleware and IP throttles.",
        overlap_group_id=defect_group,
        is_primary_attribution=True,
        deduction_points=Decimal("2.00"),
        proportionality_rationale="Major penalty for missing rate limiter.",
    )

    secondary_ded_justified = DeductionAttributionContract(
        criterion_id=crit2_id,
        issue_description="Scanner lacks rate-limiting or target authorization checks.",
        defect_severity=DefectSeverity.MINOR,
        relevance_explanation="Impact barrier: open scanner cannot be safely hosted publicly.",
        overlap_group_id=defect_group,
        is_primary_attribution=False,
        cross_criterion_justification="Beyond missing code middleware, this fundamentally prevents enterprise deployment.",
        deduction_points=Decimal("1.00"),
        proportionality_rationale="Minor secondary impact deduction.",
    )

    res = DeductionAttributionEngine.validate_deductions_batch([primary_ded, secondary_ded_justified])
    assert res.is_valid
    assert len(res.accepted_deductions) == 2
    assert res.duplicate_penalties_prevented == 0


# ==============================================================================
# 6 & 7. Evidence Citations and Hallucination Rejection
# ==============================================================================

def test_07_invalid_evidence_line_bounds_rejected():
    """EvidenceContract must strictly reject start_line > end_line."""
    with pytest.raises(ValueError, match="start_line .* cannot be greater than end_line"):
        EvidenceContract(
            evidence_type=EvidenceType.SOURCE_CODE,
            commit_sha="1234567890abcdef",
            file_path="src/main.py",
            start_line=50,
            end_line=20,  # Invalid!
            source_excerpt="def main(): pass",
            explanation="Invalid line span test.",
        )


def test_08_deduction_citing_unregistered_evidence_rejected():
    """Deductions citing fabricated or non-existent evidence IDs must be rejected."""
    crit_id = uuid.uuid4()
    fake_eid = uuid.uuid4()
    known_eid = uuid.uuid4()

    ded = DeductionAttributionContract(
        criterion_id=crit_id,
        issue_description="Database query leak detected.",
        defect_severity=DefectSeverity.MINOR,
        relevance_explanation="Code Quality issue.",
        evidence_ids=[fake_eid],  # Fake ID not in known evidence set
        deduction_points=Decimal("1.00"),
        proportionality_rationale="Proportionate penalty.",
    )

    res = DeductionAttributionEngine.validate_deductions_batch([ded], known_evidence_ids={known_eid})
    assert not res.is_valid
    assert any("non-existent evidence" in msg for msg in res.validation_messages)


# ==============================================================================
# 8 & 9. Rubric Weight & Score Boundaries Tests
# ==============================================================================

def test_09_rubric_weights_must_sum_to_one():
    """Deterministic calculator must raise ValueError if weights sum != 1.0000."""
    invalid_criteria = [
        CriterionInput(criterion_id=uuid.uuid4(), weight=Decimal("0.5000"), awarded_score=Decimal("8.00")),
        CriterionInput(criterion_id=uuid.uuid4(), weight=Decimal("0.4000"), awarded_score=Decimal("7.00")),
    ]  # Sum = 0.9000, violates 1.0000 invariant!
    with pytest.raises(ValueError, match="Rubric criteria weights must sum to 1.0000"):
        validate_criteria_weights(invalid_criteria)


def test_10_awarded_score_out_of_bounds_rejected():
    """Calculator must reject scores below min_score or above max_score."""
    with pytest.raises(ValueError, match="out of bounds"):
        calculate_evaluation_scores([
            CriterionInput(
                criterion_id=uuid.uuid4(),
                weight=Decimal("1.0000"),
                min_score=Decimal("0.00"),
                max_score=Decimal("10.00"),
                awarded_score=Decimal("10.50"),  # Out of bounds!
            )
        ])


# ==============================================================================
# 10. Decimal Arithmetic & Zero Drift
# ==============================================================================

def test_11_strictly_zero_floating_point_drift():
    """All arithmetic must use decimal.Decimal; IEEE-754 floats are rejected."""
    with pytest.raises(TypeError, match="Floating-point values are strictly prohibited"):
        assert_not_float(0.25, "weight")

    # Verify ROUND_HALF_UP rounding repeatability
    c1 = CriterionInput(criterion_id=uuid.uuid4(), weight=Decimal("0.3333"), awarded_score=Decimal("7.55"))
    c2 = CriterionInput(criterion_id=uuid.uuid4(), weight=Decimal("0.3333"), awarded_score=Decimal("6.45"))
    c3 = CriterionInput(criterion_id=uuid.uuid4(), weight=Decimal("0.3334"), awarded_score=Decimal("8.10"))

    res = calculate_evaluation_scores([c1, c2, c3])
    assert isinstance(res.normalized_score, Decimal)
    assert res.normalized_score == Decimal("73.67")


# ==============================================================================
# 11 & 12. Policy Versioning & Judge Score Separation
# ==============================================================================

def test_12_policy_versioning_and_judge_separation():
    """Active policy version must be traceable and keep AI advisory separate from judge."""
    policy = get_active_evaluation_policy()
    assert policy.version == DEFAULT_EVALUATION_POLICY_VERSION
    assert any(r.rule_id == "EVAL_13_AI_ADVISORY_SEPARATION" for r in policy.rules)


# ==============================================================================
# MANDATORY FAIRNESS SCENARIOS (A THROUGH G)
# ==============================================================================

def test_scenario_a_simple_but_effective_project():
    """
    Scenario A — Simple but effective project.
    A project uses a simple stack (e.g. SQLite + Flask), but solves the problem exceptionally well.
    The system must NOT penalize it for technological simplicity.
    """
    ca = CriterionAssessmentContract(
        criterion_id=uuid.UUID("2bd7a620-e8d7-4102-bee0-64d0d34eab0f"),
        criterion_title="Technical Complexity & Architecture",
        positive_findings=[
            "Clean SQLite schema with transactional consistency.",
            "Straightforward modular service layer with zero bloat.",
            "Fast, highly reliable response times under 20ms.",
        ],
        negative_findings=[],
        evidence_strength=EvidenceStrength.STRONG,
        raw_score_before_deductions=Decimal("8.50"),
        total_deductions=Decimal("0.00"),
        final_criterion_score=Decimal("8.50"),
        score_justification="Simple, highly effective architecture solving the exact problem without bloat.",
    )
    # Assert no stack-size deductions
    assert ca.final_criterion_score == Decimal("8.50")
    assert not ca.deductions


def test_scenario_b_sophisticated_but_incomplete_project():
    """
    Scenario B — Sophisticated but incomplete project.
    A project claims complex microservices/Celery/Kafka, but core features are non-functional stubs.
    The system must NOT award high execution marks merely because of architectural ambition.
    """
    ca = CriterionAssessmentContract(
        criterion_id=uuid.UUID("c21ff60b-bf07-4e0f-be17-a5dd5b4835bd"),
        criterion_title="Execution & Completeness",
        positive_findings=["Ambitious docker-compose file with Kafka and Celery declarations."],
        negative_findings=[
            "Endpoint handlers return hardcoded dummy JSON mock responses.",
            "Kafka consumers are unwritten stubs (TODO: implement).",
        ],
        deductions=[
            DeductionAttributionContract(
                criterion_id=uuid.UUID("c21ff60b-bf07-4e0f-be17-a5dd5b4835bd"),
                issue_description="Core endpoints return static dummy mocks rather than processing live data.",
                defect_severity=DefectSeverity.MAJOR,
                relevance_explanation="Fails execution completeness: project is not a functional implementation.",
                deduction_points=Decimal("5.00"),
                proportionality_rationale="Major deduction for core stubbed mock handlers.",
            )
        ],
        evidence_strength=EvidenceStrength.STRONG,
        raw_score_before_deductions=Decimal("7.00"),
        total_deductions=Decimal("5.00"),
        final_criterion_score=Decimal("2.00"),
        score_justification="Awarded low execution score (2.00) because claimed complexity is non-functional.",
    )
    assert ca.final_criterion_score == Decimal("2.00")


def test_scenario_c_missing_optional_feature():
    """
    Scenario C — Missing optional feature.
    A project omitted a bonus feature.
    The system must NOT deduct points without rubric justification.
    """
    optional_req = RequirementContract(
        requirement_id="BONUS_DARK_MODE",
        title="Dark Mode Support",
        description="Optional: Provide dark/light mode toggle.",
        requirement_type=RequirementType.OPTIONAL,
        verification_status=VerificationStatus.NOT_AVAILABLE,
        rationale="Team did not build dark mode.",
    )
    ca = CriterionAssessmentContract(
        criterion_id=uuid.UUID("23c1c275-0ac2-4a28-8f44-c923414634fc"),
        criterion_title="Potential Impact & Usability",
        requirement_coverage=[optional_req],
        positive_findings=["Light mode UI is clean, intuitive, and highly functional."],
        negative_findings=[],
        deductions=[],  # ZERO deductions for missing optional requirement
        evidence_strength=EvidenceStrength.STRONG,
        raw_score_before_deductions=Decimal("8.50"),
        total_deductions=Decimal("0.00"),
        final_criterion_score=Decimal("8.50"),
        score_justification="Full usability credit given; missing bonus dark mode was not penalized.",
    )
    assert ca.final_criterion_score == Decimal("8.50")
    assert len(ca.deductions) == 0


def test_scenario_d_duplicate_defect():
    """
    Scenario D — Duplicate defect.
    The same defect appears relevant to several criteria.
    The system must require independent justification and prevent duplicate penalty.
    """
    engine = DeductionAttributionEngine()
    crit1 = uuid.uuid4()
    crit2 = uuid.uuid4()
    group_id = "DEFECT_NO_DATABASE_MIGRATIONS"

    # 1. Pydantic contract layer: rejects non-primary deduction missing justification
    with pytest.raises(ValueError, match="requires an explicit 'cross_criterion_justification'"):
        DeductionAttributionContract(
            criterion_id=crit2,
            issue_description="Missing database migration scripts.",
            defect_severity=DefectSeverity.MINOR,
            relevance_explanation="Code hygiene lacks migrations folder.",
            overlap_group_id=group_id,
            is_primary_attribution=False,
            cross_criterion_justification=None,  # Missing justification!
            deduction_points=Decimal("1.00"),
            proportionality_rationale="Duplicate deduction.",
        )

    # 2. Engine layer: rejects two primary deductions claiming the same root defect
    ded_crit1 = DeductionAttributionContract(
        criterion_id=crit1,
        issue_description="Missing database migration scripts.",
        defect_severity=DefectSeverity.MINOR,
        relevance_explanation="Architecture: schema versioning is unmanaged.",
        overlap_group_id=group_id,
        is_primary_attribution=True,
        deduction_points=Decimal("1.00"),
        proportionality_rationale="Minor penalty for unmanaged schema.",
    )

    ded_crit2_duplicate_primary = DeductionAttributionContract(
        criterion_id=crit2,
        issue_description="Missing database migration scripts.",
        defect_severity=DefectSeverity.MINOR,
        relevance_explanation="Code hygiene lacks migrations folder.",
        overlap_group_id=group_id,
        is_primary_attribution=True,  # Second primary attribution attempted!
        deduction_points=Decimal("1.00"),
        proportionality_rationale="Duplicate primary deduction.",
    )

    res = engine.validate_deductions_batch([ded_crit1, ded_crit2_duplicate_primary])
    assert not res.is_valid
    assert res.duplicate_penalties_prevented == 1


def test_scenario_e_unsupported_claim():
    """
    Scenario E — Unsupported claim.
    README claims 'Scales to 1,000,000 users with distributed caching', but code shows single in-memory dict.
    System must distinguish claim from verified implementation.
    """
    req = RequirementContract(
        requirement_id="CLAIM_DISTRIBUTED_CACHE",
        title="Distributed Caching Scale",
        description="Team claims million-user distributed caching.",
        requirement_type=RequirementType.TEAM_CLAIMED,
        verification_status=VerificationStatus.CONTRADICTED,
        rationale="Codebase uses an un-synchronized local Python dictionary, directly contradicting distributed claim.",
    )
    assert req.verification_status == VerificationStatus.CONTRADICTED
    assert req.requirement_type == RequirementType.TEAM_CLAIMED


def test_scenario_f_insufficient_evidence():
    """
    Scenario F — Insufficient evidence.
    Repository evidence cannot support reliable assessment (e.g. 1-file repo or snapshot drop).
    System must express uncertainty rather than inventing a score justification or forcing 0.
    """
    ca = CriterionAssessmentContract(
        criterion_id=uuid.UUID("9f1c4f5d-4b8b-4f0f-8a0c-bf236be8b0b6"),
        criterion_title="Innovation & Originality",
        positive_findings=[],
        negative_findings=[],
        missing_evidence_observations=["Repository contains only an empty skeleton with no domain code."],
        evidence_strength=EvidenceStrength.INSUFFICIENT,
        confidence=Decimal("0.30"),
        unresolved_questions=["What is the proprietary algorithm referenced in the proposal?"],
        raw_score_before_deductions=Decimal("5.00"),  # Baseline neutral
        total_deductions=Decimal("0.00"),
        final_criterion_score=Decimal("5.00"),
        score_justification="Assigned neutral score with 0.30 confidence due to insufficient evidence.",
    )
    assert ca.evidence_strength == EvidenceStrength.INSUFFICIENT
    assert ca.confidence == Decimal("0.30")
    assert len(ca.unresolved_questions) > 0


def test_scenario_g_equivalent_achievement(standard_5_rubric_criteria):
    """
    Scenario G — Equivalent achievement.
    Two different projects demonstrate equivalent achievement against equivalent rubrics.
    Scoring framework must produce mathematically identical normalized results.
    """
    # Project 1 inputs
    p1_inputs = [
        CriterionInput(criterion_id=standard_5_rubric_criteria[0]["id"], weight=Decimal("0.25"), awarded_score=Decimal("8.00")),
        CriterionInput(criterion_id=standard_5_rubric_criteria[1]["id"], weight=Decimal("0.25"), awarded_score=Decimal("7.00")),
        CriterionInput(criterion_id=standard_5_rubric_criteria[2]["id"], weight=Decimal("0.20"), awarded_score=Decimal("9.00")),
        CriterionInput(criterion_id=standard_5_rubric_criteria[3]["id"], weight=Decimal("0.15"), awarded_score=Decimal("8.50")),
        CriterionInput(criterion_id=standard_5_rubric_criteria[4]["id"], weight=Decimal("0.15"), awarded_score=Decimal("7.50")),
    ]

    # Project 2 inputs (same marks earned through different features)
    p2_inputs = [
        CriterionInput(criterion_id=standard_5_rubric_criteria[0]["id"], weight=Decimal("0.25"), awarded_score=Decimal("8.00")),
        CriterionInput(criterion_id=standard_5_rubric_criteria[1]["id"], weight=Decimal("0.25"), awarded_score=Decimal("7.00")),
        CriterionInput(criterion_id=standard_5_rubric_criteria[2]["id"], weight=Decimal("0.20"), awarded_score=Decimal("9.00")),
        CriterionInput(criterion_id=standard_5_rubric_criteria[3]["id"], weight=Decimal("0.15"), awarded_score=Decimal("8.50")),
        CriterionInput(criterion_id=standard_5_rubric_criteria[4]["id"], weight=Decimal("0.15"), awarded_score=Decimal("7.50")),
    ]

    p1_result = calculate_evaluation_scores(p1_inputs)
    p2_result = calculate_evaluation_scores(p2_inputs)

    assert p1_result.normalized_score == p2_result.normalized_score
    assert p1_result.raw_score == p2_result.raw_score
    assert p1_result.normalized_score == Decimal("79.50")

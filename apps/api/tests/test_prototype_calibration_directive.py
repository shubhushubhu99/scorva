"""
Scorva Phase 1 Final Calibration Patch: Prototype-Versus-Production Directive Regression Suite.

Verifies:
1. A working prototype without Kubernetes or distributed infrastructure must not lose points solely for those omissions.
2. A simple architecture must not be penalized merely for not using microservices.
3. Missing cloud deployment manifests must not reduce scores unless required.
4. A missing live integration explicitly required by the problem statement must affect the relevant criterion.
5. An optional feature must not attract a deduction.
6. An incomplete mandatory feature must still be identified and appropriately reflected in scoring.
7. Prototype calibration must not inflate scores or override criterion-specific anchors.
8. The prototype calibration directive is actively compiled and injected into the live prompt pipeline.
"""

from decimal import Decimal
import uuid
import pytest

from apps.api.modules.evaluations.evidence_indexer import EvidenceIndex
from apps.api.modules.evaluations.output_validator import (
    AIEvaluationValidationError,
    validate_standardized_evaluation_output,
)
from apps.api.modules.evaluations.policy.contracts import (
    CriterionAssessmentContract,
    DeductionAttributionContract,
    DefectSeverity,
    EvidenceContract,
    EvidenceType,
    RequirementContract,
    RequirementType,
    StandardizedEvaluationOutput,
    VerificationStatus,
)
from apps.api.modules.evaluations.policy.deduction_engine import DeductionAttributionEngine
from apps.api.modules.evaluations.prompt_compiler import (
    compile_evaluation_prompt,
    get_standardized_evaluation_json_schema,
)


@pytest.fixture
def calibration_test_setup():
    crit_arch_id = uuid.uuid4()
    crit_exec_id = uuid.uuid4()
    crit_usab_id = uuid.uuid4()

    rubric_crit = [
        {
            "id": crit_arch_id,
            "title": "Technical Complexity & Architecture",
            "description": "Evaluate clean code modularity and engineering rigor.",
            "min_score": Decimal("0.00"),
            "max_score": Decimal("10.00"),
            "evidence_requirements": "Source code architecture and modular boundaries.",
        },
        {
            "id": crit_exec_id,
            "title": "Execution & Completeness",
            "description": "Functional implementation satisfying stated requirements.",
            "min_score": Decimal("0.00"),
            "max_score": Decimal("10.00"),
            "evidence_requirements": "Runnable code and passing automated tests.",
        },
        {
            "id": crit_usab_id,
            "title": "Potential Impact & Usability",
            "description": "Practical utility and clear user documentation.",
            "min_score": Decimal("0.00"),
            "max_score": Decimal("10.00"),
            "evidence_requirements": "Clear README setup and execution instructions.",
        },
    ]

    ev_id = uuid.uuid4()
    evidence_records = [
        EvidenceContract(
            evidence_id=ev_id,
            evidence_type=EvidenceType.SOURCE_CODE,
            commit_sha="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            file_path="src/main.py",
            start_line=1,
            end_line=20,
            source_excerpt="class App:\n    def start(self):\n        return True\n",
            verification_status=VerificationStatus.VERIFIED,
            confidence=Decimal("1.00"),
            explanation="Main application entrypoint.",
        )
    ]

    return {
        "crit_arch_id": crit_arch_id,
        "crit_exec_id": crit_exec_id,
        "crit_usab_id": crit_usab_id,
        "rubric_crit": rubric_crit,
        "ev_id": ev_id,
        "evidence_records": evidence_records,
    }


def test_prototype_without_kubernetes_or_distributed_infra_not_penalized(calibration_test_setup):
    """
    1. A working prototype without Kubernetes or distributed infrastructure
       must not lose points solely for those omissions (Directive 6).
    """
    s = calibration_test_setup
    crit_id = s["crit_arch_id"]

    d = DeductionAttributionContract(
        criterion_id=crit_id,
        evidence_ids=[s["ev_id"]],
        issue_description="Submission lacks Kubernetes manifests and distributed scalability cluster configs",
        defect_severity=DefectSeverity.MODERATE,
        relevance_explanation="Not ready for enterprise cluster deployment.",
        is_primary_attribution=True,
        deduction_points=Decimal("2.00"),
        proportionality_rationale="Deduction for missing Kubernetes infrastructure.",
    )

    payload = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=s["evidence_records"],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Technical Complexity & Architecture",
                raw_score_before_deductions=Decimal("8.00"),
                deductions=[d],
                total_deductions=Decimal("2.00"),
                final_criterion_score=Decimal("6.00"),
                score_justification="Clean code but missing enterprise Kubernetes infrastructure.",
            ),
            CriterionAssessmentContract(
                criterion_id=s["crit_exec_id"],
                criterion_title="Execution & Completeness",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Solid execution.",
            ),
            CriterionAssessmentContract(
                criterion_id=s["crit_usab_id"],
                criterion_title="Potential Impact & Usability",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Clear README.",
            ),
        ],
        overall_quick_summary="Prototype evaluation.",
        overall_detailed_summary="Evaluated against rubric.",
    )

    with pytest.raises(AIEvaluationValidationError) as exc:
        validate_standardized_evaluation_output(payload, rubric_criteria=s["rubric_crit"])
    assert exc.value.error_code == "UNREQUESTED_INFRASTRUCTURE_DEDUCTION"
    assert "Kubernetes or distributed infrastructure" in str(exc.value)


def test_simple_architecture_not_penalized_for_not_using_microservices(calibration_test_setup):
    """
    2. A simple architecture must not be penalized merely for not using microservices (Directive 6).
    """
    s = calibration_test_setup
    crit_id = s["crit_arch_id"]

    d = DeductionAttributionContract(
        criterion_id=crit_id,
        evidence_ids=[s["ev_id"]],
        issue_description="Penalized for monolith instead of not using microservices architecture",
        defect_severity=DefectSeverity.MODERATE,
        relevance_explanation="Project is a clean monolith instead of microservices.",
        is_primary_attribution=True,
        deduction_points=Decimal("2.00"),
        proportionality_rationale="Did not implement microservices architecture.",
    )

    payload = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=s["evidence_records"],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Technical Complexity & Architecture",
                raw_score_before_deductions=Decimal("8.00"),
                deductions=[d],
                total_deductions=Decimal("2.00"),
                final_criterion_score=Decimal("6.00"),
                score_justification="Clean monolith architecture.",
            ),
            CriterionAssessmentContract(
                criterion_id=s["crit_exec_id"],
                criterion_title="Execution & Completeness",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Solid execution.",
            ),
            CriterionAssessmentContract(
                criterion_id=s["crit_usab_id"],
                criterion_title="Potential Impact & Usability",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Clear README.",
            ),
        ],
        overall_quick_summary="Architecture evaluation.",
        overall_detailed_summary="Evaluated architecture against rubric.",
    )

    with pytest.raises(AIEvaluationValidationError) as exc:
        validate_standardized_evaluation_output(payload, rubric_criteria=s["rubric_crit"])
    assert exc.value.error_code == "STACK_SIMPLICITY_DEDUCTION"
    assert "not using microservices" in str(exc.value)


def test_missing_cloud_deployment_manifests_not_penalized_unless_required(calibration_test_setup):
    """
    3. Missing cloud deployment manifests must not reduce scores unless required (Directive 6).
    """
    s = calibration_test_setup
    crit_id = s["crit_usab_id"]

    d = DeductionAttributionContract(
        criterion_id=crit_id,
        evidence_ids=[s["ev_id"]],
        issue_description="Lacks cloud deployment manifests and terraform deployment configs in repository",
        defect_severity=DefectSeverity.MINOR,
        relevance_explanation="No cloud deployment manifests provided in repo.",
        is_primary_attribution=True,
        deduction_points=Decimal("1.50"),
        proportionality_rationale="Omitted terraform and cloud manifests.",
    )

    payload = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=s["evidence_records"],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=s["crit_arch_id"],
                criterion_title="Technical Complexity & Architecture",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Clean architecture.",
            ),
            CriterionAssessmentContract(
                criterion_id=s["crit_exec_id"],
                criterion_title="Execution & Completeness",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Solid execution.",
            ),
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Potential Impact & Usability",
                raw_score_before_deductions=Decimal("8.00"),
                deductions=[d],
                total_deductions=Decimal("1.50"),
                final_criterion_score=Decimal("6.50"),
                score_justification="Good README but missing cloud deployment manifests.",
            ),
        ],
        overall_quick_summary="Usability evaluation.",
        overall_detailed_summary="Evaluated usability against rubric.",
    )

    # In unrequested scenario: must be rejected!
    with pytest.raises(AIEvaluationValidationError) as exc:
        validate_standardized_evaluation_output(payload, rubric_criteria=s["rubric_crit"])
    assert exc.value.error_code == "UNREQUESTED_DEPLOYMENT_DEDUCTION"

    # But if the rubric explicitly demands cloud deployment manifests: accepted!
    rubric_with_deployment = [
        dict(c) for c in s["rubric_crit"]
    ]
    rubric_with_deployment[2]["description"] = "Evaluates cloud deployment manifests and terraform infrastructure."
    # When explicitly mandated, it passes without error:
    val = validate_standardized_evaluation_output(payload, rubric_criteria=rubric_with_deployment)
    assert val is not None


def test_missing_live_integration_explicitly_required_affects_score(calibration_test_setup):
    """
    4. A missing live integration explicitly required by the problem statement must affect the relevant criterion.
    """
    s = calibration_test_setup
    crit_id = s["crit_exec_id"]

    req_stripe = RequirementContract(
        requirement_id="REQ_STRIPE_LIVE",
        title="Live Stripe Payment Gateway Integration",
        description="Must integrate directly with live Stripe API to process real payments.",
        requirement_type=RequirementType.MANDATORY,
        verification_status=VerificationStatus.CONTRADICTED,
        confidence=Decimal("1.00"),
        rationale="Stripe endpoints are completely stubbed with static mock dicts.",
    )

    d = DeductionAttributionContract(
        criterion_id=crit_id,
        evidence_ids=[s["ev_id"]],
        issue_description="Mandatory requirement REQ_STRIPE_LIVE was stubbed instead of implementing live integration",
        defect_severity=DefectSeverity.MAJOR,
        relevance_explanation="Required live payment processing was not implemented.",
        is_primary_attribution=True,
        deduction_points=Decimal("3.50"),
        proportionality_rationale="Core mandatory integration is a mock stub.",
        affected_requirement_id="REQ_STRIPE_LIVE",
    )

    payload = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=s["evidence_records"],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=s["crit_arch_id"],
                criterion_title="Technical Complexity & Architecture",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Clean architecture.",
            ),
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Execution & Completeness",
                raw_score_before_deductions=Decimal("8.00"),
                deductions=[d],
                total_deductions=Decimal("3.50"),
                final_criterion_score=Decimal("4.50"),
                requirement_coverage=[req_stripe],
                score_justification="Core structure runs, but required live Stripe payment integration is stubbed.",
            ),
            CriterionAssessmentContract(
                criterion_id=s["crit_usab_id"],
                criterion_title="Potential Impact & Usability",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Clear documentation.",
            ),
        ],
        overall_quick_summary="Execution evaluation with missing mandatory integration.",
        overall_detailed_summary="Evaluated against mandatory problem statement requirements.",
    )

    validated = validate_standardized_evaluation_output(payload, rubric_criteria=s["rubric_crit"])
    assert validated is not None
    assert validated.criterion_assessments[1].final_criterion_score == Decimal("4.50")
    assert validated.criterion_assessments[1].total_deductions == Decimal("3.50")


def test_optional_feature_must_not_attract_deduction(calibration_test_setup):
    """
    5. An optional feature must not attract a deduction (Directive 5 & EVAL_05).
    """
    s = calibration_test_setup
    crit_id = s["crit_arch_id"]

    req_opt = RequirementContract(
        requirement_id="OPT_AI_AUTOCOMPLETE",
        title="AI Autocomplete Feature",
        description="Optional bonus feature for autocomplete recommendations.",
        requirement_type=RequirementType.OPTIONAL,
        verification_status=VerificationStatus.NOT_AVAILABLE,
        confidence=Decimal("1.00"),
        rationale="Optional feature not attempted.",
    )

    d = DeductionAttributionContract(
        criterion_id=crit_id,
        evidence_ids=[s["ev_id"]],
        issue_description="Failed to implement optional bonus feature OPT_AI_AUTOCOMPLETE",
        defect_severity=DefectSeverity.MINOR,
        relevance_explanation="Optional feature missing.",
        is_primary_attribution=True,
        deduction_points=Decimal("1.00"),
        proportionality_rationale="Deduction for omitting optional bonus feature.",
        affected_requirement_id="OPT_AI_AUTOCOMPLETE",
    )

    payload = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=s["evidence_records"],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Technical Complexity & Architecture",
                raw_score_before_deductions=Decimal("8.00"),
                deductions=[d],
                total_deductions=Decimal("1.00"),
                final_criterion_score=Decimal("7.00"),
                requirement_coverage=[req_opt],
                score_justification="Good architecture but omitted optional AI autocomplete.",
            ),
            CriterionAssessmentContract(
                criterion_id=s["crit_exec_id"],
                criterion_title="Execution & Completeness",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Solid execution.",
            ),
            CriterionAssessmentContract(
                criterion_id=s["crit_usab_id"],
                criterion_title="Potential Impact & Usability",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Clear documentation.",
            ),
        ],
        overall_quick_summary="Evaluation with optional feature deduction attempt.",
        overall_detailed_summary="Evaluated against rubric.",
    )

    with pytest.raises(AIEvaluationValidationError) as exc:
        validate_standardized_evaluation_output(payload, rubric_criteria=s["rubric_crit"])
    assert exc.value.error_code == "OPTIONAL_REQUIREMENT_DEDUCTION"
    assert "OPT_AI_AUTOCOMPLETE" in str(exc.value)


def test_incomplete_mandatory_feature_identified_and_reflected(calibration_test_setup):
    """
    6. An incomplete mandatory feature must still be identified and appropriately reflected in scoring.
       A prototype label does NOT excuse missing mandatory functionality.
    """
    s = calibration_test_setup
    crit_id = s["crit_exec_id"]

    req_mandatory = RequirementContract(
        requirement_id="REQ_USER_AUTH",
        title="User Authentication & Session Management",
        description="Mandatory user sign-in and session verification.",
        requirement_type=RequirementType.MANDATORY,
        verification_status=VerificationStatus.CONTRADICTED,
        confidence=Decimal("1.00"),
        rationale="Auth token verification function always returns True without validating signatures.",
    )

    d = DeductionAttributionContract(
        criterion_id=crit_id,
        evidence_ids=[s["ev_id"]],
        issue_description="Mandatory user authentication verification is incomplete and insecure in REQ_USER_AUTH",
        defect_severity=DefectSeverity.MAJOR,
        relevance_explanation="Incomplete core security feature.",
        is_primary_attribution=True,
        deduction_points=Decimal("3.00"),
        proportionality_rationale="Core mandatory authentication is only a non-functional placeholder.",
        affected_requirement_id="REQ_USER_AUTH",
        impact_explanation="Allows unauthenticated bypass of mandatory session checks.",
    )

    payload = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=s["evidence_records"],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=s["crit_arch_id"],
                criterion_title="Technical Complexity & Architecture",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Clean structure.",
            ),
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Execution & Completeness",
                raw_score_before_deductions=Decimal("8.00"),
                deductions=[d],
                total_deductions=Decimal("3.00"),
                final_criterion_score=Decimal("5.00"),
                requirement_coverage=[req_mandatory],
                score_justification="Core structure runs, but mandatory authentication is incomplete.",
            ),
            CriterionAssessmentContract(
                criterion_id=s["crit_usab_id"],
                criterion_title="Potential Impact & Usability",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Clear documentation.",
            ),
        ],
        overall_quick_summary="Evaluation with incomplete mandatory feature.",
        overall_detailed_summary="Evaluated against rubric.",
    )

    validated = validate_standardized_evaluation_output(payload, rubric_criteria=s["rubric_crit"])
    assert validated is not None
    assert validated.criterion_assessments[1].final_criterion_score == Decimal("5.00")
    assert validated.criterion_assessments[1].total_deductions == Decimal("3.00")


def test_prototype_calibration_does_not_inflate_scores_or_override_anchors(calibration_test_setup):
    """
    7. Prototype calibration must not inflate scores or override criterion-specific anchors.
       Scores above maximum bounds [min_score, max_score] must be rejected.
    """
    s = calibration_test_setup
    crit_id = s["crit_arch_id"]

    # Attempting to award an inflated score of 12.00 on a [0.00, 10.00] criterion:
    payload = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=s["evidence_records"],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Technical Complexity & Architecture",
                raw_score_before_deductions=Decimal("12.00"),  # Inflated score!
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("12.00"),  # Inflated score!
                score_justification="Inflated score beyond rubric maximum.",
            ),
            CriterionAssessmentContract(
                criterion_id=s["crit_exec_id"],
                criterion_title="Execution & Completeness",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Solid execution.",
            ),
            CriterionAssessmentContract(
                criterion_id=s["crit_usab_id"],
                criterion_title="Potential Impact & Usability",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Clear documentation.",
            ),
        ],
        overall_quick_summary="Evaluation with inflated score.",
        overall_detailed_summary="Evaluated against rubric.",
    )

    with pytest.raises(AIEvaluationValidationError) as exc:
        validate_standardized_evaluation_output(payload, rubric_criteria=s["rubric_crit"])
    assert exc.value.error_code == "SCORE_OUT_OF_BOUNDS"
    assert "outside permissible bounds" in str(exc.value)


def test_prototype_calibration_directive_injected_into_pipeline_prompt(calibration_test_setup):
    """
    8. Verify that the prototype calibration directive is actively compiled and injected
       into the live prompt pipeline.
    """
    s = calibration_test_setup
    evidence_index = EvidenceIndex()

    prompt = compile_evaluation_prompt(
        rubric_criteria=s["rubric_crit"],
        evidence_index=evidence_index,
        submission_meta={"team_name": "Zenith AI Labs"},
        schema=get_standardized_evaluation_json_schema(),
    )

    # 1. Exact directive text presence
    assert "Calibrate raw baseline scores against hackathon prototype standards, not enterprise production systems" in prompt
    assert "Do NOT penalize prototypes for omitting distributed scalability, complex state management, or cloud deployment infrastructure" in prompt

    # 2. Key clarifying principles presence
    assert "Enterprise architecture" in prompt
    assert "Distributed systems and microservices are not automatically superior to simpler architectures" in prompt
    assert "Missing deployment infrastructure" in prompt
    assert "Missing live third-party integrations should only affect scores when those specific integrations are required" in prompt
    assert "A prototype label must not excuse missing mandatory functionality" in prompt
    assert "No Score Inflation" in prompt

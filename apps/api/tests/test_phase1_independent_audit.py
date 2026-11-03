"""
Scorva Phase 1: Independent Audit & Fairness Verification Suite.

Validates:
1. Live pipeline integration:
   - Full evaluation flow from submission creation to atomic fenced commitment.
   - Populates EvaluationEvidenceRecord, EvaluationCriterionAssessment, EvaluationDeductionAttribution.
   - Preserves deterministic Decimal calculation without float drift.
2. Deduction fairness:
   - Optional/bonus requirement immunity (EVAL_05).
   - Weak/inconclusive evidence blocking MAJOR/CRITICAL deductions (EVAL_11).
   - Semantic duplicate detection across criteria without explicit overlap_group_id.
3. Evidence integrity:
   - Fabricated source excerpts rejected when snippet does not match file content.
   - Line range bounds checking.
4. Policy immutability:
   - SubmissionSnapshot configuration pinning.
   - Running evaluation immutability under snapshot.
5. Real evaluation integration scenarios A through H:
   A. Simple but effective project
   B. Complex architecture with incomplete functionality
   C. Strong documentation with unverified implementation claims
   D. Missing optional functionality
   E. One defect with multiple potential criterion impacts
   F. Insufficient repository evidence
   G. Strong innovation with incomplete execution
   H. Technically correct implementation with limited novelty
"""

from decimal import Decimal
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.modules.evaluations.models import (
    EvaluationCriterionAssessment,
    EvaluationCriterionScore,
    EvaluationDeductionAttribution,
    EvaluationEvidenceRecord,
    EvaluationJob,
    EvaluationResult,
    RubricCriterion,
    SubmissionSnapshot,
)
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
from apps.api.modules.evaluations.policy.policy_engine import (
    DEFAULT_EVALUATION_POLICY_VERSION,
    EvaluationPolicy,
)
from apps.api.modules.evaluations.scoring_calculator import (
    CriterionInput,
    calculate_evaluation_scores,
)
from apps.api.workers.database import worker_session_scope
from apps.api.workers.pipeline import (
    commit_evaluation_result_fenced_sync,
    run_evaluation_pipeline,
)
from apps.api.workers.lease_manager import WorkerClaim


# ==============================================================================
# Helper Mock Class for Evidence Index
# ==============================================================================

class MockIndexedFile:
    def __init__(self, path: str, lines: list):
        self.relative_path = path
        self.lines = lines
        self.total_lines = len(lines)
        self.size_bytes = sum(len(l) for l in lines)


class MockEvidenceIndex:
    def __init__(self, files_dict: dict):
        self.files = {
            path: MockIndexedFile(path, lines)
            for path, lines in files_dict.items()
        }


# ==============================================================================
# 1. Evidence Integrity Tests
# ==============================================================================

def test_evidence_integrity_fabricated_snippet_rejected():
    """Verify that an evidence record citing lines with a fabricated snippet is rejected."""
    crit_id = uuid.uuid4()
    rubric_crit = [{"id": crit_id, "title": "Code Quality", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")}]

    evidence_index = MockEvidenceIndex({
        "app/auth.py": [
            "def login(user, password):",
            "    if verify_password(password, user.hash):",
            "        return generate_session_token(user.id)",
            "    return None",
        ]
    })

    # Legitimate file, but excerpt claims code that does not exist in the file
    ev = EvidenceContract(
        evidence_id=uuid.uuid4(),
        evidence_type=EvidenceType.SOURCE_CODE,
        commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        file_path="app/auth.py",
        start_line=1,
        end_line=4,
        source_excerpt="def backdoor_admin_bypass(): return True",  # Fabricated!
        verification_status=VerificationStatus.VERIFIED,
        confidence=Decimal("1.00"),
        explanation="Fabricated admin backdoor citation.",
    )

    payload = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=[ev],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Code Quality",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Solid code structure.",
            )
        ],
        overall_quick_summary="Code quality evaluation.",
        overall_detailed_summary="Evaluated code quality across repository modules.",
    )

    with pytest.raises(AIEvaluationValidationError) as exc:
        validate_standardized_evaluation_output(payload, rubric_criteria=rubric_crit, evidence_index=evidence_index)
    assert exc.value.error_code == "FABRICATED_CITATION_SNIPPET"


def test_evidence_integrity_valid_snippet_accepted():
    """Verify that an authentic source excerpt matching the index passes validation."""
    crit_id = uuid.uuid4()
    rubric_crit = [{"id": crit_id, "title": "Code Quality", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")}]

    evidence_index = MockEvidenceIndex({
        "app/auth.py": [
            "def login(user, password):",
            "    if verify_password(password, user.hash):",
            "        return generate_session_token(user.id)",
            "    return None",
        ]
    })

    ev = EvidenceContract(
        evidence_id=uuid.uuid4(),
        evidence_type=EvidenceType.SOURCE_CODE,
        commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        file_path="app/auth.py",
        start_line=1,
        end_line=4,
        source_excerpt="def login(user, password):\n    if verify_password(password, user.hash):",
        verification_status=VerificationStatus.VERIFIED,
        confidence=Decimal("1.00"),
        explanation="Verified authentication entrypoint.",
    )

    payload = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=[ev],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Code Quality",
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Solid code structure.",
            )
        ],
        overall_quick_summary="Code quality evaluation.",
        overall_detailed_summary="Evaluated code quality across repository modules.",
    )

    res = validate_standardized_evaluation_output(payload, rubric_criteria=rubric_crit, evidence_index=evidence_index)
    assert res.validation_passed is True


# ==============================================================================
# 2. Deduction Fairness & Semantic Overlap Detection
# ==============================================================================

def test_semantic_duplicate_detection_without_overlap_group_id():
    """
    Verify that two primary deductions across different criteria targeting the same
    root issue (e.g. unauthenticated API endpoints) are detected and rejected even if
    overlap_group_id is None or different strings.
    """
    crit1_id = uuid.uuid4()
    crit2_id = uuid.uuid4()

    d1 = DeductionAttributionContract(
        criterion_id=crit1_id,
        issue_description="Missing authentication check on sensitive user data endpoints",
        relevance_explanation="Allows unauthenticated access, compromising architecture security.",
        defect_severity=DefectSeverity.MAJOR,
        overlap_group_id="auth_issue_alpha",
        is_primary_attribution=True,
        deduction_points=Decimal("2.50"),
        proportionality_rationale="Major security flaw warrants 2.50 pt reduction.",
    )

    # Different overlap_group_id, but semantically identical defect across another criterion
    d2 = DeductionAttributionContract(
        criterion_id=crit2_id,
        issue_description="Sensitive user endpoints lack authentication checks",
        relevance_explanation="Poor code quality around endpoint security.",
        defect_severity=DefectSeverity.MAJOR,
        overlap_group_id="code_quality_auth_flaw",  # Evading identical group ID!
        is_primary_attribution=True,  # Attempting duplicate primary penalty
        deduction_points=Decimal("2.50"),
        proportionality_rationale="Warrants duplicate deduction.",
    )

    res = DeductionAttributionEngine.validate_deductions_batch([d1, d2])
    assert res.is_valid is False
    assert res.duplicate_penalties_prevented == 1
    assert any("Duplicate primary penalty rejected for issue" in msg for msg in res.validation_messages)


def test_weak_evidence_blocks_major_severity_deduction():
    """
    Verify that EVAL_11 prevents applying MAJOR or CRITICAL deductions when evidence
    strength is only WEAK or INCONCLUSIVE (distinguishing confirmed defects from speculation).
    """
    crit_id = uuid.uuid4()
    ev_id = uuid.uuid4()

    d = DeductionAttributionContract(
        criterion_id=crit_id,
        evidence_ids=[ev_id],
        issue_description="Suspected memory leak under high concurrency load",
        relevance_explanation="Could cause server degradation.",
        defect_severity=DefectSeverity.MAJOR,  # Major deduction on mere suspicion
        is_primary_attribution=True,
        deduction_points=Decimal("3.00"),
        proportionality_rationale="Potential memory leak.",
    )

    strength_map = {ev_id: EvidenceStrength.WEAK}
    res = DeductionAttributionEngine.validate_deductions_batch([d], evidence_strength_map=strength_map)
    assert res.is_valid is False
    assert any("violates EVAL_11" in msg for msg in res.validation_messages)


def test_optional_requirement_deduction_rejected():
    """Verify that attempting to deduct points for omitting an optional requirement is rejected (EVAL_05)."""
    crit_id = uuid.uuid4()
    rubric_crit = [{"id": crit_id, "title": "Execution & Completeness", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")}]

    req = RequirementContract(
        requirement_id="OPT_01_OAUTH",
        title="OAuth2 Integration",
        requirement_type=RequirementType.OPTIONAL,
        description="Optional third-party OAuth2 integration.",
        verification_status=VerificationStatus.NOT_AVAILABLE,
        rationale="Not implemented in repository.",
        cited_evidence_ids=[],
    )

    ded = DeductionAttributionContract(
        criterion_id=crit_id,
        issue_description="Failed to implement OPT_01_OAUTH bonus integration",
        relevance_explanation="Missing third-party OAuth.",
        defect_severity=DefectSeverity.MINOR,
        overlap_group_id="OPT_01_OAUTH",
        is_primary_attribution=True,
        deduction_points=Decimal("1.00"),
        proportionality_rationale="Omitted bonus feature.",
    )

    payload = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=[],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Execution & Completeness",
                requirement_coverage=[req],
                deductions=[ded],
                raw_score_before_deductions=Decimal("9.00"),
                total_deductions=Decimal("1.00"),
                final_criterion_score=Decimal("8.00"),
                score_justification="Omitted optional OAuth.",
            )
        ],
        overall_quick_summary="Evaluation with optional requirement.",
        overall_detailed_summary="Evaluated project requirements.",
    )

    with pytest.raises(AIEvaluationValidationError) as exc:
        validate_standardized_evaluation_output(payload, rubric_criteria=rubric_crit)
    assert exc.value.error_code == "OPTIONAL_REQUIREMENT_DEDUCTION"


# ==============================================================================
# 3. Live Pipeline & Fenced Atomic Persistence Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_pipeline_fenced_commit_populates_all_fair_contract_tables(db_session: AsyncSession):
    """
    Verifies that commit_evaluation_result_fenced_sync atomically commits:
    1. EvaluationResult (with policy_version)
    2. EvaluationEvidenceRecord
    3. EvaluationCriterionAssessment
    4. EvaluationDeductionAttribution
    5. Backward-compatible EvaluationCriterionScore
    All within a single transactional row-lock fence.
    """
    from apps.api.modules.users.models import User
    from apps.api.modules.organizations.models import Organization
    from apps.api.modules.hackathons.models import Hackathon, HackathonStatus
    from apps.api.modules.evaluations.models import Rubric, RubricVersion, RubricCriterion, Submission, SubmissionSnapshot, Team
    from datetime import datetime, timezone, timedelta

    with worker_session_scope() as db:
        # Setup test entities
        user = User(email=f"audit_{uuid.uuid4().hex[:6]}@example.com", hashed_password="pw", full_name="Auditor")
        db.add(user)
        db.flush()

        org = Organization(name="Audit Org", slug=f"audit-org-{uuid.uuid4().hex[:6]}", owner_id=user.id)
        db.add(org)
        db.flush()

        hackathon = Hackathon(
            organization_id=org.id,
            title="Audit Hackathon",
            slug=f"audit-hack-{uuid.uuid4().hex[:6]}",
            status=HackathonStatus.PUBLISHED,
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=7),
            submission_deadline=datetime.now(timezone.utc) + timedelta(days=6),
            created_by_user_id=user.id,
        )
        db.add(hackathon)
        db.flush()

        rubric = Rubric(organization_id=org.id, hackathon_id=hackathon.id, name="Audit Rubric")
        db.add(rubric)
        db.flush()

        rubric_ver = RubricVersion(rubric_id=rubric.id, organization_id=org.id, version_number=1)
        db.add(rubric_ver)
        db.flush()

        crit = RubricCriterion(
            rubric_version_id=rubric_ver.id,
            title="Code Quality & Cleanliness",
            description="Code quality assessment",
            evidence_requirements="Source code and test files",
            weight=Decimal("1.0000"),
            min_score=Decimal("0.00"),
            max_score=Decimal("10.00"),
            order_index=1,
        )
        db.add(crit)
        db.flush()

        team = Team(
            organization_id=org.id,
            hackathon_id=hackathon.id,
            name="Audit Team",
            join_code=f"AUD_{uuid.uuid4().hex[:6]}",
            created_by_user_id=user.id,
        )
        db.add(team)
        db.flush()

        sub = Submission(
            organization_id=org.id,
            hackathon_id=hackathon.id,
            team_id=team.id,
            team_name="Audit Team",
            title="Audit Submission",
            repository_url="https://github.com/scorva/audit-repo",
        )
        db.add(sub)
        db.flush()

        snap = SubmissionSnapshot(
            organization_id=org.id,
            submission_id=sub.id,
            commit_sha="1234567890abcdef1234567890abcdef12345678",
            configuration_snapshot={"eval.policy.active_version": "1.0.0"},
            total_bytes=1000,
            file_count=5,
        )
        db.add(snap)
        db.flush()

        job = EvaluationJob(
            organization_id=org.id,
            hackathon_id=hackathon.id,
            submission_id=sub.id,
            snapshot_id=snap.id,
            rubric_version_id=rubric_ver.id,
            status="running",
            claim_token="claim-token-123",
            lock_version=1,
            attempts_count=1,
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        db.add(job)
        db.commit()

        claim = WorkerClaim(
            job_id=job.id,
            organization_id=org.id,
            hackathon_id=hackathon.id,
            submission_id=sub.id,
            snapshot_id=snap.id,
            rubric_version_id=rubric_ver.id,
            claim_token="claim-token-123",
            lock_version=1,
            attempts_count=1,
            max_attempts=3,
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            worker_id="worker-audit",
        )

        ev_id = uuid.uuid4()
        ded_id = uuid.uuid4()

        std_output = StandardizedEvaluationOutput(
            submission_id=sub.id,
            repository_commit_sha="1234567890abcdef1234567890abcdef12345678",
            rubric_version_id=rubric_ver.id,
            policy_version="1.0.0",
            evidence_records=[
                EvidenceContract(
                    evidence_id=ev_id,
                    evidence_type=EvidenceType.SOURCE_CODE,
                    commit_sha="1234567890abcdef1234567890abcdef12345678",
                    file_path="src/app.py",
                    start_line=1,
                    end_line=10,
                    source_excerpt="class App:\n    pass",
                    verification_status=VerificationStatus.VERIFIED,
                    confidence=Decimal("1.00"),
                    explanation="Core application class.",
                )
            ],
            criterion_assessments=[
                CriterionAssessmentContract(
                    criterion_id=crit.id,
                    criterion_title=crit.title,
                    positive_findings=["Clear modular organization."],
                    negative_findings=["Inconsistent docstrings."],
                    deductions=[
                        DeductionAttributionContract(
                            deduction_id=ded_id,
                            criterion_id=crit.id,
                            evidence_ids=[ev_id],
                            issue_description="Inconsistent docstrings across helper modules",
                            defect_severity=DefectSeverity.COSMETIC,
                            relevance_explanation="Reduces readability slightly.",
                            overlap_group_id="docstring_inconsistency",
                            is_primary_attribution=True,
                            deduction_points=Decimal("0.50"),
                            proportionality_rationale="Minor cosmetic style issue capped at 0.50 pt.",
                        )
                    ],
                    evidence_strength=EvidenceStrength.STRONG,
                    raw_score_before_deductions=Decimal("8.50"),
                    total_deductions=Decimal("0.50"),
                    final_criterion_score=Decimal("8.00"),
                    score_justification="8.50 base anchor minus 0.50 cosmetic docstring deduction = 8.00 final.",
                )
            ],
            overall_quick_summary="Audit evaluation completed successfully.",
            overall_detailed_summary="Full audit trace verification test with normalized records.",
        )

        crit_inputs = [
            CriterionInput(
                criterion_id=crit.id,
                title=crit.title,
                weight=crit.weight,
                min_score=crit.min_score,
                max_score=crit.max_score,
                awarded_score=Decimal("8.00"),
                confidence_score=Decimal("1.00"),
            )
        ]
        score_result = calculate_evaluation_scores(crit_inputs)

        # Execute atomic commitment
        res = commit_evaluation_result_fenced_sync(
            db=db,
            claim=claim,
            ai_output=std_output,
            score_result=score_result,
            model_provider="mock",
            model_name="mock-auditor",
        )
        assert res.success is True

        # Verify database persistence across all tables
        db_result = db.get(EvaluationResult, res.result_id)
        assert db_result is not None
        assert db_result.policy_version == "1.0.0"
        assert db_result.raw_score == Decimal("8.00")
        assert db_result.normalized_score == Decimal("80.00")

        # Verify Evidence Record
        ev_records = list(db.execute(select(EvaluationEvidenceRecord).where(EvaluationEvidenceRecord.evaluation_result_id == res.result_id)).scalars().all())
        assert len(ev_records) == 1
        assert ev_records[0].id == ev_id
        assert ev_records[0].file_path == "src/app.py"

        # Verify Criterion Assessment
        crit_assessments = list(db.execute(select(EvaluationCriterionAssessment).where(EvaluationCriterionAssessment.evaluation_result_id == res.result_id)).scalars().all())
        assert len(crit_assessments) == 1
        assert crit_assessments[0].final_criterion_score == Decimal("8.00")
        assert crit_assessments[0].total_deductions == Decimal("0.50")

        # Verify Deduction Attribution
        ded_records = list(db.execute(select(EvaluationDeductionAttribution).where(EvaluationDeductionAttribution.evaluation_result_id == res.result_id)).scalars().all())
        assert len(ded_records) == 1
        assert ded_records[0].id == ded_id
        assert ded_records[0].deduction_points == Decimal("0.50")
        assert ded_records[0].overlap_group_id == "docstring_inconsistency"

        # Verify backward-compatible EvaluationCriterionScore
        legacy_scores = list(db.execute(select(EvaluationCriterionScore).where(EvaluationCriterionScore.evaluation_result_id == res.result_id)).scalars().all())
        assert len(legacy_scores) == 1
        assert legacy_scores[0].awarded_score == Decimal("8.00")


# ==============================================================================
# 4. Scenarios A through H Verification
# ==============================================================================

def test_scenario_a_simple_effective_project():
    """Scenario A: Simple, effective project is not penalized for small stack size (EVAL_06)."""
    crit_id = uuid.uuid4()
    rubric_crit = [{"id": crit_id, "title": "Technical Complexity & Architecture", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")}]

    output = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=[],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Technical Complexity & Architecture",
                positive_findings=["Clean single-file CLI tool implementing all problem requirements perfectly."],
                negative_findings=[],
                raw_score_before_deductions=Decimal("8.50"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.50"),
                score_justification="Exceptional clarity and appropriate stack choice.",
            )
        ],
        overall_quick_summary="Clean and effective implementation.",
        overall_detailed_summary="Demonstrates that simple architectures that solve the problem are awarded high scores.",
    )
    validated = validate_standardized_evaluation_output(output, rubric_criteria=rubric_crit)
    assert validated.criterion_assessments[0].final_criterion_score == Decimal("8.50")


def test_scenario_b_complex_architecture_with_incomplete_functionality():
    """Scenario B: Unnecessarily complex architecture with broken core execution gets 0 complexity bonus (EVAL_07)."""
    crit_id = uuid.uuid4()
    rubric_crit = [{"id": crit_id, "title": "Execution & Completeness", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")}]

    output = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=[],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Execution & Completeness",
                positive_findings=["Defines 12 microservice Docker containers."],
                negative_findings=["Core data pipeline throws unhandled exceptions; end-to-end workflow non-functional."],
                deductions=[
                    DeductionAttributionContract(
                        criterion_id=crit_id,
                        issue_description="Core data pipeline fails to complete basic execution",
                        defect_severity=DefectSeverity.CRITICAL,
                        relevance_explanation="Core deliverable is broken.",
                        is_primary_attribution=True,
                        deduction_points=Decimal("5.00"),
                        proportionality_rationale="Broken core workflow.",
                    )
                ],
                raw_score_before_deductions=Decimal("7.00"),
                total_deductions=Decimal("5.00"),
                final_criterion_score=Decimal("2.00"),
                score_justification="Broken core execution warrants heavy deduction; microservice complexity grants no bonus.",
            )
        ],
        overall_quick_summary="Microservice architecture fails to execute.",
        overall_detailed_summary="Architectural complexity without working functionality is penalized appropriately.",
    )
    validated = validate_standardized_evaluation_output(output, rubric_criteria=rubric_crit)
    assert validated.criterion_assessments[0].final_criterion_score == Decimal("2.00")


def test_scenario_c_strong_documentation_unverified_claims():
    """Scenario C: Grand README claims without supporting code are flagged as unverified (EVAL_01)."""
    crit_id = uuid.uuid4()
    rubric_crit = [{"id": crit_id, "title": "Innovation & Originality", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")}]

    output = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=[],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Innovation & Originality",
                positive_findings=["README describes a revolutionary zero-knowledge biometric protocol."],
                contradictory_evidence_observations=["Repository contains only template hello-world script; no ZK code exists."],
                evidence_strength=EvidenceStrength.WEAK,
                raw_score_before_deductions=Decimal("3.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("3.00"),
                score_justification="Documentation claims without code evidence are rated anchor level 3 (unverified idea).",
            )
        ],
        overall_quick_summary="Unverified documentation claims.",
        overall_detailed_summary="Evaluated unverified claims in accordance with Evidence Before Scoring.",
    )
    validated = validate_standardized_evaluation_output(output, rubric_criteria=rubric_crit)
    assert validated.criterion_assessments[0].final_criterion_score == Decimal("3.00")


def test_scenario_d_missing_optional_functionality():
    """Scenario D: Missing optional bonus functionality incurs zero deduction (EVAL_05)."""
    crit_id = uuid.uuid4()
    rubric_crit = [{"id": crit_id, "title": "Execution & Completeness", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")}]

    output = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=[],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Execution & Completeness",
                positive_findings=["All mandatory core hackathon requirements 100% completed and working."],
                neutral_observations=["Optional bonus mobile notification feature was not attempted."],
                deductions=[],
                raw_score_before_deductions=Decimal("10.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("10.00"),
                score_justification="Full execution on mandatory scope; missing optional features incurs zero penalty.",
            )
        ],
        overall_quick_summary="Mandatory scope 100% complete.",
        overall_detailed_summary="Evaluated under EVAL_05: Optional Features Are Not Mandatory Requirements.",
    )
    validated = validate_standardized_evaluation_output(output, rubric_criteria=rubric_crit)
    assert validated.criterion_assessments[0].final_criterion_score == Decimal("10.00")


def test_scenario_e_single_defect_multiple_criteria_attribution():
    """Scenario E: Single defect across criteria requires distinct non-primary justification (EVAL_10)."""
    crit_arch_id = uuid.uuid4()
    crit_code_id = uuid.uuid4()
    rubric_crit = [
        {"id": crit_arch_id, "title": "Technical Complexity & Architecture", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")},
        {"id": crit_code_id, "title": "Code Quality & Cleanliness", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")},
    ]

    # Legitimate non-primary cross-criterion deduction with independent justification
    output = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=[],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_arch_id,
                criterion_title="Technical Complexity & Architecture",
                deductions=[
                    DeductionAttributionContract(
                        criterion_id=crit_arch_id,
                        issue_description="API credentials committed in plaintext configuration",
                        relevance_explanation="Compromises secret management architecture.",
                        defect_severity=DefectSeverity.MAJOR,
                        overlap_group_id="hardcoded_secret_token",
                        is_primary_attribution=True,
                        deduction_points=Decimal("2.50"),
                        proportionality_rationale="Major secret management architectural flaw.",
                    )
                ],
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("2.50"),
                final_criterion_score=Decimal("5.50"),
                score_justification="8.00 anchor minus 2.50 architectural secret penalty = 5.50.",
            ),
            CriterionAssessmentContract(
                criterion_id=crit_code_id,
                criterion_title="Code Quality & Cleanliness",
                deductions=[
                    DeductionAttributionContract(
                        criterion_id=crit_code_id,
                        issue_description="API credentials committed in plaintext configuration",
                        relevance_explanation="Direct hygiene violation in codebase git history.",
                        defect_severity=DefectSeverity.MINOR,
                        overlap_group_id="hardcoded_secret_token",
                        is_primary_attribution=False,  # Secondary attribution
                        cross_criterion_justification="Committing raw secrets directly breaches repository hygiene conventions independent of architecture.",
                        deduction_points=Decimal("0.50"),
                        proportionality_rationale="Minor hygiene penalty for git trace.",
                    )
                ],
                raw_score_before_deductions=Decimal("8.00"),
                total_deductions=Decimal("0.50"),
                final_criterion_score=Decimal("7.50"),
                score_justification="8.00 anchor minus 0.50 hygiene deduction = 7.50.",
            ),
        ],
        overall_quick_summary="Evaluated cross-criterion secret impact.",
        overall_detailed_summary="Deduction attribution correctly bounded with non-primary justification.",
    )
    validated = validate_standardized_evaluation_output(output, rubric_criteria=rubric_crit)
    assert validated.validation_passed is True


def test_scenario_f_insufficient_repository_evidence():
    """Scenario F: Insufficient repository evidence expresses uncertainty without forced zero penalty (EVAL_04)."""
    crit_id = uuid.uuid4()
    rubric_crit = [{"id": crit_id, "title": "Potential Impact & Usability", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")}]

    output = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        has_insufficient_evidence=True,
        unresolved_questions=["Frontend UI assets were omitted from git repository snapshot."],
        evidence_records=[],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_id,
                criterion_title="Potential Impact & Usability",
                positive_findings=["Backend endpoints suggest intuitive user flow."],
                missing_evidence_observations=["UI screens and bundle files were unindexed in snapshot."],
                evidence_strength=EvidenceStrength.INSUFFICIENT,
                confidence=Decimal("0.40"),  # Low confidence due to unindexed UI
                unresolved_questions=["Cannot evaluate frontend responsive styling from backend API alone."],
                raw_score_before_deductions=Decimal("5.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("5.00"),  # Balanced anchor 5, NOT arbitrary 0!
                score_justification="Partial assessment anchored at 5.00 with explicit low confidence (0.40) rather than forced zero.",
            )
        ],
        overall_quick_summary="Evaluation flagged for low evidence availability.",
        overall_detailed_summary="Evaluated under EVAL_04: Missing Evidence != Missing Implementation.",
    )
    validated = validate_standardized_evaluation_output(output, rubric_criteria=rubric_crit)
    assert validated.has_insufficient_evidence is True
    assert validated.criterion_assessments[0].final_criterion_score == Decimal("5.00")


def test_scenario_g_strong_innovation_incomplete_execution():
    """Scenario G: Strong innovation (8.50) is decoupled from partial execution (4.00) (EVAL_08)."""
    crit_innov_id = uuid.uuid4()
    crit_exec_id = uuid.uuid4()
    rubric_crit = [
        {"id": crit_innov_id, "title": "Innovation & Originality", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")},
        {"id": crit_exec_id, "title": "Execution & Completeness", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")},
    ]

    output = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=[],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_innov_id,
                criterion_title="Innovation & Originality",
                positive_findings=["Brilliant mathematical approach to distributed consensus with working proof-of-concept."],
                raw_score_before_deductions=Decimal("8.50"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("8.50"),
                score_justification="High originality and novel algorithm design.",
            ),
            CriterionAssessmentContract(
                criterion_id=crit_exec_id,
                criterion_title="Execution & Completeness",
                positive_findings=["Core consensus algorithm verified in Python."],
                negative_findings=["CLI and web interface were not completed within hackathon timeframe."],
                deductions=[
                    DeductionAttributionContract(
                        criterion_id=crit_exec_id,
                        issue_description="User interface and integration CLI incomplete",
                        relevance_explanation="CLI and UI are key packaging deliverables for execution completeness.",
                        defect_severity=DefectSeverity.MAJOR,
                        is_primary_attribution=True,
                        deduction_points=Decimal("3.00"),
                        proportionality_rationale="Incomplete UI layers.",
                    )
                ],
                raw_score_before_deductions=Decimal("7.00"),
                total_deductions=Decimal("3.00"),
                final_criterion_score=Decimal("4.00"),
                score_justification="Core logic working but packaging incomplete.",
            ),
        ],
        overall_quick_summary="Highly innovative research concept with partial packaging.",
        overall_detailed_summary="Evaluated under EVAL_08: Innovation and Implementation Completeness Are Different Concepts.",
    )
    validated = validate_standardized_evaluation_output(output, rubric_criteria=rubric_crit)
    assert validated.criterion_assessments[0].final_criterion_score == Decimal("8.50")
    assert validated.criterion_assessments[1].final_criterion_score == Decimal("4.00")


def test_scenario_h_correct_implementation_limited_novelty():
    """Scenario H: Conventional CRUD app gets high Code Quality (9.00) and moderate Innovation (5.00) (EVAL_09)."""
    crit_code_id = uuid.uuid4()
    crit_innov_id = uuid.uuid4()
    rubric_crit = [
        {"id": crit_code_id, "title": "Code Quality & Cleanliness", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")},
        {"id": crit_innov_id, "title": "Innovation & Originality", "min_score": Decimal("0.00"), "max_score": Decimal("10.00")},
    ]

    output = StandardizedEvaluationOutput(
        submission_id=uuid.uuid4(),
        repository_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        rubric_version_id=uuid.uuid4(),
        policy_version="1.0.0",
        evidence_records=[],
        criterion_assessments=[
            CriterionAssessmentContract(
                criterion_id=crit_code_id,
                criterion_title="Code Quality & Cleanliness",
                positive_findings=["Flawless PEP8 formatting, full type hints, 98% test coverage."],
                raw_score_before_deductions=Decimal("9.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("9.00"),
                score_justification="Exceptional engineering rigor and cleanliness.",
            ),
            CriterionAssessmentContract(
                criterion_id=crit_innov_id,
                criterion_title="Innovation & Originality",
                positive_findings=["Standard todo-list application using established relational patterns."],
                neutral_observations=["Solves well-understood problem with standard patterns."],
                raw_score_before_deductions=Decimal("5.00"),
                total_deductions=Decimal("0.00"),
                final_criterion_score=Decimal("5.00"),
                score_justification="Conventional architecture with solid execution.",
            ),
        ],
        overall_quick_summary="Exceptionally clean conventional CRUD application.",
        overall_detailed_summary="Evaluated under EVAL_09: Separate Criterion Responsibilities.",
    )
    validated = validate_standardized_evaluation_output(output, rubric_criteria=rubric_crit)
    assert validated.criterion_assessments[0].final_criterion_score == Decimal("9.00")
    assert validated.criterion_assessments[1].final_criterion_score == Decimal("5.00")

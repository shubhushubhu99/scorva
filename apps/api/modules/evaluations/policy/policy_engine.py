"""
Scorva Centralized Evaluation Policy Engine.

Enforces versioned, immutable evaluation principles, hooks into the platform
configuration catalog, and verifies evaluations against fairness invariants.
"""

from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from apps.api.modules.configuration.catalog import CONFIGURATION_CATALOG, SettingDefinition
from apps.api.modules.evaluations.policy.contracts import (
    CriterionAssessmentContract,
    EvidenceContract,
    RequirementContract,
    RequirementType,
    StandardizedEvaluationOutput,
    VerificationStatus,
)
from apps.api.modules.evaluations.policy.deduction_engine import DeductionAttributionEngine

logger = logging.getLogger("scorva.evaluation_policy")

DEFAULT_EVALUATION_POLICY_VERSION = "1.0.0"


# ==============================================================================
# Dynamic Configuration Registration (Integrated into Scorva Catalog)
# ==============================================================================

FAIR_EVALUATION_SETTINGS = [
    SettingDefinition(
        key="eval.policy.active_version",
        tier="tier_2",
        data_type="string",
        default_value="1.0.0",
        allow_org_override=True,
        allow_hackathon_override=True,
        min_value=None,
        max_value=None,
        is_configurable=True,
        effect_timing="next_job",
        description="Active version of Scorva Fair Evaluation Policy",
    ),
    SettingDefinition(
        key="eval.policy.prevent_duplicate_deductions",
        tier="tier_2",
        data_type="bool",
        default_value="true",
        allow_org_override=True,
        allow_hackathon_override=True,
        min_value=None,
        max_value=None,
        is_configurable=True,
        effect_timing="next_job",
        description="Strictly prevent deducting points on multiple criteria for the same root defect without explicit justification",
    ),
    SettingDefinition(
        key="eval.policy.prohibit_stack_size_bias",
        tier="tier_2",
        data_type="bool",
        default_value="true",
        allow_org_override=False,
        allow_hackathon_override=False,
        min_value=None,
        max_value=None,
        is_configurable=True,
        effect_timing="immediate",
        description="Forbid models from penalizing clean, effective projects merely for using a small, simple technology stack",
    ),
    SettingDefinition(
        key="eval.policy.penalize_missing_optional_requirements",
        tier="tier_2",
        data_type="bool",
        default_value="false",
        allow_org_override=False,
        allow_hackathon_override=False,
        min_value=None,
        max_value=None,
        is_configurable=True,
        effect_timing="immediate",
        description="Forbid deductions when an optional or bonus requirement was not implemented",
    ),
]

# Ensure settings are present in CONFIGURATION_CATALOG without duplicating
_existing_keys = {s.key for s in CONFIGURATION_CATALOG}
for _setting in FAIR_EVALUATION_SETTINGS:
    if _setting.key not in _existing_keys:
        CONFIGURATION_CATALOG.append(_setting)
        _existing_keys.add(_setting.key)


# ==============================================================================
# Evaluation Policy Definition
# ==============================================================================

class EvaluationPolicyRule(BaseModel):
    """An immutable, versioned evaluation principle."""
    rule_id: str
    title: str
    description: str
    is_mandatory: bool = True


class EvaluationPolicy(BaseModel):
    """
    Versioned Scorva Fair Evaluation Policy.
    Codifies all 13 core evaluation principles into an enforceable governance engine.
    """
    model_config = ConfigDict(extra="forbid")

    version: str = DEFAULT_EVALUATION_POLICY_VERSION
    name: str = "Scorva Fair Evaluation Policy"
    description: str = "Governs objective, evidence-grounded, non-overlapping hackathon evaluation."
    rules: List[EvaluationPolicyRule] = Field(default_factory=list)

    @classmethod
    def get_default_policy(cls) -> "EvaluationPolicy":
        """Constructs the standard v1.0.0 Fair Evaluation Policy."""
        return cls(
            version="1.0.0",
            name="Scorva Fair Evaluation Policy (v1.0.0)",
            description="Authoritative, evidence-backed evaluation standard establishing fairness contracts.",
            rules=[
                EvaluationPolicyRule(
                    rule_id="EVAL_01_EVIDENCE_BEFORE_SCORING",
                    title="Evidence Before Scoring",
                    description="Every score and deduction must be grounded in captured repository evidence.",
                ),
                EvaluationPolicyRule(
                    rule_id="EVAL_02_RUBRIC_SUPREMACY",
                    title="Evaluate Against the Official Rubric",
                    description="Assessments must adhere strictly to the frozen criteria and weights of the hackathon rubric.",
                ),
                EvaluationPolicyRule(
                    rule_id="EVAL_03_RESPECT_PROBLEM_STATEMENT",
                    title="Respect the Actual Problem Statement",
                    description="Teams may only be judged on requirements specified in the problem statement, not invented expectations.",
                ),
                EvaluationPolicyRule(
                    rule_id="EVAL_04_MISSING_EVIDENCE_NOT_MISSING_CODE",
                    title="Missing Evidence != Missing Implementation",
                    description="If evidence was unindexed, truncated, or unavailable, flag uncertainty; do not force zero points.",
                ),
                EvaluationPolicyRule(
                    rule_id="EVAL_05_OPTIONAL_NOT_MANDATORY",
                    title="Optional Features Are Not Mandatory Requirements",
                    description="Failure to implement optional or bonus features must never result in score deductions.",
                ),
                EvaluationPolicyRule(
                    rule_id="EVAL_06_STACK_SIZE_NEUTRALITY",
                    title="Technology-Stack Size Does Not Determine Quality",
                    description="A clean, simple stack that solves the problem exceptionally must not be penalized for simplicity.",
                ),
                EvaluationPolicyRule(
                    rule_id="EVAL_07_COMPLEXITY_NOT_AUTOMATIC_POINTS",
                    title="Architectural Complexity Does Not Automatically Deserve More Points",
                    description="Over-engineered, broken complexity must receive lower marks than clean, working simplicity.",
                ),
                EvaluationPolicyRule(
                    rule_id="EVAL_08_SEPARATE_INNOVATION_AND_COMPLETENESS",
                    title="Separate Innovation from Implementation Completeness",
                    description="A novel idea remains innovative even if early in implementation; separate novelty from execution.",
                ),
                EvaluationPolicyRule(
                    rule_id="EVAL_09_SEPARATE_CRITERION_RESPONSIBILITIES",
                    title="Separate Criterion Responsibilities",
                    description="Code quality, architecture, completeness, innovation, and impact measure distinct orthogonal qualities.",
                ),
                EvaluationPolicyRule(
                    rule_id="EVAL_10_AVOID_DUPLICATE_PENALTIES",
                    title="Avoid Duplicate Penalties Across Criteria",
                    description="The same root defect must not generate multiple deductions unless distinct, independent justification is provided.",
                ),
                EvaluationPolicyRule(
                    rule_id="EVAL_11_DISTINGUISH_DEFECTS_FROM_RISKS",
                    title="Distinguish Confirmed Defects from Potential Risks",
                    description="A proven bug is a deduction; a theoretical risk or advisory note is feedback, not a raw score penalty.",
                ),
                EvaluationPolicyRule(
                    rule_id="EVAL_12_EXPLICIT_UNCERTAINTY",
                    title="Communicate Uncertainty Explicitly",
                    description="When evidence is insufficient or conflicting, communicate confidence intervals rather than inventing justifications.",
                ),
                EvaluationPolicyRule(
                    rule_id="EVAL_13_AI_ADVISORY_SEPARATION",
                    title="AI Recommendations Remain Separate from Final Decisions",
                    description="Automated AI models advise; human judges retain final authority to adjust scores and submit final reviews.",
                ),
            ],
        )

    def validate_evaluation_fairness(
        self,
        output: StandardizedEvaluationOutput,
        problem_requirements: Optional[List[RequirementContract]] = None,
    ) -> List[str]:
        """
        Validates an evaluation output against the policy rules.
        Returns a list of violations (empty list = passed).
        """
        violations: List[str] = []

        # 1. Check deduction anti-duplicate rules
        all_deductions = []
        for ca in output.criterion_assessments:
            all_deductions.extend(ca.deductions)

        known_eids = {e.evidence_id for e in output.evidence_records}
        ded_res = DeductionAttributionEngine.validate_deductions_batch(
            all_deductions,
            known_evidence_ids=known_eids if known_eids else None,
        )
        if not ded_res.is_valid:
            violations.extend(ded_res.validation_messages)

        # 2. Check for deductions on optional requirements (Rule EVAL_05)
        for ca in output.criterion_assessments:
            for req in ca.requirement_coverage:
                if req.requirement_type == RequirementType.OPTIONAL:
                    if req.verification_status in (VerificationStatus.UNVERIFIED, VerificationStatus.NOT_AVAILABLE):
                        # Verify no deductions cite this optional requirement
                        for d in ca.deductions:
                            if req.requirement_id.lower() in d.issue_description.lower():
                                violations.append(
                                    f"Policy Violation (EVAL_05): Criterion '{ca.criterion_title}' deducted "
                                    f"points for missing optional feature '{req.title}'."
                                )

        # 3. Check for ungrounded zero scores due to missing evidence (Rule EVAL_04)
        for ca in output.criterion_assessments:
            if ca.evidence_strength == "INSUFFICIENT" or any(
                "missing" in m.lower() for m in ca.missing_evidence_observations
            ):
                if ca.final_criterion_score == Decimal("0.00") and not ca.deductions and not ca.negative_findings:
                    violations.append(
                        f"Policy Violation (EVAL_04): Criterion '{ca.criterion_title}' was penalized to 0.00 "
                        f"merely due to missing evidence, without proven absence of implementation."
                    )

        return violations


def get_active_evaluation_policy() -> EvaluationPolicy:
    """Returns the currently active evaluation policy."""
    return EvaluationPolicy.get_default_policy()

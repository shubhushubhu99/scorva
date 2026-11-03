"""
Scorva Fair Evaluation Foundation & Scoring Contracts Module.
Implements Phase 1 versioned policy, criteria frameworks, evidence contracts,
and deduction attribution mechanics.
"""

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
    CriterionFramework,
    get_all_standard_criteria_frameworks,
    get_criterion_framework,
)
from apps.api.modules.evaluations.policy.deduction_engine import (
    DeductionAttributionEngine,
    DeductionValidationResult,
)
from apps.api.modules.evaluations.policy.policy_engine import (
    DEFAULT_EVALUATION_POLICY_VERSION,
    EvaluationPolicy,
    get_active_evaluation_policy,
)

__all__ = [
    "CriterionAssessmentContract",
    "CriterionFramework",
    "DeductionAttributionContract",
    "DeductionAttributionEngine",
    "DeductionValidationResult",
    "DEFAULT_EVALUATION_POLICY_VERSION",
    "DefectSeverity",
    "EvaluationPolicy",
    "EvidenceContract",
    "EvidenceStrength",
    "EvidenceType",
    "RequirementContract",
    "RequirementType",
    "StandardizedEvaluationOutput",
    "VerificationStatus",
    "get_active_evaluation_policy",
    "get_all_standard_criteria_frameworks",
    "get_criterion_framework",
]

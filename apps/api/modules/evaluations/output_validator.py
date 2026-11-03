"""
Scorva Structured Output Validator & Schema Verification Engine.

Enforces strict Pydantic schema validation, rubric criterion completeness,
numerical score bounds, line-level citation verification, and bounded retry
mechanisms for AI-generated evaluations.
"""

from decimal import Decimal
import json
import logging
import math
import re
from typing import Any, Dict, List, Literal, Optional, Set, Union
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.api.modules.evaluations.ai_provider import (
    AIProviderClient,
    AIProviderConfigError,
    AIProviderConnectionError,
    AIProviderError,
    AIProviderFormatError,
    AIProviderResponseSizeError,
    AIProviderSSRFError,
    AIProviderTimeoutError,
)

from apps.api.modules.evaluations.policy.contracts import (
    CriterionAssessmentContract,
    DeductionAttributionContract,
    EvidenceContract,
    RequirementType,
    StandardizedEvaluationOutput,
)
from apps.api.modules.evaluations.policy.deduction_engine import DeductionAttributionEngine
from apps.api.modules.evaluations.policy.policy_engine import get_active_evaluation_policy

logger = logging.getLogger("scorva.output_validator")


# ==============================================================================
# Validation Error Definitions
# ==============================================================================

class AIEvaluationValidationError(Exception):
    """
    Raised when AI model output violates schema, rubric criteria,
    numerical bounds, or verifiable evidence citations.
    """
    def __init__(self, error_code: str, details: str, retryable: bool = True):
        super().__init__(f"[{error_code}] {details}")
        self.error_code = error_code
        self.details = details
        self.retryable = retryable


# ==============================================================================
# Pydantic Schemas for AI Output
# ==============================================================================

class AIEvidenceReferencePayload(BaseModel):
    """Line-level citation grounding an awarded score in repository evidence."""
    file_path: str = Field(..., min_length=1, max_length=500)
    start_line: Optional[int] = Field(None, ge=1)
    end_line: Optional[int] = Field(None, ge=1)
    snippet: str = Field(..., min_length=1, max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_line_range(self) -> "AIEvidenceReferencePayload":
        if self.start_line is not None and self.end_line is not None:
            if self.start_line > self.end_line:
                raise ValueError(
                    f"start_line ({self.start_line}) cannot be greater than end_line ({self.end_line})."
                )
        return self


def parse_explanations(text: Optional[str]) -> tuple[str, str]:
    """
    Parses an explanation or rationale into a tuple of:
    (quick_explanation, detailed_explanation).
    
    Extracts explicitly labeled sections if present, or cleanly derives:
    - quick_explanation: 1-2 short sentences (plain, simple summary).
    - detailed_explanation: full comprehensive text.
    """
    if not text or not str(text).strip():
        return ("", "")
    
    clean_text = str(text).strip()
    
    # 1. Match explicit headers like "Quick Summary:", "Quick Explanation:", "Quick Take:", etc.
    q_match = re.search(
        r"(?:^|\n)\s*(?:\*\*)?(?:Quick (?:Summary|Explanation|Take)|Brief Summary):\s*(?:\*\*)?\s*(.*?)(?=\n\s*(?:\*\*)?(?:Detailed|Deep|Full (?:Breakdown|Analysis|Explanation))|\Z)",
        clean_text,
        re.DOTALL | re.IGNORECASE,
    )
    d_match = re.search(
        r"(?:^|\n)\s*(?:\*\*)?(?:Detailed|Deep|Full) (?:Breakdown|Analysis|Explanation):\s*(?:\*\*)?\s*(.*)",
        clean_text,
        re.DOTALL | re.IGNORECASE,
    )
    
    if q_match and d_match:
        quick = q_match.group(1).strip()
        detailed = d_match.group(1).strip()
        if quick and detailed:
            return (quick, detailed)
            
    # 2. If no distinct headers, split by sentence to create quick small summary and deep detailed explanation
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_text) if s.strip()]
    if len(sentences) > 1:
        quick = sentences[0]
        if len(quick) < 50 and len(sentences) > 2:
            quick = f"{sentences[0]} {sentences[1]}"
        return (quick, clean_text)
    
    return (clean_text, clean_text)


class AICriterionScorePayload(BaseModel):
    """Criterion evaluation awarded by the model with dual quick and detailed explanations."""
    criterion_id: uuid.UUID
    awarded_score: Decimal
    confidence_score: Decimal = Field(default=Decimal("1.00"), ge=Decimal("0.00"), le=Decimal("1.00"))
    quick_explanation: Optional[str] = Field(None, min_length=5, description="Brief 1-2 sentence explanation in simple everyday words without technical jargon.")
    detailed_explanation: Optional[str] = Field(None, min_length=10, description="Deep, thorough explanation in simple, clear words explaining what was verified, strengths, and missing elements.")
    rationale: Optional[str] = Field(None, min_length=10)
    evidence_status: Literal["verified", "partial", "missing"]
    evidence_references: List[AIEvidenceReferencePayload] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("awarded_score", "confidence_score", mode="before")
    @classmethod
    def validate_finite_decimal(cls, v: Any) -> Decimal:
        if v is None:
            raise ValueError("Score value cannot be None.")
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            raise ValueError(f"Score cannot be NaN or Infinity, got {v}")
        try:
            d = Decimal(str(v))
        except Exception as exc:
            raise ValueError(f"Invalid decimal value: {v}") from exc
        if not d.is_finite():
            raise ValueError(f"Score cannot be non-finite decimal: {d}")
        return d

    @model_validator(mode="after")
    def populate_and_normalize_explanations(self) -> "AICriterionScorePayload":
        # If rationale is missing, synthesize from quick and detailed explanations
        if not self.rationale or not self.rationale.strip():
            if self.quick_explanation and self.detailed_explanation:
                self.rationale = (
                    f"Quick Summary:\n{self.quick_explanation.strip()}\n\n"
                    f"Detailed Breakdown:\n{self.detailed_explanation.strip()}"
                )
            elif self.detailed_explanation:
                self.rationale = self.detailed_explanation.strip()
            elif self.quick_explanation:
                self.rationale = self.quick_explanation.strip()
            else:
                raise ValueError("Criterion evaluation must include rationale or quick_explanation/detailed_explanation.")
        
        # If quick_explanation or detailed_explanation are missing, extract from rationale
        if not self.quick_explanation or not self.detailed_explanation:
            q_parsed, d_parsed = parse_explanations(self.rationale)
            if not self.quick_explanation:
                self.quick_explanation = q_parsed
            if not self.detailed_explanation:
                self.detailed_explanation = d_parsed

        return self


class AIEvaluationOutputPayload(BaseModel):
    """
    Authoritative structured output schema produced by AI evaluation models.
    Strictly forbids extra fields, enforces criterion presence and non-empty summaries.
    Provides dual-level explanations: quick small summary and deep detailed breakdown.
    """
    quick_summary: Optional[str] = Field(None, min_length=5, description="Short 1-2 sentence overview in plain everyday words without jargon.")
    detailed_summary: Optional[str] = Field(None, min_length=10, description="Deep, thorough technical breakdown in simple, clear words.")
    summary_assessment: Optional[str] = Field(None, min_length=10)
    has_insufficient_evidence: bool = False
    criterion_scores: List[AICriterionScorePayload] = Field(..., min_length=1)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def populate_and_normalize_summaries(self) -> "AIEvaluationOutputPayload":
        # If summary_assessment is missing, synthesize from quick and detailed summaries
        if not self.summary_assessment or not self.summary_assessment.strip():
            if self.quick_summary and self.detailed_summary:
                self.summary_assessment = (
                    f"Quick Summary:\n{self.quick_summary.strip()}\n\n"
                    f"Detailed Breakdown:\n{self.detailed_summary.strip()}"
                )
            elif self.detailed_summary:
                self.summary_assessment = self.detailed_summary.strip()
            elif self.quick_summary:
                self.summary_assessment = self.quick_summary.strip()
            else:
                raise ValueError("Evaluation must include summary_assessment or quick_summary/detailed_summary.")

        # If quick_summary or detailed_summary are missing, extract from summary_assessment
        if not self.quick_summary or not self.detailed_summary:
            q_parsed, d_parsed = parse_explanations(self.summary_assessment)
            if not self.quick_summary:
                self.quick_summary = q_parsed
            if not self.detailed_summary:
                self.detailed_summary = d_parsed

        return self


# ==============================================================================
# Pure Validation Functions
# ==============================================================================

def validate_ai_evaluation_output(
    raw_output: Union[str, Dict[str, Any]],
    rubric_criteria: List[Any],
    evidence_index: Optional[Any] = None,
) -> AIEvaluationOutputPayload:
    """
    Validates model output against:
    1. Structural Pydantic JSON Schema (rejects extra/missing/invalid fields).
    2. Criterion completeness and uniqueness (every criterion present, no duplicates, no unknown).
    3. Numerical score bounds ([min_score, max_score]).
    4. Missing evidence rule (missing evidence must receive min_score).
    5. Evidence citation existence (cited files and line ranges must exist in evidence index).
    """
    # 1. Parse JSON if string
    if isinstance(raw_output, str):
        try:
            data = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise AIEvaluationValidationError(
                "MALFORMED_JSON",
                f"Failed to parse raw output as JSON: {exc}",
                retryable=True,
            ) from exc
    elif isinstance(raw_output, dict):
        data = raw_output
    else:
        raise AIEvaluationValidationError(
            "INVALID_PAYLOAD_TYPE",
            f"Expected dict or JSON string, got {type(raw_output).__name__}",
            retryable=False,
        )

    # 2. Pydantic schema validation
    try:
        payload = AIEvaluationOutputPayload.model_validate(data)
    except Exception as exc:
        raise AIEvaluationValidationError(
            "SCHEMA_VALIDATION_ERROR",
            f"Model output violates Pydantic schema: {exc}",
            retryable=True,
        ) from exc

    # 3. Rubric Criterion Completeness & Uniqueness
    expected_map: Dict[uuid.UUID, Any] = {}
    for crit in rubric_criteria:
        crit_id_raw = getattr(crit, "id", None) or (crit.get("id") if isinstance(crit, dict) else None)
        crit_uuid = uuid.UUID(str(crit_id_raw))
        expected_map[crit_uuid] = crit

    expected_ids: Set[uuid.UUID] = set(expected_map.keys())
    reported_ids = [cs.criterion_id for cs in payload.criterion_scores]

    # Check for duplicate criteria
    if len(reported_ids) != len(set(reported_ids)):
        duplicates = [uid for uid in reported_ids if reported_ids.count(uid) > 1]
        raise AIEvaluationValidationError(
            "DUPLICATE_CRITERIA_DETECTED",
            f"Model output contains duplicate criterion IDs: {set(duplicates)}",
            retryable=True,
        )

    # Check for unknown criteria
    unknown_ids = set(reported_ids) - expected_ids
    if unknown_ids:
        raise AIEvaluationValidationError(
            "UNKNOWN_CRITERIA_DETECTED",
            f"Model output contains unknown criterion IDs not present in rubric: {unknown_ids}",
            retryable=True,
        )

    # Check for missing criteria
    missing_ids = expected_ids - set(reported_ids)
    if missing_ids:
        raise AIEvaluationValidationError(
            "MISSING_CRITERIA_DETECTED",
            f"Model output omitted required rubric criteria: {missing_ids}",
            retryable=True,
        )

    # 4. Numerical Score Bounds & Missing Evidence Rule
    has_missing_evidence = False

    for cs in payload.criterion_scores:
        crit = expected_map[cs.criterion_id]
        min_score = Decimal(str(getattr(crit, "min_score", None) or (crit.get("min_score") if isinstance(crit, dict) else Decimal("0.00"))))
        max_score = Decimal(str(getattr(crit, "max_score", None) or (crit.get("max_score") if isinstance(crit, dict) else Decimal("10.00"))))

        # Check score bounds
        if cs.awarded_score < min_score or cs.awarded_score > max_score:
            raise AIEvaluationValidationError(
                "SCORE_OUT_OF_BOUNDS",
                f"Awarded score {cs.awarded_score} is outside permissible bounds [{min_score}, {max_score}] for criterion {cs.criterion_id}.",
                retryable=True,
            )

        # Missing evidence rule
        if cs.evidence_status == "missing":
            has_missing_evidence = True
            if cs.awarded_score != min_score:
                raise AIEvaluationValidationError(
                    "MISSING_EVIDENCE_SCORE_MISMATCH",
                    f"Criterion {cs.criterion_id} has 'missing' evidence status but was awarded {cs.awarded_score} instead of min_score {min_score}.",
                    retryable=True,
                )

        # 5. Evidence Citation Verification
        if evidence_index and hasattr(evidence_index, "files") and evidence_index.files:
            for ref in cs.evidence_references:
                norm_path = ref.file_path.replace("\\", "/").strip().lstrip("/")
                if norm_path not in evidence_index.files and ref.file_path not in evidence_index.files:
                    raise AIEvaluationValidationError(
                        "FABRICATED_CITATION_FILE",
                        f"Cited file '{ref.file_path}' does not exist in repository evidence index.",
                        retryable=True,
                    )

                indexed_file = evidence_index.files.get(norm_path) or evidence_index.files.get(ref.file_path)
                if indexed_file and ref.end_line is not None:
                    if ref.end_line > indexed_file.total_lines:
                        raise AIEvaluationValidationError(
                            "INVALID_CITATION_LINE_RANGE",
                            f"Cited end_line {ref.end_line} exceeds total lines ({indexed_file.total_lines}) in file '{ref.file_path}'.",
                            retryable=True,
                        )

    if has_missing_evidence and not payload.has_insufficient_evidence:
        payload.has_insufficient_evidence = True

    return payload


def validate_standardized_evaluation_output(
    raw_output: Union[str, Dict[str, Any], StandardizedEvaluationOutput],
    rubric_criteria: List[Any],
    evidence_index: Optional[Any] = None,
) -> StandardizedEvaluationOutput:
    """
    Validates a Phase 1 StandardizedEvaluationOutput against:
    1. Schema conformance (rejects extra/missing fields).
    2. Rubric criterion completeness & uniqueness (all criteria must be present).
    3. Numerical score boundaries ([min_score, max_score] per criterion).
    4. Evidence validity (file existence, non-negative line spans, line limits).
    5. Deduction attribution rules (anti-duplicate penalties, proportionality, severity limits).
    6. Policy fairness rules (EVAL_01 through EVAL_13).
    """
    # 1. Parse into StandardizedEvaluationOutput
    def _normalize_dict_floats(obj: Any) -> Any:
        if isinstance(obj, float):
            return Decimal(str(obj))
        if isinstance(obj, dict):
            return {k: _normalize_dict_floats(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_normalize_dict_floats(v) for v in obj]
        return obj

    if isinstance(raw_output, StandardizedEvaluationOutput):
        payload = raw_output
    elif isinstance(raw_output, str):
        try:
            data = json.loads(raw_output, parse_float=Decimal)
            payload = StandardizedEvaluationOutput.model_validate(data)
        except Exception as exc:
            raise AIEvaluationValidationError(
                "MALFORMED_STANDARDIZED_OUTPUT",
                f"Failed to parse standardized evaluation output: {exc}",
                retryable=True,
            ) from exc
    elif isinstance(raw_output, dict):
        try:
            normalized_dict = _normalize_dict_floats(raw_output)
            payload = StandardizedEvaluationOutput.model_validate(normalized_dict)
        except Exception as exc:
            raise AIEvaluationValidationError(
                "SCHEMA_VALIDATION_ERROR",
                f"Standardized evaluation output violates Pydantic schema: {exc}",
                retryable=True,
            ) from exc
    else:
        raise AIEvaluationValidationError(
            "INVALID_PAYLOAD_TYPE",
            f"Expected dict, str, or StandardizedEvaluationOutput, got {type(raw_output).__name__}",
            retryable=False,
        )

    # 2. Rubric Criteria Completeness & Uniqueness
    expected_map: Dict[uuid.UUID, Any] = {}
    for crit in rubric_criteria:
        crit_id_raw = getattr(crit, "id", None) or (crit.get("id") if isinstance(crit, dict) else None)
        crit_uuid = uuid.UUID(str(crit_id_raw))
        expected_map[crit_uuid] = crit

    expected_ids: Set[uuid.UUID] = set(expected_map.keys())
    reported_ids = [ca.criterion_id for ca in payload.criterion_assessments]

    if len(reported_ids) != len(set(reported_ids)):
        duplicates = [uid for uid in reported_ids if reported_ids.count(uid) > 1]
        raise AIEvaluationValidationError(
            "DUPLICATE_CRITERIA_DETECTED",
            f"Evaluation output contains duplicate criterion assessments for: {set(duplicates)}",
            retryable=True,
        )

    unknown_ids = set(reported_ids) - expected_ids
    if unknown_ids:
        raise AIEvaluationValidationError(
            "UNKNOWN_CRITERIA_DETECTED",
            f"Evaluation output contains unknown criterion IDs: {unknown_ids}",
            retryable=True,
        )

    missing_ids = expected_ids - set(reported_ids)
    if missing_ids:
        raise AIEvaluationValidationError(
            "MISSING_CRITERIA_DETECTED",
            f"Evaluation output omitted required rubric criteria assessments: {missing_ids}",
            retryable=True,
        )

    # 3. Score Boundaries Check
    for ca in payload.criterion_assessments:
        crit = expected_map[ca.criterion_id]
        min_score = Decimal(str(getattr(crit, "min_score", None) or (crit.get("min_score") if isinstance(crit, dict) else Decimal("0.00"))))
        max_score = Decimal(str(getattr(crit, "max_score", None) or (crit.get("max_score") if isinstance(crit, dict) else Decimal("10.00"))))

        if ca.final_criterion_score < min_score or ca.final_criterion_score > max_score:
            raise AIEvaluationValidationError(
                "SCORE_OUT_OF_BOUNDS",
                f"Criterion '{ca.criterion_title}' final score ({ca.final_criterion_score}) "
                f"is outside permissible bounds [{min_score}, {max_score}].",
                retryable=True,
            )

    # 4. Evidence Citation Verification
    if evidence_index and hasattr(evidence_index, "files") and evidence_index.files:
        for ev in payload.evidence_records:
            norm_path = ev.file_path.replace("\\", "/").strip().lstrip("/")
            if norm_path not in evidence_index.files and ev.file_path not in evidence_index.files:
                raise AIEvaluationValidationError(
                    "FABRICATED_CITATION_FILE",
                    f"Cited file '{ev.file_path}' does not exist in repository evidence index.",
                    retryable=True,
                )

            indexed_file = evidence_index.files.get(norm_path) or evidence_index.files.get(ev.file_path)
            if indexed_file and ev.end_line is not None:
                # Clamp minor trailing newline offsets (within 2 lines of file end)
                if ev.end_line > indexed_file.total_lines:
                    if ev.end_line <= indexed_file.total_lines + 2:
                        ev.end_line = indexed_file.total_lines
                    else:
                        raise AIEvaluationValidationError(
                            "INVALID_CITATION_LINE_RANGE",
                            f"Cited end_line {ev.end_line} exceeds total lines ({indexed_file.total_lines}) "
                            f"in file '{ev.file_path}'.",
                            retryable=True,
                        )

                # Verify exact source excerpt consistency if snippet is provided
                if ev.start_line and ev.end_line and indexed_file.lines and ev.source_excerpt and len(ev.source_excerpt.strip()) > 10:
                    start_idx = max(0, ev.start_line - 1)
                    end_idx = min(len(indexed_file.lines), ev.end_line)
                    actual_text = "\n".join(indexed_file.lines[start_idx:end_idx])
                    norm_actual = re.sub(r"\s+", " ", actual_text).strip()
                    norm_excerpt = re.sub(r"\s+", " ", ev.source_excerpt).strip()
                    clean_excerpt = re.sub(r"\s+", " ", ev.source_excerpt.rstrip(". ")).strip()

                    # Check exact substring, or with +/- 5 lines tolerance to account for LLM line-number indexing
                    match_found = (
                        norm_excerpt in norm_actual
                        or clean_excerpt in norm_actual
                        or any(part.strip().rstrip(". ") in norm_actual for part in ev.source_excerpt.split("\n") if len(part.strip().rstrip(". ")) > 15)
                    )
                    if not match_found:
                        expanded_start = max(0, start_idx - 5)
                        expanded_end = min(len(indexed_file.lines), end_idx + 5)
                        expanded_actual = re.sub(r"\s+", " ", "\n".join(indexed_file.lines[expanded_start:expanded_end])).strip()
                        match_found = (
                            norm_excerpt in expanded_actual
                            or clean_excerpt in expanded_actual
                            or any(part.strip().rstrip(". ") in expanded_actual for part in ev.source_excerpt.split("\n") if len(part.strip().rstrip(". ")) > 15)
                        )

                    if not match_found:
                        raise AIEvaluationValidationError(
                            "FABRICATED_CITATION_SNIPPET",
                            f"Cited snippet for '{ev.file_path}#L{ev.start_line}-L{ev.end_line}' does not match actual repository content.",
                            retryable=True,
                        )

    # 5. Deduction Attribution & Anti-Duplicate Validation
    all_deductions = []
    for ca in payload.criterion_assessments:
        all_deductions.extend(ca.deductions)

    known_eids = {e.evidence_id for e in payload.evidence_records}
    ev_status_map = {e.evidence_id: e.verification_status for e in payload.evidence_records}

    # Collect optional requirement IDs for immunity enforcement
    all_opt_ids: Set[str] = set()
    for ca in payload.criterion_assessments:
        for r in ca.requirement_coverage:
            if r.requirement_type == RequirementType.OPTIONAL:
                all_opt_ids.add(r.requirement_id)

    ded_result = DeductionAttributionEngine.validate_deductions_batch(
        deductions=all_deductions,
        known_evidence_ids=known_eids if known_eids else None,
        evidence_status_map=ev_status_map,
    )
    if not ded_result.is_valid:
        raise AIEvaluationValidationError(
            "DEDUCTION_ATTRIBUTION_VIOLATION",
            "; ".join(ded_result.validation_messages),
            retryable=True,
        )

    # Validate raw-score and deduction non-overlap (Double Punishment Protection)
    for ca in payload.criterion_assessments:
        raw_score_violations = DeductionAttributionEngine.validate_criterion_raw_score_interaction(ca)
        if raw_score_violations:
            raise AIEvaluationValidationError(
                "RAW_SCORE_DEDUCTION_DOUBLE_COUNTING",
                "; ".join(raw_score_violations),
                retryable=True,
            )

    # Check optional requirement immunity (EVAL_05)
    for ca in payload.criterion_assessments:
        opt_req_ids = {
            r.requirement_id.lower().strip()
            for r in ca.requirement_coverage
            if r.requirement_type == RequirementType.OPTIONAL
        }
        for d in ca.deductions:
            desc_lower = d.issue_description.lower()
            overlap_lower = (d.overlap_group_id or "").lower()
            for opt_id in opt_req_ids:
                if opt_id in desc_lower or opt_id in overlap_lower:
                    raise AIEvaluationValidationError(
                        "OPTIONAL_REQUIREMENT_DEDUCTION",
                        f"Deduction '{d.issue_description}' improperly penalizes optional requirement '{opt_id}' "
                        f"(violates EVAL_05: Optional Features Are Not Mandatory Requirements).",
                        retryable=True,
                    )

    # Check prototype calibration and unrequested infrastructure immunity (Directive 6)
    unrequested_infra_patterns = [
        (re.compile(r"\b(kubernetes|k8s|distributed infrastructure|distributed scalability)\b", re.I), "UNREQUESTED_INFRASTRUCTURE_DEDUCTION", "Kubernetes or distributed infrastructure"),
        (re.compile(r"\b(not using microservices|microservice|microservices architecture|monolith instead of microservices)\b", re.I), "STACK_SIMPLICITY_DEDUCTION", "not using microservices"),
        (re.compile(r"\b(cloud deployment manifests?|missing deployment manifests?|cloud deployment infrastructure|terraform|helm)\b", re.I), "UNREQUESTED_DEPLOYMENT_DEDUCTION", "missing cloud deployment manifests"),
    ]

    for ca in payload.criterion_assessments:
        crit_meta = expected_map.get(ca.criterion_id)
        crit_text = ""
        if crit_meta:
            crit_text = f"{getattr(crit_meta, 'title', '')} {getattr(crit_meta, 'description', '')} {getattr(crit_meta, 'evidence_requirements', '')}".lower()

        mandatory_req_text = " ".join([
            f"{r.title} {r.description}".lower()
            for r in ca.requirement_coverage
            if r.requirement_type == RequirementType.MANDATORY
        ])

        full_req_context = f"{crit_text} {mandatory_req_text}"

        for d in ca.deductions:
            desc_text = f"{d.issue_description} {d.proportionality_rationale} {getattr(d, 'impact_explanation', '') or ''}".lower()
            for pattern, err_code, label in unrequested_infra_patterns:
                if pattern.search(desc_text):
                    if not pattern.search(full_req_context):
                        raise AIEvaluationValidationError(
                            err_code,
                            f"Deduction '{d.issue_description}' improperly penalizes prototype for {label} "
                            f"which was not mandated by the problem statement or rubric (violates Directive 6: Prototype Calibration & Stack Neutrality).",
                            retryable=True,
                        )

    # 6. Policy Fairness Verification
    active_policy = get_active_evaluation_policy()
    violations = active_policy.validate_evaluation_fairness(payload)
    if violations:
        raise AIEvaluationValidationError(
            "FAIR_EVALUATION_POLICY_VIOLATION",
            "; ".join(violations),
            retryable=True,
        )

    return payload


# ==============================================================================
# Bounded Retry Execution Pipeline
# ==============================================================================

async def execute_evaluation_with_retry(
    provider_client: AIProviderClient,
    prompt: str,
    schema: Dict[str, Any],
    model_name: str,
    rubric_criteria: List[Any],
    evidence_index: Optional[Any] = None,
    timeout_seconds: float = 120.0,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    max_retries: int = 1,
) -> Union[StandardizedEvaluationOutput, AIEvaluationOutputPayload]:
    """
    Executes model inference and validates output against schema, rubric criteria,
    score bounds, and verifiable evidence citations.
    Supports both StandardizedEvaluationOutput and legacy AIEvaluationOutputPayload.
    Performs at most one bounded retry for recoverable parse/schema failures with temperature 0.0.
    Fails closed immediately on SSRF, network policy, or unrecoverable errors.
    """
    last_error: Optional[Exception] = None
    is_standardized = (
        "criterion_assessments" in (schema.get("properties") or {})
        or "StandardizedEvaluationOutput" in str(schema)
    )

    for attempt in range(max_retries + 1):
        is_retry = attempt > 0

        current_prompt = prompt
        current_temp = 0.0 if is_retry else temperature

        if is_retry and last_error:
            missing_evidence_rule = (
                "- For missing or unindexed evidence, do NOT award arbitrary minimum scores; "
                "express uncertainty in missing_evidence_observations."
                if is_standardized else
                "- For missing evidence, record evidence_status as 'missing' with explicit rationale."
            )
            current_prompt = (
                f"{prompt}\n\n"
                f"CRITICAL CORRECTION REQUIRED:\n"
                f"Your previous response was rejected due to validation errors:\n"
                f"{str(last_error)}\n"
                f"You must strictly satisfy all schema requirements:\n"
                f"- Output valid JSON only, conforming exactly to the schema.\n"
                f"- Include EVERY required criterion ID exactly once with no duplicates.\n"
                f"- Ensure each awarded score is strictly within [min_score, max_score].\n"
                f"{missing_evidence_rule}\n"
                f"- Cite only files that exist in the repository evidence."
            )

        try:
            raw_response = await provider_client.generate_evaluation(
                prompt=current_prompt,
                schema=schema,
                model_name=model_name,
                timeout_seconds=timeout_seconds,
                temperature=current_temp,
                max_tokens=max_tokens,
            )
        except (
            AIProviderTimeoutError,
            AIProviderConnectionError,
            AIProviderSSRFError,
            AIProviderResponseSizeError,
            AIProviderConfigError,
        ):
            # Network infrastructure, timeouts, SSRF, oversized response, and configuration errors
            # must NEVER be retried with schema correction prompts. Propagate immediately as typed errors.
            raise
        except AIProviderFormatError as exc:
            last_error = exc
            if attempt < max_retries and getattr(exc, "retryable", False):
                logger.warning(
                    "Recoverable AI provider format error on attempt %d: %s. Retrying with temperature 0.0...",
                    attempt + 1,
                    exc,
                )
                continue
            raise AIEvaluationValidationError(
                "EVAL_PARSE_ERROR",
                f"AI provider failed after {attempt + 1} attempt(s): {exc}",
                retryable=False,
            ) from exc
        except AIProviderError:
            # Other non-retryable provider errors fail closed without schema retries
            raise

        # Validate structured output against rubric criteria and evidence
        try:
            resp_dict = raw_response
            if isinstance(raw_response, str):
                try:
                    resp_dict = json.loads(raw_response)
                except Exception:
                    resp_dict = {}

            has_assessments = isinstance(resp_dict, dict) and "criterion_assessments" in resp_dict
            if is_standardized and has_assessments:
                validated_payload = validate_standardized_evaluation_output(
                    raw_output=raw_response,
                    rubric_criteria=rubric_criteria,
                    evidence_index=evidence_index,
                )
            else:
                validated_payload = validate_ai_evaluation_output(
                    raw_output=raw_response,
                    rubric_criteria=rubric_criteria,
                    evidence_index=evidence_index,
                )
            return validated_payload
        except AIEvaluationValidationError as val_exc:
            last_error = val_exc
            if attempt < max_retries and val_exc.retryable:
                logger.warning(
                    "Schema/rubric validation failure on attempt %d: %s. Retrying with temperature 0.0...",
                    attempt + 1,
                    val_exc,
                )
                continue
            raise AIEvaluationValidationError(
                "EVAL_PARSE_ERROR",
                f"Evaluation failed schema validation after {attempt + 1} attempt(s): {val_exc.details}",
                retryable=False,
            ) from val_exc

    raise AIEvaluationValidationError(
        "EVAL_PARSE_ERROR",
        f"Evaluation failed after {max_retries + 1} attempts: {last_error}",
        retryable=False,
    )

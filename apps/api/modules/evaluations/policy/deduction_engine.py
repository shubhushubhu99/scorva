"""
Scorva Deduction Attribution Engine & Anti-Duplicate Penalty System.

Enforces:
1. Every deduction must be grounded in cited evidence, severity tier, and criterion relevance.
2. Anti-double-counting: the same root defect cannot trigger multiple deductions across criteria
   without an explicit, distinct, independent justification.
3. Proportionality: deductions must remain bounded and fair relative to defect severity.
"""

import re
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid
from pydantic import BaseModel, ConfigDict, Field

from apps.api.modules.evaluations.policy.contracts import (
    DeductionAttributionContract,
    DefectSeverity,
    EvidenceStrength,
)

logger = logging.getLogger("scorva.deduction_engine")

# Permissible deduction bounds per severity tier
SEVERITY_MAX_DEDUCTION_BOUNDS: Dict[DefectSeverity, Decimal] = {
    DefectSeverity.COSMETIC: Decimal("0.50"),   # Max 0.50 pt
    DefectSeverity.MINOR: Decimal("1.50"),      # Max 1.50 pt
    DefectSeverity.MODERATE: Decimal("3.00"),   # Max 3.00 pt
    DefectSeverity.MAJOR: Decimal("6.00"),      # Max 6.00 pt
    DefectSeverity.CRITICAL: Decimal("10.00"),  # Up to 10.00 pts (complete failure)
}

# Stopwords for semantic overlap tokenization
_STOPWORDS = {
    "a", "an", "the", "in", "on", "of", "for", "to", "at", "by", "from", "with",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do",
    "does", "did", "and", "or", "not", "but", "if", "that", "this", "these", "those",
    "project", "code", "system", "submission", "application", "criterion", "issue",
}


def _extract_semantic_tokens(text: str) -> Set[str]:
    """Extracts normalized significant tokens from issue descriptions for semantic duplicate detection."""
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _has_semantic_duplicate(
    tokens: Set[str],
    seen_token_sets: List[Tuple[Set[str], str, uuid.UUID]],
    current_crit_id: uuid.UUID,
) -> Optional[str]:
    """
    Checks if a set of tokens significantly overlaps with an already attributed defect
    in a different criterion. Returns the description of the overlapping defect if found.
    """
    if len(tokens) < 2:
        return None

    for prior_tokens, prior_desc, prior_crit_id in seen_token_sets:
        if prior_crit_id == current_crit_id:
            continue  # Cross-criterion check ignores issues within the same criterion
        
        overlap = tokens.intersection(prior_tokens)
        # If overlap is 50% or more of either set, or contains at least 3 matching core tokens
        if len(overlap) >= 3 or (len(prior_tokens) > 0 and len(overlap) / len(prior_tokens) >= 0.5):
            return prior_desc

    return None


def _has_within_criterion_duplicate(
    tokens: Set[str],
    deduction: DeductionAttributionContract,
    seen_in_criterion: List[Tuple[Set[str], DeductionAttributionContract]],
) -> Optional[Tuple[DeductionAttributionContract, str]]:
    """
    Checks if a deduction significantly overlaps with another deduction in the SAME criterion.
    Returns (prior_deduction, reason) if it is an unjustified duplicate penalty.
    Allows separate attribution ONLY if genuinely distinct, independent impacts are evidenced.
    """
    if len(tokens) < 2:
        return None

    for prior_tokens, prior_d in seen_in_criterion:
        overlap = tokens.intersection(prior_tokens)
        is_token_overlap = len(overlap) >= 3 or (len(prior_tokens) > 0 and len(overlap) / len(prior_tokens) >= 0.5)
        same_group = bool(
            deduction.overlap_group_id
            and prior_d.overlap_group_id
            and deduction.overlap_group_id.strip().lower() == prior_d.overlap_group_id.strip().lower()
        )

        if is_token_overlap or same_group:
            # Check if genuinely distinct independent impact is demonstrated (Scenario C)
            has_distinct_evidence = bool(
                deduction.evidence_ids
                and prior_d.evidence_ids
                and set(deduction.evidence_ids) != set(prior_d.evidence_ids)
            )
            has_distinct_impact = bool(
                getattr(deduction, "impact_explanation", None)
                and getattr(prior_d, "impact_explanation", None)
                and deduction.impact_explanation.strip().lower() != prior_d.impact_explanation.strip().lower()
                and len(deduction.impact_explanation.strip()) >= 15
            )
            different_reqs = bool(
                getattr(deduction, "affected_requirement_id", None)
                and getattr(prior_d, "affected_requirement_id", None)
                and deduction.affected_requirement_id.strip().lower() != prior_d.affected_requirement_id.strip().lower()
            )

            # If distinct impacts are documented and evidence is independent -> permit separate attribution
            if has_distinct_impact and (has_distinct_evidence or different_reqs):
                continue

            # Otherwise, reject duplicate penalty within criterion (Scenario A)
            reason = (
                f"Duplicate penalty rejected within criterion: Issue '{deduction.issue_description[:60]}' "
                f"penalizes the same defect already attributed in '{prior_d.issue_description[:60]}' "
                f"without demonstrating an independent impact and distinct evidence."
            )
            return (prior_d, reason)

    return None


class DeductionValidationResult(BaseModel):
    """Result of deduction attribution validation across an evaluation run."""
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    accepted_deductions: List[DeductionAttributionContract] = Field(default_factory=list)
    rejected_deductions: List[Tuple[DeductionAttributionContract, str]] = Field(default_factory=list)
    duplicate_penalties_prevented: int = 0
    total_deducted_points_by_criterion: Dict[uuid.UUID, Decimal] = Field(default_factory=dict)
    validation_messages: List[str] = Field(default_factory=list)


class DeductionAttributionEngine:
    """
    Validates proposed deductions against anti-duplicate penalty rules,
    evidence linkage, severity bounds, and cross-criterion justifications.
    """

    @classmethod
    def validate_deductions_batch(
        cls,
        deductions: List[DeductionAttributionContract],
        known_evidence_ids: Optional[Set[uuid.UUID]] = None,
        allow_cross_criterion_duplicates: bool = False,
        evidence_strength_map: Optional[Dict[uuid.UUID, Any]] = None,
        evidence_status_map: Optional[Dict[uuid.UUID, Any]] = None,
        optional_requirement_ids: Optional[Set[str]] = None,
    ) -> DeductionValidationResult:
        """
        Validates a batch of deductions across an evaluation.
        Prevents duplicate penalties for the same root defect unless distinctly justified,
        and enforces evidence grounding, optional requirement immunity, and severity limits.
        """
        accepted: List[DeductionAttributionContract] = []
        rejected: List[Tuple[DeductionAttributionContract, str]] = []
        prevented_count = 0
        totals: Dict[uuid.UUID, Decimal] = {}
        messages: List[str] = []

        # Track seen root issues by overlap_group_id or normalized issue text
        seen_overlap_groups: Set[str] = set()
        seen_token_sets: List[Tuple[Set[str], str, uuid.UUID]] = []
        seen_within_criterion: Dict[uuid.UUID, List[Tuple[Set[str], DeductionAttributionContract]]] = {}

        for d in deductions:
            # 1. Evidence Grounding Check
            if known_evidence_ids is not None and d.evidence_ids:
                missing_refs = [eid for eid in d.evidence_ids if eid not in known_evidence_ids]
                if missing_refs:
                    msg = f"Deduction references non-existent evidence IDs: {missing_refs}"
                    rejected.append((d, msg))
                    messages.append(msg)
                    continue

            # 2. Contextual Evidence Strength vs Severity (EVAL_11)
            if evidence_strength_map and d.evidence_ids:
                strengths = [evidence_strength_map.get(eid) for eid in d.evidence_ids if eid in evidence_strength_map]
                if strengths and all((getattr(s, "value", str(s)).upper() in ("WEAK", "INSUFFICIENT", "INCONCLUSIVE") or s == EvidenceStrength.WEAK or s == EvidenceStrength.INSUFFICIENT) for s in strengths):
                    if d.defect_severity in (DefectSeverity.MAJOR, DefectSeverity.CRITICAL):
                        msg = (
                            f"Defect '{d.issue_description[:60]}' assigned severity '{d.defect_severity.value}' "
                            f"without strong or moderate evidence (violates EVAL_11: Distinguish Confirmed Defects from Potential Risks)."
                        )
                        rejected.append((d, msg))
                        messages.append(msg)
                        continue

            if evidence_status_map and d.evidence_ids:
                statuses = [evidence_status_map.get(eid) for eid in d.evidence_ids if eid in evidence_status_map]
                if statuses and all(getattr(s, "value", str(s)).upper() in ("UNVERIFIED", "NOT_AVAILABLE") for s in statuses):
                    if d.defect_severity in (DefectSeverity.MAJOR, DefectSeverity.CRITICAL):
                        msg = (
                            f"Defect '{d.issue_description[:60]}' assigned severity '{d.defect_severity.value}' "
                            f"against unverified evidence (violates EVAL_11: Distinguish Confirmed Defects from Potential Risks)."
                        )
                        rejected.append((d, msg))
                        messages.append(msg)
                        continue

            # 3. Optional Requirements Immunity (EVAL_05)
            if optional_requirement_ids:
                norm_opts = {r.strip().lower() for r in optional_requirement_ids}
                aff_req = (getattr(d, "affected_requirement_id", None) or "").strip().lower()
                desc_lower = d.issue_description.lower()
                overlap_lower = (d.overlap_group_id or "").lower()
                is_opt = False
                if aff_req and aff_req in norm_opts:
                    is_opt = True
                for opt_id in norm_opts:
                    if opt_id in desc_lower or opt_id in overlap_lower:
                        is_opt = True
                        break
                if is_opt:
                    msg = (
                        f"Deduction rejected: Defect '{d.issue_description[:60]}' penalizes optional requirement "
                        f"(violates EVAL_05: Optional Features Are Not Mandatory Requirements)."
                    )
                    rejected.append((d, msg))
                    messages.append(msg)
                    continue

            # 4. Severity Proportionality & Ceiling Check
            max_allowed = SEVERITY_MAX_DEDUCTION_BOUNDS.get(d.defect_severity, Decimal("3.00"))
            if d.deduction_points > max_allowed:
                msg = (
                    f"Deduction of {d.deduction_points} pts exceeds maximum allowable "
                    f"({max_allowed} pts) for severity tier '{d.defect_severity.value}'."
                )
                rejected.append((d, msg))
                messages.append(msg)
                continue

            # Proportionality safeguard: Distinguish severity label from point calculation
            minor_markers = ["minor", "cosmetic", "trivial", "non-blocking", "formatting", "typo", "minor omission", "edge case only"]
            text_context = f"{d.issue_description.lower()} {(getattr(d, 'impact_explanation', '') or '').lower()} {d.proportionality_rationale.lower()}"
            if d.defect_severity == DefectSeverity.CRITICAL:
                if d.deduction_points > Decimal("3.00") and any(m in text_context for m in minor_markers):
                    msg = (
                        f"Disproportionate deduction rejected: Defect '{d.issue_description[:60]}' classified as CRITICAL "
                        f"with {d.deduction_points} pts deduction, but describes only minor or non-blocking impact."
                    )
                    rejected.append((d, msg))
                    messages.append(msg)
                    continue
            elif d.defect_severity == DefectSeverity.MAJOR:
                if d.deduction_points > Decimal("2.50") and any(m in text_context for m in minor_markers):
                    msg = (
                        f"Disproportionate deduction rejected: Defect '{d.issue_description[:60]}' classified as MAJOR "
                        f"with {d.deduction_points} pts deduction, but describes limited or minor impact."
                    )
                    rejected.append((d, msg))
                    messages.append(msg)
                    continue

            # 5. Within-Criterion Duplicate Penalty Check (Scenarios A, C, D)
            tokens = _extract_semantic_tokens(d.issue_description)
            within_list = seen_within_criterion.setdefault(d.criterion_id, [])
            within_dup = _has_within_criterion_duplicate(tokens, d, within_list)
            if within_dup is not None:
                _, reason = within_dup
                rejected.append((d, reason))
                prevented_count += 1
                messages.append(reason)
                continue

            # 6. Cross-Criterion Duplicate Penalty Check (overlap_group_id and cross-criterion semantic similarity)
            overlap_key = (d.overlap_group_id or d.issue_description.strip().lower()[:100]).strip()
            sem_dup_desc = _has_semantic_duplicate(tokens, seen_token_sets, d.criterion_id) if d.is_primary_attribution else None
            
            is_duplicate = (overlap_key in seen_overlap_groups) or (sem_dup_desc is not None)

            if is_duplicate:
                # Issue already penalized in a prior criterion
                if d.is_primary_attribution:
                    # Cannot have two primary attributions for the same root defect
                    msg = (
                        f"Duplicate primary penalty rejected for issue '{d.issue_description[:60]}...'. "
                        f"A primary deduction was already attributed to another criterion"
                        f"{f' (matches prior issue: {sem_dup_desc[:50]}...)' if sem_dup_desc else ''}."
                    )
                    rejected.append((d, msg))
                    prevented_count += 1
                    messages.append(msg)
                    continue
                else:
                    # Non-primary attribution requires explicit cross_criterion_justification
                    if not allow_cross_criterion_duplicates:
                        if not d.cross_criterion_justification or len(d.cross_criterion_justification.strip()) < 15:
                            msg = (
                                f"Secondary deduction for issue '{d.issue_description[:60]}...' rejected: "
                                f"Missing rigorous cross_criterion_justification explaining why this defect "
                                f"independently compromises this criterion beyond its primary attribution."
                            )
                            rejected.append((d, msg))
                            prevented_count += 1
                            messages.append(msg)
                            continue
            else:
                seen_overlap_groups.add(overlap_key)
                if d.is_primary_attribution and tokens:
                    seen_token_sets.append((tokens, d.issue_description, d.criterion_id))

            # Accept deduction
            within_list.append((tokens, d))
            accepted.append(d)
            crit_id = d.criterion_id
            totals[crit_id] = totals.get(crit_id, Decimal("0.00")) + d.deduction_points

        # Cap criterion total deductions at 10.00 pts
        for cid, tot in list(totals.items()):
            if tot > Decimal("10.00"):
                totals[cid] = Decimal("10.00")

        is_valid = len(rejected) == 0

        return DeductionValidationResult(
            is_valid=is_valid,
            accepted_deductions=accepted,
            rejected_deductions=rejected,
            duplicate_penalties_prevented=prevented_count,
            total_deducted_points_by_criterion=totals,
            validation_messages=messages,
        )

    @classmethod
    def apply_deductions_to_raw_score(
        cls,
        raw_score: Decimal,
        deductions: List[DeductionAttributionContract],
        min_score: Decimal = Decimal("0.00"),
        max_score: Decimal = Decimal("10.00"),
    ) -> Tuple[Decimal, Decimal]:
        """
        Calculates total deductions and applies them to raw score within [min_score, max_score].
        Returns: (final_score, total_deductions).
        """
        total_ded = sum((d.deduction_points for d in deductions), Decimal("0.00"))
        # Floor final score at min_score
        final_score = max(min_score, min(max_score, raw_score - total_ded))
        return (
            final_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            total_ded.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )

    @classmethod
    def validate_criterion_raw_score_interaction(
        cls,
        assessment: Any,
    ) -> List[str]:
        """
        Enforces that a defect cannot reduce raw_score_before_deductions and subsequently
        receive an additional deduction for the same underlying issue (Double Punishment Protection).

        Scenarios:
        - Scenario A: Same defect counted twice (raw score lowered because of defect + deduction for same issue) -> rejected.
        - Scenario B: Evaluator explicitly states raw score already accounts for the defect -> rejected.
        - Scenario C: Legitimate separate impact with documented non-overlap justification -> permitted.
        - Scenario D: Different defects in the same criterion -> permitted.
        """
        violations: List[str] = []
        deductions = getattr(assessment, "deductions", None) or []
        if not deductions:
            return violations

        raw_score = getattr(assessment, "raw_score_before_deductions", Decimal("10.00"))
        # If raw score is at maximum permitted (10.00), no defects reduced the raw score
        if raw_score >= Decimal("10.00"):
            return violations

        score_justification = (getattr(assessment, "score_justification", "") or "").lower()

        # Regex patterns capturing explicit statements that a defect reduced / lowered / penalized raw score
        explicit_reduction_patterns = [
            r"(?:raw\s*score|score|baseline)\s*(?:was|is)?\s*(?:already\s*)?(?:reduced|lowered|penalized|deducted|discounted|accounted\s*for|factored\s*in)\s*(?:to\s*[\d.]+|\s*by\s*[\d.]+)?\s*(?:due to|because of|owing to|for)\s*([^.,;]+)",
            r"(?:reduced|lowered|penalized|deducted|discounted)\s*(?:the\s*)?(?:raw\s*score|score|baseline)\s*(?:to\s*[\d.]+|\s*by\s*[\d.]+)?\s*(?:due to|because of|owing to|for)\s*([^.,;]+)",
            r"(?:already\s*accounts?\s*for|already\s*accounted\s*for|already\s*reduced\s*(?:the\s*score\s*)?for)\s*([^.,;]+)",
            r"(?:lower(?:ed)?\s*raw\s*score|lower\s*score)\s*(?:due to|because of|for)\s*([^.,;]+)",
            r"raw\s*score\s*(?:already\s*)?reflects?\s*(?:the\s*)?defect\s*(?:of|in|for)?\s*([^.,;]+)",
            r"(?:defect|issue|flaw|vulnerability|omission)?\s*(?:of|in)?\s*([^.,;]+?)\s*(?:has|have|is|was)?\s*(?:already\s*)?(?:reduced|lowered|penalized|deducted|discounted)\s*(?:the\s*)?(?:raw\s*score|score|baseline)",
        ]

        reduced_defect_clauses: List[str] = []
        for pat in explicit_reduction_patterns:
            matches = re.findall(pat, score_justification)
            for m in matches:
                if isinstance(m, str) and len(m.strip()) > 3:
                    reduced_defect_clauses.append(m.strip())

        # If no explicit statement that raw score was reduced for a specific defect, no double punishment in justification
        if not reduced_defect_clauses:
            return violations

        for clause in reduced_defect_clauses:
            clause_tokens = _extract_semantic_tokens(clause)
            if len(clause_tokens) < 2:
                continue

            for d in deductions:
                d_tokens = _extract_semantic_tokens(d.issue_description)
                overlap = d_tokens.intersection(clause_tokens)
                is_semantic_overlap = len(overlap) >= 2 and (
                    len(overlap) >= 3 or len(overlap) / len(d_tokens) >= 0.4 or len(overlap) / len(clause_tokens) >= 0.4
                )

                if is_semantic_overlap:
                    # Check for legitimate separate impact (Scenario C)
                    non_overlap_just = (getattr(d, "raw_score_non_overlap_justification", None) or "").strip()
                    impact_expl = (getattr(d, "impact_explanation", None) or "").strip()
                    has_legitimate_distinct_impact = len(non_overlap_just) >= 15 and len(impact_expl) >= 15

                    if has_legitimate_distinct_impact:
                        continue  # Legitimate separate impact documented

                    # Check whether explicitly stated as already reduced (Scenario B) vs lower raw score (Scenario A)
                    is_scenario_b = any(
                        term in score_justification
                        for term in ["already reduced", "already accounts", "already accounted", "already factored", "already penalized"]
                    )

                    if is_scenario_b:
                        violations.append(
                            f"Double Punishment Rejected (Scenario B): Defect '{d.issue_description}' "
                            f"was explicitly stated in score justification as having already reduced "
                            f"raw_score_before_deductions to {raw_score}/10.00. Applying an additional "
                            f"deduction of {d.deduction_points} pts for the same defect constitutes duplicate punishment."
                        )
                    else:
                        violations.append(
                            f"Double Punishment Rejected (Scenario A): Defect '{d.issue_description}' "
                            f"caused raw_score_before_deductions to be lowered to {raw_score}/10.00 ('{clause}'). "
                            f"An additional deduction of {d.deduction_points} pts for the same defect constitutes "
                            f"duplicate punishment unless a distinct independent impact is evidenced via 'raw_score_non_overlap_justification'."
                        )

        return violations

"""
Investigation script: Executes 2 additional live runs on the exact frozen inputs
without modifying the original pi_verification_runs.json.
Saves results into apps/api/scripts/pi_investigation_additional_runs.json.
"""

import asyncio
from decimal import Decimal
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List
import uuid

from apps.api.modules.evaluations.evidence_indexer import EvidenceIndex
from apps.api.modules.evaluations.output_validator import (
    AIEvaluationValidationError,
    validate_standardized_evaluation_output,
)
from apps.api.modules.evaluations.policy.contracts import StandardizedEvaluationOutput
from apps.api.modules.evaluations.prompt_compiler import compile_evaluation_prompt
from apps.api.modules.evaluations.providers.pi.client import PiProviderClient
from apps.api.modules.evaluations.scoring_calculator import CriterionInput, calculate_evaluation_scores
from apps.api.scripts.verify_real_pi_inference import (
    build_frozen_evidence_index,
    build_frozen_rubric,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pi_investigation")


async def run_additional_live_evaluations(count: int = 2, model_name: str = "google/gemini-3.5-flash-lite"):
    client = PiProviderClient()

    submission_id = uuid.UUID("57ae4343-8500-4be8-8270-52f3f22d0553")
    commit_sha = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
    rubric_version_id = uuid.UUID("74a810f8-e9aa-4856-bb6b-a2eb9197c02b")
    policy_version = "1.0.0"

    criteria = build_frozen_rubric()
    evidence_index = build_frozen_evidence_index()

    submission_meta = {
        "team_name": "Zenith AI Labs",
        "commit_sha": commit_sha,
        "target_branch": "main",
    }

    schema = StandardizedEvaluationOutput.model_json_schema()
    prompt = compile_evaluation_prompt(
        rubric_criteria=criteria,
        evidence_index=evidence_index,
        submission_meta=submission_meta,
        schema=schema,
    )

    additional_runs: List[Dict[str, Any]] = []

    for i in range(1, count + 1):
        run_number = 3 + i
        logger.info("--- [ADDITIONAL LIVE RUN %d (Run %d overall)] Starting ---", i, run_number)
        start_wall = time.time()

        detailed = None
        for attempt in range(2):
            try:
                detailed = await client.generate_evaluation_detailed(
                    prompt=prompt,
                    schema=schema,
                    model_name=model_name,
                    timeout_seconds=90.0,
                    temperature=0.0,
                )
                break
            except Exception as exc:
                if attempt == 0:
                    logger.warning("Run %d attempt 1 failed: %s. Retrying...", run_number, exc)
                    await asyncio.sleep(1.0)
                else:
                    logger.error("Run %d failed on retry: %s", run_number, exc)
                    additional_runs.append({
                        "run_index": run_number,
                        "status": "ERROR",
                        "error": str(exc),
                    })

        if not detailed:
            continue

        duration_wall = time.time() - start_wall
        output_dict = detailed.get("output", {})
        usage = detailed.get("usage", {})
        duration_ms = detailed.get("duration_ms", 0)

        if isinstance(output_dict, dict):
            output_dict["submission_id"] = str(submission_id)
            output_dict["repository_commit_sha"] = commit_sha
            output_dict["rubric_version_id"] = str(rubric_version_id)
            output_dict["policy_version"] = policy_version
            output_dict["validation_passed"] = True

        validated_payload = None
        try:
            validated_payload = validate_standardized_evaluation_output(
                output_dict,
                rubric_criteria=criteria,
                evidence_index=evidence_index,
            )
            logger.info("Run %d validation passed successfully!", run_number)
        except AIEvaluationValidationError as val_exc:
            logger.warning("Run %d validation failed: %s", run_number, val_exc)

        calc_result = None
        if validated_payload:
            crit_inputs = []
            crit_map = {c.id: c for c in criteria}
            for ca in validated_payload.criterion_assessments:
                meta = crit_map[ca.criterion_id]
                crit_inputs.append(
                    CriterionInput(
                        criterion_id=ca.criterion_id,
                        title=meta.title,
                        weight=meta.weight,
                        min_score=meta.min_score,
                        max_score=meta.max_score,
                        awarded_score=ca.final_criterion_score,
                        confidence_score=ca.confidence,
                    )
                )
            calc_result = calculate_evaluation_scores(crit_inputs)
            logger.info(
                "Run %d Deterministic Score: Raw=%.4f, Normalized=%.2f",
                run_number,
                calc_result.raw_score,
                calc_result.normalized_score,
            )

        additional_runs.append({
            "run_index": run_number,
            "status": "SUCCESS" if validated_payload else "VALIDATION_FAILED",
            "model_provider": detailed.get("provider"),
            "model_name": detailed.get("model"),
            "duration_ms": duration_ms,
            "wall_clock_seconds": round(duration_wall, 3),
            "usage": usage,
            "scores": {
                "raw_score": str(calc_result.raw_score) if calc_result else None,
                "normalized_score": str(calc_result.normalized_score) if calc_result else None,
            },
            "criterion_assessments": [
                {
                    "criterion_id": str(ca.criterion_id),
                    "criterion_title": ca.criterion_title,
                    "raw_score_before_deductions": str(ca.raw_score_before_deductions),
                    "total_deductions": str(ca.total_deductions),
                    "final_criterion_score": str(ca.final_criterion_score),
                    "confidence": str(ca.confidence),
                    "deductions_count": len(ca.deductions),
                    "score_justification": ca.score_justification,
                }
                for ca in (validated_payload.criterion_assessments if validated_payload else [])
            ],
            "evidence_count": len(validated_payload.evidence_records) if validated_payload else 0,
            "quick_summary": validated_payload.overall_quick_summary if validated_payload else None,
            "detailed_summary": validated_payload.overall_detailed_summary if validated_payload else None,
            "raw_output": output_dict,
        })

    out_file = Path("/home/shubh/scorva/apps/api/scripts/pi_investigation_additional_runs.json")
    out_file.write_text(json.dumps({"additional_runs": additional_runs}, indent=2, default=str))
    logger.info("Saved additional runs to %s", out_file)


if __name__ == "__main__":
    asyncio.run(run_additional_live_evaluations(2))

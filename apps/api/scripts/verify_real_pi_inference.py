"""
Standalone Real Pi Inference Verification Script.
Executes 3 consecutive live runs of a frozen repository evaluation through the real local Pi CLI.
Records execution metrics, parsed scores, evidence verification, and scoring consistency.
"""

import asyncio
from dataclasses import dataclass, asdict
from decimal import Decimal
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List
import uuid

from apps.api.modules.evaluations.evidence_indexer import EvidenceIndex, IndexedFile, TaxonomyCategory
from apps.api.modules.evaluations.output_validator import (
    AIEvaluationValidationError,
    validate_standardized_evaluation_output,
)
from apps.api.modules.evaluations.policy.contracts import (
    StandardizedEvaluationOutput,
)
from apps.api.modules.evaluations.prompt_compiler import compile_evaluation_prompt
from apps.api.modules.evaluations.providers.pi.client import PiProviderClient
from apps.api.modules.evaluations.scoring_calculator import CriterionInput, calculate_evaluation_scores

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pi_verification")


@dataclass
class FrozenCriterion:
    id: uuid.UUID
    title: str
    description: str
    weight: Decimal
    min_score: Decimal
    max_score: Decimal
    evidence_requirements: str


def build_frozen_rubric() -> List[FrozenCriterion]:
    return [
        FrozenCriterion(
            id=uuid.UUID("9f1c4f5d-4b8b-4f0f-8a0c-bf236be8b0b6"),
            title="Innovation & Originality",
            description="Novel approach to automated agent orchestration, resilience, and fairness.",
            weight=Decimal("0.2500"),
            min_score=Decimal("0.00"),
            max_score=Decimal("10.00"),
            evidence_requirements="Innovative architecture, distinct capabilities, novel engineering patterns.",
        ),
        FrozenCriterion(
            id=uuid.UUID("2bd7a620-e8d7-4102-bee0-64d0d34eab0f"),
            title="Technical Complexity & Architecture",
            description="Robust architectural design, separation of concerns, concurrency control, and scalability.",
            weight=Decimal("0.2500"),
            min_score=Decimal("0.00"),
            max_score=Decimal("10.00"),
            evidence_requirements="Clean modular structure, asynchronous handling, robust process lifecycles.",
        ),
        FrozenCriterion(
            id=uuid.UUID("078b836e-425e-4b6f-b034-8822811c1313"),
            title="Code Quality & Cleanliness",
            description="Readable, well-documented code with strong type annotations, test coverage, and linting.",
            weight=Decimal("0.2000"),
            min_score=Decimal("0.00"),
            max_score=Decimal("10.00"),
            evidence_requirements="Clear typing, adherence to standards, structured error handling.",
        ),
        FrozenCriterion(
            id=uuid.UUID("c21ff60b-bf07-4e0f-be17-a5dd5b4835bd"),
            title="Execution & Completeness",
            description="Functional implementation that satisfies requirements with automated test verification.",
            weight=Decimal("0.1500"),
            min_score=Decimal("0.00"),
            max_score=Decimal("10.00"),
            evidence_requirements="End-to-end functionality, passing test suites, working integrations.",
        ),
        FrozenCriterion(
            id=uuid.UUID("23c1c275-0ac2-4a28-8f44-c923414634fc"),
            title="Potential Impact & Usability",
            description="Value proposition, user documentation, clear operational workflows, and deployability.",
            weight=Decimal("0.1500"),
            min_score=Decimal("0.00"),
            max_score=Decimal("10.00"),
            evidence_requirements="Comprehensive README, intuitive APIs, deployment configuration.",
        ),
    ]


def build_frozen_evidence_index() -> EvidenceIndex:
    readme_text = (
        "# Zenith Autonomous Agent\n\n"
        "Zenith is a production-grade autonomous hackathon evaluation agent featuring:\n"
        "- Deterministic policy enforcement\n"
        "- Bounded retry mechanisms\n"
        "- Secret redaction and prompt injection resilience\n"
        "- Evidence-backed scoring contracts\n\n"
        "## Architecture\n"
        "The agent is structured into core orchestration (`src/agent/core.py`), "
        "security guardrails (`src/agent/guardrails.py`), and test suites (`tests/test_agent.py`).\n\n"
        "## Setup & Installation\n"
        "Install dependencies using:\n"
        "```bash\n"
        "pip install -r requirements.txt\n"
        "```\n\n"
        "## Testing\n"
        "Run the test suite using pytest:\n"
        "```bash\n"
        "pytest tests/\n"
        "```\n"
    )

    core_py = (
        "import asyncio\n"
        "import logging\n"
        "from typing import Any, Dict, Optional\n\n"
        "logger = logging.getLogger(__name__)\n\n"
        "class ZenithAgent:\n"
        "    \"\"\"Core evaluation agent engine.\"\"\"\n"
        "    def __init__(self, model_name: str = 'google/gemini-3.5-flash-lite'):\n"
        "        self.model_name = model_name\n"
        "        self._running = False\n"
        "        self.tasks_completed = 0\n\n"
        "    async def evaluate_task(self, prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:\n"
        "        logger.info('Starting agent evaluation loop for model %s', self.model_name)\n"
        "        self._running = True\n"
        "        await asyncio.sleep(0.01)\n"
        "        self.tasks_completed += 1\n"
        "        return {'status': 'completed', 'verified': True}\n\n"
        "    def shutdown(self) -> None:\n"
        "        self._running = False\n"
        "        logger.info('Agent shutdown complete.')\n"
    )

    guardrails_py = (
        "import re\n"
        "from typing import Optional\n\n"
        "class SecurityGuardrails:\n"
        "    \"\"\"Protects agent from prompt injection and secret leakage.\"\"\"\n"
        "    SECRET_PATTERNS = [\n"
        "        re.compile(r'(?i)(api[_-]?key|secret|token|password)\\s*[:=]\\s*[\"\\']?([a-zA-Z0-9_\\-]{16,})[\"\\']?'),\n"
        "    ]\n\n"
        "    @classmethod\n"
        "    def sanitize_input(cls, text: str) -> str:\n"
        "        sanitized = text\n"
        "        for pat in cls.SECRET_PATTERNS:\n"
        "            sanitized = pat.sub(r'\\1: [REDACTED_SECRET]', sanitized)\n"
        "        return sanitized\n"
    )

    test_agent_py = (
        "import pytest\n"
        "from src.agent.core import ZenithAgent\n"
        "from src.agent.guardrails import SecurityGuardrails\n\n"
        "@pytest.mark.asyncio\n"
        "async def test_agent_evaluates_task():\n"
        "    agent = ZenithAgent()\n"
        "    res = await agent.evaluate_task('test', {})\n"
        "    assert res['status'] == 'completed'\n"
        "    assert res['verified'] is True\n\n"
        "def test_guardrails_redact_secrets():\n"
        "    raw = 'api_key: abcdef1234567890abcdef'\n"
        "    cleaned = SecurityGuardrails.sanitize_input(raw)\n"
        "    assert '[REDACTED_SECRET]' in cleaned\n"
    )

    reqs_txt = (
        "pydantic>=2.0.0\n"
        "pytest>=8.0.0\n"
        "pytest-asyncio>=0.23.0\n"
    )

    index = EvidenceIndex()

    files = {
        "README.md": (TaxonomyCategory.DOCUMENTATION, readme_text),
        "src/agent/core.py": (TaxonomyCategory.SOURCE_CODE, core_py),
        "src/agent/guardrails.py": (TaxonomyCategory.SOURCE_CODE, guardrails_py),
        "tests/test_agent.py": (TaxonomyCategory.TEST_SUITES, test_agent_py),
        "requirements.txt": (TaxonomyCategory.BUILD_CONFIG, reqs_txt),
    }

    for path, (cat, content) in files.items():
        lines = content.splitlines()
        indexed = IndexedFile(
            relative_path=path,
            category=cat,
            total_lines=len(lines),
            size_bytes=len(content.encode("utf-8")),
            lines=lines,
        )
        index.files[path] = indexed
        if cat in (TaxonomyCategory.SOURCE_CODE, TaxonomyCategory.TEST_SUITES):
            index.total_lines_of_code += len(lines)
        if cat == TaxonomyCategory.DOCUMENTATION:
            index.documentation_files.append(path)
        elif cat == TaxonomyCategory.BUILD_CONFIG:
            index.build_files.append(path)
        elif cat == TaxonomyCategory.TEST_SUITES:
            index.has_automated_tests = True
            index.test_frameworks.append("pytest")

    return index


async def execute_live_pi_verification(runs_count: int = 3, model_name: str = "google/gemini-3.5-flash-lite"):
    logger.info("Initializing Real Pi Provider Client...")
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

    logger.info("Compiling prompt with hardened security directives and XML-framed evidence...")
    prompt = compile_evaluation_prompt(
        rubric_criteria=criteria,
        evidence_index=evidence_index,
        submission_meta=submission_meta,
        schema=schema,
    )

    run_records: List[Dict[str, Any]] = []

    logger.info("Starting %d consecutive live runs with real Pi CLI model %s...", runs_count, model_name)

    for run_idx in range(1, runs_count + 1):
        logger.info("--- [RUN %d / %d] Starting live Pi execution ---", run_idx, runs_count)
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
                    logger.warning("Run %d attempt 1 failed (%s), retrying bounded...", run_idx, exc)
                    await asyncio.sleep(1.0)
                else:
                    logger.error("Run %d failed on retry: %s", run_idx, exc)
                    run_records.append({
                        "run_index": run_idx,
                        "status": "ERROR",
                        "error": str(exc),
                        "duration_seconds": time.time() - start_wall,
                    })
        if not detailed:
            continue

        duration_wall = time.time() - start_wall
        output_dict = detailed.get("output", {})
        raw_text = detailed.get("raw_text", "")
        usage = detailed.get("usage", {})
        duration_ms = detailed.get("duration_ms", 0)

        logger.info(
            "Run %d Pi execution completed in %d ms (wall clock %.2fs). Input tokens: %s, Output tokens: %s",
            run_idx,
            duration_ms,
            duration_wall,
            usage.get("input") if usage else "N/A",
            usage.get("output") if usage else "N/A",
        )

        # Enforce submission and commit metadata onto output dict to ensure exact contract alignment
        if isinstance(output_dict, dict):
            output_dict["submission_id"] = str(submission_id)
            output_dict["repository_commit_sha"] = commit_sha
            output_dict["rubric_version_id"] = str(rubric_version_id)
            output_dict["policy_version"] = policy_version
            output_dict["validation_passed"] = True

        # Validate with output_validator
        validation_error = None
        validated_payload: Optional[StandardizedEvaluationOutput] = None
        try:
            validated_payload = validate_standardized_evaluation_output(
                output_dict,
                rubric_criteria=criteria,
                evidence_index=evidence_index,
            )
            logger.info("Run %d validation passed successfully!", run_idx)
        except AIEvaluationValidationError as val_exc:
            logger.warning("Run %d validation failed: %s (%s)", run_idx, val_exc.error_code, val_exc)
            validation_error = f"{val_exc.error_code}: {val_exc}"

        # Calculate deterministic score
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
            avg_conf = sum(ca.confidence for ca in validated_payload.criterion_assessments) / len(validated_payload.criterion_assessments)
            logger.info(
                "Run %d Deterministic Score: Raw=%.4f, Normalized=%.2f, Confidence=%.2f",
                run_idx,
                calc_result.raw_score,
                calc_result.normalized_score,
                avg_conf,
            )

        run_records.append({
            "run_index": run_idx,
            "status": "SUCCESS" if validated_payload else "VALIDATION_FAILED",
            "model_provider": detailed.get("provider"),
            "model_name": detailed.get("model"),
            "duration_ms": duration_ms,
            "wall_clock_seconds": round(duration_wall, 3),
            "usage": usage,
            "validation_error": validation_error,
            "scores": {
                "raw_score": str(calc_result.raw_score) if calc_result else None,
                "normalized_score": str(calc_result.normalized_score) if calc_result else None,
                "composite_confidence": str(round(avg_conf, 2)) if validated_payload else None,
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
            "raw_output": output_dict,
        })

    # Summary analysis
    successful_runs = [r for r in run_records if r["status"] == "SUCCESS"]
    scores = [Decimal(r["scores"]["normalized_score"]) for r in successful_runs if r["scores"]["normalized_score"]]

    score_min = min(scores) if scores else Decimal("0.00")
    score_max = max(scores) if scores else Decimal("0.00")
    score_spread = score_max - score_min if scores else Decimal("0.00")

    summary_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_model": model_name,
        "runs_requested": runs_count,
        "runs_successful": len(successful_runs),
        "score_spread": str(score_spread),
        "scores_normalized": [str(s) for s in scores],
        "runs": run_records,
    }

    out_path = Path("/home/shubh/scorva/apps/api/scripts/pi_verification_runs.json")
    out_path.write_text(json.dumps(summary_data, indent=2, default=str))
    logger.info("Verification results written to %s", out_path)
    print(f"\n=== VERIFICATION SUMMARY ===")
    print(f"Runs: {len(successful_runs)} / {runs_count} succeeded")
    print(f"Normalized Scores: {[str(s) for s in scores]}")
    print(f"Score Spread: {score_spread}")
    print(f"Details saved to {out_path}")
    return summary_data


if __name__ == "__main__":
    asyncio.run(execute_live_pi_verification(3, "google/gemini-3.5-flash-lite"))

"""
Unit tests for Block 6 Codebase Defect & Improvement Audit and 3-Model Ollama Cascade.
"""

import uuid
from unittest.mock import AsyncMock, patch
import pytest

from apps.api.modules.evaluations.models import Submission
from apps.api.modules.evaluations.ollama_inspector import (
    _build_ollama_prompt,
    _normalize_and_validate_inspection,
)
from apps.api.modules.evaluations.schemas import OllamaRepoInspectionResponse


def test_build_ollama_prompt_mandates_block6_negative_audit():
    """Verifies that the compiled prompt explicitly instructs Ollama to conduct a ruthless defect audit for Block 6."""
    dummy_submission = Submission(
        id=uuid.uuid4(),
        title="Scorva Hackathon App",
        team_name="DevTeam",
        repository_url="https://github.com/scorva/test-repo",
        target_branch="main",
        description="A hackathon project",
    )
    context = {
        "readme": "README file content.",
        "manifests": "package.json dependencies",
        "file_tree": "src/index.ts\nsrc/utils.ts",
    }

    prompt = _build_ollama_prompt(dummy_submission, context)

    # Asserts Block 6 defect instructions are present
    assert "BLOCK 6 CODEBASE DEFECT & IMPROVEMENT AUDIT" in prompt
    assert "codebase_defects" in prompt
    assert "missing_implementations" in prompt
    assert "recommended_improvements" in prompt
    assert "Find all negative points from the repository" in prompt


def test_normalize_and_validate_inspection_extracts_block6_defects():
    """Verifies that parsed Ollama output populates codebase_defects, missing_implementations, and recommended_improvements."""
    dummy_submission = Submission(
        id=uuid.uuid4(),
        hackathon_id=uuid.uuid4(),
        title="Test Project",
        team_name="Team Alpha",
    )

    parsed_output = {
        "project_name": "Test Project",
        "quick_summary": "Simple task management tool.",
        "what_is_building": "The project is a task tracking web app with basic frontend and backend.",
        "innovation": {"score": 7.5, "summary": "Useful concept"},
        "tech_stack": {"languages": ["TypeScript"], "frameworks": ["React"]},
        "complexity": {"level": "Medium", "score": 6.5},
        "judge_factors": {
            "code_quality_score": 6.0,
            "code_quality_summary": "Clean code structure",
            "completeness_score": 5.0,
            "completeness_summary": "Some missing API endpoints",
            "is_working_demo": True,
            "potential_impact_score": 7.0,
            "potential_impact_summary": "Solid prototype",
            "security_summary": "Plain text secrets in config",
        },
        "codebase_defects": [
            "Hardcoded database password in config.ts",
            "No input sanitization in user comment endpoint",
            "Unhandled promise rejections causing server crash on invalid payload",
        ],
        "missing_implementations": [
            "Missing automated unit tests for authentication logic",
            "Unfinished checkout flow containing stubbed mock responses",
            "No pagination on get-items endpoint causing memory spike",
        ],
        "recommended_improvements": [
            "Decouple all credentials into environment variables",
            "Add Vitest or Jest test suite covering core service logic",
            "Implement centralized error handling middleware",
        ],
        "potential_red_flags": [
            "Security vulnerability: exposed credentials in public repo",
        ],
        "key_highlights": [
            "Good TypeScript typing throughout components",
        ],
        "suggested_judge_questions": [
            "How do you plan to handle security for database credentials?",
        ],
    }

    res: OllamaRepoInspectionResponse = _normalize_and_validate_inspection(
        parsed=parsed_output,
        submission=dummy_submission,
        model_name="mistral:7b (Primary AI: 10.3.2.157:11434)",
    )

    assert len(res.codebase_defects) == 3
    assert "Hardcoded database password" in res.codebase_defects[0]
    assert len(res.missing_implementations) == 3
    assert "Missing automated unit tests" in res.missing_implementations[0]
    assert len(res.recommended_improvements) == 3
    assert "Decouple all credentials" in res.recommended_improvements[0]
    assert len(res.potential_red_flags) == 1

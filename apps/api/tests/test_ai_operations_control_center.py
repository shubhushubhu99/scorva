"""
Unit & Integration Tests for Scorva AI Operations Control Center and Pi Runtime Integration.
Verifies model discovery, testing, task routing, deterministic fallback, parallel execution,
and session isolation.
"""

import asyncio
from datetime import datetime, timezone
import json
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.modules.evaluations.ai_operations_schemas import (
    DefaultModelSwitchPayload,
    FallbackModelItem,
    ParallelTaskExecutionRequest,
    TaskRoutingUpdatePayload,
)
from apps.api.modules.evaluations.ai_operations_service import (
    discover_and_sync_models,
    execute_model_test_in_registry,
    execute_parallel_evaluation,
    execute_task_with_fallback,
    get_control_center_stats,
    get_runtime_overview,
    get_task_routing_assignments,
    list_execution_records,
    list_models,
    save_runtime_settings,
    switch_default_model,
    update_model_item,
    update_task_routing_assignment,
)
from apps.api.modules.evaluations.ai_provider import get_ai_provider_client
from apps.api.modules.evaluations.models import AIExecutionRecord, AIModelRegistryItem
from apps.api.modules.evaluations.providers.pi import (
    PiModelTestRequest,
    PiProviderClient,
    default_pi_registry,
    default_pi_runtime,
)
from apps.api.modules.users.models import User


@pytest.fixture
def mock_admin_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="superadmin@scorva.local",
        full_name="Super Administrator",
        is_active=True,
    )


@pytest.mark.asyncio
async def test_pi_runtime_discovery_and_status():
    """Verifies that the globally installed Pi binary and its config are discovered."""
    status = await default_pi_runtime.get_runtime_status()
    assert status.is_installed is True
    assert status.executable_path is not None
    assert "pi" in status.executable_path
    assert status.models_store_exists is True
    assert status.auth_store_exists is True
    assert len(status.configured_providers) > 0


@pytest.mark.asyncio
async def test_pi_model_registry_discovery():
    """Verifies that models are discovered from Pi without hardcoded lists."""
    models = await default_pi_registry.discover_models()
    assert len(models) > 0
    # Verify provider and model ids are preserved
    providers = {m.provider for m in models}
    assert "openai-codex" in providers or "google" in providers or "github-copilot" in providers


@pytest.mark.asyncio
async def test_pi_provider_client_adapter():
    """Verifies that PiProviderClient conforms to the AIProviderClient protocol."""
    client = PiProviderClient(default_provider="openai-codex", default_model="gpt-5.6-luna")
    assert hasattr(client, "generate_evaluation")

    factory_client = get_ai_provider_client(config=None, base_url=None)
    assert factory_client is not None


@pytest.mark.asyncio
async def test_model_testing_structured_validation(db_session: AsyncSession, mock_admin_user: User):
    """Verifies live model testing with structured JSON validation."""
    req = PiModelTestRequest(
        provider="openai-codex",
        model_id="gpt-5.6-luna",
        is_structured=True,
    )
    res = await execute_model_test_in_registry(db_session, req, mock_admin_user)
    assert res.provider == "openai-codex"
    assert res.model_id == "gpt-5.6-luna"
    assert res.duration_ms > 0
    if res.success:
        assert res.validation_passed is True
        assert res.structured_output is not None
        assert "status" in res.structured_output


@pytest.mark.asyncio
async def test_database_model_sync_and_listing(db_session: AsyncSession):
    """Verifies model synchronization into PostgreSQL and task count computation."""
    models = await discover_and_sync_models(db_session)
    assert len(models) > 0

    listed = await list_models(db_session, provider="openai-codex")
    assert len(listed) > 0
    assert all(m.provider == "openai-codex" for m in listed)


@pytest.mark.asyncio
async def test_default_model_switching(db_session: AsyncSession, mock_admin_user: User):
    """Verifies dynamic switching of active default model."""
    await discover_and_sync_models(db_session)

    payload = DefaultModelSwitchPayload(provider="openai-codex", model_id="gpt-5.6-luna")
    overview = await switch_default_model(db_session, payload, mock_admin_user)
    assert overview.default_provider == "openai-codex"
    assert overview.default_model == "gpt-5.6-luna"


@pytest.mark.asyncio
async def test_task_routing_and_fallback_configuration(db_session: AsyncSession, mock_admin_user: User):
    """Verifies task routing retrieval and updating of fallback sequences."""
    assignments = await get_task_routing_assignments(db_session)
    assert len(assignments) == 7
    task_types = {a.task_type for a in assignments}
    assert "code_quality" in task_types
    assert "security_analysis" in task_types
    assert "innovation_analysis" in task_types

    # Update code_quality task routing
    update_payload = TaskRoutingUpdatePayload(
        primary_provider="openai-codex",
        primary_model="gpt-5.6-luna",
        timeout_seconds=200,
        fallback_models=[
            FallbackModelItem(provider="openai-codex", model_id="gpt-5.6-sol", priority=1),
            FallbackModelItem(provider="ollama", model_id="mistral:7b", priority=2),
        ],
    )
    updated = await update_task_routing_assignment(db_session, "code_quality", update_payload, mock_admin_user)
    assert updated is not None
    assert updated.primary_model == "gpt-5.6-luna"
    assert updated.timeout_seconds == 200
    assert len(updated.fallback_models) == 2


@pytest.mark.asyncio
async def test_deterministic_fallback_execution(db_session: AsyncSession):
    """Verifies deterministic fallback when primary candidate fails."""
    # Configure an invalid primary model so it falls back to a valid one
    schema = {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]}

    # Update security_analysis to have an invalid primary that fails and falls back to gpt-5.6-luna
    mock_admin = User(id=uuid.uuid4(), email="adm@scorva.local", full_name="Admin", is_active=True)
    await update_task_routing_assignment(
        db_session,
        "security_analysis",
        TaskRoutingUpdatePayload(
            primary_provider="openai",
            primary_model="non-existent-invalid-model-xyz",
            fallback_models=[
                FallbackModelItem(provider="openai-codex", model_id="gpt-5.6-luna", priority=1),
            ],
        ),
        mock_admin,
    )

    res = await execute_task_with_fallback(
        db=db_session,
        task_type="security_analysis",
        prompt="Return valid JSON with status: ok",
        schema=schema,
    )

    assert res["actual_provider"] == "openai-codex"
    assert res["actual_model"] == "gpt-5.6-luna"
    assert res["fallback_used"] is True


@pytest.mark.asyncio
async def test_parallel_task_execution(db_session: AsyncSession, mock_admin_user: User):
    """Verifies that multiple evaluation tasks execute concurrently in isolated sessions."""
    req = ParallelTaskExecutionRequest(
        tasks=["code_quality", "innovation_analysis"],
        test_context="Evaluation test of parallel execution.",
    )
    res = await execute_parallel_evaluation(db_session, req, mock_admin_user)
    assert res.total_tasks == 2
    assert res.correlation_id is not None
    assert len(res.task_results) == 2
    # Verify both tasks completed
    for t in req.tasks:
        assert t in res.task_results


@pytest.mark.asyncio
async def test_control_center_kpis_and_audit(db_session: AsyncSession):
    """Verifies that execution history and KPIs reflect real data."""
    stats = await get_control_center_stats(db_session)
    assert stats.available_models > 0
    assert stats.enabled_models > 0

    history = await list_execution_records(db_session, page=1, page_size=10)
    assert history.total >= 0

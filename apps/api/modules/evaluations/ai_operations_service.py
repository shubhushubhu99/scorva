"""
Scorva AI Operations Control Center Service.
Manages Model Discovery, Model Testing, Dynamic Task Routing, Ordered Fallback Execution,
Parallel Multi-Task Execution, Execution History Audit, and Runtime Settings.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import uuid

import httpx
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.core.redis import get_redis_client
from apps.api.core.ssrf_guard import allow_internal_ai_host
from apps.api.modules.configuration.models import ConfigurationSetting
from apps.api.modules.evaluations.ai_operations_schemas import (
    AIEndpointConfig,
    AIEndpointProbeResponse,
    AIExecutionListResponse,
    AIExecutionRecordDetail,
    AIExecutionRecordSummary,
    AIModelItem,
    AIModelUpdatePayload,
    AIOperationsControlCenterStats,
    AIOperationsStatsResponse,
    AIRoutingConfigRequest,
    AIRoutingConfigResponse,
    AIRuntimeOverviewResponse,
    AIRuntimeSettingsUpdate,
    DefaultModelSwitchPayload,
    FallbackModelItem,
    ParallelTaskExecutionRequest,
    ParallelTaskExecutionResponse,
    ProviderStatusItem,
    TaskRoutingAssignment,
    TaskRoutingUpdatePayload,
)
from apps.api.modules.evaluations.models import (
    AIExecutionRecord,
    AIModelRegistryItem,
    AIModelTestRecord,
    AITaskModelAssignment,
    SubmissionRepoInspection,
)
from apps.api.modules.evaluations.providers.pi import (
    PiModelTestRequest,
    PiModelTestResponse,
    PiProviderClient,
    default_pi_registry,
    default_pi_runtime,
    default_session_manager,
)
from apps.api.modules.users.models import User

logger = logging.getLogger("scorva.ai_operations.service")

REDIS_AI_ROUTING_KEY = "scorva:ai_routing_config"
REDIS_TASK_ROUTING_PREFIX = "scorva:ai_task_routing:"
REDIS_RUNTIME_SETTINGS_KEY = "scorva:ai_runtime_settings"
DB_SETTING_KEY = "ai.routing.config"
DB_RUNTIME_KEY = "ai.runtime.settings"

# The 7 canonical evaluation tasks
INITIAL_TASK_DEFINITIONS = [
    {
        "task_type": "repository_understanding",
        "name": "Repository Understanding",
        "description": "Understand project structure, manifests, implementation, and core capabilities.",
        "primary_provider": "openai-codex",
        "primary_model": "gpt-5.6-luna",
        "secondary_provider": "ollama",
        "secondary_model": "mistral:7b",
        "fallback_models": [
            {"provider": "openai-codex", "model_id": "gpt-5.6-sol", "priority": 1},
            {"provider": "ollama", "model_id": "mistral:7b", "priority": 2},
        ],
    },
    {
        "task_type": "code_quality",
        "name": "Code Quality",
        "description": "Evaluate maintainability, design patterns, architecture, and code cleanliness.",
        "primary_provider": "openai-codex",
        "primary_model": "gpt-5.6-luna",
        "secondary_provider": "ollama",
        "secondary_model": "mistral:7b",
        "fallback_models": [
            {"provider": "openai-codex", "model_id": "gpt-5.6-sol", "priority": 1},
            {"provider": "ollama", "model_id": "mistral:7b", "priority": 2},
        ],
    },
    {
        "task_type": "security_analysis",
        "name": "Security Analysis",
        "description": "Identify relevant security weaknesses, credential exposure, and architectural risks.",
        "primary_provider": "openai-codex",
        "primary_model": "gpt-5.6-luna",
        "secondary_provider": "ollama",
        "secondary_model": "mistral:7b",
        "fallback_models": [
            {"provider": "openai-codex", "model_id": "gpt-5.6-sol", "priority": 1},
            {"provider": "ollama", "model_id": "mistral:7b", "priority": 2},
        ],
    },
    {
        "task_type": "innovation_analysis",
        "name": "Innovation Analysis",
        "description": "Assess originality, technical complexity, novelty, and creative differentiation.",
        "primary_provider": "openai-codex",
        "primary_model": "gpt-5.6-luna",
        "secondary_provider": "ollama",
        "secondary_model": "qwen2.5:3b",
        "fallback_models": [
            {"provider": "openai-codex", "model_id": "gpt-5.6-sol", "priority": 1},
            {"provider": "ollama", "model_id": "qwen2.5:3b", "priority": 2},
        ],
    },
    {
        "task_type": "requirements_assessment",
        "name": "Requirements Assessment",
        "description": "Compare implemented submission features against hackathon problem statements.",
        "primary_provider": "openai-codex",
        "primary_model": "gpt-5.6-luna",
        "secondary_provider": "ollama",
        "secondary_model": "mistral:7b",
        "fallback_models": [
            {"provider": "openai-codex", "model_id": "gpt-5.6-sol", "priority": 1},
            {"provider": "ollama", "model_id": "mistral:7b", "priority": 2},
        ],
    },
    {
        "task_type": "evidence_analysis",
        "name": "Evidence Analysis",
        "description": "Analyze supporting repository evidence, commits, test cases, and file hierarchy.",
        "primary_provider": "openai-codex",
        "primary_model": "gpt-5.6-luna",
        "secondary_provider": "ollama",
        "secondary_model": "mistral:7b",
        "fallback_models": [
            {"provider": "openai-codex", "model_id": "gpt-5.6-sol", "priority": 1},
            {"provider": "ollama", "model_id": "mistral:7b", "priority": 2},
        ],
    },
    {
        "task_type": "evaluation_synthesis",
        "name": "Evaluation Synthesis",
        "description": "Combine validated task results into a coherent, structured assessment for judges.",
        "primary_provider": "openai-codex",
        "primary_model": "gpt-5.6-luna",
        "secondary_provider": "ollama",
        "secondary_model": "mistral:7b",
        "fallback_models": [
            {"provider": "openai-codex", "model_id": "gpt-5.6-sol", "priority": 1},
            {"provider": "ollama", "model_id": "mistral:7b", "priority": 2},
        ],
    },
]


# ==============================================================================
# Runtime Overview & Settings
# ==============================================================================

async def get_runtime_overview(db: AsyncSession) -> AIRuntimeOverviewResponse:
    """
    Returns runtime health, connection status, and model counts across Pi, Ollama, and Mock.
    """
    # 1. Pi status probe
    pi_status = await default_pi_runtime.get_runtime_status()

    # Query last successful execution for Pi
    pi_last_exec_stmt = (
        select(AIExecutionRecord.completed_at)
        .where(AIExecutionRecord.status.in_(["completed", "fallback_used"]))
        .where(AIExecutionRecord.actual_provider != "ollama")
        .order_by(AIExecutionRecord.completed_at.desc())
        .limit(1)
    )
    pi_last_exec = (await db.execute(pi_last_exec_stmt)).scalar_one_or_none()

    pi_provider_item = ProviderStatusItem(
        name="pi",
        display_name="Pi AI Runtime (Global)",
        is_available=pi_status.is_installed,
        connection_status="connected" if pi_status.is_installed else "offline",
        version=pi_status.version,
        config_path_or_url=pi_status.config_dir,
        last_successful_execution_at=pi_last_exec,
        last_error=None,
        total_models=pi_status.total_discovered_models,
    )

    # 2. Ollama probe
    ollama_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_online = False
    ollama_version = None
    ollama_models_count = 0
    ollama_err = None

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            v_res = await client.get(f"{ollama_url.rstrip('/')}/api/version")
            if v_res.status_code == 200:
                ollama_online = True
                ollama_version = v_res.json().get("version")
            t_res = await client.get(f"{ollama_url.rstrip('/')}/api/tags")
            if t_res.status_code == 200:
                ollama_models_count = len(t_res.json().get("models", []))
    except Exception as exc:
        ollama_err = str(exc)

    ollama_provider_item = ProviderStatusItem(
        name="ollama",
        display_name="Ollama Local Inference",
        is_available=ollama_online,
        connection_status="connected" if ollama_online else "offline",
        version=ollama_version,
        config_path_or_url=ollama_url,
        last_error=ollama_err if not ollama_online else None,
        total_models=ollama_models_count,
    )

    # 3. Mock provider
    mock_provider_item = ProviderStatusItem(
        name="mock",
        display_name="Deterministic Mock Provider (CI / Testing)",
        is_available=True,
        connection_status="connected",
        version="1.0.0",
        config_path_or_url="memory://canned-evaluations",
        total_models=1,
    )

    # 4. Dynamic settings
    runtime_settings = await get_runtime_settings(db)

    return AIRuntimeOverviewResponse(
        providers=[pi_provider_item, ollama_provider_item, mock_provider_item],
        pi_status=pi_status,
        global_max_concurrency=runtime_settings.get("global_max_concurrency", 10),
        default_timeout_seconds=runtime_settings.get("default_timeout_seconds", 180),
        default_provider=runtime_settings.get("default_provider", "openai-codex"),
        default_model=runtime_settings.get("default_model", "gpt-5.6-luna"),
        updated_at=datetime.now(timezone.utc),
    )


async def get_runtime_settings(db: AsyncSession) -> Dict[str, Any]:
    """Retrieves dynamic runtime settings from Redis/DB."""
    try:
        redis = await get_redis_client()
        cached = await redis.get(REDIS_RUNTIME_SETTINGS_KEY)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    try:
        stmt = select(ConfigurationSetting).where(ConfigurationSetting.key == DB_RUNTIME_KEY)
        setting = (await db.execute(stmt)).scalar_one_or_none()
        if setting and setting.current_value:
            data = json.loads(setting.current_value)
            return data
    except Exception:
        pass

    # Defaults
    return {
        "global_max_concurrency": 10,
        "default_timeout_seconds": 180,
        "default_provider": "openai-codex",
        "default_model": "gpt-5.6-luna",
    }


async def save_runtime_settings(
    db: AsyncSession,
    payload: AIRuntimeSettingsUpdate,
    actor: User,
) -> Dict[str, Any]:
    """Persists dynamic runtime settings without requiring backend restart."""
    current = await get_runtime_settings(db)
    if payload.global_max_concurrency is not None:
        current["global_max_concurrency"] = payload.global_max_concurrency
    if payload.default_timeout_seconds is not None:
        current["default_timeout_seconds"] = payload.default_timeout_seconds
    if payload.default_provider is not None:
        current["default_provider"] = payload.default_provider
    if payload.default_model is not None:
        current["default_model"] = payload.default_model

    serialized = json.dumps(current)

    try:
        stmt = select(ConfigurationSetting).where(ConfigurationSetting.key == DB_RUNTIME_KEY)
        setting = (await db.execute(stmt)).scalar_one_or_none()
        if setting:
            setting.current_value = serialized
            setting.updated_at = datetime.now(timezone.utc)
            setting.updated_by_user_id = actor.id
            setting.version = (setting.version or 1) + 1
        else:
            setting = ConfigurationSetting(
                key=DB_RUNTIME_KEY,
                tier="tier_1",
                data_type="json",
                default_value=serialized,
                current_value=serialized,
                allow_org_override=False,
                allow_hackathon_override=False,
                is_configurable=True,
                version=1,
                updated_at=datetime.now(timezone.utc),
                updated_by_user_id=actor.id,
            )
            db.add(setting)
        await db.commit()
    except Exception as exc:
        logger.error("Failed saving runtime settings to DB: %s", exc)
        await db.rollback()

    try:
        redis = await get_redis_client()
        await redis.set(REDIS_RUNTIME_SETTINGS_KEY, serialized, ex=86400)
    except Exception:
        pass

    return current


# ==============================================================================
# Model Registry & Discovery
# ==============================================================================

async def discover_and_sync_models(
    db: AsyncSession,
    force_refresh: bool = False,
) -> List[AIModelItem]:
    """
    Discovers models from Pi runtime and synchronizes them with PostgreSQL ai_model_registry.
    Preserves user overrides (is_enabled, display_name, last test metrics).
    """
    discovered_pi_models = await default_pi_registry.discover_models(force_refresh=force_refresh)

    # Fetch existing DB records
    existing_stmt = select(AIModelRegistryItem)
    existing_records = {
        f"{r.provider}:{r.model_id}": r
        for r in (await db.execute(existing_stmt)).scalars().all()
    }

    runtime_settings = await get_runtime_settings(db)
    active_default_prov = runtime_settings.get("default_provider", "openai-codex")
    active_default_mod = runtime_settings.get("default_model", "gpt-5.6-luna")

    for dm in discovered_pi_models:
        key = f"{dm.provider}:{dm.id}"
        is_def = (dm.provider == active_default_prov and dm.id == active_default_mod)

        input_c = None
        output_c = None
        if dm.cost:
            if "input" in dm.cost:
                input_c = Decimal(str(dm.cost["input"]))
            if "output" in dm.cost:
                output_c = Decimal(str(dm.cost["output"]))

        caps = {
            "reasoning": dm.reasoning,
            "modalities": dm.input_modalities,
        }

        if key in existing_records:
            item = existing_records[key]
            item.context_window = dm.context_window
            item.max_tokens = dm.max_tokens
            item.input_cost = input_c
            item.output_cost = output_c
            item.capabilities = caps
            item.is_available = True
            if is_def:
                item.is_default = True
        else:
            item = AIModelRegistryItem(
                id=uuid.uuid4(),
                provider=dm.provider,
                model_id=dm.id,
                display_name=dm.name,
                context_window=dm.context_window,
                max_tokens=dm.max_tokens,
                input_cost=input_c,
                output_cost=output_c,
                capabilities=caps,
                is_available=True,
                is_enabled=True,
                is_default=is_def,
                last_test_status="untested",
            )
            db.add(item)
            existing_records[key] = item

    await db.commit()
    return await list_models(db)


async def list_models(
    db: AsyncSession,
    provider: Optional[str] = None,
    search: Optional[str] = None,
    enabled_only: Optional[bool] = None,
) -> List[AIModelItem]:
    """Lists registered models with task assignment counts and filter support."""
    # Ensure seed discovery if table is completely empty
    count_stmt = select(func.count(AIModelRegistryItem.id))
    total_count = (await db.execute(count_stmt)).scalar() or 0
    if total_count == 0:
        await discover_and_sync_models(db)

    # Fetch task assignment counts
    task_stmt = select(AITaskModelAssignment)
    assignments = (await db.execute(task_stmt)).scalars().all()
    model_task_counts: Dict[str, int] = {}
    for a in assignments:
        primary_key = f"{a.primary_provider}:{a.primary_model}"
        model_task_counts[primary_key] = model_task_counts.get(primary_key, 0) + 1
        if a.secondary_provider and a.secondary_model:
            sec_key = f"{a.secondary_provider}:{a.secondary_model}"
            model_task_counts[sec_key] = model_task_counts.get(sec_key, 0) + 1
        if a.fallback_models:
            for fb in a.fallback_models:
                fb_key = f"{fb.get('provider')}:{fb.get('model_id')}"
                model_task_counts[fb_key] = model_task_counts.get(fb_key, 0) + 1

    # Query registry
    query = select(AIModelRegistryItem)
    if provider:
        query = query.where(AIModelRegistryItem.provider == provider)
    if enabled_only is not None:
        query = query.where(AIModelRegistryItem.is_enabled == enabled_only)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                AIModelRegistryItem.display_name.ilike(search_pattern),
                AIModelRegistryItem.model_id.ilike(search_pattern),
                AIModelRegistryItem.provider.ilike(search_pattern),
            )
        )

    query = query.order_by(
        AIModelRegistryItem.is_default.desc(),
        AIModelRegistryItem.is_enabled.desc(),
        AIModelRegistryItem.provider.asc(),
        AIModelRegistryItem.display_name.asc(),
    )

    rows = (await db.execute(query)).scalars().all()
    results: List[AIModelItem] = []
    for r in rows:
        key = f"{r.provider}:{r.model_id}"
        results.append(
            AIModelItem(
                id=str(r.id),
                provider=r.provider,
                model_id=r.model_id,
                display_name=r.display_name,
                context_window=r.context_window,
                max_tokens=r.max_tokens,
                input_cost=float(r.input_cost) if r.input_cost is not None else None,
                output_cost=float(r.output_cost) if r.output_cost is not None else None,
                capabilities=r.capabilities,
                is_available=r.is_available,
                is_enabled=r.is_enabled,
                is_default=r.is_default,
                assigned_tasks_count=model_task_counts.get(key, 0),
                last_tested_at=r.last_tested_at,
                last_test_status=r.last_test_status,
                last_test_latency_ms=r.last_test_latency_ms,
                last_test_error=r.last_test_error,
            )
        )
    return results


async def update_model_item(
    db: AsyncSession,
    model_id: str,
    payload: AIModelUpdatePayload,
    actor: User,
) -> Optional[AIModelItem]:
    """Enables/disables a model or updates its display name."""
    try:
        m_uuid = uuid.UUID(model_id)
        stmt = select(AIModelRegistryItem).where(AIModelRegistryItem.id == m_uuid)
    except ValueError:
        # Search by model_id string
        stmt = select(AIModelRegistryItem).where(AIModelRegistryItem.model_id == model_id)

    item = (await db.execute(stmt)).scalar_one_or_none()
    if not item:
        return None

    if payload.is_enabled is not None:
        item.is_enabled = payload.is_enabled
    if payload.display_name is not None:
        item.display_name = payload.display_name

    item.updated_at = datetime.now(timezone.utc)
    await db.commit()

    all_models = await list_models(db)
    for m in all_models:
        if m.id == str(item.id):
            return m
    return None


async def switch_default_model(
    db: AsyncSession,
    payload: DefaultModelSwitchPayload,
    actor: User,
) -> AIRuntimeOverviewResponse:
    """
    Switches the platform active default model immediately without restarting Scorva.
    """
    # 1. Update in ai_model_registry table
    clear_stmt = update(AIModelRegistryItem).values(is_default=False)
    await db.execute(clear_stmt)

    set_stmt = (
        update(AIModelRegistryItem)
        .where(
            AIModelRegistryItem.provider == payload.provider,
            AIModelRegistryItem.model_id == payload.model_id,
        )
        .values(is_default=True, is_enabled=True)
    )
    await db.execute(set_stmt)
    await db.commit()

    # 2. Persist in runtime settings
    await save_runtime_settings(
        db=db,
        payload=AIRuntimeSettingsUpdate(
            default_provider=payload.provider,
            default_model=payload.model_id,
        ),
        actor=actor,
    )

    logger.info("Switched default AI model to %s/%s by user %s", payload.provider, payload.model_id, actor.id)
    return await get_runtime_overview(db)


async def execute_model_test_in_registry(
    db: AsyncSession,
    request: PiModelTestRequest,
    actor: Optional[User] = None,
) -> PiModelTestResponse:
    """
    Tests an individual model using the actual runtime adapter.
    Records the test in ai_model_test_records and updates model health in ai_model_registry.
    """
    test_result = await default_pi_registry.test_model(request)

    # 1. Update AIModelRegistryItem
    stmt = select(AIModelRegistryItem).where(
        AIModelRegistryItem.provider == request.provider,
        AIModelRegistryItem.model_id == request.model_id,
    )
    item = (await db.execute(stmt)).scalar_one_or_none()
    if item:
        item.last_tested_at = datetime.now(timezone.utc)
        item.last_test_status = "success" if test_result.success else "failed"
        item.last_test_latency_ms = test_result.duration_ms
        item.last_test_error = test_result.error_message
        item.is_available = test_result.success

    # 2. Persist test record if actor exists in DB
    actor_id = None
    if actor and actor.id:
        user_check = (await db.execute(select(User.id).where(User.id == actor.id))).scalar_one_or_none()
        if user_check:
            actor_id = actor.id

    total_tokens = test_result.usage.total_tokens if test_result.usage else None
    test_record = AIModelTestRecord(
        id=uuid.uuid4(),
        provider=request.provider,
        model_id=request.model_id,
        prompt=test_result.prompt,
        is_structured=request.is_structured,
        response_text=test_result.response_text,
        structured_output=test_result.structured_output,
        validation_passed=test_result.validation_passed,
        status="success" if test_result.success else "failed",
        duration_ms=test_result.duration_ms,
        tokens_used=total_tokens,
        error_message=test_result.error_message,
        tested_by_user_id=actor_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(test_record)
    await db.commit()

    return test_result


# ==============================================================================
# Task Routing & Fallback Configuration
# ==============================================================================

async def get_task_routing_assignments(db: AsyncSession) -> List[TaskRoutingAssignment]:
    """Retrieves all 7 task routing assignments, seeding initial defaults if needed."""
    stmt = select(AITaskModelAssignment).order_by(AITaskModelAssignment.priority.asc())
    rows = (await db.execute(stmt)).scalars().all()

    if not rows:
        # Seed initial standard tasks
        for defn in INITIAL_TASK_DEFINITIONS:
            record = AITaskModelAssignment(
                id=uuid.uuid4(),
                task_type=defn["task_type"],
                name=defn["name"],
                description=defn["description"],
                is_enabled=True,
                primary_provider=defn["primary_provider"],
                primary_model=defn["primary_model"],
                secondary_provider=defn.get("secondary_provider"),
                secondary_model=defn.get("secondary_model"),
                fallback_models=defn.get("fallback_models", []),
                timeout_seconds=180,
                max_retries=2,
                parallel_enabled=True,
                priority=0,
            )
            db.add(record)
        await db.commit()
        rows = (await db.execute(stmt)).scalars().all()

    results: List[TaskRoutingAssignment] = []
    for r in rows:
        fallbacks: List[FallbackModelItem] = []
        if r.fallback_models:
            for fb in r.fallback_models:
                fallbacks.append(
                    FallbackModelItem(
                        provider=fb.get("provider", ""),
                        model_id=fb.get("model_id", ""),
                        priority=fb.get("priority", 1),
                    )
                )

        results.append(
            TaskRoutingAssignment(
                task_type=r.task_type,
                name=r.name,
                description=r.description,
                is_enabled=r.is_enabled,
                primary_provider=r.primary_provider,
                primary_model=r.primary_model,
                secondary_provider=r.secondary_provider,
                secondary_model=r.secondary_model,
                fallback_models=fallbacks,
                timeout_seconds=r.timeout_seconds,
                max_retries=r.max_retries,
                parallel_enabled=r.parallel_enabled,
                priority=r.priority,
            )
        )
    return results


async def update_task_routing_assignment(
    db: AsyncSession,
    task_type: str,
    payload: TaskRoutingUpdatePayload,
    actor: User,
) -> Optional[TaskRoutingAssignment]:
    """Updates routing and fallback settings for a specific task."""
    stmt = select(AITaskModelAssignment).where(AITaskModelAssignment.task_type == task_type)
    item = (await db.execute(stmt)).scalar_one_or_none()
    if not item:
        return None

    if payload.is_enabled is not None:
        item.is_enabled = payload.is_enabled
    if payload.primary_provider is not None:
        item.primary_provider = payload.primary_provider
    if payload.primary_model is not None:
        item.primary_model = payload.primary_model
    if payload.secondary_provider is not None:
        item.secondary_provider = payload.secondary_provider
    if payload.secondary_model is not None:
        item.secondary_model = payload.secondary_model
    if payload.fallback_models is not None:
        item.fallback_models = [fb.model_dump() for fb in payload.fallback_models]
    if payload.timeout_seconds is not None:
        item.timeout_seconds = payload.timeout_seconds
    if payload.max_retries is not None:
        item.max_retries = payload.max_retries
    if payload.parallel_enabled is not None:
        item.parallel_enabled = payload.parallel_enabled
    if payload.priority is not None:
        item.priority = payload.priority

    item.updated_at = datetime.now(timezone.utc)
    await db.commit()

    # Invalidate Redis cache for task routing
    try:
        redis = await get_redis_client()
        await redis.delete(f"{REDIS_TASK_ROUTING_PREFIX}{task_type}")
    except Exception:
        pass

    all_tasks = await get_task_routing_assignments(db)
    for t in all_tasks:
        if t.task_type == task_type:
            return t
    return None


# ==============================================================================
# Dynamic Execution with Deterministic Fallbacks
# ==============================================================================

async def execute_task_with_fallback(
    db: AsyncSession,
    task_type: str,
    prompt: str,
    schema: Dict[str, Any],
    evaluation_id: Optional[uuid.UUID] = None,
    submission_id: Optional[uuid.UUID] = None,
) -> Dict[str, Any]:
    """
    Executes an evaluation task using its configured primary model.
    If the primary model experiences an eligible failure (offline, timeout, rate limit, parse error),
    deterministically steps through the ordered fallback sequence.
    Persists complete execution and fallback audit records in PostgreSQL.
    """
    # 1. Fetch task assignment
    stmt = select(AITaskModelAssignment).where(AITaskModelAssignment.task_type == task_type)
    assignment = (await db.execute(stmt)).scalar_one_or_none()

    if not assignment:
        # Fallback to default
        primary_provider = "openai-codex"
        primary_model = "gpt-5.6-luna"
        timeout_seconds = 180
        fallback_chain: List[Tuple[str, str]] = []
    else:
        primary_provider = assignment.primary_provider
        primary_model = assignment.primary_model
        timeout_seconds = assignment.timeout_seconds
        fallback_chain = []
        if assignment.fallback_models:
            for fb in sorted(assignment.fallback_models, key=lambda x: x.get("priority", 1)):
                p = fb.get("provider")
                m = fb.get("model_id")
                if p and m and (p, m) != (primary_provider, primary_model):
                    if (p, m) not in fallback_chain:
                        fallback_chain.append((p, m))

    candidates: List[Tuple[str, str]] = [(primary_provider, primary_model)] + fallback_chain

    t_start = datetime.now(timezone.utc)
    last_error = None
    fallback_used = False
    fallback_reason = None
    attempt_count = 0

    client = PiProviderClient()

    for idx, (cand_provider, cand_model) in enumerate(candidates):
        attempt_count += 1
        if idx > 0:
            fallback_used = True
            fallback_reason = f"Primary failed: {last_error}"

        logger.info(
            "Task '%s' attempt %d: invoking %s/%s (fallback=%s)",
            task_type,
            attempt_count,
            cand_provider,
            cand_model,
            fallback_used,
        )

        try:
            detailed = await client.generate_evaluation_detailed(
                prompt=prompt,
                schema=schema,
                model_name=f"{cand_provider}/{cand_model}",
                timeout_seconds=float(timeout_seconds),
            )

            # Record success in AIExecutionRecord
            usage_data = detailed.get("usage") or {}
            tokens = usage_data.get("total_tokens")
            cost_val = None
            if "cost" in usage_data and isinstance(usage_data["cost"], dict):
                cost_val = Decimal(str(usage_data["cost"].get("total", 0.0)))

            exec_record = AIExecutionRecord(
                id=uuid.uuid4(),
                evaluation_id=evaluation_id,
                submission_id=submission_id,
                task_type=task_type,
                primary_provider=primary_provider,
                primary_model=primary_model,
                actual_provider=cand_provider,
                actual_model=cand_model,
                status="fallback_used" if fallback_used else "completed",
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                attempt_count=attempt_count,
                duration_ms=detailed.get("duration_ms", 0),
                prompt_tokens=usage_data.get("input"),
                completion_tokens=usage_data.get("output"),
                total_tokens=tokens,
                estimated_cost=cost_val,
                prompt_preview=prompt[:300],
                output_payload=json.loads(json.dumps(detailed.get("output"), default=str)) if detailed.get("output") else None,
                validation_passed=True,
                started_at=t_start,
                completed_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
            )
            db.add(exec_record)
            await db.commit()

            return {
                "output": detailed["output"],
                "actual_provider": cand_provider,
                "actual_model": cand_model,
                "fallback_used": fallback_used,
                "duration_ms": detailed.get("duration_ms", 0),
                "tokens": tokens,
            }

        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "Task '%s' candidate %s/%s failed: %s",
                task_type,
                cand_provider,
                cand_model,
                last_error,
            )

    # All candidates exhausted: record failure
    fail_record = AIExecutionRecord(
        id=uuid.uuid4(),
        evaluation_id=evaluation_id,
        submission_id=submission_id,
        task_type=task_type,
        primary_provider=primary_provider,
        primary_model=primary_model,
        actual_provider=candidates[-1][0],
        actual_model=candidates[-1][1],
        status="failed",
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        attempt_count=attempt_count,
        duration_ms=0,
        prompt_preview=prompt[:300],
        validation_passed=False,
        error_message=last_error,
        started_at=t_start,
        completed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db.add(fail_record)
    await db.commit()

    raise RuntimeError(
        f"All configured model candidates exhausted for task '{task_type}'. Last error: {last_error}"
    )


# ==============================================================================
# Parallel Model Execution Engine
# ==============================================================================

async def execute_parallel_evaluation(
    db: AsyncSession,
    request: ParallelTaskExecutionRequest,
    actor: User,
) -> ParallelTaskExecutionResponse:
    """
    Executes multiple evaluation tasks in parallel with strict process isolation.
    Guarantees that a failure in one model does not cancel unrelated tasks.
    """
    correlation_id = str(uuid.uuid4())
    t0 = time.perf_counter()

    sample_context = (
        request.test_context
        or "Project Scorva: Next.js + FastAPI + Postgres hackathon evaluation engine. "
        "Implements deterministic scoring, cryptographic hashing, and automated rubric grading."
    )

    sample_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "score": {"type": "number"},
            "summary": {"type": "string"},
            "strengths": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["status", "score", "summary"],
    }

    async def _run_single_task(task_type: str) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
        task_prompt = (
            f"Perform evaluation for task category: {task_type}.\n"
            f"Context: {sample_context}\n"
            "Return valid JSON containing status, score (0-100), summary, and strengths array."
        )
        try:
            res = await execute_task_with_fallback(
                db=db,
                task_type=task_type,
                prompt=task_prompt,
                schema=sample_schema,
            )
            return task_type, res, None
        except Exception as exc:
            logger.error("Parallel task '%s' failed: %s", task_type, exc)
            return task_type, None, str(exc)

    # Launch all tasks in parallel
    task_futures = [_run_single_task(t) for t in request.tasks]
    results = await asyncio.gather(*task_futures, return_exceptions=False)

    total_duration_ms = int((time.perf_counter() - t0) * 1000)
    task_results: Dict[str, Any] = {}
    successful = 0
    failed = 0

    for task_type, data, err in results:
        if err or data is None:
            failed += 1
            task_results[task_type] = {"status": "failed", "error": err}
        else:
            successful += 1
            task_results[task_type] = {
                "status": "completed",
                "output": data.get("output"),
                "provider": data.get("actual_provider"),
                "model": data.get("actual_model"),
                "fallback_used": data.get("fallback_used"),
                "duration_ms": data.get("duration_ms"),
            }

    # Fetch recently created executions for this run
    recent_execs = await list_execution_records(db, page=1, page_size=len(request.tasks))

    return ParallelTaskExecutionResponse(
        correlation_id=correlation_id,
        total_tasks=len(request.tasks),
        successful_tasks=successful,
        failed_tasks=failed,
        total_duration_ms=total_duration_ms,
        task_results=task_results,
        executions=recent_execs.items,
    )


# ==============================================================================
# Execution History & Monitoring
# ==============================================================================

async def list_execution_records(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 25,
    task_type: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> AIExecutionListResponse:
    """Retrieves paginated execution audit history with filters."""
    query = select(AIExecutionRecord)

    if task_type:
        query = query.where(AIExecutionRecord.task_type == task_type)
    if provider:
        query = query.where(AIExecutionRecord.actual_provider == provider)
    if model:
        query = query.where(AIExecutionRecord.actual_model == model)
    if status:
        query = query.where(AIExecutionRecord.status == status)
    if search:
        search_pat = f"%{search}%"
        query = query.where(
            or_(
                AIExecutionRecord.task_type.ilike(search_pat),
                AIExecutionRecord.actual_model.ilike(search_pat),
                AIExecutionRecord.primary_model.ilike(search_pat),
                AIExecutionRecord.error_message.ilike(search_pat),
            )
        )

    # Count total
    count_stmt = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(AIExecutionRecord.created_at.desc()).offset(offset).limit(page_size)
    rows = (await db.execute(query)).scalars().all()

    items = [
        AIExecutionRecordSummary(
            id=str(r.id),
            evaluation_id=str(r.evaluation_id) if r.evaluation_id else None,
            submission_id=str(r.submission_id) if r.submission_id else None,
            task_type=r.task_type,
            primary_provider=r.primary_provider,
            primary_model=r.primary_model,
            actual_provider=r.actual_provider,
            actual_model=r.actual_model,
            status=r.status,
            fallback_used=r.fallback_used,
            fallback_reason=r.fallback_reason,
            attempt_count=r.attempt_count,
            duration_ms=r.duration_ms,
            total_tokens=r.total_tokens,
            estimated_cost=float(r.estimated_cost) if r.estimated_cost is not None else None,
            validation_passed=r.validation_passed,
            error_message=r.error_message,
            created_at=r.created_at,
        )
        for r in rows
    ]

    return AIExecutionListResponse(
        total=total,
        items=items,
        page=page,
        page_size=page_size,
    )


async def get_execution_record_detail(
    db: AsyncSession,
    execution_id: str,
) -> Optional[AIExecutionRecordDetail]:
    """Retrieves full detail of a specific model execution."""
    try:
        e_uuid = uuid.UUID(execution_id)
    except ValueError:
        return None

    stmt = select(AIExecutionRecord).where(AIExecutionRecord.id == e_uuid)
    r = (await db.execute(stmt)).scalar_one_or_none()
    if not r:
        return None

    return AIExecutionRecordDetail(
        id=str(r.id),
        evaluation_id=str(r.evaluation_id) if r.evaluation_id else None,
        submission_id=str(r.submission_id) if r.submission_id else None,
        task_type=r.task_type,
        primary_provider=r.primary_provider,
        primary_model=r.primary_model,
        actual_provider=r.actual_provider,
        actual_model=r.actual_model,
        status=r.status,
        fallback_used=r.fallback_used,
        fallback_reason=r.fallback_reason,
        attempt_count=r.attempt_count,
        duration_ms=r.duration_ms,
        prompt_tokens=r.prompt_tokens,
        completion_tokens=r.completion_tokens,
        total_tokens=r.total_tokens,
        estimated_cost=float(r.estimated_cost) if r.estimated_cost is not None else None,
        prompt_preview=r.prompt_preview,
        output_payload=r.output_payload,
        validation_passed=r.validation_passed,
        validation_errors=r.validation_errors,
        error_message=r.error_message,
        started_at=r.started_at,
        completed_at=r.completed_at,
        created_at=r.created_at,
    )


async def get_control_center_stats(db: AsyncSession) -> AIOperationsControlCenterStats:
    """Aggregates comprehensive KPIs across models, executions, fallbacks, and token costs."""
    # Models metrics
    m_total_stmt = select(func.count(AIModelRegistryItem.id))
    m_total = (await db.execute(m_total_stmt)).scalar() or 0

    m_enabled_stmt = select(func.count(AIModelRegistryItem.id)).where(AIModelRegistryItem.is_enabled == True)
    m_enabled = (await db.execute(m_enabled_stmt)).scalar() or 0

    # Executions metrics
    success_stmt = select(func.count(AIExecutionRecord.id)).where(AIExecutionRecord.status == "completed")
    success_count = (await db.execute(success_stmt)).scalar() or 0

    fallback_stmt = select(func.count(AIExecutionRecord.id)).where(AIExecutionRecord.status == "fallback_used")
    fallback_count = (await db.execute(fallback_stmt)).scalar() or 0

    failed_stmt = select(func.count(AIExecutionRecord.id)).where(AIExecutionRecord.status == "failed")
    failed_count = (await db.execute(failed_stmt)).scalar() or 0

    avg_time_stmt = select(func.avg(AIExecutionRecord.duration_ms)).where(AIExecutionRecord.duration_ms > 0)
    avg_time = (await db.execute(avg_time_stmt)).scalar() or 0

    # Token & cost aggregations
    sum_tokens_stmt = select(func.sum(AIExecutionRecord.total_tokens)).where(AIExecutionRecord.total_tokens > 0)
    sum_tokens = (await db.execute(sum_tokens_stmt)).scalar()

    sum_cost_stmt = select(func.sum(AIExecutionRecord.estimated_cost)).where(AIExecutionRecord.estimated_cost > 0)
    sum_cost = (await db.execute(sum_cost_stmt)).scalar()

    total_evals = success_count + fallback_count + failed_count
    avg_tokens = int(sum_tokens / total_evals) if sum_tokens and total_evals > 0 else None

    # Recent activity
    recent_list = await list_execution_records(db, page=1, page_size=10)

    return AIOperationsControlCenterStats(
        available_models=m_total,
        enabled_models=m_enabled,
        active_executions=0,
        successful_executions=success_count,
        failed_executions=failed_count,
        fallback_executions=fallback_count,
        average_execution_time_ms=int(avg_time),
        total_tokens_consumed=sum_tokens,
        estimated_total_cost=float(sum_cost) if sum_cost is not None else None,
        average_tokens_per_eval=avg_tokens,
        recent_executions=recent_list.items,
    )


# ==============================================================================
# Legacy Endpoints (Preserved for Backward Compatibility)
# ==============================================================================

DEFAULT_ENDPOINTS = [
    AIEndpointConfig(
        id="primary-remote",
        name="Remote GPU Ollama 1 (Primary - 10.3.2.157)",
        url="http://10.3.2.157:11434",
        role="primary",
        is_enabled=True,
        model_name="mistral:7b",
        timeout_seconds=240,
        is_custom=False,
    ),
    AIEndpointConfig(
        id="secondary-remote-2",
        name="Remote GPU Ollama 2 (Secondary Remote - 10.3.2.158)",
        url="http://10.3.2.158:11434",
        role="secondary",
        is_enabled=True,
        model_name="mistral:7b",
        timeout_seconds=240,
        is_custom=False,
    ),
    AIEndpointConfig(
        id="local-fallback",
        name="Local Machine Ollama (Secondary Local)",
        url="http://localhost:11434",
        role="secondary",
        is_enabled=True,
        model_name="qwen2.5:3b",
        timeout_seconds=180,
        is_custom=False,
    ),
]


def _build_default_routing_response() -> AIRoutingConfigResponse:
    return AIRoutingConfigResponse(
        endpoints=DEFAULT_ENDPOINTS,
        primary_endpoint_id="primary-remote",
        secondary_endpoint_id="local-fallback",
        primary_url="http://10.3.2.157:11434",
        secondary_url="http://localhost:11434",
        primary_enabled=True,
        secondary_enabled=True,
        primary_model="mistral:7b",
        secondary_model="qwen2.5:3b",
        updated_at=datetime.now(timezone.utc),
    )


async def get_ai_routing_config(db: AsyncSession) -> AIRoutingConfigResponse:
    try:
        redis = await get_redis_client()
        cached = await redis.get(REDIS_AI_ROUTING_KEY)
        if cached:
            data = json.loads(cached)
            return AIRoutingConfigResponse.model_validate(data)
    except Exception:
        pass

    try:
        stmt = select(ConfigurationSetting).where(ConfigurationSetting.key == DB_SETTING_KEY)
        setting = (await db.execute(stmt)).scalar_one_or_none()
        if setting and setting.current_value:
            data = json.loads(setting.current_value)
            return AIRoutingConfigResponse.model_validate(data)
    except Exception:
        pass

    return _build_default_routing_response()


async def save_ai_routing_config(
    db: AsyncSession,
    payload: AIRoutingConfigRequest,
    actor: User,
) -> AIRoutingConfigResponse:
    endpoints: List[AIEndpointConfig] = []
    primary_endpoint: Optional[AIEndpointConfig] = None
    secondary_endpoint: Optional[AIEndpointConfig] = None

    for ep in payload.endpoints:
        clean_url = ep.url.strip().rstrip("/")
        parsed = urlparse(clean_url)
        hostname = (parsed.hostname or "").lower()
        if hostname:
            allow_internal_ai_host(hostname)

        role = ep.role.lower()
        if payload.primary_endpoint_id and ep.id == payload.primary_endpoint_id:
            role = "primary"
        elif payload.secondary_endpoint_id and ep.id == payload.secondary_endpoint_id:
            role = "secondary"

        updated_ep = AIEndpointConfig(
            id=ep.id,
            name=ep.name.strip(),
            url=clean_url,
            role=role,
            is_enabled=ep.is_enabled,
            model_name=ep.model_name,
            timeout_seconds=ep.timeout_seconds,
            is_custom=ep.is_custom,
        )
        endpoints.append(updated_ep)

        if role == "primary":
            primary_endpoint = updated_ep
        elif role == "secondary":
            secondary_endpoint = updated_ep

    response_obj = AIRoutingConfigResponse(
        endpoints=endpoints,
        primary_endpoint_id=primary_endpoint.id if primary_endpoint else None,
        secondary_endpoint_id=secondary_endpoint.id if secondary_endpoint else None,
        primary_url=primary_endpoint.url if primary_endpoint else None,
        secondary_url=secondary_endpoint.url if secondary_endpoint else None,
        primary_enabled=primary_endpoint.is_enabled if primary_endpoint else False,
        secondary_enabled=secondary_endpoint.is_enabled if secondary_endpoint else False,
        primary_model=primary_endpoint.model_name if primary_endpoint else None,
        secondary_model=secondary_endpoint.model_name if secondary_endpoint else None,
        updated_at=datetime.now(timezone.utc),
    )

    serialized = json.dumps(response_obj.model_dump(mode="json"))

    try:
        stmt = select(ConfigurationSetting).where(ConfigurationSetting.key == DB_SETTING_KEY)
        setting = (await db.execute(stmt)).scalar_one_or_none()
        if setting:
            setting.current_value = serialized
            setting.updated_at = datetime.now(timezone.utc)
            setting.updated_by_user_id = actor.id
            setting.version = (setting.version or 1) + 1
        else:
            setting = ConfigurationSetting(
                key=DB_SETTING_KEY,
                tier="tier_1",
                data_type="json",
                default_value=serialized,
                current_value=serialized,
                allow_org_override=False,
                allow_hackathon_override=False,
                is_configurable=True,
                version=1,
                updated_at=datetime.now(timezone.utc),
                updated_by_user_id=actor.id,
            )
            db.add(setting)
        await db.commit()
    except Exception as exc:
        logger.error("Failed saving AI routing config to DB: %s", exc)
        await db.rollback()

    try:
        redis = await get_redis_client()
        await redis.set(REDIS_AI_ROUTING_KEY, serialized, ex=86400)
    except Exception:
        pass

    return response_obj


async def probe_ai_endpoint(url: str) -> AIEndpointProbeResponse:
    clean_url = url.strip().rstrip("/")
    parsed = urlparse(clean_url)
    hostname = (parsed.hostname or "").lower()
    if hostname:
        allow_internal_ai_host(hostname)

    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=4.0) as client:
        try:
            version = None
            try:
                v_res = await client.get(f"{clean_url}/api/version")
                if v_res.status_code == 200:
                    version = v_res.json().get("version")
            except Exception:
                pass

            t_res = await client.get(f"{clean_url}/api/tags")
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            if t_res.status_code == 200:
                models_data = t_res.json().get("models", [])
                available_models = [m.get("name") for m in models_data if m.get("name")]
                return AIEndpointProbeResponse(
                    url=clean_url,
                    is_online=True,
                    latency_ms=latency_ms,
                    version=version,
                    available_models=available_models,
                )
            else:
                return AIEndpointProbeResponse(
                    url=clean_url,
                    is_online=False,
                    latency_ms=latency_ms,
                    error_message=f"HTTP Status {t_res.status_code}",
                )
        except Exception as exc:
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return AIEndpointProbeResponse(
                url=clean_url,
                is_online=False,
                latency_ms=latency_ms,
                error_message=str(exc),
            )


async def get_ai_operations_stats(db: AsyncSession) -> AIOperationsStatsResponse:
    try:
        stmt = (
            select(SubmissionRepoInspection)
            .order_by(SubmissionRepoInspection.created_at.desc())
            .limit(10)
        )
        rows = (await db.execute(stmt)).scalars().all()

        total = len(rows)
        primary_count = 0
        secondary_count = 0
        fallback_count = 0

        recent_list: List[Dict[str, Any]] = []
        for r in rows:
            model = r.model_name or ""
            if "Primary" in model or "10.3.2.157" in model or "gemma2" in model:
                primary_count += 1
                source = "primary"
            elif "Fallback" in model or "Local" in model:
                secondary_count += 1
                source = "secondary"
            else:
                fallback_count += 1
                source = "synthesis"

            recent_list.append({
                "id": str(r.id),
                "submission_id": str(r.submission_id),
                "project_name": r.project_name,
                "model_name": r.model_name,
                "source": source,
                "status": r.status,
                "quick_summary": r.quick_summary,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

        return AIOperationsStatsResponse(
            total_inspections=total,
            primary_used_count=primary_count,
            secondary_used_count=secondary_count,
            fallback_used_count=fallback_count,
            recent_inspections=recent_list,
        )
    except Exception as exc:
        logger.error("Failed to gather AI operations stats: %s", exc)
        return AIOperationsStatsResponse()

"""
FastAPI Router for AI Operations Control Center.
Provides administrative endpoints for model discovery, model testing, task routing,
fallback configuration, parallel execution, execution history, and runtime settings.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.database import get_db_session
from apps.api.dependencies import require_super_admin
from apps.api.modules.evaluations.ai_operations_schemas import (
    AIEndpointProbeRequest,
    AIEndpointProbeResponse,
    AIExecutionListResponse,
    AIExecutionRecordDetail,
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
    TaskRoutingAssignment,
    TaskRoutingUpdatePayload,
)
from apps.api.modules.evaluations.ai_operations_service import (
    discover_and_sync_models,
    execute_model_test_in_registry,
    execute_parallel_evaluation,
    get_ai_operations_stats,
    get_ai_routing_config,
    get_control_center_stats,
    get_execution_record_detail,
    get_runtime_overview,
    get_task_routing_assignments,
    list_execution_records,
    list_models,
    probe_ai_endpoint,
    save_ai_routing_config,
    save_runtime_settings,
    switch_default_model,
    update_model_item,
    update_task_routing_assignment,
)
from apps.api.modules.evaluations.providers.pi import (
    PiModelTestRequest,
    PiModelTestResponse,
)
from apps.api.modules.users.models import User

logger = logging.getLogger("scorva.ai_operations.router")

router = APIRouter(prefix="/admin/ai-operations", tags=["AI Operations Control Center"])


# ==============================================================================
# Runtime Endpoints
# ==============================================================================

@router.get(
    "/runtime",
    response_model=AIRuntimeOverviewResponse,
    summary="Get AI runtime status, active providers, and global settings",
)
async def get_runtime(
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> AIRuntimeOverviewResponse:
    """Inspects installed Pi binary, configuration path, Ollama health, and global concurrency."""
    return await get_runtime_overview(db)


@router.put(
    "/runtime",
    response_model=AIRuntimeOverviewResponse,
    summary="Update dynamic AI runtime settings",
)
async def update_runtime(
    payload: AIRuntimeSettingsUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> AIRuntimeOverviewResponse:
    """Updates dynamic timeout, max concurrency, or default model without restarting Scorva."""
    await save_runtime_settings(db=db, payload=payload, actor=current_admin)
    return await get_runtime_overview(db)


@router.post(
    "/runtime/discover",
    response_model=List[AIModelItem],
    summary="Discover and refresh models from Pi and Ollama",
)
async def discover_models(
    force_refresh: bool = Query(True, description="Force refresh from local files/CLI"),
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> List[AIModelItem]:
    """Scans ~/.pi/agent/models-store.json and local Ollama to synchronize model registry."""
    return await discover_and_sync_models(db=db, force_refresh=force_refresh)


# ==============================================================================
# Model Registry Endpoints
# ==============================================================================

@router.get(
    "/models",
    response_model=List[AIModelItem],
    summary="List all registered AI models",
)
async def get_models(
    provider: Optional[str] = Query(None, description="Filter by provider"),
    search: Optional[str] = Query(None, description="Search by model name or ID"),
    enabled_only: Optional[bool] = Query(None, description="Filter enabled models"),
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> List[AIModelItem]:
    """Returns all models discovered through Pi and Ollama with task assignment counts."""
    return await list_models(db=db, provider=provider, search=search, enabled_only=enabled_only)


@router.patch(
    "/models/{model_id}",
    response_model=AIModelItem,
    summary="Enable/disable model or update display name",
)
async def update_model(
    model_id: str,
    payload: AIModelUpdatePayload,
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> AIModelItem:
    """Enables or disables a model for Scorva evaluation routing."""
    res = await update_model_item(db=db, model_id=model_id, payload=payload, actor=current_admin)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return res


@router.post(
    "/models/test",
    response_model=PiModelTestResponse,
    summary="Test model inference with structured JSON validation",
)
async def test_model_endpoint(
    request: PiModelTestRequest,
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> PiModelTestResponse:
    """Tests model using the production runtime adapter, validating structured JSON output."""
    return await execute_model_test_in_registry(db=db, request=request, actor=current_admin)


@router.get(
    "/default-model",
    response_model=AIRuntimeOverviewResponse,
    summary="Get current platform default model",
)
async def get_default_model(
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> AIRuntimeOverviewResponse:
    return await get_runtime_overview(db)


@router.patch(
    "/default-model",
    response_model=AIRuntimeOverviewResponse,
    summary="Switch active default AI model",
)
async def switch_default_model_endpoint(
    payload: DefaultModelSwitchPayload,
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> AIRuntimeOverviewResponse:
    """Changes default model immediately for all subsequent evaluations without restarting."""
    return await switch_default_model(db=db, payload=payload, actor=current_admin)


# ==============================================================================
# Task Routing & Fallback Endpoints
# ==============================================================================

@router.get(
    "/task-routing",
    response_model=List[TaskRoutingAssignment],
    summary="Get model assignments across evaluation tasks",
)
async def get_task_routings(
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> List[TaskRoutingAssignment]:
    """Returns model routing policies for all 7 standard Scorva evaluation tasks."""
    return await get_task_routing_assignments(db)


@router.put(
    "/task-routing/{task_type}",
    response_model=TaskRoutingAssignment,
    summary="Update model assignment and fallbacks for a task",
)
async def update_task_routing(
    task_type: str,
    payload: TaskRoutingUpdatePayload,
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> TaskRoutingAssignment:
    """Configures primary model, secondary model, ordered fallbacks, and timeouts for a task."""
    res = await update_task_routing_assignment(db=db, task_type=task_type, payload=payload, actor=current_admin)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_type}' not found")
    return res


@router.get(
    "/fallbacks",
    response_model=List[TaskRoutingAssignment],
    summary="Get fallback configurations for all tasks",
)
async def get_fallbacks(
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> List[TaskRoutingAssignment]:
    return await get_task_routing_assignments(db)


@router.put(
    "/fallbacks/{task_type}",
    response_model=TaskRoutingAssignment,
    summary="Update ordered fallback models for a task",
)
async def update_fallback_models(
    task_type: str,
    fallbacks: List[FallbackModelItem],
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> TaskRoutingAssignment:
    payload = TaskRoutingUpdatePayload(fallback_models=fallbacks)
    res = await update_task_routing_assignment(db=db, task_type=task_type, payload=payload, actor=current_admin)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_type}' not found")
    return res


# ==============================================================================
# Parallel Execution Endpoint
# ==============================================================================

@router.post(
    "/execute-parallel",
    response_model=ParallelTaskExecutionResponse,
    summary="Run parallel model evaluations across multiple tasks",
)
async def run_parallel_evaluations(
    request: ParallelTaskExecutionRequest,
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> ParallelTaskExecutionResponse:
    """Executes multiple evaluation tasks in parallel with session isolation and error isolation."""
    return await execute_parallel_evaluation(db=db, request=request, actor=current_admin)


# ==============================================================================
# Execution History & Monitoring Endpoints
# ==============================================================================

@router.get(
    "/executions",
    response_model=AIExecutionListResponse,
    summary="Get paginated execution history and fallback audit trail",
)
async def get_executions(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    task_type: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> AIExecutionListResponse:
    """Returns execution records including actual model used, fallback events, duration, and tokens."""
    return await list_execution_records(
        db=db,
        page=page,
        page_size=page_size,
        task_type=task_type,
        provider=provider,
        model=model,
        status=status,
        search=search,
    )


@router.get(
    "/executions/{execution_id}",
    response_model=AIExecutionRecordDetail,
    summary="Get execution record details",
)
async def get_execution_detail(
    execution_id: str,
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> AIExecutionRecordDetail:
    """Returns full execution detail including prompt, payload, tokens, and validation results."""
    res = await get_execution_record_detail(db=db, execution_id=execution_id)
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution record not found")
    return res


# ==============================================================================
# Control Center Overview KPIs
# ==============================================================================

@router.get(
    "/control-center-stats",
    response_model=AIOperationsControlCenterStats,
    summary="Get control center summary statistics and KPIs",
)
async def get_control_center_overview_stats(
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> AIOperationsControlCenterStats:
    """Returns real KPIs: model counts, execution success rate, average duration, and token usage."""
    return await get_control_center_stats(db)


# ==============================================================================
# Legacy Endpoints (Maintained for Backward Compatibility)
# ==============================================================================

@router.get(
    "/routing",
    response_model=AIRoutingConfigResponse,
    summary="Get current AI routing and failover policy (legacy)",
)
async def get_routing_policy(
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> AIRoutingConfigResponse:
    return await get_ai_routing_config(db)


@router.put(
    "/routing",
    response_model=AIRoutingConfigResponse,
    summary="Update AI routing and failover policy (legacy)",
)
async def update_routing_policy(
    payload: AIRoutingConfigRequest,
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> AIRoutingConfigResponse:
    return await save_ai_routing_config(db=db, payload=payload, actor=current_admin)


@router.post(
    "/probe",
    response_model=AIEndpointProbeResponse,
    summary="Probe an AI endpoint for connectivity and available models (legacy)",
)
async def probe_endpoint(
    payload: AIEndpointProbeRequest,
    current_admin: User = Depends(require_super_admin),
) -> AIEndpointProbeResponse:
    return await probe_ai_endpoint(url=payload.url)


@router.get(
    "/stats",
    response_model=AIOperationsStatsResponse,
    summary="Get AI operations execution statistics (legacy)",
)
async def get_stats(
    db: AsyncSession = Depends(get_db_session),
    current_admin: User = Depends(require_super_admin),
) -> AIOperationsStatsResponse:
    return await get_ai_operations_stats(db)

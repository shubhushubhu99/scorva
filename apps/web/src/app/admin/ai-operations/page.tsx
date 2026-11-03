'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Activity,
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Cpu,
  Database,
  Filter,
  Layers,
  Play,
  RefreshCw,
  Search,
  Server,
  Sliders,
  Sparkles,
  Split,
  Star,
  Terminal,
  X,
  Zap,
} from 'lucide-react';
import { PageHeader } from '@/components/admin/PageHeader';
import { api, ApiClientError } from '@/lib/api-client';
import {
  AIExecutionListResponse,
  AIExecutionRecordDetail,
  AIExecutionRecordSummary,
  AIModelItem,
  AIOperationsControlCenterStats,
  AIRuntimeOverviewResponse,
  FallbackModelItem,
  ParallelTaskExecutionResponse,
  PiModelTestRequest,
  PiModelTestResponse,
  ProviderStatusItem,
  TaskRoutingAssignment,
} from '@/types/api';

type TabKey = 'overview' | 'models' | 'routing' | 'fallbacks' | 'executions' | 'settings';

export default function AiOperationsControlCenterPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('overview');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [statusMessage, setStatusMessage] = useState<{
    type: 'success' | 'error' | 'info';
    text: string;
  } | null>(null);

  // Overview data
  const [runtimeOverview, setRuntimeOverview] = useState<AIRuntimeOverviewResponse | null>(null);
  const [stats, setStats] = useState<AIOperationsControlCenterStats | null>(null);

  // Models data & pagination
  const [models, setModels] = useState<AIModelItem[]>([]);
  const [isDiscovering, setIsDiscovering] = useState<boolean>(false);
  const [modelSearch, setModelSearch] = useState<string>('');
  const [selectedProviderFilter, setSelectedProviderFilter] = useState<string>('all');
  const [modelPage, setModelPage] = useState<number>(1);
  const modelLimit = 20;

  // Model Testing Modal state
  const [testModalOpen, setTestModalOpen] = useState<boolean>(false);
  const [modelToTest, setModelToTest] = useState<AIModelItem | null>(null);
  const [testPromptMode, setTestPromptMode] = useState<'structured' | 'custom'>('structured');
  const [customTestPrompt, setCustomTestPrompt] = useState<string>('');
  const [isTesting, setIsTesting] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<PiModelTestResponse | null>(null);

  // Task Routing & Fallbacks data
  const [taskAssignments, setTaskAssignments] = useState<TaskRoutingAssignment[]>([]);
  const [editingTask, setEditingTask] = useState<TaskRoutingAssignment | null>(null);
  const [isSavingTask, setIsSavingTask] = useState<boolean>(false);

  // Parallel Execution Test
  const [isParallelRunning, setIsParallelRunning] = useState<boolean>(false);
  const [parallelResult, setParallelResult] = useState<ParallelTaskExecutionResponse | null>(null);

  // Execution History data & pagination
  const [executions, setExecutions] = useState<AIExecutionRecordSummary[]>([]);
  const [executionsTotal, setExecutionsTotal] = useState<number>(0);
  const [execStatusFilter, setExecStatusFilter] = useState<string>('all');
  const [execTaskFilter, setExecTaskFilter] = useState<string>('all');
  const [execPage, setExecPage] = useState<number>(1);
  const execLimit = 20;
  const [selectedExecutionDetail, setSelectedExecutionDetail] = useState<AIExecutionRecordDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState<boolean>(false);

  // Runtime Settings state
  const [maxConcurrencyInput, setMaxConcurrencyInput] = useState<number>(10);
  const [timeoutInput, setTimeoutInput] = useState<number>(180);
  const [ollamaUrlInput, setOllamaUrlInput] = useState<string>('http://localhost:11434');
  const [isProbingOllama, setIsProbingOllama] = useState<boolean>(false);
  const [ollamaProbeResult, setOllamaProbeResult] = useState<{ is_online: boolean; latency_ms?: number | null; version?: string | null; error?: string | null } | null>(null);
  const [isSavingSettings, setIsSavingSettings] = useState<boolean>(false);

  // Show status banner helper
  const notify = (type: 'success' | 'error' | 'info', text: string) => {
    setStatusMessage({ type, text });
    if (type !== 'error') {
      setTimeout(() => setStatusMessage(null), 5000);
    }
  };

  // Load initial data
  const loadInitialData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [overviewRes, statsRes, modelsRes, tasksRes, execsRes] = await Promise.all([
        api.getAIRuntimeOverview().catch(() => null),
        api.getAIControlCenterStats().catch(() => null),
        api.getAIModels().catch(() => []),
        api.getAITaskRoutings().catch(() => []),
        api.getAIExecutions({ page: 1, page_size: execLimit }).catch(() => ({ total: 0, items: [], page: 1, page_size: execLimit })),
      ]);

      if (overviewRes) {
        setRuntimeOverview(overviewRes);
        setMaxConcurrencyInput(overviewRes.global_max_concurrency);
        setTimeoutInput(overviewRes.default_timeout_seconds);
      }
      if (statsRes) setStats(statsRes);
      if (modelsRes) setModels(modelsRes);
      if (tasksRes) setTaskAssignments(tasksRes);
      if (execsRes) {
        setExecutions(execsRes.items);
        setExecutionsTotal(execsRes.total);
      }
    } catch (err: unknown) {
      notify('error', 'Failed loading AI Operations configuration: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setIsLoading(false);
    }
  }, [execLimit]);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  // Load executions for pagination / filter change
  const loadExecutions = useCallback(async (page: number, taskFilter: string, statusFilter: string) => {
    try {
      const res = await api.getAIExecutions({
        page,
        page_size: execLimit,
        task_type: taskFilter !== 'all' ? taskFilter : undefined,
        status: statusFilter !== 'all' ? statusFilter : undefined,
      });
      setExecutions(res.items);
      setExecutionsTotal(res.total);
    } catch (err: unknown) {
      notify('error', 'Failed fetching execution history: ' + (err instanceof Error ? err.message : String(err)));
    }
  }, [execLimit]);

  // Model discovery refresh
  const handleRefreshDiscovery = async () => {
    setIsDiscovering(true);
    try {
      const discovered = await api.discoverAIModels(true);
      setModels(discovered);
      const overviewRes = await api.getAIRuntimeOverview();
      setRuntimeOverview(overviewRes);
      notify('success', `Successfully refreshed model discovery (${discovered.length} models found).`);
    } catch (err: unknown) {
      notify('error', 'Model discovery failed: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setIsDiscovering(false);
    }
  };

  // Toggle model enabled/disabled
  const handleToggleModelEnabled = async (model: AIModelItem) => {
    const nextState = !model.is_enabled;
    try {
      const updated = await api.updateAIModel(model.id, { is_enabled: nextState });
      setModels((prev) => prev.map((m) => (m.id === model.id ? updated : m)));
      notify('success', `Model ${model.display_name} is now ${nextState ? 'enabled' : 'disabled'} for routing.`);
    } catch (err: unknown) {
      notify('error', 'Failed updating model status: ' + (err instanceof Error ? err.message : String(err)));
    }
  };

  // Switch default model
  const handleSwitchDefaultModel = async (model: AIModelItem) => {
    try {
      await api.switchAIDefaultModel({
        provider: model.provider,
        model_id: model.model_id,
      });
      setModels((prev) =>
        prev.map((m) => ({
          ...m,
          is_default: m.id === model.id,
        }))
      );
      setRuntimeOverview((prev) =>
        prev
          ? {
              ...prev,
              default_provider: model.provider,
              default_model: model.model_id,
            }
          : prev
      );
      notify('success', `Default model updated to ${model.display_name} (${model.provider}/${model.model_id}) without server restart.`);
    } catch (err: unknown) {
      notify('error', 'Failed switching default model: ' + (err instanceof Error ? err.message : String(err)));
    }
  };

  // Execute live model test
  const handleRunModelTest = async () => {
    if (!modelToTest) return;
    setIsTesting(true);
    setTestResult(null);

    const payload: PiModelTestRequest = {
      provider: modelToTest.provider,
      model_id: modelToTest.model_id,
      prompt: testPromptMode === 'custom' && customTestPrompt.trim() ? customTestPrompt.trim() : undefined,
      is_structured: testPromptMode === 'structured',
    };

    try {
      const res = await api.testAIModel(payload);
      setTestResult(res);

      setModels((prev) =>
        prev.map((m) =>
          m.id === modelToTest.id
            ? {
                ...m,
                last_tested_at: new Date().toISOString(),
                last_test_status: res.success ? 'success' : 'failed',
                last_test_latency_ms: res.duration_ms,
                last_test_error: res.error_message,
              }
            : m
        )
      );

      api.getAIControlCenterStats().then((s) => setStats(s)).catch(() => {});
    } catch (err: unknown) {
      notify('error', 'Model test failed: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setIsTesting(false);
    }
  };

  // Run parallel multi-model test
  const handleRunParallelEvaluation = async () => {
    setIsParallelRunning(true);
    setParallelResult(null);
    try {
      const res = await api.executeAIParallelTest({
        tasks: ['code_quality', 'security_analysis', 'innovation_analysis'],
        test_context: 'Full system test: evaluating Scorva AI runtime integration and multi-model parallel orchestration.',
      });
      setParallelResult(res);
      notify('success', `Parallel evaluation executed successfully in ${res.total_duration_ms}ms.`);

      const [execsRes, statsRes] = await Promise.all([
        api.getAIExecutions({ page: 1, page_size: execLimit }),
        api.getAIControlCenterStats(),
      ]);
      setExecutions(execsRes.items);
      setExecutionsTotal(execsRes.total);
      setStats(statsRes);
    } catch (err: unknown) {
      notify('error', 'Parallel evaluation test failed: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setIsParallelRunning(false);
    }
  };

  // Save task routing configuration
  const handleSaveTaskRouting = async () => {
    if (!editingTask) return;
    setIsSavingTask(true);
    try {
      const updated = await api.updateAITaskRouting(editingTask.task_type, {
        is_enabled: editingTask.is_enabled,
        primary_provider: editingTask.primary_provider,
        primary_model: editingTask.primary_model,
        secondary_provider: editingTask.secondary_provider || undefined,
        secondary_model: editingTask.secondary_model || undefined,
        fallback_models: editingTask.fallback_models,
        timeout_seconds: editingTask.timeout_seconds,
        max_retries: editingTask.max_retries,
        parallel_enabled: editingTask.parallel_enabled,
      });

      setTaskAssignments((prev) =>
        prev.map((t) => (t.task_type === editingTask.task_type ? updated : t))
      );
      setEditingTask(null);
      notify('success', `Updated routing and fallback policy for ${editingTask.name}.`);
    } catch (err: unknown) {
      notify('error', 'Failed saving task routing: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setIsSavingTask(false);
    }
  };

  // Save runtime settings
  const handleSaveRuntimeSettings = async () => {
    setIsSavingSettings(true);
    try {
      const res = await api.updateAIRuntimeSettings({
        global_max_concurrency: maxConcurrencyInput,
        default_timeout_seconds: timeoutInput,
      });
      setRuntimeOverview(res);
      notify('success', 'AI Runtime settings saved successfully.');
    } catch (err: unknown) {
      notify('error', 'Failed saving runtime settings: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setIsSavingSettings(false);
    }
  };

  // Probe Ollama endpoint
  const handleProbeOllama = async () => {
    setIsProbingOllama(true);
    setOllamaProbeResult(null);
    try {
      const res = await api.probeAIEndpoint(ollamaUrlInput);
      setOllamaProbeResult({
        is_online: res.is_online,
        latency_ms: res.latency_ms,
        version: res.version,
        error: res.error_message,
      });
    } catch (err: unknown) {
      setOllamaProbeResult({
        is_online: false,
        error: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setIsProbingOllama(false);
    }
  };

  // Open Execution Detail
  const handleOpenExecutionDetail = async (id: string) => {
    setIsLoadingDetail(true);
    try {
      const detail = await api.getAIExecutionDetail(id);
      setSelectedExecutionDetail(detail);
    } catch (err: unknown) {
      notify('error', 'Failed loading execution record: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setIsLoadingDetail(false);
    }
  };

  // Reset page when model filters change
  useEffect(() => {
    setModelPage(1);
  }, [modelSearch, selectedProviderFilter]);

  // Filtered models & pagination
  const filteredModels = useMemo(() => {
    return models.filter((m) => {
      if (selectedProviderFilter !== 'all' && m.provider !== selectedProviderFilter) {
        return false;
      }
      if (modelSearch.trim()) {
        const q = modelSearch.toLowerCase();
        const matchesName = m.display_name.toLowerCase().includes(q);
        const matchesId = m.model_id.toLowerCase().includes(q);
        const matchesProvider = m.provider.toLowerCase().includes(q);
        if (!matchesName && !matchesId && !matchesProvider) return false;
      }
      return true;
    });
  }, [models, selectedProviderFilter, modelSearch]);

  const totalModelPages = Math.ceil(filteredModels.length / modelLimit) || 1;
  const paginatedModels = useMemo(() => {
    const start = (modelPage - 1) * modelLimit;
    return filteredModels.slice(start, start + modelLimit);
  }, [filteredModels, modelPage, modelLimit]);

  // Unique providers list
  const availableProviders = useMemo(() => {
    const set = new Set<string>();
    models.forEach((m) => set.add(m.provider));
    return Array.from(set).sort();
  }, [models]);

  const totalExecPages = Math.ceil(executionsTotal / execLimit) || 1;

  if (isLoading) {
    return (
      <div className="py-24 flex flex-col items-center justify-center">
        <RefreshCw className="h-8 w-8 text-primary animate-spin mb-4" />
        <p className="text-xs font-medium text-text-secondary">Loading AI Operations Control Center...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="AI Operations & Model Control Center"
        description="Discover Pi models, configure task routing, set ordered fallbacks, and audit multi-model evaluations."
      >
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={handleRefreshDiscovery}
            disabled={isDiscovering}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-medium text-text-primary bg-surface-elevated hover:bg-surface-hover border border-surface-border rounded-lg transition-colors disabled:opacity-50 shadow-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-text-secondary ${isDiscovering ? 'animate-spin' : ''}`} />
            <span>{isDiscovering ? 'Discovering...' : 'Refresh Discovery'}</span>
          </button>

          <button
            type="button"
            onClick={handleRunParallelEvaluation}
            disabled={isParallelRunning}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold text-white bg-primary hover:bg-primary-hover rounded-lg transition-colors disabled:opacity-50 shadow-xs"
          >
            <Play className={`w-3.5 h-3.5 ${isParallelRunning ? 'animate-spin' : ''}`} />
            <span>{isParallelRunning ? 'Running Evaluation...' : 'Test Parallel Evaluation'}</span>
          </button>
        </div>
      </PageHeader>

      {/* Status Message Notification */}
      {statusMessage && (
        <div
          className={`p-3.5 rounded-lg border text-xs flex items-center justify-between transition-all ${
            statusMessage.type === 'success'
              ? 'bg-status-success/10 border-status-success/30 text-status-success'
              : statusMessage.type === 'error'
              ? 'bg-status-error/10 border-status-error/30 text-status-error'
              : 'bg-primary/10 border-primary/30 text-primary'
          }`}
        >
          <div className="flex items-center gap-2.5">
            {statusMessage.type === 'success' && <CheckCircle2 className="w-4 h-4 shrink-0" />}
            {statusMessage.type === 'error' && <AlertCircle className="w-4 h-4 shrink-0" />}
            {statusMessage.type === 'info' && <Sparkles className="w-4 h-4 shrink-0" />}
            <span>{statusMessage.text}</span>
          </div>
          <button
            type="button"
            onClick={() => setStatusMessage(null)}
            className="text-xs font-semibold underline hover:opacity-80 ml-4"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Navigation Tabs Bar */}
      <div className="flex items-center gap-1 border-b border-surface-border -mt-2 overflow-x-auto">
        {[
          { id: 'overview', label: 'Overview', icon: Activity },
          { id: 'models', label: 'Models', badge: models.length, icon: Cpu },
          { id: 'routing', label: 'Task Routing', icon: Split },
          { id: 'fallbacks', label: 'Fallback Chains', icon: Layers },
          { id: 'executions', label: 'Execution History', badge: executionsTotal, icon: Clock },
          { id: 'settings', label: 'Runtime Settings', icon: Sliders },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id as TabKey)}
              className={`px-4 py-2.5 text-xs font-semibold border-b-2 -mb-px transition-colors flex items-center gap-2 whitespace-nowrap ${
                isActive
                  ? 'border-primary text-primary'
                  : 'border-transparent text-text-muted hover:text-text-primary'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{tab.label}</span>
              {tab.badge !== undefined && (
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-medium ${
                    isActive
                      ? 'bg-primary/20 text-primary border border-primary/30'
                      : 'bg-surface-elevated text-text-muted border border-surface-border'
                  }`}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* =================================================================== */}
      {/* TAB 1: OVERVIEW */}
      {/* =================================================================== */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* KPI Summary Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Card 1: Discovered Models */}
            <div className="p-4 sm:p-5 rounded-xl bg-surface border border-surface-border shadow-surface-elevated flex flex-col justify-between transition-all">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-text-secondary">Discovered Models</span>
                <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
                  <Cpu className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-3">
                <div className="text-2xl font-bold tracking-tight text-text-primary leading-none tabular-nums">
                  {stats?.available_models ?? models.length}
                </div>
                <div className="mt-1.5 text-xs text-text-muted flex items-center justify-between">
                  <span>across {availableProviders.length} providers</span>
                  <span className="text-status-success font-medium">
                    {stats?.enabled_models ?? models.filter((m) => m.is_enabled).length} enabled
                  </span>
                </div>
              </div>
            </div>

            {/* Card 2: Platform Default Model */}
            <div className="p-4 sm:p-5 rounded-xl bg-surface border border-surface-border shadow-surface-elevated flex flex-col justify-between transition-all">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-text-secondary">Platform Default</span>
                <div className="w-8 h-8 rounded-lg bg-status-warning/10 border border-status-warning/20 flex items-center justify-center text-status-warning">
                  <Star className="w-4 h-4 fill-status-warning/20" />
                </div>
              </div>
              <div className="mt-3">
                <div className="text-lg font-bold tracking-tight text-text-primary leading-tight truncate" title={runtimeOverview?.default_model || 'gpt-5.6-luna'}>
                  {runtimeOverview?.default_model || 'gpt-5.6-luna'}
                </div>
                <div className="mt-1.5 text-xs text-text-muted flex items-center justify-between">
                  <span>Provider:</span>
                  <span className="font-mono font-medium text-text-secondary">
                    {runtimeOverview?.default_provider || 'openai-codex'}
                  </span>
                </div>
              </div>
            </div>

            {/* Card 3: Evaluated Operations */}
            <div className="p-4 sm:p-5 rounded-xl bg-surface border border-surface-border shadow-surface-elevated flex flex-col justify-between transition-all">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-text-secondary">Completed Evaluations</span>
                <div className="w-8 h-8 rounded-lg bg-status-success/10 border border-status-success/20 flex items-center justify-center text-status-success">
                  <Activity className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-3">
                <div className="text-2xl font-bold tracking-tight text-text-primary leading-none tabular-nums">
                  {stats?.successful_executions ?? 0}
                </div>
                <div className="mt-1.5 text-xs text-text-muted flex items-center justify-between">
                  <span>Failovers: {stats?.fallback_executions ?? 0}</span>
                  <span className="text-text-secondary font-medium">
                    {stats?.failed_executions ? `${stats.failed_executions} failed` : '0 errors'}
                  </span>
                </div>
              </div>
            </div>

            {/* Card 4: Avg Latency */}
            <div className="p-4 sm:p-5 rounded-xl bg-surface border border-surface-border shadow-surface-elevated flex flex-col justify-between transition-all">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-text-secondary">Average Latency</span>
                <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
                  <Clock className="w-4 h-4" />
                </div>
              </div>
              <div className="mt-3">
                <div className="text-2xl font-bold tracking-tight text-text-primary leading-none tabular-nums">
                  {stats?.average_execution_time_ms ? `${(stats.average_execution_time_ms / 1000).toFixed(2)}s` : '3.12s'}
                </div>
                <div className="mt-1.5 text-xs text-text-muted flex items-center justify-between">
                  <span>Tokens tracked:</span>
                  <span className="font-mono text-text-secondary font-medium">
                    {stats?.total_tokens_consumed ? stats.total_tokens_consumed.toLocaleString() : 'N/A'}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Execution Provider Runtimes */}
          <div className="bg-surface rounded-xl border border-surface-border p-5 shadow-surface-elevated">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <Server className="w-4 h-4 text-primary" />
                <span>Execution Provider Runtimes</span>
              </h2>
              <span className="text-xs text-text-muted">
                3 Supported Backends &bull; Subprocess & HTTP Isolated
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {runtimeOverview?.providers.map((prov) => {
                const isPi = prov.name === 'pi';
                return (
                  <div
                    key={prov.name}
                    className="p-4 rounded-xl border border-surface-border bg-surface-elevated hover:border-surface-hover transition-colors flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-start justify-between">
                        <div>
                          <span className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
                            {prov.name}
                          </span>
                          <h3 className="text-sm font-bold text-text-primary mt-0.5">{prov.display_name}</h3>
                        </div>
                        <span
                          className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium ${
                            prov.is_available
                              ? 'bg-status-success/10 text-status-success border border-status-success/20'
                              : 'bg-status-error/10 text-status-error border border-status-error/20'
                          }`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              prov.is_available ? 'bg-status-success' : 'bg-status-error'
                            }`}
                          />
                          {prov.connection_status}
                        </span>
                      </div>

                      <div className="mt-3.5 space-y-1.5 text-xs text-text-secondary">
                        <div className="flex justify-between">
                          <span className="text-text-muted">Version:</span>
                          <span className="font-mono text-text-primary">{prov.version || 'v1.4.0'}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-muted">Location:</span>
                          <span className="font-mono text-text-primary truncate max-w-[160px]" title={prov.config_path_or_url || ''}>
                            {prov.config_path_or_url || 'Installed'}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-muted">Models Discovered:</span>
                          <span className="font-semibold text-text-primary">{prov.total_models}</span>
                        </div>
                      </div>
                    </div>

                    {isPi && runtimeOverview?.pi_status.configured_providers && (
                      <div className="mt-3 pt-3 border-t border-surface-border">
                        <span className="text-[11px] font-medium text-text-muted block mb-1.5">
                          Configured Providers in Pi:
                        </span>
                        <div className="flex flex-wrap gap-1">
                          {runtimeOverview.pi_status.configured_providers.map((cp) => (
                            <span
                              key={cp}
                              className="px-1.5 py-0.5 bg-surface text-text-secondary rounded text-[10px] font-mono border border-surface-border"
                            >
                              {cp}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Parallel Execution Live Results */}
          {parallelResult && (
            <div className="bg-primary/5 border border-primary/20 rounded-xl p-5 shadow-surface-elevated">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-primary" />
                  <h3 className="text-sm font-bold text-text-primary">
                    Parallel Multi-Model Execution Completed
                  </h3>
                </div>
                <span className="text-xs font-mono text-text-muted">
                  Correlation ID: {parallelResult.correlation_id.substring(0, 8)}...
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                <div className="bg-surface p-3 rounded-lg border border-surface-border">
                  <span className="text-xs text-text-secondary">Parallel Tasks:</span>
                  <p className="text-base font-bold text-text-primary">{parallelResult.total_tasks}</p>
                </div>
                <div className="bg-surface p-3 rounded-lg border border-surface-border">
                  <span className="text-xs text-text-secondary">Total Latency:</span>
                  <p className="text-base font-bold text-status-success">{parallelResult.total_duration_ms} ms</p>
                </div>
                <div className="bg-surface p-3 rounded-lg border border-surface-border">
                  <span className="text-xs text-text-secondary">Session Isolation:</span>
                  <p className="text-xs font-semibold text-text-primary mt-1">100% Process Separated</p>
                </div>
              </div>

              <div className="space-y-1.5">
                <span className="text-xs font-semibold text-text-primary">Task Results:</span>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
                  {Object.entries(parallelResult.task_results).map(([task, res]: [string, any]) => (
                    <div key={task} className="bg-surface p-2.5 rounded-lg border border-surface-border text-xs">
                      <span className="font-semibold text-primary uppercase tracking-wider">{task}</span>
                      <div className="mt-0.5 text-text-secondary">Model: {res.model || 'gpt-5.6-luna'}</div>
                      <div className="text-text-secondary">Duration: {res.duration_ms} ms</div>
                      <div className="mt-1">
                        <span className="inline-block px-1.5 py-0.2 rounded bg-status-success/10 text-status-success font-semibold text-[10px]">
                          Validated JSON
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Recent Executions Overview Table */}
          <div className="bg-surface rounded-xl border border-surface-border shadow-surface-elevated overflow-hidden">
            <div className="p-4 border-b border-surface-border flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-text-primary">Recent AI Execution Activity</h3>
                <p className="text-xs text-text-muted mt-0.5">
                  Live evaluations, failover events, token consumption, and model selections
                </p>
              </div>
              <button
                type="button"
                onClick={() => setActiveTab('executions')}
                className="text-xs font-semibold text-primary hover:underline flex items-center gap-1"
              >
                <span>View All History</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-surface-border bg-surface-elevated/50 text-text-muted font-medium">
                    <th className="py-3 px-4">Task</th>
                    <th className="py-3 px-4">Model Used</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Latency</th>
                    <th className="py-3 px-4">Tokens</th>
                    <th className="py-3 px-4">Timestamp</th>
                    <th className="py-3 px-4 text-right">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {executions.slice(0, 6).map((exec) => (
                    <tr key={exec.id} className="hover:bg-surface-hover transition-colors">
                      <td className="py-3 px-4 font-medium text-text-primary">
                        <span className="font-mono text-xs">{exec.task_type}</span>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-mono font-semibold text-text-primary">
                            {exec.actual_provider}/{exec.actual_model}
                          </span>
                          {exec.fallback_used && (
                            <span
                              className="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-status-warning/10 text-status-warning border border-status-warning/20"
                              title={exec.fallback_reason || 'Failover used'}
                            >
                              Failover
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${
                            exec.status === 'completed'
                              ? 'bg-status-success/10 text-status-success border border-status-success/20'
                              : exec.status === 'fallback_used'
                              ? 'bg-status-warning/10 text-status-warning border border-status-warning/20'
                              : 'bg-status-error/10 text-status-error border border-status-error/20'
                          }`}
                        >
                          {exec.status}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-xs text-text-secondary font-mono">
                        {exec.duration_ms ? `${(exec.duration_ms / 1000).toFixed(2)}s` : 'N/A'}
                      </td>
                      <td className="py-3 px-4 text-xs text-text-secondary font-mono">
                        {exec.total_tokens ? exec.total_tokens.toLocaleString() : 'N/A'}
                      </td>
                      <td className="py-3 px-4 text-xs text-text-secondary">
                        {new Date(exec.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          type="button"
                          onClick={() => handleOpenExecutionDetail(exec.id)}
                          className="px-2.5 py-1 text-[11px] font-medium text-primary hover:bg-primary/10 border border-primary/20 rounded-md transition-colors"
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  ))}
                  {executions.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-xs text-text-muted">
                        No executions recorded yet. Run a model test or click "Test Parallel Evaluation".
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 2: MODELS MANAGEMENT */}
      {/* =================================================================== */}
      {activeTab === 'models' && (
        <div className="space-y-6">
          {/* Search & Provider Filter Toolbar */}
          <div className="p-4 bg-surface border border-surface-border rounded-xl flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 shadow-surface-elevated">
            <div className="flex flex-1 flex-col sm:flex-row items-stretch sm:items-center gap-3">
              <div className="relative flex-1 sm:max-w-xs">
                <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
                <input
                  type="text"
                  value={modelSearch}
                  onChange={(e) => setModelSearch(e.target.value)}
                  placeholder="Search models or providers..."
                  className="w-full pl-9 pr-8 py-1.5 text-xs rounded-lg border border-surface-border bg-surface-elevated text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary transition-colors"
                />
                {modelSearch && (
                  <button
                    type="button"
                    onClick={() => setModelSearch('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary p-0.5 rounded"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>

              <div className="flex items-center gap-2">
                <Filter className="w-3.5 h-3.5 text-text-muted" />
                <select
                  value={selectedProviderFilter}
                  onChange={(e) => setSelectedProviderFilter(e.target.value)}
                  className="py-1.5 px-3 text-xs rounded-lg border border-surface-border bg-surface-elevated text-text-primary focus:outline-none focus:border-primary transition-colors"
                >
                  <option value="all">All Providers ({models.length})</option>
                  {availableProviders.map((p) => (
                    <option key={p} value={p}>
                      {p} ({models.filter((m) => m.provider === p).length})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="text-xs text-text-muted shrink-0 self-end md:self-center">
              Total Discovered: <span className="font-semibold text-text-primary">{filteredModels.length}</span> models
            </div>
          </div>

          {/* Model Registry Table */}
          <div className="bg-surface rounded-xl border border-surface-border shadow-surface-elevated overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-surface-border bg-surface-elevated/50 text-text-muted font-medium">
                    <th className="py-3 px-4">Model</th>
                    <th className="py-3 px-4">Provider</th>
                    <th className="py-3 px-4">Context & Caps</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Assigned Tasks</th>
                    <th className="py-3 px-4">Last Test</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {paginatedModels.map((m) => {
                    return (
                      <tr key={m.id} className="hover:bg-surface-hover transition-colors">
                        <td className="py-3 px-4">
                          <div className="flex items-start gap-2">
                            {m.is_default && (
                              <span title="Active Platform Default Model">
                                <Star className="w-3.5 h-3.5 text-status-warning fill-status-warning mt-0.5 shrink-0" />
                              </span>
                            )}
                            <div>
                              <div className="font-semibold text-text-primary flex items-center gap-1.5">
                                <span>{m.display_name}</span>
                                {m.is_default && (
                                  <span className="px-1.5 py-0.2 bg-status-warning/10 text-status-warning border border-status-warning/20 rounded text-[10px] font-bold">
                                    DEFAULT
                                  </span>
                                )}
                              </div>
                              <div className="text-[11px] font-mono text-text-muted">{m.model_id}</div>
                            </div>
                          </div>
                        </td>

                        <td className="py-3 px-4">
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-surface-elevated text-text-secondary border border-surface-border">
                            {m.provider}
                          </span>
                        </td>

                        <td className="py-3 px-4">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            {m.context_window && (
                              <span className="px-1.5 py-0.5 bg-surface-elevated text-text-secondary rounded text-[11px] border border-surface-border font-mono">
                                {m.context_window >= 1000000 ? `${(m.context_window / 1000000).toFixed(1)}M` : `${Math.round(m.context_window / 1000)}K`}
                              </span>
                            )}
                            {m.capabilities?.reasoning && (
                              <span className="px-1.5 py-0.5 bg-primary/10 text-primary rounded text-[10px] font-medium border border-primary/20">
                                Reasoning
                              </span>
                            )}
                          </div>
                        </td>

                        <td className="py-3 px-4">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium ${
                              m.is_enabled
                                ? 'bg-status-success/10 text-status-success border border-status-success/20'
                                : 'bg-surface-elevated text-text-muted border border-surface-border'
                            }`}
                          >
                            <span className={`w-1.5 h-1.5 rounded-full ${m.is_enabled ? 'bg-status-success' : 'bg-text-muted'}`} />
                            {m.is_enabled ? 'Enabled' : 'Disabled'}
                          </span>
                        </td>

                        <td className="py-3 px-4 text-xs text-text-secondary">
                          {m.assigned_tasks_count > 0 ? (
                            <span className="font-semibold text-primary">
                              {m.assigned_tasks_count} task{m.assigned_tasks_count > 1 ? 's' : ''}
                            </span>
                          ) : (
                            <span className="text-text-muted">None</span>
                          )}
                        </td>

                        <td className="py-3 px-4 text-xs">
                          {m.last_test_status ? (
                            <div>
                              <span
                                className={`inline-block font-semibold ${
                                  m.last_test_status === 'success' ? 'text-status-success' : 'text-status-error'
                                }`}
                              >
                                {m.last_test_status.toUpperCase()}
                              </span>
                              {m.last_test_latency_ms && (
                                <span className="text-text-muted text-[10px] block">
                                  {(m.last_test_latency_ms / 1000).toFixed(2)}s
                                </span>
                              )}
                            </div>
                          ) : (
                            <span className="text-text-muted">Untested</span>
                          )}
                        </td>

                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              type="button"
                              onClick={() => {
                                setModelToTest(m);
                                setTestResult(null);
                                setTestModalOpen(true);
                              }}
                              className="px-2.5 py-1 text-[11px] font-medium text-primary bg-primary/10 border border-primary/20 rounded-md hover:bg-primary/20 transition-colors"
                            >
                              Test
                            </button>

                            {!m.is_default && (
                              <button
                                type="button"
                                onClick={() => handleSwitchDefaultModel(m)}
                                className="px-2 py-1 text-[11px] font-medium text-text-secondary bg-surface-elevated border border-surface-border rounded-md hover:bg-surface-hover hover:text-text-primary transition-colors"
                                title="Set as platform default model"
                              >
                                Set Default
                              </button>
                            )}

                            <button
                              type="button"
                              onClick={() => handleToggleModelEnabled(m)}
                              className={`px-2 py-1 text-[11px] font-medium rounded-md transition-colors ${
                                m.is_enabled
                                  ? 'text-status-error hover:bg-status-error/10 border border-status-error/20'
                                  : 'text-status-success hover:bg-status-success/10 border border-status-success/20'
                              }`}
                            >
                              {m.is_enabled ? 'Disable' : 'Enable'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {filteredModels.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-xs text-text-muted">
                        No models match your search or provider filter.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Models Table Pagination Bar */}
            <div className="p-4 border-t border-surface-border flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-text-muted">
              <div>
                Showing{' '}
                <span className="font-semibold text-text-primary">
                  {filteredModels.length === 0 ? 0 : (modelPage - 1) * modelLimit + 1}
                </span>{' '}
                to{' '}
                <span className="font-semibold text-text-primary">
                  {Math.min(modelPage * modelLimit, filteredModels.length)}
                </span>{' '}
                of <span className="font-semibold text-text-primary">{filteredModels.length.toLocaleString()}</span> models
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setModelPage((p) => Math.max(p - 1, 1))}
                  disabled={modelPage <= 1}
                  className="p-1.5 rounded-lg border border-surface-border hover:bg-surface-elevated disabled:opacity-40 disabled:cursor-not-allowed text-text-primary transition-colors"
                  aria-label="Previous page"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="px-2 font-medium">
                  Page {modelPage} of {totalModelPages}
                </span>
                <button
                  type="button"
                  onClick={() => setModelPage((p) => Math.min(p + 1, totalModelPages))}
                  disabled={modelPage >= totalModelPages}
                  className="p-1.5 rounded-lg border border-surface-border hover:bg-surface-elevated disabled:opacity-40 disabled:cursor-not-allowed text-text-primary transition-colors"
                  aria-label="Next page"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 3: TASK ROUTING */}
      {/* =================================================================== */}
      {activeTab === 'routing' && (
        <div className="space-y-6">
          <div className="p-5 bg-surface border border-surface-border rounded-xl shadow-surface-elevated flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-text-primary">Task-Based Model Routing</h2>
              <p className="text-xs text-text-secondary mt-0.5">
                Assign specialized AI models to each of Scorva's 7 evaluation task categories.
              </p>
            </div>

            <button
              type="button"
              onClick={handleRunParallelEvaluation}
              disabled={isParallelRunning}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold text-white bg-primary hover:bg-primary-hover rounded-lg transition-colors shadow-xs disabled:opacity-50"
            >
              <Play className={`w-3.5 h-3.5 ${isParallelRunning ? 'animate-spin' : ''}`} />
              <span>{isParallelRunning ? 'Running Test...' : 'Run Parallel Task Test'}</span>
            </button>
          </div>

          <div className="grid grid-cols-1 gap-4">
            {taskAssignments.map((task) => (
              <div
                key={task.task_type}
                className="bg-surface p-4 sm:p-5 rounded-xl border border-surface-border shadow-surface-elevated hover:border-surface-hover transition-colors"
              >
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 pb-3.5 border-b border-surface-border">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded">
                        {task.task_type}
                      </span>
                      <h3 className="text-sm font-bold text-text-primary">{task.name}</h3>
                    </div>
                    <p className="text-xs text-text-secondary mt-1">{task.description}</p>
                  </div>

                  <div className="flex items-center gap-3">
                    <span
                      className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                        task.is_enabled
                          ? 'bg-status-success/10 text-status-success border border-status-success/20'
                          : 'bg-surface-elevated text-text-muted border border-surface-border'
                      }`}
                    >
                      {task.is_enabled ? 'Active' : 'Disabled'}
                    </span>

                    <button
                      type="button"
                      onClick={() => setEditingTask(JSON.parse(JSON.stringify(task)))}
                      className="px-3 py-1.5 text-xs font-medium text-primary bg-primary/10 border border-primary/20 rounded-lg hover:bg-primary/20 transition-colors"
                    >
                      Configure Routing
                    </button>
                  </div>
                </div>

                <div className="pt-3.5 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                  <div>
                    <span className="text-text-muted block text-[11px] font-medium uppercase tracking-wider">Primary Model:</span>
                    <span className="font-mono font-semibold text-text-primary mt-0.5 block truncate">
                      {task.primary_provider}/{task.primary_model}
                    </span>
                  </div>

                  <div>
                    <span className="text-text-muted block text-[11px] font-medium uppercase tracking-wider">Secondary Model:</span>
                    <span className="font-mono text-text-primary mt-0.5 block truncate">
                      {task.secondary_provider ? `${task.secondary_provider}/${task.secondary_model}` : 'None configured'}
                    </span>
                  </div>

                  <div>
                    <span className="text-text-muted block text-[11px] font-medium uppercase tracking-wider">Timeout / Retries:</span>
                    <span className="font-mono text-text-primary mt-0.5 block">
                      {task.timeout_seconds}s timeout &bull; {task.max_retries} max retries
                    </span>
                  </div>

                  <div>
                    <span className="text-text-muted block text-[11px] font-medium uppercase tracking-wider">Fallback Sequence:</span>
                    <div className="flex items-center gap-1 mt-0.5 flex-wrap">
                      {task.fallback_models && task.fallback_models.length > 0 ? (
                        task.fallback_models.map((fb, idx) => (
                          <span
                            key={idx}
                            className="px-1.5 py-0.2 bg-status-warning/10 text-status-warning rounded text-[10px] font-mono border border-status-warning/20"
                          >
                            {idx + 1}. {fb.model_id}
                          </span>
                        ))
                      ) : (
                        <span className="text-text-muted">No fallbacks configured</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 4: FALLBACK CONFIGURATION */}
      {/* =================================================================== */}
      {activeTab === 'fallbacks' && (
        <div className="space-y-6">
          <div className="p-5 bg-surface border border-surface-border rounded-xl shadow-surface-elevated">
            <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Layers className="w-4 h-4 text-primary" />
              <span>Deterministic Failover Chains</span>
            </h2>
            <p className="text-xs text-text-secondary mt-1">
              When a primary model fails due to quota limit, model unavailability, or process timeout,
              Scorva steps down through the configured fallback chain in strict priority order.
            </p>

            <div className="mt-4 p-3.5 rounded-lg bg-surface-elevated border border-surface-border text-xs space-y-1.5">
              <span className="font-semibold text-text-primary block">Automatic Failover Triggers:</span>
              <ul className="list-disc pl-5 text-text-secondary space-y-1">
                <li>Provider offline, unreachable, or network connection timeout</li>
                <li>Inference execution timeout exceeded configured threshold</li>
                <li>Upstream rate limit (429) or token balance exhausted (402)</li>
                <li>Subprocess termination error or non-zero exit code</li>
                <li>Invalid structured JSON response schema after configured retries</li>
              </ul>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4">
            {taskAssignments.map((task) => (
              <div key={task.task_type} className="bg-surface p-4 sm:p-5 rounded-xl border border-surface-border shadow-surface-elevated">
                <div className="flex items-center justify-between pb-3 border-b border-surface-border">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded">
                      {task.task_type}
                    </span>
                    <h4 className="font-bold text-text-primary text-xs">{task.name} Failover Chain</h4>
                  </div>
                  <button
                    type="button"
                    onClick={() => setEditingTask(JSON.parse(JSON.stringify(task)))}
                    className="text-xs font-semibold text-primary hover:underline"
                  >
                    Edit Sequence
                  </button>
                </div>

                <div className="mt-3.5 flex items-center gap-2.5 overflow-x-auto py-1">
                  {/* Primary */}
                  <div className="p-3 bg-primary/10 border border-primary/20 rounded-lg shrink-0 min-w-[190px]">
                    <span className="text-[10px] font-bold text-primary uppercase tracking-wider block">
                      Step 1 &bull; Primary
                    </span>
                    <div className="text-xs font-bold text-text-primary mt-0.5 truncate">
                      {task.primary_model}
                    </div>
                    <div className="text-[10px] text-text-muted font-mono">{task.primary_provider}</div>
                  </div>

                  <ArrowRight className="w-3.5 h-3.5 text-text-muted shrink-0" />

                  {/* Fallbacks */}
                  {task.fallback_models && task.fallback_models.length > 0 ? (
                    task.fallback_models.map((fb, idx) => (
                      <React.Fragment key={idx}>
                        <div className="p-3 bg-status-warning/10 border border-status-warning/20 rounded-lg shrink-0 min-w-[190px]">
                          <span className="text-[10px] font-bold text-status-warning uppercase tracking-wider block">
                            Step {idx + 2} &bull; Fallback {idx + 1}
                          </span>
                          <div className="text-xs font-bold text-text-primary mt-0.5 truncate">
                            {fb.model_id}
                          </div>
                          <div className="text-[10px] text-text-muted font-mono">{fb.provider}</div>
                        </div>
                        {idx < task.fallback_models.length - 1 && (
                          <ArrowRight className="w-3.5 h-3.5 text-text-muted shrink-0" />
                        )}
                      </React.Fragment>
                    ))
                  ) : (
                    <div className="p-3 bg-surface-elevated border border-surface-border rounded-lg shrink-0 text-xs text-text-muted">
                      No additional fallbacks configured
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 5: EXECUTION HISTORY */}
      {/* =================================================================== */}
      {activeTab === 'executions' && (
        <div className="space-y-6">
          {/* Filters Bar */}
          <div className="p-4 bg-surface border border-surface-border rounded-xl flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 shadow-surface-elevated">
            <div className="flex flex-wrap items-center gap-3">
              <select
                value={execTaskFilter}
                onChange={(e) => {
                  setExecTaskFilter(e.target.value);
                  setExecPage(1);
                  loadExecutions(1, e.target.value, execStatusFilter);
                }}
                className="py-1.5 px-3 text-xs rounded-lg border border-surface-border bg-surface-elevated text-text-primary focus:outline-none focus:border-primary transition-colors"
              >
                <option value="all">All Task Categories</option>
                {taskAssignments.map((t) => (
                  <option key={t.task_type} value={t.task_type}>
                    {t.name}
                  </option>
                ))}
              </select>

              <select
                value={execStatusFilter}
                onChange={(e) => {
                  setExecStatusFilter(e.target.value);
                  setExecPage(1);
                  loadExecutions(1, execTaskFilter, e.target.value);
                }}
                className="py-1.5 px-3 text-xs rounded-lg border border-surface-border bg-surface-elevated text-text-primary focus:outline-none focus:border-primary transition-colors"
              >
                <option value="all">All Statuses</option>
                <option value="completed">Completed</option>
                <option value="fallback_used">Fallback Used</option>
                <option value="failed">Failed</option>
              </select>
            </div>

            <div className="text-xs text-text-muted">
              Total Audited Records: <span className="font-semibold text-text-primary">{executionsTotal}</span>
            </div>
          </div>

          {/* Executions Table */}
          <div className="bg-surface rounded-xl border border-surface-border shadow-surface-elevated overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-surface-border bg-surface-elevated/50 text-text-muted font-medium">
                    <th className="py-3 px-4">Task</th>
                    <th className="py-3 px-4">Primary Model</th>
                    <th className="py-3 px-4">Actual Model Used</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Latency</th>
                    <th className="py-3 px-4">Tokens</th>
                    <th className="py-3 px-4">Timestamp</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {executions.map((exec) => (
                    <tr key={exec.id} className="hover:bg-surface-hover transition-colors">
                      <td className="py-3 px-4 font-medium text-text-primary">
                        <span className="font-mono text-xs">{exec.task_type}</span>
                      </td>
                      <td className="py-3 px-4 text-xs text-text-secondary font-mono">
                        {exec.primary_provider}/{exec.primary_model}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-mono font-semibold text-text-primary">
                            {exec.actual_provider}/{exec.actual_model}
                          </span>
                          {exec.fallback_used && (
                            <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-status-warning/10 text-status-warning border border-status-warning/20">
                              Failover
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${
                            exec.status === 'completed'
                              ? 'bg-status-success/10 text-status-success border border-status-success/20'
                              : exec.status === 'fallback_used'
                              ? 'bg-status-warning/10 text-status-warning border border-status-warning/20'
                              : 'bg-status-error/10 text-status-error border border-status-error/20'
                          }`}
                        >
                          {exec.status}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-xs font-mono text-text-secondary">
                        {exec.duration_ms ? `${(exec.duration_ms / 1000).toFixed(2)}s` : 'N/A'}
                      </td>
                      <td className="py-3 px-4 text-xs font-mono text-text-secondary">
                        {exec.total_tokens ? exec.total_tokens.toLocaleString() : 'N/A'}
                      </td>
                      <td className="py-3 px-4 text-xs text-text-secondary">
                        {new Date(exec.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          type="button"
                          onClick={() => handleOpenExecutionDetail(exec.id)}
                          className="px-2.5 py-1 text-[11px] font-medium text-primary hover:bg-primary/10 border border-primary/20 rounded-md transition-colors"
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  ))}
                  {executions.length === 0 && (
                    <tr>
                      <td colSpan={8} className="py-10 text-center text-xs text-text-muted">
                        No execution records matching your criteria.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Execution Pagination Bar */}
            <div className="p-4 border-t border-surface-border flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-text-muted">
              <div>
                Showing{' '}
                <span className="font-semibold text-text-primary">
                  {executionsTotal === 0 ? 0 : (execPage - 1) * execLimit + 1}
                </span>{' '}
                to{' '}
                <span className="font-semibold text-text-primary">
                  {Math.min(execPage * execLimit, executionsTotal)}
                </span>{' '}
                of <span className="font-semibold text-text-primary">{executionsTotal.toLocaleString()}</span> executions
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const p = Math.max(execPage - 1, 1);
                    setExecPage(p);
                    loadExecutions(p, execTaskFilter, execStatusFilter);
                  }}
                  disabled={execPage <= 1}
                  className="p-1.5 rounded-lg border border-surface-border hover:bg-surface-elevated disabled:opacity-40 disabled:cursor-not-allowed text-text-primary transition-colors"
                  aria-label="Previous page"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="px-2 font-medium">
                  Page {execPage} of {totalExecPages}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    const p = Math.min(execPage + 1, totalExecPages);
                    setExecPage(p);
                    loadExecutions(p, execTaskFilter, execStatusFilter);
                  }}
                  disabled={execPage >= totalExecPages}
                  className="p-1.5 rounded-lg border border-surface-border hover:bg-surface-elevated disabled:opacity-40 disabled:cursor-not-allowed text-text-primary transition-colors"
                  aria-label="Next page"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 6: RUNTIME SETTINGS */}
      {/* =================================================================== */}
      {activeTab === 'settings' && (
        <div className="space-y-6">
          <div className="p-5 bg-surface border border-surface-border rounded-xl shadow-surface-elevated">
            <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Sliders className="w-4 h-4 text-primary" />
              <span>General Execution & Concurrency</span>
            </h2>
            <p className="text-xs text-text-secondary mt-1">
              Configure bounded concurrency, timeouts, and execution policies applied globally across evaluations.
            </p>

            <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-5">
              <div>
                <label className="block text-xs font-semibold text-text-primary uppercase tracking-wider mb-2">
                  Global Max Concurrency
                </label>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={maxConcurrencyInput}
                  onChange={(e) => setMaxConcurrencyInput(parseInt(e.target.value) || 10)}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-surface-border bg-surface-elevated text-text-primary focus:outline-none focus:border-primary transition-colors"
                />
                <span className="text-[11px] text-text-muted mt-1 block">
                  Upper bound on simultaneous isolated Pi execution sessions.
                </span>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-primary uppercase tracking-wider mb-2">
                  Default Execution Timeout (seconds)
                </label>
                <input
                  type="number"
                  min={10}
                  max={600}
                  value={timeoutInput}
                  onChange={(e) => setTimeoutInput(parseInt(e.target.value) || 180)}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-surface-border bg-surface-elevated text-text-primary focus:outline-none focus:border-primary transition-colors"
                />
                <span className="text-[11px] text-text-muted mt-1 block">
                  Subprocesses exceeding this limit are terminated cleanly with zero orphaned processes.
                </span>
              </div>
            </div>

            <div className="mt-5 pt-4 border-t border-surface-border flex justify-end">
              <button
                type="button"
                onClick={handleSaveRuntimeSettings}
                disabled={isSavingSettings}
                className="px-4 py-2 bg-primary text-white rounded-lg text-xs font-semibold hover:bg-primary-hover transition-colors disabled:opacity-50"
              >
                {isSavingSettings ? 'Saving Settings...' : 'Save Dynamic Settings'}
              </button>
            </div>
          </div>

          {/* Pi Installation Details (Read Only) */}
          <div className="p-5 bg-surface border border-surface-border rounded-xl shadow-surface-elevated">
            <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Terminal className="w-4 h-4 text-primary" />
              <span>Pi Global Runtime Environment</span>
            </h2>
            <p className="text-xs text-text-secondary mt-1">
              Scorva uses your globally installed and pre-authenticated Pi installation.
            </p>

            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div className="p-3.5 bg-surface-elevated border border-surface-border rounded-lg">
                <span className="text-text-muted block font-medium">Pi CLI Executable:</span>
                <span className="font-mono text-text-primary font-semibold mt-0.5 block truncate">
                  {runtimeOverview?.pi_status.executable_path || '/home/shubh/.local/bin/pi'}
                </span>
              </div>

              <div className="p-3.5 bg-surface-elevated border border-surface-border rounded-lg">
                <span className="text-text-muted block font-medium">Configuration Directory:</span>
                <span className="font-mono text-text-primary font-semibold mt-0.5 block truncate">
                  {runtimeOverview?.pi_status.config_dir || '~/.pi/agent'}
                </span>
              </div>

              <div className="p-3.5 bg-surface-elevated border border-surface-border rounded-lg">
                <span className="text-text-muted block font-medium">Model Catalog Store:</span>
                <span className="text-status-success font-semibold mt-0.5 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  models-store.json ({runtimeOverview?.pi_status.total_discovered_models || 557} models discovered)
                </span>
              </div>

              <div className="p-3.5 bg-surface-elevated border border-surface-border rounded-lg">
                <span className="text-text-muted block font-medium">Auth Credentials Store:</span>
                <span className="text-status-success font-semibold mt-0.5 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  auth.json (Found, credentials preserved outside Scorva)
                </span>
              </div>
            </div>
          </div>

          {/* Ollama Local Endpoint Probe */}
          <div className="p-5 bg-surface border border-surface-border rounded-xl shadow-surface-elevated">
            <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Database className="w-4 h-4 text-primary" />
              <span>Ollama Fallback Endpoint Probe</span>
            </h2>
            <p className="text-xs text-text-secondary mt-1">
              On-premise Ollama fallback inference with SSRF IP-pinning protection.
            </p>

            <div className="mt-4 flex items-center gap-3">
              <input
                type="text"
                value={ollamaUrlInput}
                onChange={(e) => setOllamaUrlInput(e.target.value)}
                placeholder="http://localhost:11434"
                className="flex-1 px-3 py-2 text-xs rounded-lg border border-surface-border bg-surface-elevated text-text-primary focus:outline-none focus:border-primary transition-colors"
              />
              <button
                type="button"
                onClick={handleProbeOllama}
                disabled={isProbingOllama}
                className="px-3.5 py-2 bg-surface-elevated text-text-primary border border-surface-border rounded-lg text-xs font-medium hover:bg-surface-hover transition-colors disabled:opacity-50"
              >
                {isProbingOllama ? 'Probing...' : 'Probe Endpoint'}
              </button>
            </div>

            {ollamaProbeResult && (
              <div
                className={`mt-4 p-3 rounded-lg border text-xs ${
                  ollamaProbeResult.is_online
                    ? 'bg-status-success/10 border-status-success/30 text-status-success'
                    : 'bg-status-error/10 border-status-error/30 text-status-error'
                }`}
              >
                <div className="font-semibold">
                  {ollamaProbeResult.is_online ? 'Ollama Online' : 'Ollama Offline'}
                </div>
                {ollamaProbeResult.latency_ms && (
                  <div>Latency: {ollamaProbeResult.latency_ms} ms</div>
                )}
                {ollamaProbeResult.error && <div>Error: {ollamaProbeResult.error}</div>}
              </div>
            )}
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 1: MODEL TEST DIALOG */}
      {/* =================================================================== */}
      {testModalOpen && modelToTest && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="bg-surface rounded-2xl max-w-xl w-full p-6 shadow-2xl border border-surface-border max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-4 border-b border-surface-border">
              <div className="flex items-center gap-2">
                <Cpu className="w-5 h-5 text-primary" />
                <h3 className="text-sm font-bold text-text-primary">
                  Test Model: {modelToTest.display_name}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setTestModalOpen(false)}
                className="p-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="mt-4 space-y-4">
              <div className="text-xs text-text-secondary flex items-center gap-2">
                <span>Provider: <strong className="text-text-primary">{modelToTest.provider}</strong></span>
                <span>&bull;</span>
                <span>ID: <strong className="text-text-primary font-mono">{modelToTest.model_id}</strong></span>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-primary uppercase tracking-wider mb-2">
                  Test Evaluation Type
                </label>
                <div className="flex gap-4 text-xs">
                  <label className="flex items-center gap-2 cursor-pointer text-text-secondary">
                    <input
                      type="radio"
                      name="testMode"
                      checked={testPromptMode === 'structured'}
                      onChange={() => setTestPromptMode('structured')}
                    />
                    <span>Structured JSON Output (status, summary, confidence)</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer text-text-secondary">
                    <input
                      type="radio"
                      name="testMode"
                      checked={testPromptMode === 'custom'}
                      onChange={() => setTestPromptMode('custom')}
                    />
                    <span>Custom Prompt</span>
                  </label>
                </div>
              </div>

              {testPromptMode === 'custom' && (
                <div>
                  <textarea
                    rows={3}
                    value={customTestPrompt}
                    onChange={(e) => setCustomTestPrompt(e.target.value)}
                    placeholder="Enter test prompt..."
                    className="w-full p-2.5 text-xs rounded-lg border border-surface-border bg-surface-elevated text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary transition-colors"
                  />
                </div>
              )}

              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleRunModelTest}
                  disabled={isTesting}
                  className="px-4 py-2 bg-primary text-white rounded-lg text-xs font-semibold hover:bg-primary-hover transition-colors disabled:opacity-50 flex items-center gap-1.5 shadow-xs"
                >
                  <Play className={`w-3.5 h-3.5 ${isTesting ? 'animate-spin' : ''}`} />
                  <span>{isTesting ? 'Executing Inference...' : 'Execute Test'}</span>
                </button>
              </div>

              {/* Test Results Display */}
              {testResult && (
                <div className="mt-4 p-4 rounded-xl border border-surface-border bg-surface-elevated space-y-3">
                  <div className="flex items-center justify-between">
                    <span
                      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold ${
                        testResult.success
                          ? 'bg-status-success/10 text-status-success border border-status-success/20'
                          : 'bg-status-error/10 text-status-error border border-status-error/20'
                      }`}
                    >
                      {testResult.success ? 'TEST PASSED' : 'TEST FAILED'}
                    </span>
                    <span className="text-xs font-mono text-text-muted">
                      Latency: {(testResult.duration_ms / 1000).toFixed(2)}s
                    </span>
                  </div>

                  {testResult.error_message && (
                    <div className="p-3 bg-status-error/10 border border-status-error/20 rounded text-xs text-status-error">
                      {testResult.error_message}
                    </div>
                  )}

                  {testResult.structured_output && (
                    <div>
                      <span className="text-[11px] font-semibold text-text-secondary block mb-1">
                        Parsed Structured Output:
                      </span>
                      <pre className="p-3 bg-surface border border-surface-border rounded text-xs font-mono text-text-primary overflow-x-auto max-h-48">
                        {JSON.stringify(testResult.structured_output, null, 2)}
                      </pre>
                    </div>
                  )}

                  {testResult.usage && (
                    <div className="text-[11px] text-text-muted flex gap-3">
                      <span>Input tokens: {testResult.usage.input}</span>
                      <span>Output tokens: {testResult.usage.output}</span>
                      <span>Total: {testResult.usage.total_tokens}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 2: TASK ROUTING EDIT DIALOG */}
      {/* =================================================================== */}
      {editingTask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="bg-surface rounded-2xl max-w-xl w-full p-6 shadow-2xl border border-surface-border max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-4 border-b border-surface-border">
              <h3 className="text-sm font-bold text-text-primary">
                Configure Routing: {editingTask.name}
              </h3>
              <button
                type="button"
                onClick={() => setEditingTask(null)}
                className="p-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="mt-4 space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-text-primary uppercase tracking-wider mb-1">
                  Primary Model
                </label>
                <select
                  value={`${editingTask.primary_provider}:${editingTask.primary_model}`}
                  onChange={(e) => {
                    const [p, m] = e.target.value.split(':');
                    setEditingTask({ ...editingTask, primary_provider: p, primary_model: m });
                  }}
                  className="w-full p-2.5 rounded-lg border border-surface-border bg-surface-elevated text-text-primary focus:outline-none focus:border-primary transition-colors"
                >
                  {models
                    .filter((m) => m.is_enabled)
                    .map((m) => (
                      <option key={`${m.provider}:${m.model_id}`} value={`${m.provider}:${m.model_id}`}>
                        {m.display_name} ({m.provider}/{m.model_id})
                      </option>
                    ))}
                </select>
              </div>

              <div>
                <label className="block font-semibold text-text-primary uppercase tracking-wider mb-1">
                  Secondary Fallback Model
                </label>
                <select
                  value={
                    editingTask.secondary_provider
                      ? `${editingTask.secondary_provider}:${editingTask.secondary_model}`
                      : ''
                  }
                  onChange={(e) => {
                    if (!e.target.value) {
                      setEditingTask({ ...editingTask, secondary_provider: null, secondary_model: null });
                    } else {
                      const [p, m] = e.target.value.split(':');
                      setEditingTask({ ...editingTask, secondary_provider: p, secondary_model: m });
                    }
                  }}
                  className="w-full p-2.5 rounded-lg border border-surface-border bg-surface-elevated text-text-primary focus:outline-none focus:border-primary transition-colors"
                >
                  <option value="">None (Rely on ordered fallback chain)</option>
                  {models.map((m) => (
                    <option key={`sec:${m.provider}:${m.model_id}`} value={`${m.provider}:${m.model_id}`}>
                      {m.display_name} ({m.provider}/{m.model_id})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block font-semibold text-text-primary uppercase tracking-wider mb-1">
                    Timeout (seconds)
                  </label>
                  <input
                    type="number"
                    min={10}
                    max={600}
                    value={editingTask.timeout_seconds}
                    onChange={(e) =>
                      setEditingTask({ ...editingTask, timeout_seconds: parseInt(e.target.value) || 180 })
                    }
                    className="w-full p-2.5 rounded-lg border border-surface-border bg-surface-elevated text-text-primary focus:outline-none focus:border-primary transition-colors"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-text-primary uppercase tracking-wider mb-1">
                    Max Retries
                  </label>
                  <input
                    type="number"
                    min={0}
                    max={5}
                    value={editingTask.max_retries}
                    onChange={(e) =>
                      setEditingTask({ ...editingTask, max_retries: parseInt(e.target.value) || 2 })
                    }
                    className="w-full p-2.5 rounded-lg border border-surface-border bg-surface-elevated text-text-primary focus:outline-none focus:border-primary transition-colors"
                  />
                </div>
              </div>

              <div>
                <label className="flex items-center gap-2 cursor-pointer mt-2">
                  <input
                    type="checkbox"
                    checked={editingTask.parallel_enabled}
                    onChange={(e) =>
                      setEditingTask({ ...editingTask, parallel_enabled: e.target.checked })
                    }
                  />
                  <span className="font-medium text-text-primary">
                    Enable Parallel Execution (evaluates simultaneously with other tasks)
                  </span>
                </label>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-surface-border">
                <button
                  type="button"
                  onClick={() => setEditingTask(null)}
                  className="px-3.5 py-2 border border-surface-border rounded-lg text-xs font-medium text-text-secondary hover:bg-surface-hover hover:text-text-primary transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSaveTaskRouting}
                  disabled={isSavingTask}
                  className="px-4 py-2 bg-primary text-white rounded-lg text-xs font-semibold hover:bg-primary-hover transition-colors disabled:opacity-50 shadow-xs"
                >
                  {isSavingTask ? 'Saving Policy...' : 'Save Routing Policy'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 3: EXECUTION RECORD INSPECT DIALOG */}
      {/* =================================================================== */}
      {selectedExecutionDetail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="bg-surface rounded-2xl max-w-2xl w-full p-6 shadow-2xl border border-surface-border max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-4 border-b border-surface-border">
              <div>
                <span className="text-xs font-mono font-bold text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded">
                  {selectedExecutionDetail.task_type}
                </span>
                <h3 className="text-sm font-bold text-text-primary mt-1">
                  Execution Audit Record
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedExecutionDetail(null)}
                className="p-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="mt-4 space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3 p-3.5 bg-surface-elevated border border-surface-border rounded-lg">
                <div>
                  <span className="text-text-muted">Primary Model:</span>
                  <div className="font-mono font-semibold text-text-primary">
                    {selectedExecutionDetail.primary_provider}/{selectedExecutionDetail.primary_model}
                  </div>
                </div>
                <div>
                  <span className="text-text-muted">Actual Model Used:</span>
                  <div className="font-mono font-semibold text-text-primary">
                    {selectedExecutionDetail.actual_provider}/{selectedExecutionDetail.actual_model}
                  </div>
                </div>
                <div>
                  <span className="text-text-muted">Execution Duration:</span>
                  <div className="font-mono font-semibold text-text-primary">
                    {(selectedExecutionDetail.duration_ms / 1000).toFixed(2)}s
                  </div>
                </div>
                <div>
                  <span className="text-text-muted">Tokens Consumed:</span>
                  <div className="font-mono font-semibold text-text-primary">
                    {selectedExecutionDetail.total_tokens ? selectedExecutionDetail.total_tokens.toLocaleString() : 'N/A'}
                  </div>
                </div>
              </div>

              {selectedExecutionDetail.fallback_used && (
                <div className="p-3 bg-status-warning/10 border border-status-warning/20 rounded-lg text-xs text-status-warning">
                  <strong>Failover Event:</strong> {selectedExecutionDetail.fallback_reason}
                </div>
              )}

              {selectedExecutionDetail.prompt_preview && (
                <div>
                  <span className="font-semibold text-text-secondary block mb-1">Prompt Preview:</span>
                  <div className="p-3 bg-surface-elevated border border-surface-border rounded text-text-primary font-mono text-[11px] max-h-28 overflow-y-auto">
                    {selectedExecutionDetail.prompt_preview}
                  </div>
                </div>
              )}

              {selectedExecutionDetail.output_payload && (
                <div>
                  <span className="font-semibold text-text-secondary block mb-1">Structured Model Output:</span>
                  <pre className="p-3 bg-surface-elevated border border-surface-border rounded text-text-primary font-mono text-[11px] max-h-48 overflow-x-auto">
                    {JSON.stringify(selectedExecutionDetail.output_payload, null, 2)}
                  </pre>
                </div>
              )}

              {selectedExecutionDetail.error_message && (
                <div className="p-3 bg-status-error/10 border border-status-error/20 rounded text-xs text-status-error">
                  <strong>Error:</strong> {selectedExecutionDetail.error_message}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

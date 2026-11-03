import {
  HealthResponse,
  ApiResponseError,
  LoginResponse,
  MfaSetupResponse,
  AuthSuccessResponse,
  UserProfile,
  PaginatedUsersResponse,
  AdminCreateUserRequest,
  DashboardOverviewResponse,
  DashboardTrendsResponse,
  AuditEventsResponse,
  ConfigurationSetting,
  OrganizationStatus,
  OrgRole,
  OrganizationDetailResponse,
  OrganizationProfileResponse,
  OrganizationDashboardResponse,
  OrganizationTeamPage,
  OrganizationTeamDetailResponse,
  OrganizationActivityResponse,
  UpdateOrganizationSettingsRequest,
  OrganizationMemberResponse,
  PaginatedOrganizationsResponse,
  CreateOrganizationRequest,
  AdminUpdateOrganizationRequest,
  UpdateOrganizationStatusRequest,
  TransferOwnershipRequest,
  AdminAddMemberRequest,
  UpdateMemberRoleRequest,
  TenantUpdateOrganizationRequest,
  InviteMemberRequest,
  MemberOperationResponse,
  HackathonStatus,
  HackathonDetailResponse,
  PaginatedHackathonsResponse,
  CreateHackathonRequest,
  UpdateHackathonRequest,
  AdminUpdateHackathonStatusRequest,
  TenantUpdateHackathonStatusRequest,
  HackathonOverviewResponse,
  TeamListItem,
  TeamDetailResponse,
  CreateTeamRequest,
  AddTeamParticipantRequest,
  AddTeamParticipantResponse,
  VerifyJoinCodeRequest,
  VerifyJoinCodeResponse,
  JoinTeamRequest,
  SubmissionListItem,
  SubmissionDetailResponse,
  CreateSubmissionRequest,
  JudgeListItem,
  AssignJudgeRequest,
  RubricDetailResponse,
  CreateRubricRequest,
  AddCriterionRequest,
  ValidateRepositoryRequest,
  RepositoryValidationResult,
  LinkRepositoryRequest,
  UpdateBranchRequest,
  RepositoryActivityItem,
  SubmissionEvaluationTransparencyResponse,
  HackathonEvaluationSummaryResponse,
  EvaluationJobListItem,
  EvaluationJobResponse,
  JudgeAssignmentItem,
  JudgeQueueItem,
  JudgeSubmissionReviewResponse,
  SaveJudgeReviewRequest,
  RevertJudgeReviewRequest,
  SubmitJudgeReviewRequest,
  JudgeReviewDetail,
  OrganizerReviewProgressResponse,
  SubmissionReviewsResponse,
  JudgeHackathonDetail,
  ParticipantTeamItem,
  PermissionItem,
  RoleItem,
  CreateRoleRequest,
  UpdateRolePermissionsRequest,
  UserRoleAssignmentItem,
  LifecycleStageItem,
  ParticipantOverviewResponse,
  LeaderboardResponse,
  PerformanceResponse,
  ParticipantTaskItem,
  UpdateTaskStatusRequest,
  NotificationListResponse,
  SupportTicketItem,
  SupportReplyItem,
  SupportTicketDetailResponse,
  CreateSupportTicketRequest,
  CreateSupportReplyRequest,
  AdminSupportTicketItem,
  AdminSupportTicketListResponse,
  AdminSupportTicketDetailResponse,
  AdminCreateSupportReplyRequest,
  AdminUpdateSupportTicketStatusRequest,
  AdminJudgeItem,
  AdminCreateJudgeRequest,
  AIRoutingConfigRequest,
  AIRoutingConfigResponse,
  AIEndpointProbeResponse,
  AIOperationsStatsResponse,
  RegistrationStatusResponse,
  ParticipantProjectRegistrationRequest,
  ProjectRegistrationSuccessResponse,
  ParticipantPatTokenStatus,
  SaveParticipantPatRequest,
  SaveParticipantPatResponse,
  ParticipantGitHubSettingsResponse,
  VerifyParticipantGitHubResponse,
  OllamaRepoInspectionResponse,
} from '@/types/api';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export class ApiClientError extends Error {
  public code: string;
  public status: number;
  public details: unknown[];
  public requestId?: string;

  constructor(
    message: string,
    status: number,
    code: string = 'API_ERROR',
    details: unknown[] = [],
    requestId?: string
  ) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

export interface FetchApiOptions extends RequestInit {
  timeoutMs?: number;
}

export async function fetchApi<T>(
  endpoint: string,
  options: FetchApiOptions = {}
): Promise<T> {
  const url = `${API_BASE_URL.replace(/\/$/, '')}/${endpoint.replace(/^\//, '')}`;

  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') &&
      !(typeof FormData !== 'undefined' && options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const timeoutMs = options.timeoutMs ?? 30000; // default 30s timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const effectiveSignal = options.signal
    ? typeof AbortSignal.any === 'function'
      ? AbortSignal.any([options.signal, controller.signal])
      : options.signal
    : controller.signal;

  try {
    const response = await fetch(url, {
      ...options,
      credentials: 'include',
      headers,
      signal: effectiveSignal,
    });

    if (!response.ok) {
      let errorBody: ApiResponseError | null = null;
      try {
        errorBody = await response.json();
      } catch {
        // Response was not JSON
      }

      if (errorBody) {
        const message =
          errorBody.detail ||
          errorBody.error?.message ||
          errorBody.title ||
          `HTTP Request failed with status ${response.status}`;
        const code = errorBody.code || errorBody.error?.code || 'API_ERROR';
        const details = (errorBody.invalid_params || errorBody.error?.details || []) as unknown[];
        const requestId = errorBody.request_id || errorBody.error?.request_id;

        if (
          response.status === 401 &&
          (code === 'SESSION_NOT_FOUND' || code === 'SESSION_REVOKED' || code === 'SESSION_EXPIRED') &&
          typeof window !== 'undefined' &&
          !window.location.pathname.startsWith('/login')
        ) {
          window.location.href = `/login?expired=1&redirect=${encodeURIComponent(window.location.pathname)}`;
        }

        throw new ApiClientError(
          message,
          response.status,
          code,
          details,
          requestId
        );
      }

      throw new ApiClientError(
        `HTTP Request failed with status ${response.status}`,
        response.status
      );
    }

    return (await response.json()) as T;
  } catch (err: unknown) {
    if (err instanceof ApiClientError) {
      throw err;
    }

    if (err instanceof DOMException && err.name === 'AbortError') {
      if (options.signal?.aborted) {
        throw new ApiClientError('Request was aborted', 0, 'REQUEST_ABORTED');
      }
      const timeoutSec = Math.round((options.timeoutMs ?? 30000) / 1000);
      throw new ApiClientError(`Request timed out after ${timeoutSec} seconds`, 408, 'REQUEST_TIMEOUT');
    }

    throw new ApiClientError(
      err instanceof Error ? err.message : 'Unknown network error',
      0,
      'NETWORK_ERROR'
    );
  } finally {
    clearTimeout(timeoutId);
  }
}

export const api = {
  // Health
  getHealth: async (): Promise<HealthResponse> => {
    return fetchApi<HealthResponse>('/api/v1/health');
  },
  getLiveness: async (): Promise<{ status: string; timestamp: string }> => {
    return fetchApi<{ status: string; timestamp: string }>('/api/v1/health/live');
  },
  getReadiness: async (): Promise<HealthResponse> => {
    return fetchApi<HealthResponse>('/api/v1/health/ready');
  },

  // Auth
  login: async (
    email: string,
    password: string,
    redirectUrl?: string,
    teamCode?: string,
    judgeCode?: string
  ): Promise<LoginResponse> => {
    return fetchApi<LoginResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        redirect_url: redirectUrl,
        team_code: teamCode || undefined,
        judge_code: judgeCode || undefined,
      }),
    });
  },
  setupMfa: async (enrollmentToken: string): Promise<MfaSetupResponse> => {
    return fetchApi<MfaSetupResponse>('/api/v1/auth/mfa/setup', {
      method: 'POST',
      body: JSON.stringify({ enrollment_token: enrollmentToken }),
    });
  },
  verifyMfa: async (token: string, totpCode: string): Promise<AuthSuccessResponse> => {
    return fetchApi<AuthSuccessResponse>('/api/v1/auth/mfa/verify', {
      method: 'POST',
      body: JSON.stringify({ token, totp_code: totpCode }),
    });
  },
  getMe: async (): Promise<UserProfile> => {
    return fetchApi<UserProfile>('/api/v1/auth/me');
  },
  logout: async (): Promise<{ message: string }> => {
    return fetchApi<{ message: string }>('/api/v1/auth/logout', {
      method: 'POST',
    });
  },

  // Users Directory & Session Revocation
  getUsers: async (params?: {
    page?: number;
    limit?: number;
    search?: string;
    role?: string;
    status?: string;
    sort_by?: string;
    sort_order?: 'asc' | 'desc';
  }, options?: RequestInit): Promise<PaginatedUsersResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.search) searchParams.set('search', params.search);
    if (params?.role) searchParams.set('role', params.role);
    if (params?.status) searchParams.set('status', params.status);
    if (params?.sort_by) searchParams.set('sort_by', params.sort_by);
    if (params?.sort_order) searchParams.set('sort_order', params.sort_order);

    const qs = searchParams.toString();
    return fetchApi<PaginatedUsersResponse>(`/api/v1/admin/users${qs ? `?${qs}` : ''}`, options);
  },
  updateUserStatus: async (userId: string, isActive: boolean, reason?: string): Promise<UserProfile> => {
    return fetchApi<UserProfile>(`/api/v1/admin/users/${userId}/status`, {
      method: 'POST',
      body: JSON.stringify({ is_active: isActive, reason }),
    });
  },
  createAdminUser: async (data: AdminCreateUserRequest): Promise<UserProfile> => {
    return fetchApi<UserProfile>('/api/v1/admin/users', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
  revokeUserSessions: async (userId: string): Promise<{ message: string }> => {
    return fetchApi<{ message: string }>(`/api/v1/admin/users/${userId}/revoke-sessions`, {
      method: 'POST',
    });
  },

  // Security Audit Log
  getAuditEvents: async (params?: {
    actor_email?: string;
    action?: string;
    resource_type?: string;
    organization_id?: string;
    limit?: number;
    offset?: number;
  }, options?: RequestInit): Promise<AuditEventsResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.actor_email) searchParams.set('actor_email', params.actor_email);
    if (params?.action) searchParams.set('action', params.action);
    if (params?.resource_type) searchParams.set('resource_type', params.resource_type);
    if (params?.organization_id) searchParams.set('organization_id', params.organization_id);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));

    const qs = searchParams.toString();
    const endpoint = `/api/v1/admin/security/audit-events${qs ? `?${qs}` : ''}`;
    return fetchApi<AuditEventsResponse>(endpoint, options);
  },

  // ==========================================
  // Platform Admin: Dashboard Overview
  getDashboardOverview: async (options?: RequestInit & { refresh?: boolean }): Promise<DashboardOverviewResponse> => {
    const qs = options?.refresh ? '?refresh=true' : '';
    return fetchApi<DashboardOverviewResponse>(`/api/v1/admin/dashboard/overview${qs}`, options);
  },

  getDashboardTrends: async (params?: { period?: string }, options?: RequestInit): Promise<DashboardTrendsResponse> => {
    const qs = params?.period ? `?period=${encodeURIComponent(params.period)}` : '';
    return fetchApi<DashboardTrendsResponse>(`/api/v1/admin/dashboard/trends${qs}`, options);
  },

  // Platform Admin: Organizations
  // ==========================================
  getAdminOrganizations: async (params?: {
    page?: number;
    limit?: number;
    search?: string;
    status?: OrganizationStatus;
    sort_by?: string;
    sort_order?: 'asc' | 'desc';
  }, options?: RequestInit): Promise<PaginatedOrganizationsResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.search) searchParams.set('search', params.search);
    if (params?.status) searchParams.set('status', params.status);
    if (params?.sort_by) searchParams.set('sort_by', params.sort_by);
    if (params?.sort_order) searchParams.set('sort_order', params.sort_order);

    const qs = searchParams.toString();
    return fetchApi<PaginatedOrganizationsResponse>(`/api/v1/admin/organizations${qs ? `?${qs}` : ''}`, options);
  },

  createAdminOrganization: async (
    data: CreateOrganizationRequest
  ): Promise<OrganizationDetailResponse> => {
    return fetchApi<OrganizationDetailResponse>('/api/v1/admin/organizations', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  getAdminOrganization: async (
    orgId: string,
    options?: RequestInit
  ): Promise<OrganizationDetailResponse> => {
    return fetchApi<OrganizationDetailResponse>(`/api/v1/admin/organizations/${orgId}`, options);
  },

  updateAdminOrganization: async (
    orgId: string,
    data: AdminUpdateOrganizationRequest
  ): Promise<OrganizationDetailResponse> => {
    return fetchApi<OrganizationDetailResponse>(`/api/v1/admin/organizations/${orgId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  updateAdminOrganizationStatus: async (
    orgId: string,
    data: UpdateOrganizationStatusRequest
  ): Promise<OrganizationDetailResponse> => {
    return fetchApi<OrganizationDetailResponse>(`/api/v1/admin/organizations/${orgId}/status`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  transferAdminOrganizationOwnership: async (
    orgId: string,
    data: TransferOwnershipRequest
  ): Promise<OrganizationDetailResponse> => {
    return fetchApi<OrganizationDetailResponse>(`/api/v1/admin/organizations/${orgId}/transfer-ownership`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  getAdminOrganizationMembers: async (
    orgId: string,
    options?: RequestInit
  ): Promise<OrganizationMemberResponse[]> => {
    return fetchApi<OrganizationMemberResponse[]>(`/api/v1/admin/organizations/${orgId}/members`, options);
  },

  addAdminOrganizationMember: async (
    orgId: string,
    data: AdminAddMemberRequest
  ): Promise<OrganizationMemberResponse> => {
    return fetchApi<OrganizationMemberResponse>(`/api/v1/admin/organizations/${orgId}/members`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  updateAdminOrganizationMemberRole: async (
    orgId: string,
    userId: string,
    data: UpdateMemberRoleRequest
  ): Promise<OrganizationMemberResponse> => {
    return fetchApi<OrganizationMemberResponse>(`/api/v1/admin/organizations/${orgId}/members/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  removeAdminOrganizationMember: async (
    orgId: string,
    userId: string
  ): Promise<MemberOperationResponse> => {
    return fetchApi<MemberOperationResponse>(`/api/v1/admin/organizations/${orgId}/members/${userId}`, {
      method: 'DELETE',
    });
  },

  // ==========================================
  // Platform Admin: Hackathons
  // ==========================================
  getAdminHackathons: async (params?: {
    page?: number;
    limit?: number;
    search?: string;
    status?: HackathonStatus;
    organization_id?: string;
    sort_by?: string;
    sort_order?: 'asc' | 'desc';
  }, options?: RequestInit): Promise<PaginatedHackathonsResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.search) searchParams.set('search', params.search);
    if (params?.status) searchParams.set('status', params.status);
    if (params?.organization_id) searchParams.set('organization_id', params.organization_id);
    if (params?.sort_by) searchParams.set('sort_by', params.sort_by);
    if (params?.sort_order) searchParams.set('sort_order', params.sort_order);

    const qs = searchParams.toString();
    return fetchApi<PaginatedHackathonsResponse>(`/api/v1/admin/hackathons${qs ? `?${qs}` : ''}`, options);
  },

  getAdminHackathon: async (
    hackathonId: string,
    options?: RequestInit
  ): Promise<HackathonDetailResponse> => {
    return fetchApi<HackathonDetailResponse>(`/api/v1/admin/hackathons/${hackathonId}`, options);
  },

  overrideAdminHackathonStatus: async (
    hackathonId: string,
    data: AdminUpdateHackathonStatusRequest
  ): Promise<HackathonDetailResponse> => {
    return fetchApi<HackathonDetailResponse>(`/api/v1/admin/hackathons/${hackathonId}/status`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // ==========================================
  // Tenant Scoped: Organizations & Hackathons
  // ==========================================
  getTenantOrganizationProfile: async (
    orgId: string,
    options?: RequestInit
  ): Promise<OrganizationProfileResponse> => {
    return fetchApi<OrganizationProfileResponse>(`/api/v1/organizations/${orgId}`, options);
  },

  getTenantOrganizationDashboard: async (
    orgId: string,
    options?: RequestInit
  ): Promise<OrganizationDashboardResponse> => {
    return fetchApi<OrganizationDashboardResponse>(
      `/api/v1/organizations/${orgId}/dashboard`,
      options
    );
  },

  updateTenantOrganizationSettings: async (
    orgId: string,
    data: UpdateOrganizationSettingsRequest
  ): Promise<OrganizationProfileResponse> => {
    return fetchApi<OrganizationProfileResponse>(
      `/api/v1/organizations/${orgId}/settings`,
      {
        method: 'PATCH',
        body: JSON.stringify(data),
      }
    );
  },

  getTenantOrganizationTeams: async (
    orgId: string,
    params: {
      page?: number;
      limit?: number;
      search?: string;
      hackathon_id?: string;
      submission_status?: string;
      evaluation_status?: string;
      sort_by?: string;
      sort_order?: 'asc' | 'desc';
    },
    options?: RequestInit
  ): Promise<OrganizationTeamPage> => {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') searchParams.set(key, String(value));
    });
    const qs = searchParams.toString();
    return fetchApi<OrganizationTeamPage>(
      `/api/v1/organizations/${orgId}/teams${qs ? `?${qs}` : ''}`,
      options
    );
  },

  getTenantOrganizationTeam: async (
    orgId: string,
    teamId: string,
    options?: RequestInit
  ): Promise<OrganizationTeamDetailResponse> => {
    return fetchApi<OrganizationTeamDetailResponse>(
      `/api/v1/organizations/${orgId}/teams/${teamId}`,
      options
    );
  },

  getTenantOrganizationActivity: async (
    orgId: string,
    params: {
      page?: number;
      limit?: number;
      activity_type?: string;
      actor?: string;
      start_date?: string;
      end_date?: string;
      hackathon_id?: string;
    },
    options?: RequestInit
  ): Promise<OrganizationActivityResponse> => {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') searchParams.set(key, String(value));
    });
    const qs = searchParams.toString();
    return fetchApi<OrganizationActivityResponse>(
      `/api/v1/organizations/${orgId}/activity${qs ? `?${qs}` : ''}`,
      options
    );
  },

  updateTenantOrganizationProfile: async (
    orgId: string,
    data: TenantUpdateOrganizationRequest
  ): Promise<OrganizationProfileResponse> => {
    return fetchApi<OrganizationProfileResponse>(`/api/v1/organizations/${orgId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  getTenantOrganizationMembers: async (
    orgId: string,
    options?: RequestInit
  ): Promise<OrganizationMemberResponse[]> => {
    return fetchApi<OrganizationMemberResponse[]>(`/api/v1/organizations/${orgId}/members`, options);
  },

  inviteTenantOrganizationMember: async (
    orgId: string,
    data: InviteMemberRequest
  ): Promise<OrganizationMemberResponse> => {
    return fetchApi<OrganizationMemberResponse>(`/api/v1/organizations/${orgId}/members`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  updateTenantOrganizationMemberRole: async (
    orgId: string,
    userId: string,
    data: UpdateMemberRoleRequest
  ): Promise<OrganizationMemberResponse> => {
    return fetchApi<OrganizationMemberResponse>(`/api/v1/organizations/${orgId}/members/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  removeTenantOrganizationMember: async (
    orgId: string,
    userId: string
  ): Promise<MemberOperationResponse> => {
    return fetchApi<MemberOperationResponse>(`/api/v1/organizations/${orgId}/members/${userId}`, {
      method: 'DELETE',
    });
  },

  transferTenantOrganizationOwnership: async (
    orgId: string,
    data: TransferOwnershipRequest
  ): Promise<OrganizationProfileResponse> => {
    return fetchApi<OrganizationProfileResponse>(`/api/v1/organizations/${orgId}/transfer-ownership`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  getTenantHackathons: async (
    orgId: string,
    params?: {
      page?: number;
      limit?: number;
      search?: string;
      status?: HackathonStatus;
      sort_by?: string;
      sort_order?: 'asc' | 'desc';
      start_date_after?: string;
      start_date_before?: string;
    },
    options?: RequestInit
  ): Promise<PaginatedHackathonsResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.search) searchParams.set('search', params.search);
    if (params?.status) searchParams.set('status', params.status);
    if (params?.sort_by) searchParams.set('sort_by', params.sort_by);
    if (params?.sort_order) searchParams.set('sort_order', params.sort_order);
    if (params?.start_date_after) searchParams.set('start_date_after', params.start_date_after);
    if (params?.start_date_before) searchParams.set('start_date_before', params.start_date_before);

    const qs = searchParams.toString();
    return fetchApi<PaginatedHackathonsResponse>(`/api/v1/organizations/${orgId}/hackathons${qs ? `?${qs}` : ''}`, options);
  },

  createTenantHackathon: async (
    orgId: string,
    data: CreateHackathonRequest
  ): Promise<HackathonDetailResponse> => {
    return fetchApi<HackathonDetailResponse>(`/api/v1/organizations/${orgId}/hackathons`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  getTenantHackathon: async (
    orgId: string,
    hackathonId: string,
    options?: RequestInit
  ): Promise<HackathonDetailResponse> => {
    return fetchApi<HackathonDetailResponse>(`/api/v1/organizations/${orgId}/hackathons/${hackathonId}`, options);
  },

  updateTenantHackathon: async (
    orgId: string,
    hackathonId: string,
    data: UpdateHackathonRequest
  ): Promise<HackathonDetailResponse> => {
    return fetchApi<HackathonDetailResponse>(`/api/v1/organizations/${orgId}/hackathons/${hackathonId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  publishTenantHackathon: async (
    orgId: string,
    hackathonId: string
  ): Promise<HackathonDetailResponse> => {
    return fetchApi<HackathonDetailResponse>(`/api/v1/organizations/${orgId}/hackathons/${hackathonId}/publish`, {
      method: 'POST',
    });
  },

  completeTenantHackathon: async (
    orgId: string,
    hackathonId: string
  ): Promise<HackathonDetailResponse> => {
    return fetchApi<HackathonDetailResponse>(`/api/v1/organizations/${orgId}/hackathons/${hackathonId}/complete`, {
      method: 'POST',
    });
  },

  archiveTenantHackathon: async (
    orgId: string,
    hackathonId: string
  ): Promise<HackathonDetailResponse> => {
    return fetchApi<HackathonDetailResponse>(`/api/v1/organizations/${orgId}/hackathons/${hackathonId}/archive`, {
      method: 'POST',
    });
  },

  updateTenantHackathonStatus: async (
    orgId: string,
    hackathonId: string,
    data: TenantUpdateHackathonStatusRequest
  ): Promise<HackathonDetailResponse> => {
    return fetchApi<HackathonDetailResponse>(`/api/v1/organizations/${orgId}/hackathons/${hackathonId}/status`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  publishHackathonResults: async (
    orgId: string,
    hackathonId: string
  ): Promise<HackathonDetailResponse> => {
    return fetchApi<HackathonDetailResponse>(`/api/v1/organizations/${orgId}/hackathons/${hackathonId}/publish-results`, {
      method: 'POST',
    });
  },

  unpublishHackathonResults: async (
    orgId: string,
    hackathonId: string
  ): Promise<HackathonDetailResponse> => {
    return fetchApi<HackathonDetailResponse>(`/api/v1/organizations/${orgId}/hackathons/${hackathonId}/unpublish-results`, {
      method: 'POST',
    });
  },

  // ==========================================
  // Platform Admin: Configuration Settings
  // ==========================================
  getConfigurationSettings: async (): Promise<ConfigurationSetting[]> => {
    return fetchApi<ConfigurationSetting[]>('/api/v1/admin/configuration');
  },

  getConfigurationSetting: async (key: string): Promise<ConfigurationSetting> => {
    return fetchApi<ConfigurationSetting>(`/api/v1/admin/configuration/${key}`);
  },

  updateConfigurationSetting: async (
    key: string,
    value: string,
    expectedVersion: number,
    changeReason?: string
  ): Promise<ConfigurationSetting> => {
    return fetchApi<ConfigurationSetting>(`/api/v1/admin/configuration/${key}`, {
      method: 'PUT',
      body: JSON.stringify({
        value,
        expected_version: expectedVersion,
        change_reason: changeReason,
      }),
    });
  },

  // ==========================================
  // Phase 6 Hackathon Subresources
  // ==========================================
  getHackathonOverview: async (
    orgId: string,
    hackathonId: string,
    options?: RequestInit
  ): Promise<HackathonOverviewResponse> => {
    return fetchApi<HackathonOverviewResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/overview`,
      options
    );
  },

  getHackathonTeams: async (
    orgId: string,
    hackathonId: string,
    options?: RequestInit
  ): Promise<TeamListItem[]> => {
    return fetchApi<TeamListItem[]>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/teams`,
      options
    );
  },

  createHackathonTeam: async (
    orgId: string,
    hackathonId: string,
    data: CreateTeamRequest
  ): Promise<TeamDetailResponse> => {
    return fetchApi<TeamDetailResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/teams`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  getHackathonTeam: async (
    orgId: string,
    hackathonId: string,
    teamId: string,
    options?: RequestInit
  ): Promise<TeamDetailResponse> => {
    return fetchApi<TeamDetailResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/teams/${teamId}`,
      options
    );
  },

  joinHackathonTeam: async (
    orgId: string,
    hackathonId: string,
    data: JoinTeamRequest
  ): Promise<TeamDetailResponse> => {
    return fetchApi<TeamDetailResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/teams/join`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  createHackathonTeamParticipant: async (
    orgId: string,
    hackathonId: string,
    teamId: string,
    data: AddTeamParticipantRequest
  ): Promise<AddTeamParticipantResponse> => {
    return fetchApi<AddTeamParticipantResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/teams/${teamId}/participants`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  getHackathonSubmissions: async (
    orgId: string,
    hackathonId: string,
    options?: RequestInit
  ): Promise<SubmissionListItem[]> => {
    return fetchApi<SubmissionListItem[]>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions`,
      options
    );
  },

  createHackathonSubmission: async (
    orgId: string,
    hackathonId: string,
    data: CreateSubmissionRequest
  ): Promise<SubmissionDetailResponse> => {
    return fetchApi<SubmissionDetailResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  getHackathonSubmission: async (
    orgId: string,
    hackathonId: string,
    submissionId: string,
    options?: RequestInit
  ): Promise<SubmissionDetailResponse> => {
    return fetchApi<SubmissionDetailResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions/${submissionId}`,
      options
    );
  },

  validateRepository: async (
    orgId: string,
    hackathonId: string,
    data: ValidateRepositoryRequest
  ): Promise<RepositoryValidationResult> => {
    return fetchApi<RepositoryValidationResult>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/repositories/validate`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  linkSubmissionRepository: async (
    orgId: string,
    hackathonId: string,
    submissionId: string,
    data: LinkRepositoryRequest
  ): Promise<SubmissionDetailResponse> => {
    return fetchApi<SubmissionDetailResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions/${submissionId}/link-repository`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  updateSubmissionBranch: async (
    orgId: string,
    hackathonId: string,
    submissionId: string,
    data: UpdateBranchRequest
  ): Promise<SubmissionDetailResponse> => {
    return fetchApi<SubmissionDetailResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions/${submissionId}/branch`,
      {
        method: 'PATCH',
        body: JSON.stringify(data),
      }
    );
  },

  refreshSubmissionVerification: async (
    orgId: string,
    hackathonId: string,
    submissionId: string
  ): Promise<SubmissionDetailResponse> => {
    return fetchApi<SubmissionDetailResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions/${submissionId}/verify`,
      {
        method: 'POST',
      }
    );
  },

  unlinkSubmissionRepository: async (
    orgId: string,
    hackathonId: string,
    submissionId: string
  ): Promise<SubmissionDetailResponse> => {
    return fetchApi<SubmissionDetailResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions/${submissionId}/unlink-repository`,
      {
        method: 'POST',
      }
    );
  },

  getSubmissionActivity: async (
    orgId: string,
    hackathonId: string,
    submissionId: string,
    options?: RequestInit
  ): Promise<RepositoryActivityItem[]> => {
    return fetchApi<RepositoryActivityItem[]>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions/${submissionId}/activity`,
      options
    );
  },

  getHackathonActivity: async (
    orgId: string,
    hackathonId: string,
    options?: RequestInit
  ): Promise<RepositoryActivityItem[]> => {
    return fetchApi<RepositoryActivityItem[]>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/activity`,
      options
    );
  },

  getHackathonJudges: async (
    orgId: string,
    hackathonId: string,
    options?: RequestInit
  ): Promise<JudgeListItem[]> => {
    return fetchApi<JudgeListItem[]>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/judges`,
      options
    );
  },

  assignHackathonJudge: async (
    orgId: string,
    hackathonId: string,
    data: AssignJudgeRequest
  ): Promise<JudgeListItem> => {
    return fetchApi<JudgeListItem>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/judges`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  removeHackathonJudge: async (
    orgId: string,
    hackathonId: string,
    judgeUserId: string
  ): Promise<void> => {
    await fetchApi<void>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/judges/${judgeUserId}`,
      {
        method: 'DELETE',
      }
    );
  },

  getHackathonRubric: async (
    orgId: string,
    hackathonId: string,
    options?: RequestInit
  ): Promise<RubricDetailResponse> => {
    return fetchApi<RubricDetailResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/rubric`,
      options
    );
  },

  createHackathonRubric: async (
    orgId: string,
    hackathonId: string,
    data: CreateRubricRequest
  ): Promise<RubricDetailResponse> => {
    return fetchApi<RubricDetailResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/rubrics`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  addRubricCriterion: async (
    orgId: string,
    hackathonId: string,
    rubricId: string,
    data: AddCriterionRequest
  ): Promise<RubricDetailResponse> => {
    return fetchApi<RubricDetailResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/rubrics/${rubricId}/criteria`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  publishRubric: async (
    orgId: string,
    hackathonId: string,
    rubricId: string
  ): Promise<RubricDetailResponse> => {
    return fetchApi<RubricDetailResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/rubrics/${rubricId}/publish`,
      {
        method: 'POST',
      }
    );
  },

  getSubmissionEvaluation: async (
    orgId: string,
    hackathonId: string,
    submissionId: string,
    jobId?: string,
    options?: RequestInit
  ): Promise<SubmissionEvaluationTransparencyResponse> => {
    const url = jobId
      ? `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions/${submissionId}/evaluation?job_id=${encodeURIComponent(jobId)}`
      : `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions/${submissionId}/evaluation`;
    return fetchApi<SubmissionEvaluationTransparencyResponse>(url, options);
  },

  getHackathonEvaluationSummary: async (
    orgId: string,
    hackathonId: string,
    options?: RequestInit
  ): Promise<HackathonEvaluationSummaryResponse> => {
    return fetchApi<HackathonEvaluationSummaryResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/evaluations/summary`,
      options
    );
  },

  getHackathonEvaluations: async (
    orgId: string,
    hackathonId: string,
    status?: string,
    options?: RequestInit
  ): Promise<EvaluationJobListItem[]> => {
    const url = status
      ? `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/evaluations?status=${encodeURIComponent(status)}`
      : `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/evaluations`;
    return fetchApi<EvaluationJobListItem[]>(url, options);
  },

  triggerSubmissionEvaluation: async (
    orgId: string,
    hackathonId: string,
    submissionId: string,
    idempotencyKey?: string
  ): Promise<EvaluationJobResponse> => {
    const headers: Record<string, string> = {};
    if (idempotencyKey) {
      headers['Idempotency-Key'] = idempotencyKey;
    }
    return fetchApi<EvaluationJobResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions/${submissionId}/evaluate`,
      {
        method: 'POST',
        headers,
      }
    );
  },

  cancelEvaluationJob: async (
    orgId: string,
    jobId: string
  ): Promise<EvaluationJobResponse> => {
    return fetchApi<EvaluationJobResponse>(
      `/api/v1/organizations/${orgId}/evaluations/${jobId}/cancel`,
      {
        method: 'POST',
      }
    );
  },

  // Judge Workspace & Review Workflow (M6.5)
  getJudgeAssignments: async (
    options?: RequestInit
  ): Promise<JudgeAssignmentItem[]> => {
    return fetchApi<JudgeAssignmentItem[]>('/api/v1/judge/assignments', options);
  },

  getJudgeSubmissions: async (
    options?: RequestInit
  ): Promise<JudgeQueueItem[]> => {
    return fetchApi<JudgeQueueItem[]>('/api/v1/judge/submissions', options);
  },

  getJudgeQueue: async (
    orgId: string,
    hackathonId: string,
    options?: RequestInit
  ): Promise<JudgeQueueItem[]> => {
    return fetchApi<JudgeQueueItem[]>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/judge/queue`,
      options
    );
  },

  getSubmissionReview: async (
    orgId: string,
    hackathonId: string,
    submissionId: string,
    judgeId?: string,
    options?: RequestInit
  ): Promise<JudgeSubmissionReviewResponse> => {
    const url = judgeId
      ? `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions/${submissionId}/review?judge_id=${encodeURIComponent(judgeId)}`
      : `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions/${submissionId}/review`;
    return fetchApi<JudgeSubmissionReviewResponse>(url, options);
  },

  saveSubmissionReviewDraft: async (
    orgId: string,
    hackathonId: string,
    submissionId: string,
    data: SaveJudgeReviewRequest
  ): Promise<JudgeReviewDetail> => {
    return fetchApi<JudgeReviewDetail>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions/${submissionId}/review`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  submitSubmissionReview: async (
    orgId: string,
    hackathonId: string,
    submissionId: string,
    data: SubmitJudgeReviewRequest
  ): Promise<JudgeReviewDetail> => {
    return fetchApi<JudgeReviewDetail>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions/${submissionId}/review/submit`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  // Dedicated Judge Workspace & Review Endpoints (Tenant-Isolated from Org Layout)
  getJudgeHackathonDetail: async (
    hackathonId: string,
    options?: RequestInit
  ): Promise<JudgeHackathonDetail> => {
    return fetchApi<JudgeHackathonDetail>(
      `/api/v1/judge/hackathons/${hackathonId}`,
      options
    );
  },

  getJudgeHackathonSubmissions: async (
    hackathonId: string,
    options?: RequestInit
  ): Promise<JudgeQueueItem[]> => {
    return fetchApi<JudgeQueueItem[]>(
      `/api/v1/judge/hackathons/${hackathonId}/submissions`,
      options
    );
  },

  getJudgeSubmissionReview: async (
    hackathonId: string,
    submissionId: string,
    options?: RequestInit
  ): Promise<JudgeSubmissionReviewResponse> => {
    return fetchApi<JudgeSubmissionReviewResponse>(
      `/api/v1/judge/hackathons/${hackathonId}/submissions/${submissionId}/review`,
      options
    );
  },

  saveJudgeSubmissionReviewDraft: async (
    hackathonId: string,
    submissionId: string,
    data: SaveJudgeReviewRequest
  ): Promise<JudgeReviewDetail> => {
    return fetchApi<JudgeReviewDetail>(
      `/api/v1/judge/hackathons/${hackathonId}/submissions/${submissionId}/review`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  submitJudgeSubmissionReview: async (
    hackathonId: string,
    submissionId: string,
    data: SubmitJudgeReviewRequest
  ): Promise<JudgeReviewDetail> => {
    return fetchApi<JudgeReviewDetail>(
      `/api/v1/judge/hackathons/${hackathonId}/submissions/${submissionId}/review/submit`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  submitJudgeReview: async (
    hackathonId: string,
    submissionId: string,
    data: SubmitJudgeReviewRequest
  ): Promise<JudgeReviewDetail> => {
    return fetchApi<JudgeReviewDetail>(
      `/api/v1/judge/hackathons/${hackathonId}/submissions/${submissionId}/review/submit`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  revertJudgeReview: async (
    hackathonId: string,
    submissionId: string,
    data: RevertJudgeReviewRequest = { target_status: 'draft' }
  ): Promise<JudgeSubmissionReviewResponse> => {
    return fetchApi<JudgeSubmissionReviewResponse>(
      `/api/v1/judge/hackathons/${hackathonId}/submissions/${submissionId}/review/revert`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  inspectJudgeSubmissionRepo: async (
    hackathonId: string,
    submissionId: string,
    forceRefresh: boolean = false
  ): Promise<OllamaRepoInspectionResponse> => {
    return fetchApi<OllamaRepoInspectionResponse>(
      `/api/v1/judge/hackathons/${hackathonId}/submissions/${submissionId}/inspect-repo${forceRefresh ? '?force_refresh=true' : ''}`,
      {
        method: 'POST',
        timeoutMs: 180000, // 3-minute timeout for deep neural codebase analysis
      }
    );
  },

  getJudgeSubmissionInspection: async (
    hackathonId: string,
    submissionId: string,
    options?: RequestInit
  ): Promise<OllamaRepoInspectionResponse | null> => {
    return fetchApi<OllamaRepoInspectionResponse | null>(
      `/api/v1/judge/hackathons/${hackathonId}/submissions/${submissionId}/inspect-repo`,
      options
    );
  },

  getJudgeSubmissionTransparency: async (
    hackathonId: string,
    submissionId: string,
    options?: RequestInit
  ): Promise<SubmissionEvaluationTransparencyResponse> => {
    return fetchApi<SubmissionEvaluationTransparencyResponse>(
      `/api/v1/judge/hackathons/${hackathonId}/submissions/${submissionId}/transparency`,
      options
    );
  },

  // Participant Workspace
  getParticipantTeams: async (
    options?: RequestInit
  ): Promise<ParticipantTeamItem[]> => {
    return fetchApi<ParticipantTeamItem[]>(
      '/api/v1/participant/teams',
      options
    );
  },

  getHackathonReviewProgress: async (
    orgId: string,
    hackathonId: string,
    options?: RequestInit
  ): Promise<OrganizerReviewProgressResponse> => {
    return fetchApi<OrganizerReviewProgressResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/reviews/progress`,
      options
    );
  },

  getSubmissionAllReviews: async (
    orgId: string,
    hackathonId: string,
    submissionId: string,
    options?: RequestInit
  ): Promise<SubmissionReviewsResponse> => {
    return fetchApi<SubmissionReviewsResponse>(
      `/api/v1/organizations/${orgId}/hackathons/${hackathonId}/submissions/${submissionId}/reviews`,
      options
    );
  },

  // Platform Admin: Roles & Permissions (RBAC)
  getPermissions: async (options?: RequestInit): Promise<PermissionItem[]> => {
    return fetchApi<PermissionItem[]>('/api/v1/admin/permissions', options);
  },

  getRoles: async (
    params?: { scope_type?: string; scope_id?: string },
    options?: RequestInit
  ): Promise<RoleItem[]> => {
    const searchParams = new URLSearchParams();
    if (params?.scope_type) searchParams.set('scope_type', params.scope_type);
    if (params?.scope_id) searchParams.set('scope_id', params.scope_id);
    const qs = searchParams.toString();
    return fetchApi<RoleItem[]>(`/api/v1/admin/roles${qs ? `?${qs}` : ''}`, options);
  },

  createRole: async (
    data: CreateRoleRequest
  ): Promise<RoleItem> => {
    return fetchApi<RoleItem>('/api/v1/admin/roles', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  updateRolePermissions: async (
    roleId: string,
    data: UpdateRolePermissionsRequest
  ): Promise<RoleItem> => {
    return fetchApi<RoleItem>(`/api/v1/admin/roles/${roleId}/permissions`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  // Participant Workspace
  getParticipantOverview: async (
    options?: RequestInit
  ): Promise<ParticipantOverviewResponse> => {
    return fetchApi<ParticipantOverviewResponse>('/api/v1/participant/overview', options);
  },

  getParticipantLeaderboard: async (
    hackathonId?: string,
    options?: RequestInit
  ): Promise<LeaderboardResponse> => {
    const qs = hackathonId ? `?hackathon_id=${encodeURIComponent(hackathonId)}` : '';
    return fetchApi<LeaderboardResponse>(`/api/v1/participant/leaderboard${qs}`, options);
  },

  getParticipantPerformance: async (
    hackathonId?: string,
    options?: RequestInit
  ): Promise<PerformanceResponse> => {
    const qs = hackathonId ? `?hackathon_id=${encodeURIComponent(hackathonId)}` : '';
    return fetchApi<PerformanceResponse>(`/api/v1/participant/performance${qs}`, options);
  },

  getParticipantTasks: async (
    options?: RequestInit
  ): Promise<ParticipantTaskItem[]> => {
    return fetchApi<ParticipantTaskItem[]>('/api/v1/participant/tasks', options);
  },

  updateParticipantTaskStatus: async (
    taskId: string,
    status: 'new' | 'in_progress' | 'completed'
  ): Promise<{ status: string; task_id: string; new_status: string }> => {
    return fetchApi<{ status: string; task_id: string; new_status: string }>(
      `/api/v1/participant/tasks/${encodeURIComponent(taskId)}/status`,
      {
        method: 'POST',
        body: JSON.stringify({ status }),
      }
    );
  },

  getParticipantNotifications: async (
    options?: RequestInit
  ): Promise<NotificationListResponse> => {
    return fetchApi<NotificationListResponse>('/api/v1/participant/notifications', options);
  },

  markParticipantNotificationRead: async (
    notificationId: string
  ): Promise<{ status: string; notification_id: string }> => {
    return fetchApi<{ status: string; notification_id: string }>(
      `/api/v1/participant/notifications/${encodeURIComponent(notificationId)}/read`,
      {
        method: 'POST',
      }
    );
  },

  markAllParticipantNotificationsRead: async (): Promise<{ status: string; count: number }> => {
    return fetchApi<{ status: string; count: number }>(
      '/api/v1/participant/notifications/read-all',
      {
        method: 'POST',
      }
    );
  },

  getParticipantSupportTickets: async (
    options?: RequestInit
  ): Promise<SupportTicketItem[]> => {
    return fetchApi<SupportTicketItem[]>('/api/v1/participant/support/tickets', options);
  },

  createParticipantSupportTicket: async (
    data: CreateSupportTicketRequest
  ): Promise<SupportTicketItem> => {
    const formData = new FormData();
    formData.append('category', data.category);
    formData.append('team_name', data.team_name);
    if (data.team_number) formData.append('team_number', data.team_number);
    if (data.block_number) formData.append('block_number', data.block_number);
    if (data.lab_number) formData.append('lab_number', data.lab_number);
    formData.append('subject', data.subject);
    formData.append('description', data.description);
    if (data.hackathon_id) formData.append('hackathon_id', data.hackathon_id);
    if (data.attachment) formData.append('attachment', data.attachment);
    return fetchApi<SupportTicketItem>('/api/v1/participant/support/tickets', {
      method: 'POST',
      body: formData,
    });
  },

  getParticipantSupportTicketDetail: async (
    ticketId: string,
    options?: RequestInit
  ): Promise<SupportTicketDetailResponse> => {
    return fetchApi<SupportTicketDetailResponse>(
      `/api/v1/participant/support/tickets/${encodeURIComponent(ticketId)}`,
      options
    );
  },

  getParticipantSupportTicketAttachmentUrl: (ticketId: string): string => {
    return `${API_BASE_URL.replace(/\/$/, '')}/api/v1/participant/support/tickets/${encodeURIComponent(ticketId)}/attachment`;
  },

  replyParticipantSupportTicket: async (
    ticketId: string,
    data: CreateSupportReplyRequest
  ): Promise<SupportReplyItem> => {
    return fetchApi<SupportReplyItem>(
      `/api/v1/participant/support/tickets/${encodeURIComponent(ticketId)}/replies`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  verifyParticipantJoinCode: async (
    joinCode: string
  ): Promise<VerifyJoinCodeResponse> => {
    return fetchApi<VerifyJoinCodeResponse>(
      '/api/v1/participant/verify-join-code',
      {
        method: 'POST',
        body: JSON.stringify({ join_code: joinCode }),
      }
    );
  },

  getParticipantRegistrationStatus: async (
    options?: RequestInit
  ): Promise<RegistrationStatusResponse> => {
    return fetchApi<RegistrationStatusResponse>(
      '/api/v1/participant/registration-status',
      options
    );
  },

  registerParticipantProject: async (
    data: ParticipantProjectRegistrationRequest
  ): Promise<ProjectRegistrationSuccessResponse> => {
    return fetchApi<ProjectRegistrationSuccessResponse>(
      '/api/v1/participant/register-project',
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  getParticipantPatStatus: async (
    options?: RequestInit
  ): Promise<ParticipantPatTokenStatus> => {
    return fetchApi<ParticipantPatTokenStatus>(
      '/api/v1/participant/settings/pat',
      options
    );
  },

  saveParticipantPat: async (
    data: SaveParticipantPatRequest
  ): Promise<SaveParticipantPatResponse> => {
    return fetchApi<SaveParticipantPatResponse>(
      '/api/v1/participant/settings/pat',
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  deleteParticipantPat: async (): Promise<{ status: string; message: string }> => {
    return fetchApi<{ status: string; message: string }>(
      '/api/v1/participant/settings/pat',
      {
        method: 'DELETE',
      }
    );
  },

  getParticipantGitHubSettings: async (
    options?: RequestInit
  ): Promise<ParticipantGitHubSettingsResponse> => {
    return fetchApi<ParticipantGitHubSettingsResponse>(
      '/api/v1/participant/settings/github',
      options
    );
  },

  verifyParticipantGitHubRepository: async (): Promise<VerifyParticipantGitHubResponse> => {
    return fetchApi<VerifyParticipantGitHubResponse>(
      '/api/v1/participant/settings/github/verify',
      {
        method: 'POST',
      }
    );
  },

  getAdminSupportTickets: async (
    params?: {
      status?: string;
      category?: string;
      search?: string;
      page?: number;
      limit?: number;
    },
    options?: RequestInit
  ): Promise<AdminSupportTicketListResponse> => {
    const query = new URLSearchParams();
    if (params?.status && params.status !== 'all') query.set('status', params.status);
    if (params?.category && params.category !== 'all') query.set('category', params.category);
    if (params?.search) query.set('search', params.search);
    if (params?.page) query.set('page', params.page.toString());
    if (params?.limit) query.set('limit', params.limit.toString());
    const qs = query.toString();
    return fetchApi<AdminSupportTicketListResponse>(
      `/api/v1/admin/support/tickets${qs ? `?${qs}` : ''}`,
      options
    );
  },

  getAdminSupportTicketDetail: async (
    ticketId: string,
    options?: RequestInit
  ): Promise<AdminSupportTicketDetailResponse> => {
    return fetchApi<AdminSupportTicketDetailResponse>(
      `/api/v1/admin/support/tickets/${encodeURIComponent(ticketId)}`,
      options
    );
  },

  replyAdminSupportTicket: async (
    ticketId: string,
    data: AdminCreateSupportReplyRequest
  ): Promise<SupportReplyItem> => {
    return fetchApi<SupportReplyItem>(
      `/api/v1/admin/support/tickets/${encodeURIComponent(ticketId)}/replies`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  updateAdminSupportTicketStatus: async (
    ticketId: string,
    status: string
  ): Promise<{ id: string; status: string }> => {
    return fetchApi<{ id: string; status: string }>(
      `/api/v1/admin/support/tickets/${encodeURIComponent(ticketId)}/status`,
      {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }
    );
  },

  getAdminSupportTicketAttachmentUrl: (ticketId: string): string => {
    return `${API_BASE_URL.replace(/\/$/, '')}/api/v1/admin/support/tickets/${encodeURIComponent(ticketId)}/attachment`;
  },

  getAdminJudges: async (
    params?: { hackathon_id?: string; search?: string },
    options?: RequestInit
  ): Promise<AdminJudgeItem[]> => {
    const query = new URLSearchParams();
    if (params?.hackathon_id) query.set('hackathon_id', params.hackathon_id);
    if (params?.search) query.set('search', params.search);
    const qs = query.toString();
    return fetchApi<AdminJudgeItem[]>(`/api/v1/admin/hackathons/judges${qs ? `?${qs}` : ''}`, options);
  },

  createAdminJudge: async (
    hackathonId: string,
    data: AdminCreateJudgeRequest
  ): Promise<AdminJudgeItem> => {
    return fetchApi<AdminJudgeItem>(
      `/api/v1/admin/hackathons/${encodeURIComponent(hackathonId)}/judges`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  },

  deleteAdminJudge: async (
    hackathonId: string,
    judgeId: string
  ): Promise<void> => {
    return fetchApi<void>(
      `/api/v1/admin/hackathons/${encodeURIComponent(hackathonId)}/judges/${encodeURIComponent(judgeId)}`,
      {
        method: 'DELETE',
      }
    );
  },

  getAIRoutingConfig: async (options?: RequestInit): Promise<AIRoutingConfigResponse> => {
    return fetchApi<AIRoutingConfigResponse>('/api/v1/admin/ai-operations/routing', options);
  },

  updateAIRoutingConfig: async (data: AIRoutingConfigRequest): Promise<AIRoutingConfigResponse> => {
    return fetchApi<AIRoutingConfigResponse>('/api/v1/admin/ai-operations/routing', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  probeAIEndpoint: async (url: string): Promise<AIEndpointProbeResponse> => {
    return fetchApi<AIEndpointProbeResponse>('/api/v1/admin/ai-operations/probe', {
      method: 'POST',
      body: JSON.stringify({ url }),
    });
  },

  getAIOperationsStats: async (options?: RequestInit): Promise<AIOperationsStatsResponse> => {
    return fetchApi<AIOperationsStatsResponse>('/api/v1/admin/ai-operations/stats', options);
  },

  // AI Operations Control Center Endpoints
  getAIRuntimeOverview: async (options?: RequestInit): Promise<import('@/types/api').AIRuntimeOverviewResponse> => {
    return fetchApi<import('@/types/api').AIRuntimeOverviewResponse>('/api/v1/admin/ai-operations/runtime', options);
  },

  updateAIRuntimeSettings: async (data: import('@/types/api').AIRuntimeSettingsUpdate): Promise<import('@/types/api').AIRuntimeOverviewResponse> => {
    return fetchApi<import('@/types/api').AIRuntimeOverviewResponse>('/api/v1/admin/ai-operations/runtime', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  discoverAIModels: async (forceRefresh: boolean = true): Promise<import('@/types/api').AIModelItem[]> => {
    return fetchApi<import('@/types/api').AIModelItem[]>(`/api/v1/admin/ai-operations/runtime/discover?force_refresh=${forceRefresh}`, {
      method: 'POST',
    });
  },

  getAIModels: async (params?: { provider?: string; search?: string; enabled_only?: boolean }): Promise<import('@/types/api').AIModelItem[]> => {
    const query = new URLSearchParams();
    if (params?.provider) query.append('provider', params.provider);
    if (params?.search) query.append('search', params.search);
    if (params?.enabled_only !== undefined) query.append('enabled_only', String(params.enabled_only));
    const qs = query.toString();
    return fetchApi<import('@/types/api').AIModelItem[]>(`/api/v1/admin/ai-operations/models${qs ? `?${qs}` : ''}`);
  },

  updateAIModel: async (modelId: string, data: import('@/types/api').AIModelUpdatePayload): Promise<import('@/types/api').AIModelItem> => {
    return fetchApi<import('@/types/api').AIModelItem>(`/api/v1/admin/ai-operations/models/${encodeURIComponent(modelId)}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  testAIModel: async (data: import('@/types/api').PiModelTestRequest): Promise<import('@/types/api').PiModelTestResponse> => {
    return fetchApi<import('@/types/api').PiModelTestResponse>('/api/v1/admin/ai-operations/models/test', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  switchAIDefaultModel: async (data: import('@/types/api').DefaultModelSwitchPayload): Promise<import('@/types/api').AIRuntimeOverviewResponse> => {
    return fetchApi<import('@/types/api').AIRuntimeOverviewResponse>('/api/v1/admin/ai-operations/default-model', {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  getAITaskRoutings: async (): Promise<import('@/types/api').TaskRoutingAssignment[]> => {
    return fetchApi<import('@/types/api').TaskRoutingAssignment[]>('/api/v1/admin/ai-operations/task-routing');
  },

  updateAITaskRouting: async (taskType: string, data: import('@/types/api').TaskRoutingUpdatePayload): Promise<import('@/types/api').TaskRoutingAssignment> => {
    return fetchApi<import('@/types/api').TaskRoutingAssignment>(`/api/v1/admin/ai-operations/task-routing/${encodeURIComponent(taskType)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  executeAIParallelTest: async (data: import('@/types/api').ParallelTaskExecutionRequest): Promise<import('@/types/api').ParallelTaskExecutionResponse> => {
    return fetchApi<import('@/types/api').ParallelTaskExecutionResponse>('/api/v1/admin/ai-operations/execute-parallel', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  getAIExecutions: async (params?: {
    page?: number;
    page_size?: number;
    task_type?: string;
    provider?: string;
    model?: string;
    status?: string;
    search?: string;
  }): Promise<import('@/types/api').AIExecutionListResponse> => {
    const query = new URLSearchParams();
    if (params?.page) query.append('page', String(params.page));
    if (params?.page_size) query.append('page_size', String(params.page_size));
    if (params?.task_type) query.append('task_type', params.task_type);
    if (params?.provider) query.append('provider', params.provider);
    if (params?.model) query.append('model', params.model);
    if (params?.status) query.append('status', params.status);
    if (params?.search) query.append('search', params.search);
    const qs = query.toString();
    return fetchApi<import('@/types/api').AIExecutionListResponse>(`/api/v1/admin/ai-operations/executions${qs ? `?${qs}` : ''}`);
  },

  getAIExecutionDetail: async (executionId: string): Promise<import('@/types/api').AIExecutionRecordDetail> => {
    return fetchApi<import('@/types/api').AIExecutionRecordDetail>(`/api/v1/admin/ai-operations/executions/${encodeURIComponent(executionId)}`);
  },

  getAIControlCenterStats: async (): Promise<import('@/types/api').AIOperationsControlCenterStats> => {
    return fetchApi<import('@/types/api').AIOperationsControlCenterStats>('/api/v1/admin/ai-operations/control-center-stats');
  },
};

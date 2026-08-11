

import axios, { AxiosError, AxiosProgressEvent, InternalAxiosRequestConfig } from 'axios'

import { getToken, forceLogout } from '@/application/state/authStore'

type ValidationDetailItem = {
  type?: string
  loc?: (string | number)[]
  msg?: string
  ctx?: Record<string, unknown>
}

const FIELD_LABELS: Record<string, string> = {
  password: '密码',
  username: '用户名',
  display_name: '显示名',
  email: '邮箱',
  message: '消息',
  name: '名称',
}

function fieldLabel(loc: (string | number)[] | undefined): string {
  if (!loc?.length) return '字段'
  const key = String(loc[loc.length - 1])
  return FIELD_LABELS[key] || key
}

function formatValidationItem(item: ValidationDetailItem): string {
  const label = fieldLabel(item.loc)
  const minLen = item.ctx?.min_length
  const maxLen = item.ctx?.max_length

  if (item.type === 'string_too_short' && minLen != null) {
    return `${label}至少需要 ${minLen} 个字符`
  }
  if (item.type === 'string_too_long' && maxLen != null) {
    return `${label}不能超过 ${maxLen} 个字符`
  }
  if (item.type === 'missing') {
    return `请填写${label}`
  }
  if (item.msg) {
    return `${label}：${item.msg}`
  }
  return `${label}格式不正确`
}

export class ApiError extends Error {

  status?: number
  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function formatApiError(err: AxiosError): string {
  const data = err.response?.data

  if (typeof data === 'string' && data.trim()) {
    return data
  }

  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail: unknown }).detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
    if (Array.isArray(detail)) {
      const lines = detail
        .filter((x): x is ValidationDetailItem => !!x && typeof x === 'object')
        .map(formatValidationItem)
        .filter(Boolean)
      if (lines.length) return lines.join('；')
    }
  }

  if (err.response?.status === 422) {
    return '提交的数据格式不正确，请检查后重试'
  }

  return err.message || '请求失败'
}

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'

export const http = axios.create({
  baseURL,
  timeout: 30_000,
})

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (resp) => resp,
  (err: AxiosError) => {

    const status = err.response?.status
    const url = err.config?.url || ''
    const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/register')
    if (status === 401 && !isAuthEndpoint) {
      forceLogout()
    }

    return Promise.reject(new ApiError(formatApiError(err), status))
  },
)

export interface Project {
  id: string
  name: string
  description: string
  workspace_path: string

  owner_id?: string | null

  role?: string | null

  visibility?: string
  created_at: string
  updated_at: string
}

export interface AuthUser {
  id: string
  username: string
  email: string
  display_name: string
  role: 'admin' | 'user' | string
  status: string

  credits_balance?: number
  created_at?: string | null
  updated_at?: string | null

  permissions?: string[]

  roles?: { id: string; name: string }[]
}

export interface Role {
  id: string
  name: string
  description: string
  is_system: boolean
  permissions: string[]
  created_at?: string | null
  updated_at?: string | null
}

export interface PermissionCatalogItem {
  key: string
  label: string
}

export interface PermissionCatalogGroup {
  group: string
  label: string
  desc: string
  items: PermissionCatalogItem[]
}

export interface MarketItem {
  project_id: string
  name: string
  description: string
  owner_name: string
  market_default_role: string

  my_status: string
  updated_at?: string | null
}

export interface AccessRequest {
  id: number
  project_id: string
  project_name: string
  requester_id: string
  requester_name?: string
  requested_role: string
  status: string
  note: string
  created_at?: string | null
  decided_at?: string | null
}

export interface CreditBalance {
  user_id: string
  balance: number
  total_recharged: number
  total_consumed: number
  total_cost_micro_cny: number
  total_cost_cny: number
  consume_count: number
}

export type CreditTxType = 'grant' | 'recharge' | 'consume' | 'adjust' | string

export interface CreditTx {
  id: number
  user_id: string
  type: CreditTxType

  amount: number
  balance_after: number
  reason: string
  operator_id?: string | null
  session_id?: string | null
  project_id?: string | null
  model?: string | null
  input_tokens: number
  cached_input_tokens: number
  output_tokens: number
  cost_micro_cny: number
  cost_cny: number
  created_at?: string | number | null
}

export interface CreditTxListResp {
  total: number
  limit: number
  offset: number
  items: CreditTx[]
}

export interface BillingConfig {

  enforce: boolean

  initial_grant: number

  markup: number

  mode: 'flat' | 'tiered' | 'split'

  flat_credits_per_1m: number

  flat_output_credits_per_1m: number
}

export interface GlobalBillingSummary {
  total_consumed_credits: number
  total_recharged_credits: number
  total_cost_micro_cny: number
  total_cost_cny: number
  consume_count: number
  total_outstanding_balance: number
  config: BillingConfig
}

export interface PricingItem {
  model: string
  label: string
  credits_per_1m_input: number
  credits_per_1m_cached_input: number
  credits_per_1m_output: number
  cny_per_1m_input: number
  cny_per_1m_cached_input: number
  cny_per_1m_output: number
  context_window: number
}

export interface PricingListResp {
  items: PricingItem[]
  markup: number
  mode: 'flat' | 'tiered' | 'split'
  flat_credits_per_1m: number
  flat_output_credits_per_1m: number
}

export interface EstimateResp {
  input_tokens: number
  reserved_output_tokens: number
  total_tokens: number
  estimated_credits: number

  source: 'moonshot' | 'heuristic'
}

export interface TokenResp {
  access_token: string
  token_type: string
  expires_in: number
  user: AuthUser
}

export interface ProjectMember {
  user_id: string
  username: string
  display_name: string
  role: 'editor' | 'viewer' | string
  created_at?: string | null
}

export interface Agent {
  id: string
  name: string
  description: string
  soul_path: string
  source: string
  status: string
}

export interface ModelInfo {
  id: string
  role: 'general' | 'fast' | 'complex' | string
}

export interface Provider {
  id: string
  name: string
  base_url: string

  api_key_preview: string
  enabled: boolean
  priority: number
  models: ModelInfo[]
  created_at?: string
}

export interface ProviderUpsert {
  name: string
  base_url: string
  api_key: string
  models: ModelInfo[]
  enabled: boolean
  priority: number
}

export interface HealthResp {
  status: 'healthy' | 'degraded'
  components: Record<string, string>
}

export interface SystemMetrics {
  timestamp: number
  system: {
    available: boolean
    cpu?: {
      percent: number
      per_core: number[]
      cores: number
      load_avg: (number | null)[]
    }
    memory?: { total: number; used: number; available: number; percent: number }
    disk?: { path: string; total: number; used: number; free: number; percent: number }
    network?: {
      bytes_sent: number
      bytes_recv: number
      sent_rate: number | null
      recv_rate: number | null
    }
    process?: {
      pid: number
      rss: number | null
      cpu_percent: number | null
      threads: number | null
    }
  }
  services: {
    status: 'healthy' | 'degraded'
    components: Record<string, string>
    backend: string
    multi_worker: boolean
  }
  app: {
    version: string
    active_sessions: number | null
    request_rate: {
      per_sec_avg: number
      last_sec: number
      peak_sec: number
      window: number
    } | null
    worker_pid: number
    worker_uptime_seconds: number
    configured_workers: number | null
  }
}

export type SkillDraftStatus = 'pending' | 'approved' | 'rejected'

export interface SkillDraftBrief {
  id: number
  name: string
  status: SkillDraftStatus
  source_session_id?: string | null
  source_agent_id?: string | null
  project_id?: string | null
  reviewed_by?: string | null
  reviewed_at?: string | null
  skill_path?: string | null
  created_at?: string | null
  updated_at?: string | null
  preview: string
}

export interface SkillDraftDetail extends SkillDraftBrief {
  content: string
}

export interface SkillDraftListResp {
  items: SkillDraftBrief[]
  total: number
  counts: Record<string, number>
}

export interface Persona {
  id: string
  name: string
  description: string
  icon: string
  suggested_tools: string[]
}

export interface PersonaDetail extends Persona {
  soul_text: string
  source_path?: string | null
}

export interface PersonaSwitchResp {
  agent_id: string
  from_persona: string | null
  to_persona: string
  name: string
  icon: string
  soul_chars: number
}

export interface SkillBrief {
  id: string
  name: string
  description: string
  tools: string[]
  relative_path: string
  group: string
  pinned: boolean
  source_file: string
}

export interface SkillGroup {
  name: string
  count: number
}

export interface SkillListResp {

  total: number

  total_all: number

  total_filtered: number
  offset: number
  limit: number
  has_more: boolean
  items: SkillBrief[]
  groups: SkillGroup[]
  pinned_ids: string[]
}

export interface SkillDetail extends SkillBrief {
  full_prompt: string
  original_frontmatter: Record<string, unknown>
}

export interface SkillUploadResp {
  ok: boolean
  accepted_files: number
  new_skills: number
  total_after: number
  target_dir: string
  message: string
}

export interface SkillRefreshResp {
  total: number
  duration_ms: number
}

export interface SkillPinsResp {
  ids: string[]
  total: number
}

export interface AttachedFileMeta {

  name: string

  path: string

  size: number

  kind?: 'image' | 'file'
}

export interface SessionMeta {
  session_id: string
  project_id: string
  agent_id: string
  title: string
  preview: string
  message_count: number
  tool_calls: number

  status: string
  jsonl_path: string
  created_at?: string | null
  updated_at?: string | null
  ended_at?: string | null
}

export interface SessionListResp {
  items: SessionMeta[]
  total: number
  limit: number
  offset: number
}

export interface SessionMessageRecord {
  role: string
  content?: unknown
  tool_calls?: Array<Record<string, unknown>>
  tool_call_id?: string
  name?: string

  created_at?: string | number | null
  [k: string]: unknown
}

export interface SessionMessagesResp {
  session_id: string

  total: number
  offset: number
  limit: number
  messages: SessionMessageRecord[]
}

export interface CitationItem {
  type: 'pmid' | 'doi' | 'unknown' | string
  id: string
  title: string
  authors: string[]
  journal: string
  year: string
  pubdate: string
  volume: string
  issue: string
  pages: string
  doi: string
  pmid: string

  abstract: string

  url: string
  source: 'pubmed' | 'crossref' | string

  is_authority?: boolean
  ok: boolean
  error: string
}

export interface CitationResolveResp {
  ok: boolean
  items: CitationItem[]
  stats: {
    requested?: number
    unique?: number
    resolved?: number
    not_found?: number
    invalid?: number
    [k: string]: number | undefined
  }
  error: string
}

export type FileRenderKind =
  | 'image'
  | 'markdown'
  | 'code'
  | 'csv'
  | 'json'
  | 'pdf'
  | 'download'

export interface PresentedFile {

  name: string

  path: string
  size: number
  mime: string
  render_kind: FileRenderKind

  preview?: string
  preview_truncated?: boolean
}

export interface FilePresentation {
  kind: 'files'
  title?: string
  description?: string
  files: PresentedFile[]
}

export type FilePreviewResp =
  | {
      kind: 'text'
      path: string
      size: number
      mime: string
      text: string
      truncated: boolean
      encoding: string
    }
  | {
      kind: 'csv'
      path: string
      size: number
      mime: string
      columns: string[]
      rows: string[][]
      truncated: boolean
      total_rows_returned: number
      delimiter: string
    }

export const api = {

  health: () => http.get<HealthResp>('/health').then((r) => r.data),

  systemMetrics: () =>
    http.get<SystemMetrics>('/admin/metrics').then((r) => r.data),

  login: (username: string, password: string) =>
    http
      .post<TokenResp>('/auth/login', { username, password })
      .then((r) => r.data),
  register: (payload: {
    username: string
    password: string
    email?: string
    display_name?: string
  }) => http.post<TokenResp>('/auth/register', payload).then((r) => r.data),
  me: () => http.get<AuthUser>('/auth/me').then((r) => r.data),

  getRegistrationStatus: () =>
    http
      .get<{ allow_registration: boolean }>('/auth/registration')
      .then((r) => r.data),
  getRegistrationSetting: () =>
    http
      .get<{ allow_registration: boolean }>('/settings/registration')
      .then((r) => r.data),
  setRegistrationSetting: (allow: boolean) =>
    http
      .put<{ allow_registration: boolean }>('/settings/registration', {
        allow_registration: allow,
      })
      .then((r) => r.data),

  listUsers: () =>
    http.get<{ total: number; items: AuthUser[] }>('/users').then((r) => r.data),
  createUser: (payload: {
    username: string
    password: string
    email?: string
    display_name?: string
    role?: 'user' | 'admin'
  }) => http.post<AuthUser>('/users', payload).then((r) => r.data),
  updateUser: (
    userId: string,
    payload: {
      email?: string
      display_name?: string
      role?: 'user' | 'admin'
      status?: 'active' | 'disabled'
      password?: string
    },
  ) => http.patch<AuthUser>(`/users/${userId}`, payload).then((r) => r.data),
  deleteUser: (userId: string) =>
    http.delete<void>(`/users/${userId}`).then((r) => r.data),

  myCredits: () => http.get<CreditBalance>('/me/credits').then((r) => r.data),
  myCreditTransactions: (params?: {
    limit?: number
    offset?: number
    type?: CreditTxType
  }) =>
    http
      .get<CreditTxListResp>('/me/credits/transactions', { params })
      .then((r) => r.data),
  getPricing: () => http.get<PricingListResp>('/billing/pricing').then((r) => r.data),
  estimateCost: (payload: {
    text: string
    model?: string
    reserved_output_tokens?: number
    prefer_api?: boolean
  }) => http.post<EstimateResp>('/billing/estimate', payload).then((r) => r.data),

  getUserCredits: (userId: string) =>
    http.get<CreditBalance>(`/users/${userId}/credits`).then((r) => r.data),
  getUserCreditTransactions: (
    userId: string,
    params?: { limit?: number; offset?: number; type?: CreditTxType },
  ) =>
    http
      .get<CreditTxListResp>(`/users/${userId}/credits/transactions`, { params })
      .then((r) => r.data),
  rechargeUser: (userId: string, payload: { amount: number; reason?: string }) =>
    http
      .post<CreditBalance>(`/users/${userId}/credits/recharge`, payload)
      .then((r) => r.data),
  adjustUser: (userId: string, payload: { delta: number; reason?: string }) =>
    http
      .post<CreditBalance>(`/users/${userId}/credits/adjust`, payload)
      .then((r) => r.data),

  billingSummary: () =>
    http.get<GlobalBillingSummary>('/admin/billing/summary').then((r) => r.data),
  getBillingConfig: () =>
    http.get<BillingConfig>('/admin/billing/config').then((r) => r.data),
  setBillingConfig: (payload: Partial<BillingConfig>) =>
    http.put<BillingConfig>('/admin/billing/config', payload).then((r) => r.data),
  updatePricing: (model: string, payload: Partial<Omit<PricingItem, 'model'>>) =>
    http
      .put<PricingItem>(`/admin/billing/pricing/${encodeURIComponent(model)}`, payload)
      .then((r) => r.data),

  listSkillDrafts: (opts?: {
    status?: SkillDraftStatus | ''
    search?: string
    limit?: number
    offset?: number
  }) => {
    const params: Record<string, string | number> = {}
    if (opts?.status) params.status = opts.status
    if (opts?.search?.trim()) params.search = opts.search.trim()
    if (opts?.limit != null) params.limit = opts.limit
    if (opts?.offset != null) params.offset = opts.offset
    return http
      .get<SkillDraftListResp>('/skill-drafts', {
        params: Object.keys(params).length ? params : undefined,
      })
      .then((r) => r.data)
  },
  getSkillDraft: (id: number) =>
    http.get<SkillDraftDetail>(`/skill-drafts/${id}`).then((r) => r.data),
  updateSkillDraft: (id: number, body: { name?: string; content?: string }) =>
    http.patch<SkillDraftDetail>(`/skill-drafts/${id}`, body).then((r) => r.data),
  approveSkillDraft: (id: number) =>
    http
      .post<{ ok: boolean; skill_path: string; total_after: number; message: string }>(
        `/skill-drafts/${id}/approve`,
      )
      .then((r) => r.data),
  rejectSkillDraft: (id: number) =>
    http.post<SkillDraftDetail>(`/skill-drafts/${id}/reject`).then((r) => r.data),

  listProjects: () =>
    http
      .get<{ total: number; items: Project[] }>('/projects')
      .then((r) => r.data),
  createProject: (payload: { name: string; description?: string }) =>
    http.post<Project>('/projects', payload).then((r) => r.data),
  getProject: (id: string) =>
    http.get<Project>(`/projects/${id}`).then((r) => r.data),
  deleteProject: (id: string) =>
    http.delete<void>(`/projects/${id}`).then((r) => r.data),

  listProjectMembers: (projectId: string) =>
    http
      .get<{ total: number; items: ProjectMember[] }>(
        `/projects/${projectId}/members`,
      )
      .then((r) => r.data),
  addProjectMember: (
    projectId: string,
    payload: { username: string; role?: 'editor' | 'viewer' },
  ) =>
    http
      .post<{ total: number; items: ProjectMember[] }>(
        `/projects/${projectId}/members`,
        payload,
      )
      .then((r) => r.data),
  updateProjectMember: (
    projectId: string,
    userId: string,
    role: 'editor' | 'viewer',
  ) =>
    http
      .patch<{ total: number; items: ProjectMember[] }>(
        `/projects/${projectId}/members/${userId}`,
        { role },
      )
      .then((r) => r.data),
  removeProjectMember: (projectId: string, userId: string) =>
    http
      .delete<{ total: number; items: ProjectMember[] }>(
        `/projects/${projectId}/members/${userId}`,
      )
      .then((r) => r.data),

  getFeatures: () =>
    http.get<{ project_sharing: boolean }>('/features').then((r) => r.data),

  getPermissionCatalog: () =>
    http
      .get<{ groups: PermissionCatalogGroup[] }>('/permissions/catalog')
      .then((r) => r.data),
  listRoles: () =>
    http.get<{ total: number; items: Role[] }>('/roles').then((r) => r.data),
  createRole: (payload: {
    name: string
    description?: string
    permissions?: string[]
  }) => http.post<Role>('/roles', payload).then((r) => r.data),
  updateRole: (
    id: string,
    payload: { name?: string; description?: string; permissions?: string[] },
  ) => http.patch<Role>(`/roles/${id}`, payload).then((r) => r.data),
  deleteRole: (id: string) =>
    http.delete<void>(`/roles/${id}`).then((r) => r.data),
  getUserRoles: (userId: string) =>
    http
      .get<{ items: { id: string; name: string }[] }>(`/users/${userId}/roles`)
      .then((r) => r.data),
  setUserRoles: (userId: string, roleIds: string[]) =>
    http
      .put<{ items: { id: string; name: string }[] }>(`/users/${userId}/roles`, {
        role_ids: roleIds,
      })
      .then((r) => r.data),

  publishProject: (projectId: string, defaultRole: 'editor' | 'viewer' = 'viewer') =>
    http
      .post<{ project_id: string; visibility: string; market_default_role: string }>(
        `/projects/${projectId}/publish`,
        { default_role: defaultRole },
      )
      .then((r) => r.data),
  unpublishProject: (projectId: string) =>
    http
      .post<{ project_id: string; visibility: string; market_default_role: string }>(
        `/projects/${projectId}/unpublish`,
      )
      .then((r) => r.data),
  adminGrantProject: (
    projectId: string,
    payload: { username: string; role: 'editor' | 'viewer' },
  ) =>
    http
      .post<{ total: number; items: ProjectMember[] }>(
        `/admin/projects/${projectId}/grant`,
        payload,
      )
      .then((r) => r.data),

  browseMarket: () =>
    http.get<{ total: number; items: MarketItem[] }>('/market').then((r) => r.data),
  applyMarket: (projectId: string, note?: string) =>
    http
      .post<AccessRequest>(`/market/${projectId}/apply`, { note: note || '' })
      .then((r) => r.data),
  myAccessRequests: () =>
    http
      .get<{ total: number; items: AccessRequest[] }>('/market/my-requests')
      .then((r) => r.data),
  incomingAccessRequests: () =>
    http
      .get<{ total: number; items: AccessRequest[] }>('/market/requests')
      .then((r) => r.data),
  approveAccessRequest: (id: number) =>
    http.post<AccessRequest>(`/market/requests/${id}/approve`).then((r) => r.data),
  rejectAccessRequest: (id: number) =>
    http.post<AccessRequest>(`/market/requests/${id}/reject`).then((r) => r.data),

  listAgents: () =>
    http.get<{ total: number; items: Agent[] }>('/agents').then((r) => r.data),

  listProviders: () =>
    http
      .get<{ total: number; items: Provider[] }>('/providers')
      .then((r) => r.data),

  createProvider: (body: ProviderUpsert) =>
    http.post<Provider>('/providers', body).then((r) => r.data),

  updateProvider: (id: string, body: Partial<ProviderUpsert>) =>
    http.patch<Provider>(`/providers/${id}`, body).then((r) => r.data),

  deleteProvider: (id: string) =>
    http.delete(`/providers/${id}`).then((r) => r.data),

  chatSync: (payload: {
    message: string
    agent_id?: string | null
    project_id?: string
  }) =>
    http
      .post<{
        reply: string
        agent_id: string
        agent_name: string
        model_calls: number
        tool_calls: number
        total_tokens: number
      }>(
        `/chat/sync${payload.project_id ? `?project_id=${payload.project_id}` : ''}`,
        { message: payload.message, agent_id: payload.agent_id ?? null },
      )
      .then((r) => r.data),

  listPendingQuestions: () =>
    http
      .get<{
        questions: Array<{ id: string; question: string; options?: string[] }>
      }>('/questions')
      .then((r) => r.data),
  answerQuestion: (id: string, answer: string) =>
    http
      .post<{ ok: boolean; question_id: string }>(`/questions/${id}/answer`, {
        answer,
      })
      .then((r) => r.data),

  listPersonas: () =>
    http
      .get<{
        total: number
        default_id: string
        personas_dir: string
        items: Persona[]
      }>('/personas')
      .then((r) => r.data),
  getPersona: (id: string) =>
    http.get<PersonaDetail>(`/personas/${id}`).then((r) => r.data),
  getAgentPersona: (agentId: string) =>
    http
      .get<{ agent_id: string; persona: Persona | null; cached: boolean }>(
        `/agents/${agentId}/persona`,
      )
      .then((r) => r.data),
  switchAgentPersona: (agentId: string, personaId: string) =>
    http
      .post<PersonaSwitchResp>(`/agents/${agentId}/persona`, {
        persona_id: personaId,
      })
      .then((r) => r.data),

  listSkills: (params?: {
    query?: string
    group?: string
    pinned_only?: boolean
    limit?: number
    offset?: number
  }) =>
    http
      .get<SkillListResp>('/skills', {
        params: {
          query: params?.query || undefined,
          group: params?.group || undefined,
          pinned_only: params?.pinned_only ? true : undefined,
          limit: params?.limit ?? undefined,
          offset: params?.offset ?? undefined,
        },
      })
      .then((r) => r.data),
  getSkill: (id: string) =>
    http.get<SkillDetail>(`/skills/${encodeURIComponent(id)}`).then((r) => r.data),
  uploadSkill: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http
      .post<SkillUploadResp>('/skills/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },

        timeout: 120_000,
      })
      .then((r) => r.data)
  },
  refreshSkills: () =>
    http.post<SkillRefreshResp>('/skills/refresh').then((r) => r.data),
  listSkillPins: () => http.get<SkillPinsResp>('/skills/pins').then((r) => r.data),
  pinSkill: (id: string) =>
    http
      .post<SkillPinsResp>(`/skills/pins/${encodeURIComponent(id)}`)
      .then((r) => r.data),
  unpinSkill: (id: string) =>
    http
      .delete<SkillPinsResp>(`/skills/pins/${encodeURIComponent(id)}`)
      .then((r) => r.data),

  uploadAttachment: (
    projectId: string,
    file: File,
    onProgress?: (percent: number) => void,
  ) => {
    const form = new FormData()
    form.append('file', file)
    return http
      .post<AttachedFileMeta>(`/projects/${projectId}/uploads`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 30 * 60_000,
        onUploadProgress: (e: AxiosProgressEvent) => {
          if (!onProgress) return
          if (e.total && e.total > 0) {
            const pct = Math.min(100, Math.round((e.loaded / e.total) * 100))
            onProgress(pct)
          }
        },
      })
      .then((r) => r.data)
  },

  deleteAttachment: (projectId: string, path: string) =>
    http
      .delete<{ ok: boolean; path: string }>(`/projects/${projectId}/uploads`, {
        params: { path },
      })
      .then((r) => r.data),

  listSessions: (
    projectId: string,
    params?: { limit?: number; offset?: number; includeArchived?: boolean },
  ) =>
    http
      .get<SessionListResp>(`/projects/${projectId}/sessions`, {
        params: {
          limit: params?.limit ?? undefined,
          offset: params?.offset ?? undefined,
          include_archived: params?.includeArchived ? true : undefined,
        },
      })
      .then((r) => r.data),

  getSession: (projectId: string, sessionId: string) =>
    http
      .get<SessionMeta>(`/projects/${projectId}/sessions/${sessionId}`)
      .then((r) => r.data),

  getSessionMessages: (
    projectId: string,
    sessionId: string,
    params?: { offset?: number; limit?: number },
  ) =>
    http
      .get<SessionMessagesResp>(
        `/projects/${projectId}/sessions/${sessionId}/messages`,
        {
          params: {
            offset: params?.offset ?? undefined,
            limit: params?.limit ?? undefined,
          },
        },
      )
      .then((r) => r.data),

  getSessionEvents: (
    projectId: string,
    sessionId: string,
    params?: { after_seq?: number; limit?: number },
  ) =>
    http
      .get<{
        session_id: string
        total: number
        after_seq: number
        events: Array<{
          seq: number
          type: string
          payload: Record<string, unknown>
          created_at: number
        }>
      }>(
        `/projects/${projectId}/sessions/${sessionId}/events`,
        {
          params: {
            after_seq: params?.after_seq ?? undefined,
            limit: params?.limit ?? undefined,
          },
        },
      )
      .then((r) => r.data),

  getLiveSessions: (projectId: string) =>
    http
      .get<{ running: string[] }>(`/projects/${projectId}/live_sessions`)
      .then((r) => r.data),

  getSessionLiveStatus: (projectId: string, sessionId: string) =>
    http
      .get<{
        running: boolean
        status: string
        last_seq: number
        error?: string | null
      }>(`/projects/${projectId}/sessions/${sessionId}/live/status`)
      .then((r) => r.data),

  cancelSessionRun: (projectId: string, sessionId: string) =>
    http
      .post<{ ok: boolean; cancelled: boolean; status: string }>(
        `/projects/${projectId}/sessions/${sessionId}/cancel`,
      )
      .then((r) => r.data),

  patchSession: (
    projectId: string,
    sessionId: string,
    body: { title?: string; status?: 'active' | 'ended' | 'archived' },
  ) =>
    http
      .patch<SessionMeta>(`/projects/${projectId}/sessions/${sessionId}`, body)
      .then((r) => r.data),

  deleteSession: (projectId: string, sessionId: string) =>
    http
      .delete<{
        session_id: string
        deleted_jsonl: boolean
        deleted_meta: boolean
        deleted_row: boolean
        deleted_history_rows: number
      }>(`/projects/${projectId}/sessions/${sessionId}`)
      .then((r) => r.data),

  reconcileSessions: (projectId: string) =>
    http
      .post<{ synced: number }>(`/projects/${projectId}/sessions/reconcile`)
      .then((r) => r.data),

  resolveCitations: (
    ids: string[],
    opts?: { fetchAbstract?: boolean; timeout?: number },
  ) =>
    http
      .post<CitationResolveResp>('/citations/resolve', {
        ids,
        fetch_abstract: !!opts?.fetchAbstract,
        timeout: opts?.timeout ?? 15,
      })
      .then((r) => r.data),

  verifyPolicyUrls: (urls: string[], opts?: { timeout?: number }) =>
    http
      .post<CitationResolveResp>('/citations/verify-url', {
        urls,
        timeout: opts?.timeout ?? 15,
      })
      .then((r) => r.data),

  fileRawUrl: (projectId: string, path: string, download = false): string => {
    const base = baseURL.replace(/\/$/, '')
    const qs = new URLSearchParams({ path })
    if (download) qs.set('download', 'true')

    const token = getToken()
    if (token) qs.set('access_token', token)
    return `${base}/projects/${projectId}/files/raw?${qs.toString()}`
  },

  previewFile: (
    projectId: string,
    path: string,
    opts?: { maxLines?: number },
  ) =>
    http
      .get<FilePreviewResp>(`/projects/${projectId}/files/preview`, {
        params: { path, max_lines: opts?.maxLines ?? undefined },
      })
      .then((r) => r.data),
}

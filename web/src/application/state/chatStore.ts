

import { create } from 'zustand'
import type { SSEEvent } from '@/client/services/sse'
import type { FilePresentation, SessionMessageRecord } from '@/client/services/client'
import { parseBackendTime } from '@/shared/foundation/utils'

export type ChatRole = 'user' | 'assistant'

export type TurnStepKind =
  | 'thinking'
  | 'tool'
  | 'ask_user'
  | 'delegate'
  | 'subagent'
  | 'pipeline'
  | 'squad'
  | 'council'
  | 'notice'
  | 'message'
  | 'error'

export interface ToolStep {
  id: string
  kind: 'tool'
  tool: string
  args: string
  status: 'running' | 'success' | 'failed'
  output?: string
  error?: string
  durationMs?: number
  data?: unknown
  truncated?: boolean
  fullLength?: number
  ts: number
}

export interface ThinkingStep {
  id: string
  kind: 'thinking'
  content: string
  agent?: string
  streaming?: boolean
  ts: number
}

export interface PretextStep {
  id: string
  kind: 'pretext'
  content: string
  toolCallIds?: string[]
  ts: number
}

export interface AskUserStep {
  id: string
  kind: 'ask_user'
  questionId: string
  question: string
  options?: string[]
  status: 'pending' | 'answered' | 'failed'
  answer?: string
  ts: number
}

export interface DelegateStep {
  id: string
  kind: 'delegate'
  persona?: string
  task?: string
  result?: string
  status: 'running' | 'success' | 'failed'
  ts: number
}

export interface SubagentStep {
  id: string
  kind: 'subagent'
  toAgent?: string
  fromAgent?: string
  question?: string
  answer?: string
  status: 'pending' | 'success' | 'failed'
  ts: number
}

export interface PipelineStep {
  id: string
  kind: 'pipeline'
  title: string
  runId?: string
  status: 'running' | 'success' | 'failed'
  durationMs?: number
  ts: number
}

export interface SquadTaskState {
  taskId: string
  title: string
  personaId?: string
  personaName?: string
  icon?: string
  status: 'pending' | 'running' | 'success' | 'failed'
  progress?: string
  progressKind?: 'thinking' | 'tool_call' | 'tool_result'
  durationMs?: number
  summary?: string
  artifacts?: string[]
  openQuestions?: string[]
  error?: string

  tokensIn?: number
  tokensOut?: number

  traceEvents?: ChatEvent[]
}

export interface SquadStep {
  id: string
  kind: 'squad'
  squadId: string
  title: string
  snapshotId?: string
  status: 'running' | 'success' | 'failed'
  tasks: SquadTaskState[]
  evidenceWarnings?: { ref: string; hit: string }[]
  durationMs?: number
  ts: number
}

export interface CouncilRoleState {
  roleId: string
  personaId: string
  personaName?: string
  status: 'pending' | 'running' | 'done' | 'failed'
  progress?: string
  progressKind?: 'thinking' | 'tool_call' | 'tool_result'
  stanceText?: string
  evidenceRefs?: string[]
  openQuestions?: string[]
  durationMs?: number
  error?: string

  rebutStatus?: 'pending' | 'running' | 'done' | 'failed'
  rebutProgress?: string
  rebutProgressKind?: 'thinking' | 'tool_call' | 'tool_result'
  rebuttalText?: string
  rebuttalEvidenceRefs?: string[]
  rebuttalError?: string

  tokensIn?: number
  tokensOut?: number
  traceEvents?: ChatEvent[]
}

export interface CouncilVerdictState {
  type: string
  text?: string
  conflictMatrix?: Array<{ axis: string; positions: Record<string, string> }>
  minorityNotes?: string
  durationMs?: number
}

export interface CouncilStep {
  id: string
  kind: 'council'
  councilId: string
  question?: string
  snapshotId?: string
  arbiterPersona: string
  status: 'running' | 'success' | 'failed' | 'escalated'
  roles: CouncilRoleState[]
  arbiterStatus?: 'pending' | 'running' | 'done'
  arbiterProgress?: string
  arbiterProgressKind?: 'thinking' | 'tool_call' | 'tool_result'

  arbiterTraceEvents?: ChatEvent[]
  verdict?: CouncilVerdictState
  evidenceWarnings?: { ref: string; hit: string }[]
  durationMs?: number
  ts: number
}

export interface NoticeStep {
  id: string
  kind: 'notice'
  level: 'info' | 'warn' | 'error'
  content: string
  ts: number
}

export interface MessageStep {
  id: string
  kind: 'message'
  content: string
  ts: number
}

export interface ErrorStep {
  id: string
  kind: 'error'
  content: string
  ts: number
}

export type TurnStep =
  | ThinkingStep
  | PretextStep
  | ToolStep
  | AskUserStep
  | DelegateStep
  | SubagentStep
  | PipelineStep
  | SquadStep
  | CouncilStep
  | NoticeStep
  | MessageStep
  | ErrorStep

export type AssistantState = 'done' | 'cancelled' | 'error'

export type UserSource = 'portal' | 'api' | 'cli' | string

export interface UserAttachmentMeta {
  name: string
  path: string
  size: number
  kind: 'image' | 'file'

  previewUrl?: string
}

export interface ChatMessage {
  id: string
  role: ChatRole
  text: string
  createdAt: number
  finishedAt?: number
  streaming?: boolean

  state?: AssistantState

  errorText?: string

  source?: UserSource

  attachments?: UserAttachmentMeta[]
  steps: TurnStep[]

  presentedFiles?: FilePresentation[]

  pendingEvidenceWarnings?: { ref: string; hit: string }[]
  tokens?: {
    input: number
    output: number
    cachedInput: number
    total: number
  }

  stats?: {
    totalTokens: number
    inputTokens: number
    outputTokens: number
    cachedInputTokens: number
    modelCalls: number
    toolCalls: number

    toolCounts: Record<string, number>

    durationMs: number

    rounds: number
  }
}

export interface ChatEvent {
  id: string
  ts: number
  raw: SSEEvent
}

export interface TurnStats {
  startedAt: number | null
  finishedAt: number | null
  totalEvents: number
  modelCalls: number
  toolCalls: number

  toolCounts: Record<string, number>
  inputTokens: number
  outputTokens: number
  cachedInputTokens: number
  totalTokens: number
  estCostUSD: number

  creditsCharged: number

  creditsBalance: number | null
}

export interface TraceDrawerState {

  stepId: string

  laneId: string

  kind: 'squad' | 'council'
}

export interface SessionSlot {
  messages: ChatMessage[]
  events: ChatEvent[]
  stats: TurnStats
  streaming: boolean
  pendingAskUserId: string | null
}

const emptySlot: SessionSlot = {
  messages: [],
  events: [],
  stats: {
    startedAt: null,
    finishedAt: null,
    totalEvents: 0,
    modelCalls: 0,
    toolCalls: 0,
    toolCounts: {},
    inputTokens: 0,
    outputTokens: 0,
    cachedInputTokens: 0,
    totalTokens: 0,
    estCostUSD: 0,
    creditsCharged: 0,
    creditsBalance: null,
  },
  streaming: false,
  pendingAskUserId: null,
}

interface ChatState {

  activeSessionId: string | null

  sessionSlots: Record<string, SessionSlot>

  messages: ChatMessage[]
  events: ChatEvent[]
  stats: TurnStats
  streaming: boolean
  pendingAskUserId: string | null

  traceDrawer: TraceDrawerState | null

  switchToSession: (sessionId: string | null) => void

  bindActiveSession: (sessionId: string) => void

  getSlot: (sessionId: string | null) => SessionSlot

  isSessionStreaming: (sessionId: string) => boolean

  pushUserMessage: (
    text: string,
    source?: UserSource,
    attachments?: UserAttachmentMeta[],
  ) => string
  beginAssistantTurn: () => string
  appendAssistantDelta: (id: string, delta: string) => void

  finishAssistantTurn: (
    id: string,
    finalState?: AssistantState,
    errorText?: string,
  ) => void

  ingestEvent: (assistantId: string, ev: SSEEvent) => void

  markAskUserAnswered: (stepId: string, answer: string) => void
  resetTurn: () => void
  clearAll: () => void

  clearSession: (sessionId: string) => void

  hydrateFromSessionRecords: (
    records: SessionMessageRecord[],
    options?: { prepend?: boolean },
  ) => void

  replayEvents: (
    events: Array<{
      seq: number
      type: string
      payload: Record<string, unknown>
      created_at: number
    }>,
    options?: { live?: boolean },
  ) => void

  openTraceDrawer: (state: TraceDrawerState) => void

  closeTraceDrawer: () => void
}

const initialStats: TurnStats = {
  startedAt: null,
  finishedAt: null,
  totalEvents: 0,
  modelCalls: 0,
  toolCalls: 0,
  toolCounts: {},
  inputTokens: 0,
  outputTokens: 0,
  cachedInputTokens: 0,
  totalTokens: 0,
  estCostUSD: 0,
  creditsCharged: 0,
  creditsBalance: null,
}

const PRICE_TABLE: Record<string, { input: number; output: number }> = {

  'kimi-k2.6': { input: 0.9, output: 3.75 },
  'kimi-k2.5': { input: 0.56, output: 2.92 },
  moonshot: { input: 1.39, output: 4.17 },
  'qwen-plus': { input: 0.4, output: 1.2 },
  'qwen-turbo': { input: 0.05, output: 0.2 },
  'qwen-max': { input: 2.5, output: 10 },
  'deepseek-chat': { input: 0.27, output: 1.1 },
  'deepseek-reasoner': { input: 0.55, output: 2.19 },
  default: { input: 0.9, output: 3.75 },
}

function priceOf(model?: string): { input: number; output: number } {
  if (!model) return PRICE_TABLE.default

  const key = Object.keys(PRICE_TABLE).find((k) => model.includes(k))
  return key ? PRICE_TABLE[key] : PRICE_TABLE.default
}

function genId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function truncateOneLine(s: string, max = 80): string {
  const cleaned = String(s || '').replace(/\s+/g, ' ').trim()
  if (!cleaned) return ''
  if (cleaned.length <= max) return cleaned
  return cleaned.slice(0, max - 1) + '…'
}

function progressForToolCall(ev: SSEEvent): string {
  const tool = String(ev.tool || ev.tool_name || 'tool')
  return `调用 ${tool}`
}

function progressForToolResult(ev: SSEEvent): string {
  const outRaw =
    typeof ev.output === 'string'
      ? ev.output
      : typeof ev.result?.output === 'string'
        ? String(ev.result.output)
        : ''
  if (outRaw) {
    const firstLine = outRaw.split(/\r?\n/, 1)[0] || outRaw
    return truncateOneLine(firstLine)
  }
  const errRaw =
    (typeof ev.error === 'string' && ev.error) ||
    (typeof ev.result?.error === 'string' && String(ev.result.error)) ||
    ''
  if (errRaw) return `失败: ${truncateOneLine(errRaw)}`
  return ev.success === false ? '失败' : '完成'
}

function replaceAt<T>(arr: T[], idx: number, value: T): T[] {
  if (idx < 0 || idx >= arr.length) return arr
  const out = arr.slice()
  out[idx] = value
  return out
}

const TRACE_EVENTS_SOFT_LIMIT = 200

function appendTrace(
  prev: ChatEvent[] | undefined,
  ev: SSEEvent,
  ts: number,
): ChatEvent[] {

  const id =
    typeof ev.id === 'string' && ev.id
      ? String(ev.id)
      : `${ts}-${String(ev.type)}-${Math.random().toString(36).slice(2, 8)}`
  const next: ChatEvent = { id, ts, raw: ev }
  const arr = prev ? [...prev, next] : [next]
  if (arr.length > TRACE_EVENTS_SOFT_LIMIT) {
    return arr.slice(arr.length - TRACE_EVENTS_SOFT_LIMIT)
  }
  return arr
}

function applySquadEvent(m: ChatMessage, ev: SSEEvent, now: number): ChatMessage {
  const t = String(ev.type)

  if (t === 'evidence_warning') {
    const ref = String(ev.ref || '')
    const hit = String(ev.hit || '')
    if (!ref && !hit) return m
    const warning = { ref, hit }
    let attached = false
    const steps = m.steps.map((step) => {
      if (!attached && step.kind === 'squad' && step.status === 'running') {
        attached = true
        return {
          ...step,
          evidenceWarnings: [...(step.evidenceWarnings || []), warning],
        }
      }
      return step
    })
    if (attached) return { ...m, steps }
    return {
      ...m,
      pendingEvidenceWarnings: [...(m.pendingEvidenceWarnings || []), warning],
    }
  }

  const squadId = String(ev.squad_id || '')
  if (!squadId) return m

  if (t === 'squad_started') {
    const buffered = m.pendingEvidenceWarnings || []
    const newStep: SquadStep = {
      id: squadId,
      kind: 'squad',
      squadId,
      title: String(ev.title || '并行小队'),
      snapshotId: ev.snapshot_id ? String(ev.snapshot_id) : undefined,
      status: 'running',
      tasks: [],
      evidenceWarnings: buffered.length > 0 ? [...buffered] : undefined,
      ts: now,
    }
    return {
      ...m,
      steps: [...m.steps, newStep],
      pendingEvidenceWarnings: undefined,
    }
  }

  const stepIdx = m.steps.findIndex(
    (step) => step.kind === 'squad' && step.squadId === squadId,
  )
  if (stepIdx < 0) return m
  const target = m.steps[stepIdx] as SquadStep

  if (t === 'squad_concluded') {
    const hasFailed = target.tasks.some((tk) => tk.status === 'failed')
    const anySuccess = target.tasks.some((tk) => tk.status === 'success')
    let newStatus: 'success' | 'failed'
    if (target.tasks.length === 0) {
      newStatus = 'failed'
    } else if (hasFailed && !anySuccess) {
      newStatus = 'failed'
    } else {
      newStatus = 'success'
    }
    const updated: SquadStep = {
      ...target,
      status: newStatus,
      durationMs: ev.duration_ms ? Number(ev.duration_ms) : target.durationMs,
    }
    return { ...m, steps: replaceAt(m.steps, stepIdx, updated) }
  }

  if (t === 'squad_task_started') {
    const taskId = String(ev.task_id || '')
    if (!taskId) return m
    if (target.tasks.some((tk) => tk.taskId === taskId)) return m

    const newTask: SquadTaskState = {
      taskId,
      title: String(ev.task_title || taskId),
      personaId: ev.persona_id ? String(ev.persona_id) : undefined,
      status: 'running',
      traceEvents: appendTrace(undefined, ev, now),
    }
    const updated: SquadStep = {
      ...target,
      tasks: [...target.tasks, newTask],
    }
    return { ...m, steps: replaceAt(m.steps, stepIdx, updated) }
  }

  const taskId = String(ev.task_id || '')
  if (!taskId) return m
  const tIdx = target.tasks.findIndex((tk) => tk.taskId === taskId)
  if (tIdx < 0) return m
  const task = target.tasks[tIdx]
  let updatedTask: SquadTaskState | null = null

  if (t === 'squad_task_thinking') {
    const content = String(ev.content || '')
    if (!content) return m
    updatedTask = {
      ...task,
      progress: truncateOneLine(content),
      progressKind: 'thinking',
    }
  } else if (t === 'squad_task_tool_call') {
    updatedTask = {
      ...task,
      progress: progressForToolCall(ev),
      progressKind: 'tool_call',
    }
  } else if (t === 'squad_task_tool_result') {
    updatedTask = {
      ...task,
      progress: progressForToolResult(ev),
      progressKind: 'tool_result',
    }
  } else if (t === 'squad_task_done') {
    const ok = ev.success !== false
    updatedTask = {
      ...task,
      status: ok ? 'success' : 'failed',
      summary: ev.summary ? String(ev.summary) : undefined,
      artifacts: Array.isArray(ev.artifacts)
        ? (ev.artifacts as unknown[]).map(String)
        : undefined,
      openQuestions: Array.isArray(ev.open_questions)
        ? (ev.open_questions as unknown[]).map(String)
        : undefined,
      durationMs: ev.duration_ms ? Number(ev.duration_ms) : undefined,
      error: ev.error ? String(ev.error) : undefined,
      progress: undefined,
      progressKind: undefined,
    }
  }

  if (!updatedTask) return m

  updatedTask = {
    ...updatedTask,
    traceEvents: appendTrace(task.traceEvents, ev, now),
  }
  const updatedStep: SquadStep = {
    ...target,
    tasks: replaceAt(target.tasks, tIdx, updatedTask),
  }
  return { ...m, steps: replaceAt(m.steps, stepIdx, updatedStep) }
}

const SQUAD_EVENT_TYPES: ReadonlySet<string> = new Set([
  'squad_started',
  'squad_task_started',
  'squad_task_thinking',
  'squad_task_tool_call',
  'squad_task_tool_result',
  'squad_task_done',
  'squad_concluded',
  'evidence_warning',
])

const COUNCIL_EVENT_TYPES: ReadonlySet<string> = new Set([
  'council_convened',
  'council_role_started',
  'council_role_thinking',
  'council_role_tool_call',
  'council_role_tool_result',
  'council_role_stance',
  'council_role_rebut_started',
  'council_role_rebut_thinking',
  'council_role_rebut_tool_call',
  'council_role_rebut_tool_result',
  'council_role_rebuttal',
  'council_arbiter_started',
  'council_arbiter_thinking',
  'council_arbiter_tool_call',
  'council_arbiter_tool_result',
  'council_verdict',
  'council_concluded',
])

function applyCouncilEvent(m: ChatMessage, ev: SSEEvent, now: number): ChatMessage {
  const t = String(ev.type)
  const councilId = String(ev.council_id || '')

  if (t === 'council_convened') {
    if (!councilId) return m
    const buffered = m.pendingEvidenceWarnings || []
    const roles = Array.isArray(ev.roles)
      ? (ev.roles as Array<{ role_id: string; persona_id: string }>).map((r) => ({
          roleId: String(r.role_id || ''),
          personaId: String(r.persona_id || ''),
          status: 'pending' as const,
        }))
      : []
    const newStep: CouncilStep = {
      id: councilId,
      kind: 'council',
      councilId,
      question: ev.question ? String(ev.question) : undefined,
      snapshotId: ev.snapshot_id ? String(ev.snapshot_id) : undefined,
      arbiterPersona: String(ev.arbiter_persona || 'critical_reviewer'),
      status: 'running',
      roles,
      evidenceWarnings: buffered.length > 0 ? [...buffered] : undefined,
      ts: now,
    }
    return {
      ...m,
      steps: [...m.steps, newStep],
      pendingEvidenceWarnings: undefined,
    }
  }

  if (!councilId) return m
  const stepIdx = m.steps.findIndex(
    (step) => step.kind === 'council' && (step as CouncilStep).councilId === councilId,
  )
  if (stepIdx < 0) return m
  const target = m.steps[stepIdx] as CouncilStep

  if (t === 'council_concluded') {
    const verdictType = target.verdict?.type || ev.verdict_type
    let newStatus: CouncilStep['status']
    if (verdictType === 'escalate') {
      newStatus = 'escalated'
    } else if (target.roles.some((r) => r.status === 'failed')) {
      newStatus = 'failed'
    } else {
      newStatus = 'success'
    }
    const updated: CouncilStep = {
      ...target,
      status: newStatus,
      durationMs: ev.duration_ms ? Number(ev.duration_ms) : target.durationMs,
    }
    return { ...m, steps: replaceAt(m.steps, stepIdx, updated) }
  }

  if (t === 'council_role_started') {
    const roleId = String(ev.role_id || '')
    const personaId = String(ev.persona_id || '')
    if (!roleId) return m
    const existIdx = target.roles.findIndex((r) => r.roleId === roleId)
    let newRoles: CouncilRoleState[]
    if (existIdx >= 0) {

      newRoles = replaceAt(target.roles, existIdx, {
        ...target.roles[existIdx],
        status: 'running',
        traceEvents: appendTrace(target.roles[existIdx].traceEvents, ev, now),
      })
    } else {
      newRoles = [
        ...target.roles,
        {
          roleId,
          personaId,
          status: 'running',
          traceEvents: appendTrace(undefined, ev, now),
        },
      ]
    }
    const updated: CouncilStep = { ...target, roles: newRoles }
    return { ...m, steps: replaceAt(m.steps, stepIdx, updated) }
  }

  if (t === 'council_role_thinking' || t === 'council_role_tool_call' || t === 'council_role_tool_result') {
    const roleId = String(ev.role_id || '')
    if (!roleId) return m
    const rIdx = target.roles.findIndex((r) => r.roleId === roleId)
    if (rIdx < 0) return m
    const role = target.roles[rIdx]
    let progress: string
    let progressKind: 'thinking' | 'tool_call' | 'tool_result'
    if (t === 'council_role_thinking') {
      progress = truncateOneLine(String(ev.content || ''))
      progressKind = 'thinking'
    } else if (t === 'council_role_tool_call') {
      progress = progressForToolCall(ev)
      progressKind = 'tool_call'
    } else {
      progress = progressForToolResult(ev)
      progressKind = 'tool_result'
    }
    const updatedRole: CouncilRoleState = {
      ...role,
      progress,
      progressKind,
      traceEvents: appendTrace(role.traceEvents, ev, now),
    }
    const updated: CouncilStep = {
      ...target,
      roles: replaceAt(target.roles, rIdx, updatedRole),
    }
    return { ...m, steps: replaceAt(m.steps, stepIdx, updated) }
  }

  if (t === 'council_role_stance') {
    const roleId = String(ev.role_id || '')
    if (!roleId) return m
    const rIdx = target.roles.findIndex((r) => r.roleId === roleId)
    if (rIdx < 0) return m
    const ok = ev.success !== false
    const updatedRole: CouncilRoleState = {
      ...target.roles[rIdx],
      status: ok ? 'done' : 'failed',

      stanceText:
        ev.text != null ? String(ev.text) : undefined,
      evidenceRefs: Array.isArray(ev.evidence_refs)
        ? (ev.evidence_refs as unknown[]).map(String)
        : undefined,
      openQuestions: Array.isArray(ev.open_questions)
        ? (ev.open_questions as unknown[]).map(String)
        : undefined,
      durationMs: ev.duration_ms ? Number(ev.duration_ms) : undefined,
      error: ev.error ? String(ev.error) : undefined,
      progress: undefined,
      progressKind: undefined,
      traceEvents: appendTrace(target.roles[rIdx].traceEvents, ev, now),
    }
    const updated: CouncilStep = {
      ...target,
      roles: replaceAt(target.roles, rIdx, updatedRole),
    }
    return { ...m, steps: replaceAt(m.steps, stepIdx, updated) }
  }

  if (t === 'council_role_rebut_started') {
    const roleId = String(ev.role_id || '')
    if (!roleId) return m
    const rIdx = target.roles.findIndex((r) => r.roleId === roleId)
    if (rIdx < 0) return m
    const updatedRole: CouncilRoleState = {
      ...target.roles[rIdx],
      rebutStatus: 'running',
      traceEvents: appendTrace(target.roles[rIdx].traceEvents, ev, now),
    }
    const updated: CouncilStep = { ...target, roles: replaceAt(target.roles, rIdx, updatedRole) }
    return { ...m, steps: replaceAt(m.steps, stepIdx, updated) }
  }

  if (t === 'council_role_rebut_thinking' || t === 'council_role_rebut_tool_call' || t === 'council_role_rebut_tool_result') {
    const roleId = String(ev.role_id || '')
    if (!roleId) return m
    const rIdx = target.roles.findIndex((r) => r.roleId === roleId)
    if (rIdx < 0) return m
    const role = target.roles[rIdx]
    let progress: string
    let progressKind: 'thinking' | 'tool_call' | 'tool_result'
    if (t === 'council_role_rebut_thinking') {
      progress = truncateOneLine(String(ev.content || ''))
      progressKind = 'thinking'
    } else if (t === 'council_role_rebut_tool_call') {
      progress = progressForToolCall(ev)
      progressKind = 'tool_call'
    } else {
      progress = progressForToolResult(ev)
      progressKind = 'tool_result'
    }
    const updatedRole: CouncilRoleState = {
      ...role,
      rebutProgress: progress,
      rebutProgressKind: progressKind,
      traceEvents: appendTrace(role.traceEvents, ev, now),
    }
    const updated: CouncilStep = { ...target, roles: replaceAt(target.roles, rIdx, updatedRole) }
    return { ...m, steps: replaceAt(m.steps, stepIdx, updated) }
  }

  if (t === 'council_role_rebuttal') {
    const roleId = String(ev.role_id || '')
    if (!roleId) return m
    const rIdx = target.roles.findIndex((r) => r.roleId === roleId)
    if (rIdx < 0) return m
    const ok = ev.success !== false
    const updatedRole: CouncilRoleState = {
      ...target.roles[rIdx],
      rebutStatus: ok ? 'done' : 'failed',
      rebuttalText: ev.text != null ? String(ev.text) : undefined,
      rebuttalEvidenceRefs: Array.isArray(ev.evidence_refs)
        ? (ev.evidence_refs as unknown[]).map(String)
        : undefined,
      rebuttalError: ev.error ? String(ev.error) : undefined,
      rebutProgress: undefined,
      rebutProgressKind: undefined,
      traceEvents: appendTrace(target.roles[rIdx].traceEvents, ev, now),
    }
    const updated: CouncilStep = { ...target, roles: replaceAt(target.roles, rIdx, updatedRole) }
    return { ...m, steps: replaceAt(m.steps, stepIdx, updated) }
  }

  if (t === 'council_arbiter_started') {
    const updated: CouncilStep = {
      ...target,
      arbiterStatus: 'running',
      arbiterTraceEvents: appendTrace(target.arbiterTraceEvents, ev, now),
    }
    return { ...m, steps: replaceAt(m.steps, stepIdx, updated) }
  }

  if (t === 'council_arbiter_thinking' || t === 'council_arbiter_tool_call' || t === 'council_arbiter_tool_result') {
    let progress: string
    let progressKind: 'thinking' | 'tool_call' | 'tool_result'
    if (t === 'council_arbiter_thinking') {
      progress = truncateOneLine(String(ev.content || ''))
      progressKind = 'thinking'
    } else if (t === 'council_arbiter_tool_call') {
      progress = progressForToolCall(ev)
      progressKind = 'tool_call'
    } else {
      progress = progressForToolResult(ev)
      progressKind = 'tool_result'
    }
    const updated: CouncilStep = {
      ...target,
      arbiterProgress: progress,
      arbiterProgressKind: progressKind,
      arbiterTraceEvents: appendTrace(target.arbiterTraceEvents, ev, now),
    }
    return { ...m, steps: replaceAt(m.steps, stepIdx, updated) }
  }

  if (t === 'council_verdict') {
    const verdict: CouncilVerdictState = {
      type: String(ev.verdict_type || ''),
      text: ev.text != null ? String(ev.text) : undefined,
      conflictMatrix: Array.isArray(ev.conflict_matrix)
        ? (ev.conflict_matrix as Array<{ axis: string; positions: Record<string, string> }>)
        : undefined,
      minorityNotes: ev.minority_notes ? String(ev.minority_notes) : undefined,
      durationMs: ev.duration_ms ? Number(ev.duration_ms) : undefined,
    }
    const updated: CouncilStep = { ...target, verdict, arbiterStatus: 'done', arbiterProgress: undefined, arbiterProgressKind: undefined }
    return { ...m, steps: replaceAt(m.steps, stepIdx, updated) }
  }

  return m
}

function eventToStep(ev: SSEEvent, ts: number): TurnStep | null {
  switch (ev.type) {
    case 'thinking': {
      const content = String(ev.content || '')
      if (!content) return null
      return {
        id: genId(),
        kind: 'thinking',
        content,
        agent: ev.agent_name ? String(ev.agent_name) : undefined,
        ts,
      }
    }
    case 'tool_call': {
      return {
        id: genId(),
        kind: 'tool',
        tool: String(ev.tool || ev.tool_name || 'tool'),
        args:
          typeof ev.arguments === 'string'
            ? ev.arguments
            : JSON.stringify(ev.arguments || {}, null, 2),
        status: 'running',
        ts,
      }
    }
    case 'assistant_pretext': {
      const content = String(ev.content || '').trim()
      if (!content) return null
      const ids = Array.isArray(ev.tool_call_ids)
        ? (ev.tool_call_ids as unknown[]).map(String)
        : undefined
      return {
        id: genId(),
        kind: 'pretext',
        content,
        toolCallIds: ids,
        ts,
      }
    }
    case 'ask_user_pending': {
      return {
        id: genId(),
        kind: 'ask_user',
        questionId: String(ev.question_id || ''),
        question: String(ev.question || ''),
        options: Array.isArray(ev.options) ? (ev.options as string[]) : undefined,
        status: 'pending',
        ts,
      }
    }
    case 'delegate_start': {
      return {
        id: genId(),
        kind: 'delegate',
        persona: String(ev.persona || ev.agent_id || ''),
        task: String(ev.task || ev.content || ''),
        status: 'running',
        ts,
      }
    }

    case 'subagent_request':
    case 'subagent_ask': {
      return {
        id: genId(),
        kind: 'subagent',
        toAgent: String(ev.to_agent || ev.target || ev.agent_id || ''),
        question: String(ev.question || ev.content || ''),
        status: 'pending',
        ts,
      }
    }

    case 'pipeline_start': {
      return {
        id: genId(),
        kind: 'pipeline',
        title: String(ev.title || ev.name || ev.content || 'Pipeline'),
        runId: ev.run_id ? String(ev.run_id) : undefined,
        status: 'running',
        ts,
      }
    }

    case 'notice':
    case 'system': {
      const lvl = String(ev.level || 'info')
      const level: 'info' | 'warn' | 'error' =
        lvl === 'warn' || lvl === 'warning'
          ? 'warn'
          : lvl === 'error'
            ? 'error'
            : 'info'
      return {
        id: genId(),
        kind: 'notice',
        level,
        content: String(ev.content || ev.message || ''),
        ts,
      }
    }
    case 'error': {
      return {
        id: genId(),
        kind: 'error',
        content: String(ev.error || ev.content || '未知错误'),
        ts,
      }
    }
    default:
      return null
  }
}

function _applyEventToMessage(
  m: ChatMessage,
  ev: SSEEvent,
  now: number,
  onAskUser: (stepId: string) => void,
): ChatMessage {

  if (ev.type === 'message_delta') {
    const delta = String(ev.delta || ev.content || '')
    if (!delta) return m
    return { ...m, text: m.text + delta }
  }

  if (ev.type === 'message') {
    const full = String(ev.content || ev.delta || '')
    if (!full) return m
    return { ...m, text: full }
  }

  if (ev.type === 'tool_result') {
    const targetId = String(ev.tool_call_id || '')
    let attached = false
    const steps = m.steps.map((step) => {
      if (
        !attached &&
        step.kind === 'tool' &&
        step.status === 'running' &&
        (targetId ? step.tool === ev.tool : true)
      ) {
        attached = true
        return {
          ...step,
          status: ev.success === false ? 'failed' : 'success',
          output: ev.output as string | undefined,
          error: ev.error as string | undefined,
          durationMs: Number(ev.duration_ms || 0),
          data: ev.data,
          truncated: Boolean(ev.truncated),
          fullLength: Number(ev.full_length || 0) || undefined,
        } as ToolStep
      }
      return step
    })
    if (!attached) {
      const toolStep: ToolStep = {
        id: genId(),
        kind: 'tool',
        tool: String(ev.tool || 'tool'),
        args: '',
        status: ev.success === false ? 'failed' : 'success',
        output: ev.output as string | undefined,
        error: ev.error as string | undefined,
        durationMs: Number(ev.duration_ms || 0),
        data: ev.data,
        ts: now,
      }
      return { ...m, steps: [...m.steps, toolStep] }
    }
    return { ...m, steps }
  }

  if (ev.type === 'delegate_result') {
    let attached = false
    const steps = m.steps.map((step) => {
      if (!attached && step.kind === 'delegate' && step.status === 'running') {
        attached = true
        return {
          ...step,
          status: 'success',
          result: String(ev.result || ev.content || ''),
        } as DelegateStep
      }
      return step
    })
    return { ...m, steps: attached ? steps : m.steps }
  }

  if (ev.type === 'subagent_reply' || ev.type === 'subagent_answer') {
    let attached = false
    const steps = m.steps.map((step) => {
      if (!attached && step.kind === 'subagent' && step.status === 'pending') {
        attached = true
        return {
          ...step,
          status: 'success' as const,
          fromAgent: String(ev.from_agent || ev.agent_id || step.toAgent || ''),
          answer: String(ev.answer || ev.content || ev.result || ''),
        } as SubagentStep
      }
      return step
    })
    return { ...m, steps: attached ? steps : m.steps }
  }

  if (ev.type === 'pipeline_result' || ev.type === 'pipeline_done') {
    let attached = false
    const steps = m.steps.map((step) => {
      if (!attached && step.kind === 'pipeline' && step.status === 'running') {
        attached = true
        const ok = ev.success !== false
        return {
          ...step,
          status: (ok ? 'success' : 'failed') as 'success' | 'failed',
          durationMs: Number(ev.duration_ms || 0) || step.durationMs,
        } as PipelineStep
      }
      return step
    })
    return { ...m, steps: attached ? steps : m.steps }
  }

  if (SQUAD_EVENT_TYPES.has(String(ev.type))) {
    return applySquadEvent(m, ev, now)
  }

  if (COUNCIL_EVENT_TYPES.has(String(ev.type))) {
    return applyCouncilEvent(m, ev, now)
  }

  const step = eventToStep(ev, now)
  if (!step) return m
  if (step.kind === 'ask_user') {
    onAskUser(step.id)
  }
  return { ...m, steps: [...m.steps, step] }
}

export const useChatStore = create<ChatState>((set, get) => ({
  activeSessionId: null,
  sessionSlots: {},
  messages: [],
  events: [],
  stats: { ...initialStats },
  streaming: false,
  pendingAskUserId: null,
  traceDrawer: null,

  openTraceDrawer: (state: TraceDrawerState) => {
    set({ traceDrawer: state })
  },
  closeTraceDrawer: () => {
    set({ traceDrawer: null })
  },

  switchToSession: (sessionId: string | null) => {
    const s = get()

    if (s.activeSessionId === sessionId) return

    const currentSid = s.activeSessionId
    let slots = { ...s.sessionSlots }
    if (currentSid) {
      slots[currentSid] = {
        messages: s.messages,
        events: s.events,
        stats: s.stats,
        streaming: s.streaming,
        pendingAskUserId: s.pendingAskUserId,
      }
    }

    const target = (sessionId && slots[sessionId]) || emptySlot
    set({
      activeSessionId: sessionId,
      sessionSlots: slots,
      messages: target.messages,
      events: target.events,
      stats: target.stats,
      streaming: target.streaming,
      pendingAskUserId: target.pendingAskUserId,
      traceDrawer: null,
    })
  },

  bindActiveSession: (sessionId: string) => {
    set((s) => {
      if (s.activeSessionId === sessionId) return s

      return { activeSessionId: sessionId }
    })
  },

  getSlot: (sessionId: string | null) => {
    if (!sessionId) return emptySlot
    return get().sessionSlots[sessionId] || emptySlot
  },

  isSessionStreaming: (sessionId: string) => {
    const s = get()
    if (s.activeSessionId === sessionId) return s.streaming
    const slot = s.sessionSlots[sessionId]
    return slot ? slot.streaming : false
  },

  pushUserMessage: (
    text: string,
    source?: UserSource,
    attachments?: UserAttachmentMeta[],
  ) => {
    const id = genId()
    set((s) => ({
      messages: [
        ...s.messages,
        {
          id,
          role: 'user',
          text,
          createdAt: Date.now(),
          source,
          attachments: attachments && attachments.length > 0 ? attachments : undefined,
          steps: [],
        },
      ],
    }))
    return id
  },

  beginAssistantTurn: () => {
    const id = genId()
    set((s) => ({
      messages: [
        ...s.messages,
        {
          id,
          role: 'assistant',
          text: '',
          streaming: true,
          createdAt: Date.now(),
          steps: [],
        },
      ],
      stats: { ...initialStats, startedAt: Date.now() },
      streaming: true,
      pendingAskUserId: null,
    }))
    return id
  },

  appendAssistantDelta: (id: string, delta: string) => {
    if (!delta) return
    set((s) => {

      const found = s.messages.some((m) => m.id === id)
      if (found) {
        return {
          messages: s.messages.map((m) =>
            m.id === id ? { ...m, text: m.text + delta } : m,
          ),
        }
      }

      const slots = { ...s.sessionSlots }
      for (const [sid, slot] of Object.entries(slots)) {
        if (slot.messages.some((m) => m.id === id)) {
          slots[sid] = {
            ...slot,
            messages: slot.messages.map((m) =>
              m.id === id ? { ...m, text: m.text + delta } : m,
            ),
          }
          return { sessionSlots: slots }
        }
      }
      return {}
    })
  },

  finishAssistantTurn: (
    id: string,
    finalState: AssistantState = 'done',
    errorText?: string,
  ) => {
    const now = Date.now()
    const s = get()
    const st = s.stats

    const finishMsg = (m: ChatMessage): ChatMessage => {
      if (m.id !== id) return m
      const durationMs = m.createdAt ? now - m.createdAt : 0
      return {
        ...m,
        streaming: false,
        finishedAt: now,
        state: finalState,
        errorText,
        steps:
          finalState === 'cancelled' || finalState === 'error'
            ? m.steps.map((step) =>
                step.kind === 'tool' && step.status === 'running'
                  ? ({ ...step, status: 'failed' } as ToolStep)
                  : step,
              )
            : m.steps,
        tokens: {
          input: st.inputTokens,
          output: st.outputTokens,
          cachedInput: st.cachedInputTokens,
          total: st.totalTokens,
        },
        stats: {
          totalTokens: st.totalTokens,
          inputTokens: st.inputTokens,
          outputTokens: st.outputTokens,
          cachedInputTokens: st.cachedInputTokens,
          modelCalls: st.modelCalls,
          toolCalls: st.toolCalls,
          toolCounts: { ...st.toolCounts },
          durationMs,
          rounds: st.modelCalls || 1,
        },
      }
    }

    if (s.messages.some((m) => m.id === id)) {
      set({
        messages: s.messages.map(finishMsg),
        stats: { ...st, finishedAt: now },
        streaming: false,
      })
      return
    }

    const slots = { ...s.sessionSlots }
    for (const [sid, slot] of Object.entries(slots)) {
      if (slot.messages.some((m) => m.id === id)) {
        slots[sid] = {
          ...slot,
          messages: slot.messages.map(finishMsg),
          stats: { ...slot.stats, finishedAt: now },
          streaming: false,
        }
        set({ sessionSlots: slots })
        return
      }
    }
  },

  ingestEvent: (assistantId: string, ev: SSEEvent) => {
    const now = Date.now()
    set((s) => {

      const inForeground = s.messages.some((m) => m.id === assistantId)

      if (!inForeground) {

        const slots = { ...s.sessionSlots }
        for (const [sid, slot] of Object.entries(slots)) {
          if (!slot.messages.some((m) => m.id === assistantId)) continue

          const slotEvents = [...slot.events, { id: genId(), ts: now, raw: ev }]
          const slotStats = { ...slot.stats, totalEvents: slotEvents.length }

          if (ev.type === 'usage') {
            const input = Number(ev.input_tokens || 0)
            const output = Number(ev.output_tokens || 0)
            const cached = Number(ev.cached_input_tokens || 0)
            const total = Number(ev.total_tokens || input + output)
            slotStats.modelCalls += 1
            slotStats.inputTokens += input
            slotStats.outputTokens += output
            slotStats.cachedInputTokens += cached
            slotStats.totalTokens += total
            const p = priceOf(ev.model as string | undefined)
            slotStats.estCostUSD +=
              (input / 1_000_000) * p.input + (output / 1_000_000) * p.output
            if (ev.credits_charged != null)
              slotStats.creditsCharged += Number(ev.credits_charged || 0)
            if (ev.credits_balance != null)
              slotStats.creditsBalance = Number(ev.credits_balance)
          }
          if (ev.type === 'tool_call') {
            slotStats.toolCalls += 1
            const toolName = String(ev.tool || ev.tool_name || 'tool')
            slotStats.toolCounts = {
              ...slotStats.toolCounts,
              [toolName]: (slotStats.toolCounts[toolName] || 0) + 1,
            }
          }
          if (ev.type === 'done' && slotStats.totalTokens === 0) {
            const dst = (ev as any).stats || {}
            slotStats.inputTokens = Number(dst.input_tokens || 0)
            slotStats.outputTokens = Number(dst.output_tokens || 0)
            slotStats.totalTokens = slotStats.inputTokens + slotStats.outputTokens
            slotStats.modelCalls = Number(dst.model_calls || 0)
            slotStats.toolCalls = Number(dst.tool_calls || 0)
          }

          let slotPendingAskUserId = slot.pendingAskUserId
          const slotMessages = slot.messages.map((m) => {
            if (m.id !== assistantId || m.role !== 'assistant') return m
            return _applyEventToMessage(m, ev, now, (askId) => { slotPendingAskUserId = askId })
          })

          slots[sid] = {
            ...slot,
            events: slotEvents,
            stats: slotStats,
            messages: slotMessages,
            pendingAskUserId: slotPendingAskUserId,
          }
          return { sessionSlots: slots }
        }
        return {}
      }

      const events = [...s.events, { id: genId(), ts: now, raw: ev }]
      const stats = { ...s.stats, totalEvents: events.length }

      if (ev.type === 'usage') {
        const input = Number(ev.input_tokens || 0)
        const output = Number(ev.output_tokens || 0)
        const cached = Number(ev.cached_input_tokens || 0)
        const total = Number(ev.total_tokens || input + output)
        stats.modelCalls += 1
        stats.inputTokens += input
        stats.outputTokens += output
        stats.cachedInputTokens += cached
        stats.totalTokens += total
        const p = priceOf(ev.model as string | undefined)
        stats.estCostUSD +=
          (input / 1_000_000) * p.input + (output / 1_000_000) * p.output
        if (ev.credits_charged != null)
          stats.creditsCharged += Number(ev.credits_charged || 0)
        if (ev.credits_balance != null)
          stats.creditsBalance = Number(ev.credits_balance)
      }

      if (ev.type === 'tool_call') {
        stats.toolCalls += 1
        const toolName = String(ev.tool || ev.tool_name || 'tool')
        stats.toolCounts = {
          ...stats.toolCounts,
          [toolName]: (stats.toolCounts[toolName] || 0) + 1,
        }
      }

      if (ev.type === 'done' && stats.totalTokens === 0) {
        const dst = (ev as any).stats || {}
        stats.inputTokens = Number(dst.input_tokens || 0)
        stats.outputTokens = Number(dst.output_tokens || 0)
        stats.totalTokens = stats.inputTokens + stats.outputTokens
        stats.modelCalls = Number(dst.model_calls || 0)
        stats.toolCalls = Number(dst.tool_calls || 0)
      }

      let pendingAskUserId = s.pendingAskUserId
      const messages = s.messages.map((m) => {
        if (m.id !== assistantId || m.role !== 'assistant') return m
        return _applyEventToMessage(m, ev, now, (askId) => { pendingAskUserId = askId })
      })

      return { events, stats, messages, pendingAskUserId }
    })
  },

  markAskUserAnswered: (stepId: string, answer: string) => {
    set((s) => ({
      messages: s.messages.map((m) => ({
        ...m,
        steps: m.steps.map((step) =>
          step.kind === 'ask_user' && step.id === stepId
            ? { ...step, status: 'answered' as const, answer }
            : step,
        ),
      })),
      pendingAskUserId:
        s.pendingAskUserId === stepId ? null : s.pendingAskUserId,
    }))
  },

  resetTurn: () =>
    set({
      events: [],
      stats: { ...initialStats },
      streaming: false,
      pendingAskUserId: null,
    }),

  clearAll: () => {
    const s = get()
    const currentSid = s.activeSessionId

    const slots = { ...s.sessionSlots }
    if (currentSid) {
      delete slots[currentSid]
    }
    set({
      messages: [],
      events: [],
      stats: { ...initialStats },
      streaming: false,
      pendingAskUserId: null,
      traceDrawer: null,
      activeSessionId: null,
      sessionSlots: slots,
    })
  },

  clearSession: (sessionId: string) => {
    const s = get()
    const slots = { ...s.sessionSlots }
    delete slots[sessionId]
    if (s.activeSessionId === sessionId) {
      set({
        messages: [],
        events: [],
        stats: { ...initialStats },
        streaming: false,
        pendingAskUserId: null,
        traceDrawer: null,
        activeSessionId: null,
        sessionSlots: slots,
      })
    } else {
      set({ sessionSlots: slots })
    }
  },

  hydrateFromSessionRecords: (
    records: SessionMessageRecord[],
    options?: { prepend?: boolean },
  ) => {

    function _parseRecordTimestamp(raw: string | number | null | undefined): number {

      return parseBackendTime(raw) ?? Date.now()
    }

    const prepend = options?.prepend === true
    const converted: ChatMessage[] = []

    for (const rec of records) {
      const role = String(rec.role || '')
      const content = rec.content
      const text =
        typeof content === 'string'
          ? content
          : content == null
            ? ''
            : Array.isArray(content)
              ? content
                  .map((p) =>
                    typeof p === 'string'
                      ? p
                      : typeof p === 'object' && p !== null && 'text' in (p as object)
                        ? String((p as { text?: unknown }).text || '')
                        : '',
                  )
                  .join('')
              : ''

      if (role === 'tool') {
        if (!text) continue
        const presentations = extractPresentationsFromContent(text)
        if (presentations.length === 0) continue

        for (let i = converted.length - 1; i >= 0; i--) {
          if (converted[i].role === 'assistant') {
            const existing = converted[i].presentedFiles || []
            converted[i] = {
              ...converted[i],
              presentedFiles: [...existing, ...presentations],
            }
            break
          }
        }
        continue
      }

      if (role !== 'user' && role !== 'assistant') continue

      if (!text && role !== 'assistant') {

        continue
      }

      if (role === 'assistant' && !text.trim()) {

        const recAny = rec as unknown as {
          tool_calls?: unknown
          tool_calls_json?: string
        }
        const hasToolCalls =
          (Array.isArray(recAny.tool_calls) && recAny.tool_calls.length > 0) ||
          !!recAny.tool_calls_json
        if (!hasToolCalls) {

          continue
        }

        continue
      }

      let displayText = text
      let attachments: UserAttachmentMeta[] | undefined
      if (role === 'user') {
        const attMatch = text.match(
          /<!--CC:ATTACHMENTS:v1-->([\s\S]*?)<!--\/CC:ATTACHMENTS-->/,
        )
        if (attMatch) {
          displayText = text
            .replace(/\n?<!--CC:ATTACHMENTS:v1-->[\s\S]*?<!--\/CC:ATTACHMENTS-->/, '')
            .trimEnd()
          try {
            const parsed = JSON.parse(attMatch[1]) as Array<{
              name: string; path: string; size: number; kind?: string
            }>
            attachments = parsed.map((a) => ({
              name: a.name,
              path: a.path,
              size: a.size,
              kind: (a.kind === 'image' ? 'image' : 'file') as 'image' | 'file',
            }))
          } catch {  }
        }
      }

      const recordTs = _parseRecordTimestamp(rec.created_at)
      converted.push({
        id: genId(),
        role: role as ChatRole,
        text: displayText,
        createdAt: recordTs,
        finishedAt: recordTs,
        streaming: false,
        state: role === 'assistant' ? 'done' : undefined,
        attachments,
        steps: [],
      })
    }

    set((s) => ({
      messages: prepend ? [...converted, ...s.messages] : converted,
      events: prepend ? s.events : [],
      stats: prepend ? s.stats : { ...initialStats },
      streaming: prepend ? s.streaming : false,
      pendingAskUserId: prepend ? s.pendingAskUserId : null,
    }))
  },

  replayEvents: (events, options) => {
    if (!events || events.length === 0) return
    const live = options?.live === true

    const REPLAY_SKIP_TYPES: ReadonlySet<string> = new Set([
      'message_delta',
      'message',
      'usage',
      'done',
      'session_started',
    ])

    const REPLAY_SKIP_TYPES_OPEN_TURN: ReadonlySet<string> = new Set([
      'usage',
      'done',
      'session_started',
    ])

    const replayedEvents: ChatEvent[] = []
    for (const ev of events) {
      const payload = ev.payload as Record<string, unknown> & { type?: string }
      const evType = String(payload.type || ev.type || '')
      if (!evType || evType === 'session_started') continue
      const ts = ev.created_at
        ? (ev.created_at < 1e12 ? ev.created_at * 1000 : ev.created_at)
        : Date.now()
      replayedEvents.push({
        id: `seq-${ev.seq}`,
        ts,
        raw: { ...payload, type: evType } as SSEEvent,
      })
    }

    type StoredEvent = (typeof events)[number]
    const turns: StoredEvent[][] = []
    let cur: StoredEvent[] = []
    for (const ev of events) {
      if (ev.type === 'session_started') continue
      cur.push(ev)
      if (ev.type === 'done') {
        turns.push(cur)
        cur = []
      }
    }

    if (cur.length > 0) turns.push(cur)

    if (turns.length === 0) {
      set({ events: replayedEvents })
      return
    }

    const state = get()
    const groups: number[][] = []
    let curGroup: number[] | null = null
    state.messages.forEach((m, i) => {
      if (m.role === 'user') {
        curGroup = []
        groups.push(curGroup)
      } else if (m.role === 'assistant') {
        if (curGroup == null) {

          curGroup = []
          groups.push(curGroup)
        }
        curGroup.push(i)
      }
    })
    if (groups.length === 0) {
      set({ events: replayedEvents })
      return
    }

    const n = Math.min(turns.length, groups.length)
    const turnSliceStart = turns.length - n
    const groupSliceStart = groups.length - n

    let msgs = [...state.messages]

    const removeIds = new Set<string>()
    for (let k = 0; k < n; k++) {
      const turn = turns[turnSliceStart + k]
      const group = groups[groupSliceStart + k]

      if (group.length === 0) continue
      const mIdx = group[group.length - 1]
      let m = msgs[mIdx]

      const turnIsOpen = !turn.some((e) => {
        const p = e.payload as Record<string, unknown>
        return String(p.type || e.type || '') === 'done'
      })
      const skipTypes =
        live && turnIsOpen ? REPLAY_SKIP_TYPES_OPEN_TURN : REPLAY_SKIP_TYPES

      for (const ev of turn) {
        const payload = ev.payload as Record<string, unknown> & { type?: string }
        const evType = String(payload.type || ev.type || '')
        if (!evType || skipTypes.has(evType)) continue

        const sseEvent = { ...payload, type: evType } as SSEEvent

        const originalTs = ev.created_at
          ? (ev.created_at < 1e12 ? ev.created_at * 1000 : ev.created_at)
          : Date.now()

        m = _applyEventToMessage(m, sseEvent, originalTs, () => {})
      }

      const pretextTexts = new Set(
        turn
          .map((e) => e.payload as Record<string, unknown>)
          .filter((p) => String(p.type || '') === 'assistant_pretext')
          .map((p) => String(p.content || '').trim())
          .filter(Boolean),
      )
      if (pretextTexts.size > 0) {
        for (let gi = 0; gi < group.length - 1; gi++) {
          const bub = msgs[group[gi]]
          if (bub.role !== 'assistant') continue
          if (!pretextTexts.has(bub.text.trim())) continue
          removeIds.add(bub.id)
          if (bub.presentedFiles && bub.presentedFiles.length > 0) {
            m = {
              ...m,
              presentedFiles: [
                ...(m.presentedFiles || []),
                ...bub.presentedFiles,
              ],
            }
          }
        }
      }

      let toolCalls = 0
      const toolCounts: Record<string, number> = {}
      let firstTs = Infinity
      let lastTs = 0
      for (const ev of turn) {
        const p = ev.payload as Record<string, unknown>
        const t = String(p.type || ev.type || '')
        const evTs = ev.created_at
          ? (ev.created_at < 1e12 ? ev.created_at * 1000 : ev.created_at)
          : 0
        if (evTs > 0 && evTs < firstTs) firstTs = evTs
        if (evTs > lastTs) lastTs = evTs
        if (t === 'tool_call') {
          toolCalls++
          const tn = String(p.tool || p.tool_name || 'tool')
          toolCounts[tn] = (toolCounts[tn] || 0) + 1
        }
      }
      const durationMs = (firstTs < Infinity && lastTs > firstTs) ? lastTs - firstTs : 0

      const doneEv = turn.find((e) => (e.payload as any)?.type === 'done' || e.type === 'done')
      const donePayload = doneEv?.payload as Record<string, unknown> | undefined
      const backendStats = (donePayload?.stats || {}) as Record<string, unknown>

      const turnStartTs = firstTs < Infinity ? firstTs : m.createdAt

      if (live && turnIsOpen) {
        m = { ...m, createdAt: turnStartTs }
        msgs = replaceAt(msgs, mIdx, m)
        continue
      }

      m = {
        ...m,
        createdAt: turnStartTs,
        finishedAt: lastTs > 0 ? lastTs : m.finishedAt,
        stats: {
          totalTokens: Number(backendStats.total_tokens || 0),
          inputTokens: Number(backendStats.input_tokens || 0),
          outputTokens: Number(backendStats.output_tokens || 0),
          cachedInputTokens: Number(backendStats.cached_input_tokens || 0),
          modelCalls: Number(backendStats.model_calls || 0),
          toolCalls: Number(backendStats.tool_calls || 0) || toolCalls,
          toolCounts,
          durationMs: Number(backendStats.duration_ms || 0) || durationMs,
          rounds: Number(backendStats.model_calls || 0) || 1,
        },
      }

      msgs = replaceAt(msgs, mIdx, m)
    }

    const finalMsgs =
      removeIds.size > 0 ? msgs.filter((m) => !removeIds.has(m.id)) : msgs
    if (live) {
      set({ messages: finalMsgs, events: replayedEvents })
    } else {
      set({
        messages: finalMsgs.map((m) =>
          m.streaming ? { ...m, streaming: false } : m,
        ),
        streaming: false,
        events: replayedEvents,
      })
    }
  },
}))

const PRESENTATION_SENTINEL_RE =
  /<!--CC:PRESENTATION:v1-->([\s\S]*?)<!--\/CC:PRESENTATION-->/g

function extractPresentationsFromContent(content: string): FilePresentation[] {
  if (!content.includes('CC:PRESENTATION')) return []
  const out: FilePresentation[] = []

  PRESENTATION_SENTINEL_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = PRESENTATION_SENTINEL_RE.exec(content)) !== null) {
    const raw = m[1]
    if (!raw) continue
    try {
      const parsed = JSON.parse(raw)
      if (
        parsed &&
        typeof parsed === 'object' &&
        parsed.kind === 'files' &&
        Array.isArray(parsed.files) &&
        parsed.files.length > 0
      ) {
        out.push(parsed as FilePresentation)
      }
    } catch {

    }
  }
  return out
}

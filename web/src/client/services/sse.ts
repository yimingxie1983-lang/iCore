

import { getToken } from '@/application/state/authStore'

function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export type SSEEventType =
  | 'thinking'
  | 'tool_call'
  | 'tool_result'
  | 'message'
  | 'message_delta'
  | 'delegate_start'
  | 'delegate_result'
  | 'ask_user_pending'
  | 'usage'
  | 'error'
  | 'done'

  | 'squad_started'
  | 'squad_task_started'
  | 'squad_task_thinking'
  | 'squad_task_tool_call'
  | 'squad_task_tool_result'
  | 'squad_task_done'
  | 'squad_concluded'

  | 'council_convened'
  | 'council_role_started'
  | 'council_role_thinking'
  | 'council_role_tool_call'
  | 'council_role_tool_result'
  | 'council_role_stance'
  | 'council_role_rebut_started'
  | 'council_role_rebut_thinking'
  | 'council_role_rebut_tool_call'
  | 'council_role_rebut_tool_result'
  | 'council_role_rebuttal'
  | 'council_arbiter_started'
  | 'council_arbiter_thinking'
  | 'council_arbiter_tool_call'
  | 'council_arbiter_tool_result'
  | 'council_verdict'
  | 'council_concluded'

  | 'evidence_warning'
  | string

export interface SSEEvent {
  type: SSEEventType

  agent_id?: string
  agent_name?: string
  depth?: number
  ts?: number

  content?: string
  delta?: string
  tool?: string
  tool_name?: string
  arguments?: string | Record<string, unknown>
  result?: { success?: boolean; output?: string; data?: unknown; error?: string }
  question_id?: string
  question?: string
  options?: string[]

  input_tokens?: number
  output_tokens?: number
  cached_input_tokens?: number
  total_tokens?: number
  model?: string

  credits_charged?: number
  credits_balance?: number

  squad_id?: string
  task_id?: string
  task_title?: string
  tasks_total?: number
  persona_id?: string
  snapshot_id?: string
  summary?: string
  artifacts?: string[]
  open_questions?: string[]
  duration_ms?: number
  success?: boolean
  output?: string
  error?: string

  council_id?: string
  role_id?: string
  roles?: Array<{ role_id: string; persona_id: string }>
  arbiter_persona?: string
  stance_text?: string
  evidence_refs?: string[]
  verdict_type?: string
  verdict_text?: string
  conflict_matrix?: Array<{ axis: string; positions: Record<string, string> }>
  minority_notes?: string

  ref?: string
  hit?: string

  [k: string]: unknown
}

export interface SquadStartedEvent extends SSEEvent {
  type: 'squad_started'
  squad_id: string
  title?: string
  snapshot_id?: string
  tasks_total: number
}

export interface SquadTaskStartedEvent extends SSEEvent {
  type: 'squad_task_started'
  squad_id: string
  task_id: string
  task_title: string
  persona_id?: string
  depth?: number
}

export interface SquadTaskThinkingEvent extends SSEEvent {
  type: 'squad_task_thinking'
  squad_id: string
  task_id: string
  content?: string
  depth?: number
}

export interface SquadTaskToolCallEvent extends SSEEvent {
  type: 'squad_task_tool_call'
  squad_id: string
  task_id: string
  tool?: string
  tool_name?: string
  arguments?: string | Record<string, unknown>
  depth?: number
}

export interface SquadTaskToolResultEvent extends SSEEvent {
  type: 'squad_task_tool_result'
  squad_id: string
  task_id: string
  result?: { success?: boolean; output?: string; data?: unknown; error?: string }
  depth?: number
}

export interface SquadTaskDoneEvent extends SSEEvent {
  type: 'squad_task_done'
  squad_id: string
  task_id: string
  success: boolean
  summary?: string
  artifacts?: string[]
  open_questions?: string[]
  duration_ms?: number
  error?: string
}

export interface SquadConcludedEvent extends SSEEvent {
  type: 'squad_concluded'
  squad_id: string
  duration_ms?: number
}

export interface CouncilConvenedEvent extends SSEEvent {
  type: 'council_convened'
  council_id: string
  question?: string
  snapshot_id?: string
  roles: Array<{ role_id: string; persona_id: string }>
  arbiter_persona: string
}

export interface CouncilRoleStartedEvent extends SSEEvent {
  type: 'council_role_started'
  council_id: string
  role_id: string
  persona_id: string
  depth?: number
}

export interface CouncilRoleThinkingEvent extends SSEEvent {
  type: 'council_role_thinking'
  council_id: string
  role_id: string
  content?: string
  depth?: number
}

export interface CouncilRoleToolCallEvent extends SSEEvent {
  type: 'council_role_tool_call'
  council_id: string
  role_id: string
  tool?: string
  tool_name?: string
  arguments?: string | Record<string, unknown>
  depth?: number
}

export interface CouncilRoleToolResultEvent extends SSEEvent {
  type: 'council_role_tool_result'
  council_id: string
  role_id: string
  result?: { success?: boolean; output?: string; data?: unknown; error?: string }
  depth?: number
}

export interface CouncilRoleStanceEvent extends SSEEvent {
  type: 'council_role_stance'
  council_id: string
  role_id: string
  success: boolean
  text?: string
  evidence_refs?: string[]
  open_questions?: string[]
  duration_ms?: number
  error?: string
}

export interface CouncilRoleRebutStartedEvent extends SSEEvent {
  type: 'council_role_rebut_started'
  council_id: string
  role_id: string
  persona_id: string
  depth?: number
}

export interface CouncilRoleRebutThinkingEvent extends SSEEvent {
  type: 'council_role_rebut_thinking'
  council_id: string
  role_id: string
  content?: string
  depth?: number
}

export interface CouncilRoleRebutToolCallEvent extends SSEEvent {
  type: 'council_role_rebut_tool_call'
  council_id: string
  role_id: string
  tool?: string
  tool_name?: string
  arguments?: string | Record<string, unknown>
  depth?: number
}

export interface CouncilRoleRebutToolResultEvent extends SSEEvent {
  type: 'council_role_rebut_tool_result'
  council_id: string
  role_id: string
  result?: { success?: boolean; output?: string; data?: unknown; error?: string }
  depth?: number
}

export interface CouncilRoleRebuttalEvent extends SSEEvent {
  type: 'council_role_rebuttal'
  council_id: string
  role_id: string
  success: boolean
  text?: string
  evidence_refs?: string[]
  duration_ms?: number
  error?: string
}

export interface CouncilArbiterStartedEvent extends SSEEvent {
  type: 'council_arbiter_started'
  council_id: string
  persona_id: string
  depth?: number
}

export interface CouncilArbiterThinkingEvent extends SSEEvent {
  type: 'council_arbiter_thinking'
  council_id: string
  content?: string
  depth?: number
}

export interface CouncilArbiterToolCallEvent extends SSEEvent {
  type: 'council_arbiter_tool_call'
  council_id: string
  tool?: string
  tool_name?: string
  arguments?: string | Record<string, unknown>
  depth?: number
}

export interface CouncilArbiterToolResultEvent extends SSEEvent {
  type: 'council_arbiter_tool_result'
  council_id: string
  result?: { success?: boolean; output?: string; data?: unknown; error?: string }
  depth?: number
}

export interface CouncilVerdictEvent extends SSEEvent {
  type: 'council_verdict'
  council_id: string
  verdict_type: string
  text?: string
  conflict_matrix?: Array<{ axis: string; positions: Record<string, string> }>
  minority_notes?: string
  duration_ms?: number
}

export interface CouncilConcludedEvent extends SSEEvent {
  type: 'council_concluded'
  council_id: string
  duration_ms?: number
  verdict_type?: string
}

export interface EvidenceWarningEvent extends SSEEvent {
  type: 'evidence_warning'
  snapshot_id?: string
  ref: string
  hit: string
}

export type SquadEvent =
  | SquadStartedEvent
  | SquadTaskStartedEvent
  | SquadTaskThinkingEvent
  | SquadTaskToolCallEvent
  | SquadTaskToolResultEvent
  | SquadTaskDoneEvent
  | SquadConcludedEvent

export function isSquadEvent(ev: SSEEvent): ev is SquadEvent {
  return typeof ev.type === 'string' && ev.type.startsWith('squad_')
}

export type CouncilEvent =
  | CouncilConvenedEvent
  | CouncilRoleStartedEvent
  | CouncilRoleThinkingEvent
  | CouncilRoleToolCallEvent
  | CouncilRoleToolResultEvent
  | CouncilRoleStanceEvent
  | CouncilRoleRebutStartedEvent
  | CouncilRoleRebutThinkingEvent
  | CouncilRoleRebutToolCallEvent
  | CouncilRoleRebutToolResultEvent
  | CouncilRoleRebuttalEvent
  | CouncilArbiterStartedEvent
  | CouncilArbiterThinkingEvent
  | CouncilArbiterToolCallEvent
  | CouncilArbiterToolResultEvent
  | CouncilVerdictEvent
  | CouncilConcludedEvent

export function isCouncilEvent(ev: SSEEvent): ev is CouncilEvent {
  return typeof ev.type === 'string' && ev.type.startsWith('council_')
}

export const COUNCIL_EVENT_TYPES: ReadonlySet<string> = new Set([
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

export interface ChatStreamOptions {
  projectId: string
  message: string
  agentId?: string | null

  sessionId?: string | null

  forceNew?: boolean

  attachedFiles?: Array<{ name: string; path: string; size: number; kind?: string }>
  signal?: AbortSignal

  onSessionId?: (sessionId: string) => void
  baseURL?: string
}

async function* parseSSEResponse(
  res: Response,
): AsyncGenerator<SSEEvent, void, void> {
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`SSE 启动失败 (HTTP ${res.status}): ${text || res.statusText}`)
  }
  if (!res.body) {
    throw new Error('SSE 响应体为空（浏览器不支持 ReadableStream？）')
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      let nlIdx = buffer.indexOf('\n')
      while (nlIdx >= 0) {
        const line = buffer.slice(0, nlIdx).trim()
        buffer = buffer.slice(nlIdx + 1)
        if (line.startsWith('data:')) {
          const payload = line.slice(5).trim()
          if (payload) {
            try {
              yield JSON.parse(payload) as SSEEvent
            } catch (e) {

              console.warn('SSE 解析失败：', payload, e)
            }
          }
        }
        nlIdx = buffer.indexOf('\n')
      }
    }

    const tail = buffer.trim()
    if (tail.startsWith('data:')) {
      const payload = tail.slice(5).trim()
      if (payload) {
        try {
          yield JSON.parse(payload) as SSEEvent
        } catch {

        }
      }
    }
  } finally {
    try {
      reader.releaseLock()
    } catch {

    }
  }
}

export async function* streamChat(
  opts: ChatStreamOptions,
): AsyncGenerator<SSEEvent, void, void> {
  const baseURL = opts.baseURL || '/api'
  const res = await fetch(`${baseURL}/projects/${opts.projectId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({
      message: opts.message,
      agent_id: opts.agentId ?? null,
      session_id: opts.sessionId ?? null,
      force_new: opts.forceNew ?? false,
      attached_files: opts.attachedFiles && opts.attachedFiles.length > 0 ? opts.attachedFiles : null,
    }),
    signal: opts.signal,
  })

  const earlySid = res.headers.get('X-Session-Id')
  if (earlySid && opts.onSessionId) {
    opts.onSessionId(earlySid)
  }

  yield* parseSSEResponse(res)
}

export async function* streamSessionLive(opts: {
  projectId: string
  sessionId: string
  fromSeq?: number
  signal?: AbortSignal
  baseURL?: string
}): AsyncGenerator<SSEEvent, void, void> {
  const baseURL = opts.baseURL || '/api'
  const fromSeq = opts.fromSeq ?? 0
  const url =
    `${baseURL}/projects/${opts.projectId}/sessions/${opts.sessionId}/live` +
    `?from_seq=${fromSeq}`
  const res = await fetch(url, {
    method: 'GET',
    headers: { ...authHeaders() },
    signal: opts.signal,
  })
  yield* parseSSEResponse(res)
}

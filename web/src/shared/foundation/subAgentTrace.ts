

import type { ChatEvent, ToolStep, TurnStep } from '@/application/state/chatStore'

export type TracePhase = 'stance' | 'rebut' | 'arbiter'

type BaseKind = 'thinking' | 'tool_call' | 'tool_result'

function normalizeType(t: string, phase: TracePhase): BaseKind | null {
  if (phase === 'stance') {
    if (t === 'council_role_thinking') return 'thinking'
    if (t === 'council_role_tool_call') return 'tool_call'
    if (t === 'council_role_tool_result') return 'tool_result'
    return null
  }
  if (phase === 'rebut') {
    if (t === 'council_role_rebut_thinking') return 'thinking'
    if (t === 'council_role_rebut_tool_call') return 'tool_call'
    if (t === 'council_role_rebut_tool_result') return 'tool_result'
    return null
  }

  if (t === 'council_arbiter_thinking') return 'thinking'
  if (t === 'council_arbiter_tool_call') return 'tool_call'
  if (t === 'council_arbiter_tool_result') return 'tool_result'
  return null
}

export function traceEventsToSteps(
  events: ChatEvent[] | undefined,
  phase: TracePhase,
): TurnStep[] {
  if (!events || events.length === 0) return []

  const steps: TurnStep[] = []

  for (const e of events) {
    const norm = normalizeType(String(e.raw.type), phase)
    if (!norm) continue
    const ev = e.raw

    if (norm === 'thinking') {
      const content = String(ev.content || '')
      if (!content) continue
      steps.push({ id: e.id, kind: 'thinking', content, ts: e.ts })
      continue
    }

    if (norm === 'tool_call') {
      steps.push({
        id: e.id,
        kind: 'tool',
        tool: String(ev.tool || ev.tool_name || 'tool'),
        args:
          typeof ev.arguments === 'string'
            ? ev.arguments
            : JSON.stringify(ev.arguments || {}, null, 2),
        status: 'running',
        ts: e.ts,
      })
      continue
    }

    const toolName = ev.tool ? String(ev.tool) : ''
    let idx = -1
    for (let i = steps.length - 1; i >= 0; i--) {
      const s = steps[i]
      if (
        s.kind === 'tool' &&
        s.status === 'running' &&
        (toolName ? s.tool === toolName : true)
      ) {
        idx = i
        break
      }
    }
    const merged: Partial<ToolStep> = {
      status: ev.success === false ? 'failed' : 'success',
      output: ev.output as string | undefined,
      error: ev.error as string | undefined,
      durationMs: Number(ev.duration_ms || 0) || undefined,
      data: ev.data,
      truncated: Boolean(ev.truncated),
      fullLength: Number(ev.full_length || 0) || undefined,
    }
    if (idx >= 0) {
      steps[idx] = { ...(steps[idx] as ToolStep), ...merged }
    } else {
      steps.push({
        id: e.id,
        kind: 'tool',
        tool: toolName || 'tool',
        args: '',
        status: merged.status as ToolStep['status'],
        output: merged.output,
        error: merged.error,
        durationMs: merged.durationMs,
        data: merged.data,
        ts: e.ts,
      })
    }
  }

  const out: TurnStep[] = []
  for (const s of steps) {
    const last = out[out.length - 1]
    if (
      s.kind === 'thinking' &&
      last &&
      last.kind === 'thinking' &&
      last.content === s.content
    ) {
      continue
    }
    out.push(s)
  }
  return out
}

export function hasTraceForPhase(
  events: ChatEvent[] | undefined,
  phase: TracePhase,
): boolean {
  if (!events) return false
  return events.some((e) => normalizeType(String(e.raw.type), phase) !== null)
}

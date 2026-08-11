

import { useMemo } from 'react'

import type { ChatEvent } from '@/application/state/chatStore'
import { COUNCIL_EVENT_TYPES } from '@/client/services/sse'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/ui/widgets/ui/tooltip'
import { cn } from '@/shared/foundation/utils'
import { personaIcon, personaName } from '@/shared/foundation/personas'

interface Props {
  events: ChatEvent[]
}

interface TypeMeta {
  label: string

  pillClass: string
  borderClass: string
  bgClass: string
}

const TYPE_META: Record<string, TypeMeta> = {
  thinking: {
    label: '思考',
    pillClass: 'bg-slate-500 text-white',
    borderClass: 'border-l-slate-500',
    bgClass: 'bg-slate-500/[0.06]',
  },
  tool_call: {
    label: '工具调用',
    pillClass: 'bg-amber-500 text-white',
    borderClass: 'border-l-amber-500',
    bgClass: 'bg-amber-500/[0.08]',
  },
  tool_result: {
    label: '工具结果',
    pillClass: 'bg-cyan-600 text-white',
    borderClass: 'border-l-cyan-600',
    bgClass: 'bg-cyan-600/[0.08]',
  },
  message: {
    label: '回复',
    pillClass: 'bg-emerald-600 text-white',
    borderClass: 'border-l-emerald-600',
    bgClass: 'bg-emerald-600/[0.08]',
  },
  message_delta: {
    label: '回复增量',
    pillClass: 'bg-emerald-500 text-white',
    borderClass: 'border-l-emerald-500',
    bgClass: 'bg-emerald-500/[0.05]',
  },
  delegate_start: {
    label: '委派',
    pillClass: 'bg-violet-600 text-white',
    borderClass: 'border-l-violet-600',
    bgClass: 'bg-violet-600/[0.08]',
  },
  delegate_result: {
    label: '委派结果',
    pillClass: 'bg-violet-500 text-white',
    borderClass: 'border-l-violet-500',
    bgClass: 'bg-violet-500/[0.06]',
  },
  ask_user_pending: {
    label: '等待用户',
    pillClass: 'bg-red-500 text-white',
    borderClass: 'border-l-red-500',
    bgClass: 'bg-red-500/[0.08]',
  },
  usage: {
    label: 'token 用量',
    pillClass: 'bg-primary text-primary-foreground',
    borderClass: 'border-l-primary',
    bgClass: 'bg-primary/[0.06]',
  },
  error: {
    label: '错误',
    pillClass: 'bg-destructive text-destructive-foreground',
    borderClass: 'border-l-destructive',
    bgClass: 'bg-destructive/[0.10]',
  },
  done: {
    label: '完成',
    pillClass: 'bg-emerald-600 text-white',
    borderClass: 'border-l-emerald-600',
    bgClass: 'bg-emerald-600/[0.10]',
  },
  system: {
    label: '系统',
    pillClass: 'bg-slate-400 text-white',
    borderClass: 'border-l-slate-400',
    bgClass: 'bg-slate-400/[0.06]',
  },

  squad_started: {
    label: '小队启动',
    pillClass: 'bg-purple-700 text-white',
    borderClass: 'border-l-purple-700',
    bgClass: 'bg-purple-700/[0.10]',
  },
  squad_task_started: {
    label: '子任务·开始',
    pillClass: 'bg-purple-500 text-white',
    borderClass: 'border-l-purple-500',
    bgClass: 'bg-purple-500/[0.07]',
  },
  squad_task_thinking: {
    label: '子任务·思考',
    pillClass: 'bg-purple-400 text-white',
    borderClass: 'border-l-purple-400',
    bgClass: 'bg-purple-400/[0.05]',
  },
  squad_task_tool_call: {
    label: '子任务·工具',
    pillClass: 'bg-purple-500 text-white',
    borderClass: 'border-l-purple-500',
    bgClass: 'bg-purple-500/[0.06]',
  },
  squad_task_tool_result: {
    label: '子任务·结果',
    pillClass: 'bg-purple-600 text-white',
    borderClass: 'border-l-purple-600',
    bgClass: 'bg-purple-600/[0.06]',
  },
  squad_task_done: {
    label: '子任务·完成',
    pillClass: 'bg-purple-600 text-white',
    borderClass: 'border-l-purple-600',
    bgClass: 'bg-purple-600/[0.08]',
  },
  squad_concluded: {
    label: '小队收口',
    pillClass: 'bg-purple-800 text-white',
    borderClass: 'border-l-purple-800',
    bgClass: 'bg-purple-800/[0.10]',
  },

  council_convened: {
    label: '议会召开',
    pillClass: 'bg-indigo-700 text-white',
    borderClass: 'border-l-indigo-700',
    bgClass: 'bg-indigo-700/[0.10]',
  },
  council_role_started: {
    label: '角色·开始',
    pillClass: 'bg-indigo-500 text-white',
    borderClass: 'border-l-indigo-500',
    bgClass: 'bg-indigo-500/[0.07]',
  },
  council_role_thinking: {
    label: '角色·思考',
    pillClass: 'bg-indigo-400 text-white',
    borderClass: 'border-l-indigo-400',
    bgClass: 'bg-indigo-400/[0.05]',
  },
  council_role_tool_call: {
    label: '角色·工具',
    pillClass: 'bg-indigo-500 text-white',
    borderClass: 'border-l-indigo-500',
    bgClass: 'bg-indigo-500/[0.06]',
  },
  council_role_tool_result: {
    label: '角色·结果',
    pillClass: 'bg-indigo-600 text-white',
    borderClass: 'border-l-indigo-600',
    bgClass: 'bg-indigo-600/[0.06]',
  },
  council_role_stance: {
    label: '角色表态',
    pillClass: 'bg-indigo-600 text-white',
    borderClass: 'border-l-indigo-600',
    bgClass: 'bg-indigo-600/[0.08]',
  },

  council_role_rebut_started: {
    label: '反驳·开始',
    pillClass: 'bg-sky-500 text-white',
    borderClass: 'border-l-sky-500',
    bgClass: 'bg-sky-500/[0.07]',
  },
  council_role_rebut_thinking: {
    label: '反驳·思考',
    pillClass: 'bg-sky-400 text-white',
    borderClass: 'border-l-sky-400',
    bgClass: 'bg-sky-400/[0.05]',
  },
  council_role_rebut_tool_call: {
    label: '反驳·工具',
    pillClass: 'bg-sky-500 text-white',
    borderClass: 'border-l-sky-500',
    bgClass: 'bg-sky-500/[0.06]',
  },
  council_role_rebut_tool_result: {
    label: '反驳·结果',
    pillClass: 'bg-sky-600 text-white',
    borderClass: 'border-l-sky-600',
    bgClass: 'bg-sky-600/[0.06]',
  },
  council_role_rebuttal: {
    label: '反驳意见',
    pillClass: 'bg-sky-600 text-white',
    borderClass: 'border-l-sky-600',
    bgClass: 'bg-sky-600/[0.08]',
  },

  council_arbiter_started: {
    label: '仲裁·开始',
    pillClass: 'bg-indigo-700 text-white',
    borderClass: 'border-l-indigo-700',
    bgClass: 'bg-indigo-700/[0.08]',
  },
  council_arbiter_thinking: {
    label: '仲裁·思考',
    pillClass: 'bg-indigo-600 text-white',
    borderClass: 'border-l-indigo-600',
    bgClass: 'bg-indigo-600/[0.06]',
  },
  council_arbiter_tool_call: {
    label: '仲裁·工具',
    pillClass: 'bg-indigo-700 text-white',
    borderClass: 'border-l-indigo-700',
    bgClass: 'bg-indigo-700/[0.07]',
  },
  council_arbiter_tool_result: {
    label: '仲裁·结果',
    pillClass: 'bg-indigo-700 text-white',
    borderClass: 'border-l-indigo-700',
    bgClass: 'bg-indigo-700/[0.07]',
  },
  council_verdict: {
    label: '裁决',
    pillClass: 'bg-indigo-900 text-white',
    borderClass: 'border-l-indigo-900',
    bgClass: 'bg-indigo-900/[0.10]',
  },
  council_concluded: {
    label: '议会收口',
    pillClass: 'bg-indigo-800 text-white',
    borderClass: 'border-l-indigo-800',
    bgClass: 'bg-indigo-800/[0.10]',
  },

  evidence_warning: {
    label: '事实告警',
    pillClass: 'bg-amber-600 text-white',
    borderClass: 'border-l-amber-600',
    bgClass: 'bg-amber-600/[0.08]',
  },
}

function metaOf(type: string): TypeMeta {
  return (
    TYPE_META[type] || {
      label: type,
      pillClass: 'bg-slate-600 text-white',
      borderClass: 'border-l-slate-600',
      bgClass: 'bg-slate-600/[0.06]',
    }
  )
}

function fmtTime(ts: number, startTs?: number): string {
  if (startTs) {
    const ms = ts - startTs
    if (ms < 1000) return `+${ms}ms`
    return `+${(ms / 1000).toFixed(1)}s`
  }
  return new Date(ts).toLocaleTimeString('zh-CN', { hour12: false })
}

function personaTag(personaId?: string): string {
  if (!personaId) return ''
  return `${personaIcon(personaId)} ${personaName(personaId)}`
}

function previewOf(ev: ChatEvent): string {
  const raw = ev.raw as any
  const t = String(raw.type || '')

  if (t === 'squad_started') {
    const total = raw.tasks_total ?? raw.tasks?.length ?? '?'
    return `${raw.title || '小队'} · ${total} 子任务 · snapshot=${raw.snapshot_id || '?'}`
  }
  if (t === 'squad_task_started') {
    const ptag = raw.persona_id ? ` · ${personaTag(raw.persona_id)}` : ''
    return `[${raw.task_id || '?'}] ${raw.task_title || ''}${ptag}`
  }
  if (t === 'squad_task_thinking') {
    return `[${raw.task_id || '?'}] ${String(raw.content || '').slice(0, 100)}`
  }
  if (t === 'squad_task_tool_call') {
    return `[${raw.task_id || '?'}] ${raw.tool || 'tool'}()`
  }
  if (t === 'squad_task_tool_result') {
    const ok = raw.success
    const out = raw.output || raw.error || ''
    return `[${raw.task_id || '?'}] ${ok === false ? '✗ ' : '✓ '}${String(out).slice(0, 90)}`
  }
  if (t === 'squad_task_done') {
    return `[${raw.task_id || '?'}] ${raw.success === false ? '✗ ' : '✓ '}${String(raw.summary || raw.error || '').slice(0, 100)}`
  }
  if (t === 'squad_concluded') {
    return `小队完成 · ${raw.duration_ms || 0}ms`
  }

  if (t === 'council_convened') {
    const roleCount = Array.isArray(raw.roles) ? raw.roles.length : '?'
    return `议会召开 · ${roleCount} 角色 · 仲裁=${personaTag(raw.arbiter_persona) || '?'}`
  }
  if (t === 'council_role_started' || t === 'council_role_rebut_started') {
    return `[${raw.role_id || '?'}] ${personaTag(raw.persona_id)}`
  }
  if (
    t === 'council_role_thinking' ||
    t === 'council_role_rebut_thinking' ||
    t === 'council_arbiter_thinking'
  ) {
    return `${t.includes('arbiter') ? '[仲裁]' : `[${raw.role_id || '?'}]`} ${String(raw.content || '').slice(0, 100)}`
  }
  if (
    t === 'council_role_tool_call' ||
    t === 'council_role_rebut_tool_call' ||
    t === 'council_arbiter_tool_call'
  ) {
    return `${t.includes('arbiter') ? '[仲裁]' : `[${raw.role_id || '?'}]`} ${raw.tool || 'tool'}()`
  }
  if (
    t === 'council_role_tool_result' ||
    t === 'council_role_rebut_tool_result' ||
    t === 'council_arbiter_tool_result'
  ) {
    const ok = raw.success
    const out = raw.output || raw.error || ''
    const tag = t.includes('arbiter') ? '[仲裁]' : `[${raw.role_id || '?'}]`
    return `${tag} ${ok === false ? '✗ ' : '✓ '}${String(out).slice(0, 90)}`
  }
  if (t === 'council_role_stance') {
    return `[${raw.role_id || '?'}] ${String(raw.stance_text || '').slice(0, 100)}`
  }
  if (t === 'council_role_rebuttal') {
    return `[${raw.role_id || '?'}] ${String(raw.rebuttal_text || raw.text || '').slice(0, 100)}`
  }
  if (t === 'council_arbiter_started') {
    return `仲裁开始 · ${personaTag(raw.arbiter_persona)}`
  }
  if (t === 'council_verdict') {
    return `裁决=${raw.verdict_type || '?'} · ${String(raw.text || '').slice(0, 90)}`
  }
  if (t === 'council_concluded') {
    return `议会收口 · ${raw.duration_ms || 0}ms`
  }
  if (t === 'evidence_warning') {
    return `${raw.snapshot_id || '?'} · ref=${raw.ref || ''} · ${String(raw.hit || '').slice(0, 80)}`
  }

  if (t === 'tool_call') {
    const args =
      typeof raw.arguments === 'string'
        ? raw.arguments
        : JSON.stringify(raw.arguments || {}, null, 0)
    return `${raw.tool || raw.tool_name || 'tool'}(${args.slice(0, 80)})`
  }
  if (t === 'tool_result') {
    const out = raw.result?.output || raw.result?.error || ''
    const ok = raw.result?.success
    return `${ok === false ? '✗ ' : '✓ '}${String(out).slice(0, 120)}`
  }
  if (t === 'thinking') return String(raw.content || '').slice(0, 120)
  if (t === 'message' || t === 'message_delta')
    return String(raw.content || raw.delta || '').slice(0, 100)
  if (t === 'ask_user_pending')
    return `Q: ${String(raw.question || '').slice(0, 100)}`
  if (t === 'usage')
    return `in=${raw.input_tokens || 0} out=${raw.output_tokens || 0} model=${raw.model || '?'}`
  if (t === 'error') return String(raw.content || raw.error || '')
  if (t === 'done') return '本轮任务结束'
  return JSON.stringify(raw).slice(0, 100)
}

export default function EventTimeline({ events }: Props) {
  const startTs = events[0]?.ts

  const rows = useMemo(() => {
    return events.map((ev) => {
      const meta = metaOf(String(ev.raw.type || 'unknown'))
      return { ev, meta, preview: previewOf(ev), depth: Number(ev.raw.depth || 0) }
    })
  }, [events])

  if (events.length === 0) {
    return (
      <p className="px-2 py-3 text-xs text-muted-foreground">
        发送消息后，这里会实时显示推理事件链。
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-1">
      {rows.map(({ ev, meta, preview, depth }) => (
        <Tooltip key={ev.id} delayDuration={300}>
          <TooltipTrigger asChild>
            <div
              className={cn(
                'cursor-help rounded-r-md border-l-[3px] px-2 py-1.5',
                meta.borderClass,
                meta.bgClass,
              )}
              style={{ marginLeft: `${Math.min(depth, 4) * 12}px` }}
            >
              <div className="mb-0.5 flex items-center gap-1.5">
                <span
                  className={cn(
                    'inline-flex h-[18px] items-center rounded px-1.5 text-[10.5px] font-medium',
                    meta.pillClass,
                  )}
                >
                  {meta.label}
                </span>
                {ev.raw.agent_id && (
                  <span className="text-[11px] text-muted-foreground">
                    {String(ev.raw.agent_id)}
                  </span>
                )}
                <span className="ml-auto text-[11px] text-muted-foreground">
                  {fmtTime(ev.ts, startTs)}
                </span>
              </div>
              <div className="break-all font-mono text-[11.5px] leading-relaxed text-foreground">
                {preview}
              </div>
            </div>
          </TooltipTrigger>
          <TooltipContent side="left" className="max-w-[480px] p-2">
            <pre className="m-0 max-h-60 overflow-auto whitespace-pre-wrap text-[10.5px]">
              {JSON.stringify(ev.raw, null, 2)}
            </pre>
          </TooltipContent>
        </Tooltip>
      ))}
    </div>
  )
}

if (import.meta.env?.DEV) {
  const SQUAD_EVENT_TYPES = [
    'squad_started',
    'squad_task_started',
    'squad_task_thinking',
    'squad_task_tool_call',
    'squad_task_tool_result',
    'squad_task_done',
    'squad_concluded',
  ] as const
  const missing: string[] = []
  for (const t of SQUAD_EVENT_TYPES) {
    if (!(t in TYPE_META)) missing.push(t)
  }
  for (const t of COUNCIL_EVENT_TYPES) {
    if (!(t in TYPE_META)) missing.push(t)
  }
  if (!('evidence_warning' in TYPE_META)) missing.push('evidence_warning')
  if (missing.length) {

    console.warn(
      '[EventTimeline] P4.2 配色缺失：以下事件类型在 TYPE_META 中未登记，' +
        '会回落到默认 slate 配色：',
      missing,
    )
  }
}

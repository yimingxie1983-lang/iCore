

import { Brain, ChevronRight, Loader2, Send, Wrench, XCircle, CheckCircle2 } from 'lucide-react'

import { cn } from '@/shared/foundation/utils'
import { personaColorClasses, personaIcon, personaName } from '@/shared/foundation/personas'

export type LaneStatus = 'pending' | 'running' | 'success' | 'failed'

export interface AgentLaneProps {

  personaId?: string

  title?: string
  status: LaneStatus

  progress?: string

  progressKind?: 'thinking' | 'tool_call' | 'tool_result'

  summary?: string

  error?: string

  tokensIn?: number
  tokensOut?: number
  durationMs?: number

  onOpenTrace?: () => void

  className?: string
}

function fmtDuration(ms?: number): string {
  if (!ms || ms <= 0) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function fmtTokens(n?: number): string {
  if (n == null) return '—'
  if (n < 1000) return String(n)
  if (n < 10_000) return `${(n / 1000).toFixed(1)}k`
  return `${Math.round(n / 1000)}k`
}

function ProgressIcon({ kind }: { kind?: AgentLaneProps['progressKind'] }) {
  if (kind === 'thinking') return <Brain className="h-3 w-3 shrink-0" />
  if (kind === 'tool_call') return <Wrench className="h-3 w-3 shrink-0" />
  if (kind === 'tool_result') return <Send className="h-3 w-3 shrink-0" />
  return null
}

function StatusBadge({ status, color }: { status: LaneStatus; color: { dot: string } }) {
  if (status === 'pending') {
    return (
      <span className="inline-flex items-center gap-1 text-[10.5px] text-muted-foreground/80">
        <span className={cn('h-1.5 w-1.5 rounded-full bg-muted-foreground/60')} />
        排队
      </span>
    )
  }
  if (status === 'running') {
    return (
      <span className="inline-flex items-center gap-1 text-[10.5px] text-secondary">
        <Loader2 className="h-3 w-3 animate-spin" />
        进行中
      </span>
    )
  }
  if (status === 'success') {
    return (
      <span className="inline-flex items-center gap-1 text-[10.5px] text-emerald-700 dark:text-emerald-400">
        <CheckCircle2 className="h-3 w-3" />
        完成
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10.5px] text-destructive">
      <XCircle className="h-3 w-3" />
      失败
    </span>
  )
}

function ProgressBar({ status, color }: { status: LaneStatus; color: { dot: string } }) {
  return (
    <div className="h-[3px] w-full overflow-hidden rounded-full bg-muted/60">
      {status === 'running' ? (
        <div
          className={cn('h-full w-1/3 animate-pulse rounded-full', color.dot)}
          aria-hidden
        />
      ) : status === 'success' ? (
        <div className="h-full w-full rounded-full bg-emerald-500" aria-hidden />
      ) : status === 'failed' ? (
        <div className="h-full w-full rounded-full bg-destructive" aria-hidden />
      ) : (
        <div className="h-full w-1/4 rounded-full bg-muted-foreground/40" aria-hidden />
      )}
    </div>
  )
}

export function AgentLane({
  personaId,
  title,
  status,
  progress,
  progressKind,
  summary,
  error,
  tokensIn,
  tokensOut,
  durationMs,
  onOpenTrace,
  className,
}: AgentLaneProps) {
  const color = personaColorClasses(personaId)
  const isRunning = status === 'running' || status === 'pending'
  const isFailed = status === 'failed'

  let body: React.ReactNode = null
  if (isRunning) {
    if (progress) {
      body = (
        <span className="inline-flex items-start gap-1 text-[11.5px] leading-relaxed text-muted-foreground">
          <span className="mt-[2px]">
            <ProgressIcon kind={progressKind} />
          </span>
          <span className="line-clamp-2 font-mono">{progress}</span>
        </span>
      )
    } else {
      body = (
        <span className="inline-flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          {status === 'pending' ? '排队中…' : '启动中…'}
        </span>
      )
    }
  } else if (isFailed) {
    body = (
      <span className="inline-flex items-start gap-1 text-[11.5px] leading-relaxed text-destructive">
        <XCircle className="mt-[2px] h-3 w-3 shrink-0" />
        <span className="line-clamp-2 font-mono">{error || '失败'}</span>
      </span>
    )
  } else {
    body = (
      <span className="line-clamp-2 text-[11.5px] leading-relaxed text-foreground/85">
        {summary || '已完成（无摘要）'}
      </span>
    )
  }

  const interactive = !!onOpenTrace

  return (
    <div
      className={cn(
        'group flex flex-col gap-1.5 rounded-md border bg-card px-3 py-2 transition-colors',
        isFailed
          ? 'border-destructive/40'
          : isRunning
            ? cn(color.border, 'bg-card-muted/40')
            : 'border-border',
        interactive &&
          'cursor-pointer hover:border-foreground/30 hover:bg-card-muted/60',
        className,
      )}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={interactive ? onOpenTrace : undefined}
      onKeyDown={(e) => {
        if (!interactive) return
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpenTrace?.()
        }
      }}
    >
      {}
      <div className="flex items-center gap-1.5">
        <span className="shrink-0 text-[13px] leading-none" aria-hidden>
          {personaIcon(personaId)}
        </span>
        <span
          title={personaId}
          className={cn('shrink-0 text-[11.5px] font-medium', color.text)}
        >
          {personaName(personaId) || '默认人格'}
        </span>
        {title && (
          <span className="line-clamp-1 text-[11px] text-muted-foreground">
            · {title}
          </span>
        )}
        <span className="ml-auto" />
        <StatusBadge status={status} color={color} />
        {interactive && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onOpenTrace?.()
            }}
            title="查看完整 trace"
            aria-label="查看完整 trace"
            className="rounded p-0.5 text-muted-foreground/60 hover:bg-muted/60 hover:text-foreground"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {}
      <div className="min-h-[16px]">{body}</div>

      {}
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <ProgressBar status={status} color={color} />
        </div>
        <span className="shrink-0 font-mono text-[10px] text-muted-foreground/80">
          in {fmtTokens(tokensIn)} / out {fmtTokens(tokensOut)}
        </span>
        {durationMs ? (
          <span className="shrink-0 font-mono text-[10px] text-muted-foreground/80">
            {fmtDuration(durationMs)}
          </span>
        ) : null}
      </div>
    </div>
  )
}

export default AgentLane

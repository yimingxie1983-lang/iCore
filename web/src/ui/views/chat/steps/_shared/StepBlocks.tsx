

import { useState } from 'react'
import {
  AlertCircle,
  Brain,
  CheckCircle2,
  ChevronRight,
  Info,
  Lightbulb,
  Loader2,
  TriangleAlert,
  Wrench,
  XCircle,
} from 'lucide-react'

import { cn } from '@/shared/foundation/utils'
import TypewriterMarkdown from '@/ui/widgets/common/TypewriterMarkdown'
import type {
  NoticeStep,
  PretextStep,
  ThinkingStep,
  ToolStep,
} from '@/application/state/chatStore'

export function fmtDuration(ms?: number): string {
  if (!ms || ms <= 0) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function fmtBytes(n?: number): string {
  if (!n || n <= 0) return ''
  if (n < 1024) return `${n}B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`
  return `${(n / 1024 / 1024).toFixed(1)}MB`
}

const THINKING_FOLD_THRESHOLD_CHARS = 220
const THINKING_FOLD_THRESHOLD_LINES = 3

export function ThinkingBlock({ step }: { step: ThinkingStep }) {
  const text = step.content || ''
  const lines = text.split('\n').length
  const tooLong =
    text.length > THINKING_FOLD_THRESHOLD_CHARS ||
    lines > THINKING_FOLD_THRESHOLD_LINES
  const [collapsed, setCollapsed] = useState(false)
  const showFold = tooLong

  return (
    <div className="px-1">
      <button
        type="button"
        onClick={showFold ? () => setCollapsed((v) => !v) : undefined}
        className={cn(
          'flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-wider text-muted-foreground/80',
          showFold && 'cursor-pointer hover:text-muted-foreground',
        )}
      >
        <Brain className="h-3 w-3 shrink-0" />
        <span>思考</span>
        {step.agent && (
          <span className="font-mono text-[11px] font-normal normal-case tracking-normal text-muted-foreground/70">
            · {step.agent}
          </span>
        )}
        {showFold && (
          <ChevronRight
            className={cn(
              'h-3 w-3 shrink-0 transition-transform',
              !collapsed && 'rotate-90',
            )}
          />
        )}
      </button>

      {!collapsed && (
        <div className="ml-1.5 mt-1 border-l border-border/80 pl-[18px]">
          <div className="whitespace-pre-wrap break-words font-mono text-[12.5px] leading-relaxed text-muted-foreground">
            {text}
            {step.streaming && (
              <span
                className="ml-0.5 inline-block h-[1em] w-[2px] align-text-bottom bg-muted-foreground animate-stream-cursor"
                aria-hidden
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export function PretextBlock({
  step,
  streaming,
}: {
  step: PretextStep
  streaming?: boolean
}) {
  const text = step.content || ''
  if (!text) return null
  const linkedCount = step.toolCallIds?.length || 0

  return (
    <div className="px-1">
      <div className="flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-wider text-secondary/90">
        <Lightbulb className="h-3 w-3 shrink-0" />
        <span>Thought</span>
        {linkedCount > 0 && (
          <span className="font-mono text-[10.5px] font-normal normal-case tracking-normal text-muted-foreground/70">
            · 关联 {linkedCount} 个工具
          </span>
        )}
      </div>
      <div className="ml-1.5 mt-1 max-h-[280px] overflow-auto border-l-2 border-secondary/40 pl-[18px]">
        <TypewriterMarkdown text={text} streaming={streaming} compact />
      </div>
    </div>
  )
}

function ToolStatusBadge({ status }: { status: ToolStep['status'] }) {
  if (status === 'running') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-secondary/[0.08] px-1.5 py-[1px] text-[10.5px] font-medium text-secondary">
        <Loader2 className="h-3 w-3 animate-spin" />
        执行中
      </span>
    )
  }
  if (status === 'success') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/[0.10] px-1.5 py-[1px] text-[10.5px] font-medium text-emerald-700 dark:text-emerald-400">
        <CheckCircle2 className="h-3 w-3" />
        成功
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-destructive/[0.10] px-1.5 py-[1px] text-[10.5px] font-medium text-destructive">
      <XCircle className="h-3 w-3" />
      失败
    </span>
  )
}

export function ToolStepCard({ step }: { step: ToolStep }) {
  const [open, setOpen] = useState<boolean>(step.status === 'failed')

  const args = step.args || ''
  const hasArgs = args && args !== '{}' && args !== '""'
  const hasOutput = !!(step.output || step.error)

  return (
    <div
      className={cn(
        'rounded-md border bg-card-muted/60 transition-colors',
        step.status === 'failed'
          ? 'border-destructive/40'
          : step.status === 'running'
            ? 'border-secondary/40'
            : 'border-border',
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex h-8 w-full items-center gap-2 px-3 text-left"
      >
        <ChevronRight
          className={cn(
            'h-3 w-3 shrink-0 text-muted-foreground transition-transform',
            open && 'rotate-90',
          )}
        />
        <Wrench className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="font-mono text-[12px] font-medium text-foreground">
          {step.tool}
        </span>
        <ToolStatusBadge status={step.status} />
        <span className="flex-1" />
        {step.durationMs ? (
          <span className="shrink-0 font-mono text-[10.5px] text-muted-foreground">
            {fmtDuration(step.durationMs)}
          </span>
        ) : null}
      </button>

      {open && (
        <div className="space-y-2 border-t border-border/70 px-3 py-2.5">
          {hasArgs && (
            <div>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                参数
              </div>
              <pre className="max-h-40 overflow-auto rounded bg-muted/60 px-2 py-1.5 font-mono text-[11.5px] leading-relaxed text-muted-foreground">
                {args}
              </pre>
            </div>
          )}
          {hasOutput && (
            <div>
              <div className="mb-1 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {step.status === 'failed' ? '错误' : '输出'}
                {step.truncated && step.fullLength ? (
                  <span className="font-mono text-[10px] font-normal normal-case tracking-normal text-muted-foreground/80">
                    （截断 · 全长 {fmtBytes(step.fullLength)}）
                  </span>
                ) : null}
              </div>
              <pre
                className={cn(
                  'max-h-72 overflow-auto rounded px-2 py-1.5 font-mono text-[11.5px] leading-relaxed',
                  step.status === 'failed'
                    ? 'max-h-60 bg-destructive/[0.08] text-destructive'
                    : 'bg-muted/60 text-foreground',
                )}
              >
                {step.error || step.output}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function NoticeRow({ step }: { step: NoticeStep }) {
  const Icon = step.level === 'error' || step.level === 'warn' ? TriangleAlert : Info
  const tone =
    step.level === 'error'
      ? 'text-destructive'
      : step.level === 'warn'
        ? 'text-amber-600 dark:text-amber-400'
        : 'text-muted-foreground'
  return (
    <div className={cn('flex items-start gap-1.5 px-1 text-[11.5px]', tone)}>
      <Icon className="mt-0.5 h-3 w-3 shrink-0" />
      <span className="leading-relaxed">{step.content}</span>
    </div>
  )
}

export function ErrorBlock({ content }: { content: string }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/[0.06] px-3 py-2 text-[12px] text-destructive">
      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>{content}</span>
    </div>
  )
}

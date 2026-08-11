

import { useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Loader2,
  ListChecks,
  ScrollText,
  Users,
  XCircle,
} from 'lucide-react'

import { cn } from '@/shared/foundation/utils'
import { useChatStore, type SquadStep, type SquadTaskState } from '@/application/state/chatStore'
import { AgentLane } from './_shared/AgentLane'

function fmtDuration(ms?: number): string {
  if (!ms || ms <= 0) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function StepStatusBadge({ status }: { status: SquadStep['status'] }) {
  if (status === 'running') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-secondary/[0.08] px-1.5 py-[1px] text-[10.5px] font-medium text-secondary">
        <Loader2 className="h-3 w-3 animate-spin" />
        派发中
      </span>
    )
  }
  if (status === 'success') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/[0.10] px-1.5 py-[1px] text-[10.5px] font-medium text-emerald-700 dark:text-emerald-400">
        <CheckCircle2 className="h-3 w-3" />
        完成
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

function laneStatusOf(status: SquadTaskState['status']) {

  return status
}

function EvidenceWarningsPanel({
  warnings,
}: {
  warnings: SquadStep['evidenceWarnings']
}) {
  const [open, setOpen] = useState(false)
  if (!warnings || warnings.length === 0) return null

  return (
    <div className="rounded-md border border-amber-500/30 bg-amber-500/[0.06] px-2.5 py-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 text-left text-[11.5px] font-medium text-amber-700 dark:text-amber-400"
      >
        <ChevronRight
          className={cn(
            'h-3 w-3 shrink-0 transition-transform',
            open && 'rotate-90',
          )}
        />
        <AlertTriangle className="h-3 w-3 shrink-0" />
        <span>事实卷宗 · {warnings.length} 条主观警告（L3 启发式命中）</span>
      </button>
      {open && (
        <ul className="ml-4 mt-1 space-y-0.5 text-[11px] text-muted-foreground">
          {warnings.map((w, i) => (
            <li key={`${w.ref}-${i}`} className="flex items-start gap-1.5">
              <code className="shrink-0 rounded bg-muted/60 px-1 py-px font-mono text-[10px]">
                {w.ref}
              </code>
              <span className="flex-1 font-mono">命中："{w.hit}"</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function SquadCard({ step }: { step: SquadStep }) {
  const total = step.tasks.length
  const doneCount = step.tasks.filter(
    (t) => t.status === 'success' || t.status === 'failed',
  ).length
  const failedCount = step.tasks.filter((t) => t.status === 'failed').length

  const openTraceDrawer = useChatStore((s) => s.openTraceDrawer)

  const allOpenQuestions: string[] = []
  if (step.status !== 'running') {
    for (const t of step.tasks) {
      if (t.openQuestions && t.openQuestions.length > 0) {
        for (const q of t.openQuestions) {
          if (q && !allOpenQuestions.includes(q)) allOpenQuestions.push(q)
        }
      }
    }
  }
  const [openQAExpanded, setOpenQAExpanded] = useState(false)

  return (
    <div className="rounded-md border border-border bg-card-muted/60">
      {}
      <div className="flex items-center gap-2 border-b border-border/70 px-3 py-2">
        <Users className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="text-[12px] font-semibold text-foreground">
          并行小队
        </span>
        {step.title && (
          <span className="line-clamp-1 text-[12px] text-muted-foreground">
            · {step.title}
          </span>
        )}
        {step.snapshotId && (
          <code
            title={`snapshot_id=${step.snapshotId}`}
            className="hidden shrink-0 rounded bg-muted/60 px-1 py-px font-mono text-[10px] text-muted-foreground/80 sm:inline-block"
          >
            snap:{step.snapshotId.slice(0, 8)}
          </code>
        )}
        <span className="ml-auto" />
        <span className="shrink-0 font-mono text-[10.5px] text-muted-foreground">
          {doneCount}/{total} 完成
          {failedCount > 0 && (
            <span className="ml-1 text-destructive">· {failedCount} 失败</span>
          )}
        </span>
        {step.durationMs ? (
          <span className="shrink-0 font-mono text-[10.5px] text-muted-foreground">
            {fmtDuration(step.durationMs)}
          </span>
        ) : null}
        <StepStatusBadge status={step.status} />
      </div>

      {}
      {step.evidenceWarnings && step.evidenceWarnings.length > 0 && (
        <div className="border-b border-border/70 px-3 py-2">
          <EvidenceWarningsPanel warnings={step.evidenceWarnings} />
        </div>
      )}

      {}
      <div className="px-3 py-2">
        {total === 0 ? (
          <div className="flex items-center gap-2 py-2 text-[11.5px] text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span>等待子任务启动…</span>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {step.tasks.map((task) => (
              <AgentLane
                key={task.taskId}
                personaId={task.personaId}
                title={task.title}
                status={laneStatusOf(task.status)}
                progress={task.progress}
                progressKind={task.progressKind}
                summary={task.summary}
                error={task.error}
                tokensIn={task.tokensIn}
                tokensOut={task.tokensOut}
                durationMs={task.durationMs}
                onOpenTrace={() =>
                  openTraceDrawer({
                    stepId: step.id,
                    laneId: task.taskId,
                    kind: 'squad',
                  })
                }
              />
            ))}
          </div>
        )}
      </div>

      {}
      {allOpenQuestions.length > 0 && (
        <div className="border-t border-border/70 px-3 py-2">
          <button
            type="button"
            onClick={() => setOpenQAExpanded((v) => !v)}
            className="flex w-full items-center gap-1.5 text-left text-[11.5px] font-medium text-muted-foreground hover:text-foreground"
          >
            <ChevronDown
              className={cn(
                'h-3 w-3 shrink-0 transition-transform',
                !openQAExpanded && '-rotate-90',
              )}
            />
            <ListChecks className="h-3 w-3 shrink-0" />
            <span>子任务遗留问题 · {allOpenQuestions.length} 条</span>
          </button>
          {openQAExpanded && (
            <ul className="ml-4 mt-1 space-y-0.5 text-[11.5px] text-muted-foreground">
              {allOpenQuestions.map((q, i) => (
                <li key={`${i}-${q.slice(0, 20)}`} className="flex items-start gap-1.5">
                  <ScrollText className="mt-0.5 h-3 w-3 shrink-0" />
                  <span className="leading-relaxed">{q}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

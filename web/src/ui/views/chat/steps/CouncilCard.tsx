

import { useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Gavel,
  Loader2,
  Scale,
  ShieldAlert,
  XCircle,
} from 'lucide-react'

import MarkdownRenderer from '@/ui/widgets/common/MarkdownRenderer'
import TypewriterMarkdown from '@/ui/widgets/common/TypewriterMarkdown'
import ConflictMatrix from './_shared/ConflictMatrix'
import { AgentLane } from './_shared/AgentLane'
import RebutTheater from './_shared/RebutTheater'
import SubAgentReasoning from './_shared/SubAgentReasoning'
import { cn } from '@/shared/foundation/utils'
import { personaIcon, personaName } from '@/shared/foundation/personas'
import {
  useChatStore,
  type CouncilRoleState,
  type CouncilStep,
  type CouncilVerdictState,
} from '@/application/state/chatStore'

function fmtDuration(ms?: number): string {
  if (!ms || ms <= 0) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function VerdictBadge({ verdict }: { verdict?: CouncilVerdictState }) {
  if (!verdict) return null
  const t = verdict.type
  if (t === 'consensus') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/[0.10] px-1.5 py-[1px] text-[10.5px] font-medium text-emerald-700 dark:text-emerald-400">
        <CheckCircle2 className="h-3 w-3" />
        共识
      </span>
    )
  }
  if (t === 'arbitrated') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/[0.10] px-1.5 py-[1px] text-[10.5px] font-medium text-amber-700 dark:text-amber-400">
        <Scale className="h-3 w-3" />
        仲裁
      </span>
    )
  }
  if (t === 'escalate') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-destructive/[0.10] px-1.5 py-[1px] text-[10.5px] font-medium text-destructive">
        <ShieldAlert className="h-3 w-3" />
        上报
      </span>
    )
  }
  return null
}

function StepStatusBadge({ status }: { status: CouncilStep['status'] }) {
  if (status === 'running') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-secondary/[0.08] px-1.5 py-[1px] text-[10.5px] font-medium text-secondary">
        <Loader2 className="h-3 w-3 animate-spin" />
        议事中
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
  if (status === 'escalated') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-destructive/[0.10] px-1.5 py-[1px] text-[10.5px] font-medium text-destructive">
        <ShieldAlert className="h-3 w-3" />
        上报
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

function RoleBody({ role }: { role: CouncilRoleState }) {
  const isDone = role.status === 'done'
  const isFailed = role.status === 'failed'

  if (!isDone && !isFailed) return null

  const hasText = !!role.stanceText
  const hasQs = !!role.openQuestions && role.openQuestions.length > 0
  const hasRefs = !!role.evidenceRefs && role.evidenceRefs.length > 0
  if (!hasText && !hasQs && !hasRefs && !role.error) return null

  return (
    <div className="ml-2 mt-1.5 rounded-md border border-border/70 bg-card-muted/30 px-3 py-2">
      {}
      {hasText && (
        <div className="max-h-[220px] overflow-auto pr-1 text-[11.5px] leading-relaxed text-foreground/90">
          <TypewriterMarkdown text={role.stanceText!} compact />
        </div>
      )}
      {!hasText && isDone && (
        <div className="text-[11px] text-muted-foreground">已表态（无文本）</div>
      )}
      {!hasText && isFailed && (
        <div className="flex items-start gap-1 text-[11px] leading-relaxed text-destructive">
          <XCircle className="mt-0.5 h-3 w-3 shrink-0" />
          <span className="line-clamp-3 font-mono">{role.error || '失败'}</span>
        </div>
      )}
      {}
      {isFailed && hasText && role.error && (
        <div className="mt-1 flex items-start gap-1 rounded border border-destructive/30 bg-destructive/[0.05] px-1.5 py-1 text-[10.5px] leading-relaxed text-destructive">
          <XCircle className="mt-0.5 h-3 w-3 shrink-0" />
          <span className="font-mono">{role.error}</span>
        </div>
      )}

      {}
      {hasQs && (
        <div className="mt-1.5 border-t border-border/60 pt-1.5">
          <span className="mb-1 block text-[10px] font-medium uppercase tracking-wide text-muted-foreground/80">
            遗留问题 · {role.openQuestions!.length}
          </span>
          <ul className="space-y-0.5 text-[10.5px] leading-relaxed text-muted-foreground">
            {role.openQuestions!.slice(0, 5).map((q, i) => (
              <li key={`${i}-${q.slice(0, 16)}`} className="flex items-start gap-1">
                <span className="mt-[5px] inline-block h-1 w-1 shrink-0 rounded-full bg-muted-foreground/50" />
                <span className="line-clamp-2">{q}</span>
              </li>
            ))}
            {role.openQuestions!.length > 5 && (
              <li className="text-[10px] text-muted-foreground/70">
                …还有 {role.openQuestions!.length - 5} 条
              </li>
            )}
          </ul>
        </div>
      )}

      {}
      {hasRefs && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1 border-t border-border/60 pt-1.5">
          {role.evidenceRefs!.slice(0, 4).map((r) => (
            <code
              key={r}
              title={r}
              className="max-w-[140px] truncate rounded bg-muted/60 px-1 py-px font-mono text-[10px] text-muted-foreground"
            >
              {r}
            </code>
          ))}
          {role.evidenceRefs!.length > 4 && (
            <span className="text-[10px] text-muted-foreground">
              +{role.evidenceRefs!.length - 4}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

function laneStatusOfRole(s: CouncilRoleState['status']) {

  if (s === 'done') return 'success' as const
  return s
}

export function EvidenceSnapshotPanel({
  warnings,
  snapshotId,
}: {
  warnings?: CouncilStep['evidenceWarnings']
  snapshotId?: string
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
        <span>
          事实卷宗{snapshotId ? ` (${snapshotId.slice(0, 8)})` : ''} · {warnings.length} 条主观警告
        </span>
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

export default function CouncilCard({ step }: { step: CouncilStep }) {
  const totalRoles = step.roles.length
  const doneRoles = step.roles.filter(
    (r) => r.status === 'done' || r.status === 'failed',
  ).length
  const failedRoles = step.roles.filter((r) => r.status === 'failed').length

  const openTraceDrawer = useChatStore((s) => s.openTraceDrawer)

  const hasVerdict = !!step.verdict
  const [verdictExpanded, setVerdictExpanded] = useState(true)

  const allOpenQuestions: string[] = []
  if (step.status !== 'running') {
    for (const r of step.roles) {
      if (r.openQuestions && r.openQuestions.length > 0) {
        for (const q of r.openQuestions) {
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
        <Gavel className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="text-[12px] font-semibold text-foreground">议会</span>
        {step.question && (
          <span className="line-clamp-1 text-[12px] text-muted-foreground">
            · {step.question}
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
          {doneRoles}/{totalRoles} 表态
          {failedRoles > 0 && (
            <span className="ml-1 text-destructive">· {failedRoles} 失败</span>
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
          <EvidenceSnapshotPanel
            warnings={step.evidenceWarnings}
            snapshotId={step.snapshotId}
          />
        </div>
      )}

      {}
      <div className="space-y-3 px-3 py-2">
        {totalRoles === 0 ? (
          <div className="flex items-center gap-2 py-2 text-[11.5px] text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span>等待角色表态…</span>
          </div>
        ) : (
          step.roles.map((role) => (
            <div key={role.roleId} className="flex flex-col">
              <AgentLane
                personaId={role.personaId}
                status={laneStatusOfRole(role.status)}
                progress={role.progress}
                progressKind={role.progressKind}
                error={role.error}
                tokensIn={role.tokensIn}
                tokensOut={role.tokensOut}
                durationMs={role.durationMs}
                onOpenTrace={() =>
                  openTraceDrawer({
                    stepId: step.id,
                    laneId: role.roleId,
                    kind: 'council',
                  })
                }
              />
              {}
              <SubAgentReasoning
                traceEvents={role.traceEvents}
                phase="stance"
                running={role.status === 'running'}
                className="ml-2 mt-1.5 px-1"
              />
              <RoleBody role={role} />
            </div>
          ))
        )}
      </div>

      {

}
      <RebutTheater
        roles={step.roles}
        onOpenTrace={(roleId) =>
          openTraceDrawer({
            stepId: step.id,
            laneId: roleId,
            kind: 'council',
          })
        }
      />

      {
}
      {(step.arbiterStatus === 'running' || hasVerdict) && (
        <div className="border-t border-border/70 px-3 py-2">
          <div className="flex items-center gap-1.5">
            <Gavel className="h-3 w-3 shrink-0 text-muted-foreground" />
            <span className="text-[11.5px] font-medium text-foreground">仲裁人</span>
            <AgentLaneArbiter step={step} />
          </div>

          {}
          <SubAgentReasoning
            traceEvents={step.arbiterTraceEvents}
            phase="arbiter"
            running={step.arbiterStatus === 'running'}
            className="ml-4 mt-1.5"
          />

          {}
          {hasVerdict && step.verdict?.text && (
            <div className="ml-4 mt-1.5">
              <button
                type="button"
                onClick={() => setVerdictExpanded((v) => !v)}
                className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground hover:text-foreground"
              >
                <ChevronDown
                  className={cn(
                    'h-3 w-3 shrink-0 transition-transform',
                    !verdictExpanded && '-rotate-90',
                  )}
                />
                裁决文
              </button>
              {verdictExpanded && (
                <div className="mt-1 rounded border border-border/50 bg-card p-2 text-[11.5px] leading-relaxed text-foreground/90">
                  <TypewriterMarkdown text={step.verdict.text} compact />
                </div>
              )}
            </div>
          )}

          {}
          {hasVerdict &&
            step.verdict?.conflictMatrix &&
            step.verdict.conflictMatrix.length > 0 && (
              <div className="ml-4 mt-1.5">
                <span className="mb-1 block text-[10.5px] font-medium text-muted-foreground">
                  分歧矩阵
                </span>
                <ConflictMatrix
                  conflictMatrix={step.verdict.conflictMatrix}
                  roles={step.roles}
                />
              </div>
            )}

          {}
          {hasVerdict && step.verdict?.minorityNotes && (
            <div className="ml-4 mt-1.5 rounded border-l-2 border-amber-400/60 pl-2 text-[11px] italic text-muted-foreground">
              少数派意见：{step.verdict.minorityNotes}
            </div>
          )}
        </div>
      )}

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
            <span>遗留问题 · {allOpenQuestions.length} 条</span>
          </button>
          {openQAExpanded && (
            <ul className="ml-4 mt-1 space-y-0.5 text-[11.5px] text-muted-foreground">
              {allOpenQuestions.map((q, i) => (
                <li key={`${i}-${q.slice(0, 20)}`} className="flex items-start gap-1.5">
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

function AgentLaneArbiter({ step }: { step: CouncilStep }) {

  const isRunning = step.arbiterStatus === 'running' && !step.verdict
  return (
    <>
      <span className="shrink-0 text-[12px] leading-none" aria-hidden>
        {personaIcon(step.arbiterPersona)}
      </span>
      <span
        title={step.arbiterPersona}
        className="shrink-0 text-[11px] text-muted-foreground"
      >
        {personaName(step.arbiterPersona)}
      </span>
      <span className="ml-auto" />
      {isRunning && (
        <span className="inline-flex items-center gap-1 text-[10.5px] text-secondary">
          <Loader2 className="h-3 w-3 animate-spin" />
          裁定中
        </span>
      )}
      {step.verdict && <VerdictBadge verdict={step.verdict} />}
    </>
  )
}

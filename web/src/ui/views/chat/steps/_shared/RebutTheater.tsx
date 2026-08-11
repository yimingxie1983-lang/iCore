

import { CheckCircle2, ChevronRight, Loader2, Megaphone, XCircle } from 'lucide-react'

import TypewriterMarkdown from '@/ui/widgets/common/TypewriterMarkdown'
import { cn } from '@/shared/foundation/utils'
import {
  personaColorClasses,
  personaIcon,
  personaName,
} from '@/shared/foundation/personas'
import type { CouncilRoleState } from '@/application/state/chatStore'
import SubAgentReasoning from './SubAgentReasoning'

export interface RebutTheaterProps {
  roles: CouncilRoleState[]
  onOpenTrace?: (roleId: string) => void
}

function StatusBadge({ status }: { status: NonNullable<CouncilRoleState['rebutStatus']> }) {
  if (status === 'running') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-secondary/[0.10] px-1.5 py-[1px] text-[10.5px] font-medium text-secondary">
        <Loader2 className="h-3 w-3 animate-spin" />
        进行中
      </span>
    )
  }
  if (status === 'done') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/[0.10] px-1.5 py-[1px] text-[10.5px] font-medium text-emerald-700 dark:text-emerald-400">
        <CheckCircle2 className="h-3 w-3" />
        已发言
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span className="inline-flex items-center gap-1 rounded-md bg-destructive/[0.10] px-1.5 py-[1px] text-[10.5px] font-medium text-destructive">
        <XCircle className="h-3 w-3" />
        失败
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-muted/60 px-1.5 py-[1px] text-[10.5px] font-medium text-muted-foreground">
      排队
    </span>
  )
}

function RebutBubble({
  role,
  index,
  onOpenTrace,
}: {
  role: CouncilRoleState
  index: number
  onOpenTrace?: (roleId: string) => void
}) {
  const colors = personaColorClasses(role.personaId)
  const isRunning = role.rebutStatus === 'running'
  const isDone = role.rebutStatus === 'done'
  const isFailed = role.rebutStatus === 'failed'

  return (
    <div
      className={cn(
        'overflow-hidden rounded-md border-l-2 bg-card-muted/30',
        colors.border,
      )}
    >
      {}
      <div
        className={cn(
          'flex items-center gap-2 px-3 py-2',
          colors.bg,
        )}
      >
        <span className="text-[16px] leading-none" aria-hidden>
          {personaIcon(role.personaId)}
        </span>
        <span className={cn('text-[12px] font-semibold', colors.text)}>
          {personaName(role.personaId)}
        </span>
        <span className="ml-1 shrink-0 font-mono text-[10px] text-muted-foreground/70">
          #{index + 1}
        </span>
        <span className="ml-auto" />
        {role.rebutStatus && <StatusBadge status={role.rebutStatus} />}
        {onOpenTrace && (
          <button
            type="button"
            onClick={() => onOpenTrace(role.roleId)}
            className="inline-flex items-center text-muted-foreground hover:text-foreground"
            title="查看完整 trace（含 thinking / tool_call）"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {}
      <div className="space-y-2 px-3 py-2">
        {}
        <SubAgentReasoning
          traceEvents={role.traceEvents}
          phase="rebut"
          running={isRunning}
        />
        {isRunning && (
          <div className="flex items-center gap-1.5 text-[11.5px] leading-relaxed text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span className="line-clamp-2 font-mono">
              {role.rebutProgress || '正在准备发言…'}
            </span>
          </div>
        )}
        {isDone && role.rebuttalText && (
          <div className="max-h-[280px] overflow-auto pr-1 text-[12px] leading-relaxed text-foreground/90">
            <TypewriterMarkdown text={role.rebuttalText} compact />
          </div>
        )}
        {isDone && !role.rebuttalText && (
          <div className="text-[11px] italic text-muted-foreground">
            （未产出反驳正文）
          </div>
        )}
        {isFailed && (
          <div className="flex items-start gap-1.5 text-[11px] leading-relaxed text-destructive">
            <XCircle className="mt-0.5 h-3 w-3 shrink-0" />
            <span className="line-clamp-3 font-mono">
              {role.rebuttalError || '反驳轮失败'}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

export default function RebutTheater({ roles, onOpenTrace }: RebutTheaterProps) {

  const participants = roles.filter((r) => !!r.rebutStatus)
  if (participants.length === 0) return null

  const totalCount = participants.length
  const doneCount = participants.filter(
    (r) => r.rebutStatus === 'done' || r.rebutStatus === 'failed',
  ).length

  return (
    <div className="border-t border-border/70">
      {}
      <div className="flex items-center gap-2 bg-amber-500/[0.05] px-3 py-2">
        <Megaphone className="h-3.5 w-3.5 shrink-0 text-amber-700 dark:text-amber-400" />
        <span className="text-[12px] font-semibold text-amber-700 dark:text-amber-400">
          反驳轮 · 议事剧场
        </span>
        <span className="ml-1 text-[11px] text-muted-foreground">
          看完一阶表态后，每个角色对其他匿名意见做出回应
        </span>
        <span className="ml-auto font-mono text-[10.5px] text-muted-foreground">
          {doneCount}/{totalCount} 已发言
        </span>
      </div>

      {}
      <div className="space-y-2 px-3 py-3">
        {participants.map((role, i) => (
          <RebutBubble
            key={role.roleId}
            role={role}
            index={i}
            onOpenTrace={onOpenTrace}
          />
        ))}
      </div>
    </div>
  )
}

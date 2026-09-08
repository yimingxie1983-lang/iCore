import { useMemo } from 'react'
import {
  Check,
  CircleEllipsis,
  Loader2,
  X,
} from 'lucide-react'

import {
  type AskUserStep,
  type TurnStep,
} from '@/application/state/chatStore'
import type { StageOutputSegment } from '@/shared/helpers/conversationArtifacts'
import { cn } from '@/shared/foundation/utils'
import { useSessionsStore } from '@/application/state/sessionsStore'
import PresentedFilesBlock from './PresentedFiles'
import { AskUserCard } from './TurnSteps'
import { narrateStepEpisodes } from './stepEpisodeNarration'

/**
 * 主界面步骤：按「活动片段」整合成完整自然语言
 * （做了什么 + 为什么），而不是每次工具调用一行。
 */
export default function StepsSummary({
  steps,
  streaming,
  stageOutputs = [],
}: {
  steps: TurnStep[]
  streaming?: boolean
  stageOutputs?: StageOutputSegment[]
}) {
  const projectId = useSessionsStore((s) => s.projectId)

  const rows = useMemo(() => narrateStepEpisodes(steps), [steps])
  const askSteps = useMemo(
    () => steps.filter((s): s is AskUserStep => s.kind === 'ask_user'),
    [steps],
  )

  if (!rows.length && !askSteps.length && !streaming) return null

  return (
    <div className="flex flex-col gap-2">
      {rows.length > 0 || streaming ? (
        <div className="rounded-lg border border-border/70 bg-muted/20 px-3 py-2">
          {rows.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {rows.map((row) => (
                <li
                  key={row.id}
                  className="flex items-start gap-2 text-[13px] leading-relaxed text-foreground/90"
                >
                  <StatusIcon status={row.status} />
                  <span className="min-w-0 flex-1">{row.label}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {streaming ? (
            <div className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <CircleEllipsis className="h-3 w-3 animate-pulse" />
              还在继续…
            </div>
          ) : null}
        </div>
      ) : null}

      {askSteps.map((step) => (
        <AskUserCard key={step.id} step={step} />
      ))}

      {projectId
        ? stageOutputs.map((segment) =>
            segment.presentations.length ? (
              <PresentedFilesBlock
                key={`${segment.afterStepId}:${segment.title || 'stage'}`}
                projectId={projectId}
                groups={segment.presentations}
              />
            ) : null,
          )
        : null}
    </div>
  )
}

function StatusIcon({
  status,
}: {
  status: 'running' | 'success' | 'failed' | 'pending'
}) {
  if (status === 'running' || status === 'pending') {
    return <Loader2 className="mt-1 h-3.5 w-3.5 shrink-0 animate-spin text-secondary" />
  }
  if (status === 'failed') {
    return <X className="mt-1 h-3.5 w-3.5 shrink-0 text-destructive" />
  }
  return (
    <Check
      className={cn('mt-1 h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400')}
    />
  )
}

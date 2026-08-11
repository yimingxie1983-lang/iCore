

import { useMemo, useState } from 'react'
import { Brain, ChevronRight, Loader2 } from 'lucide-react'

import { cn } from '@/shared/foundation/utils'
import {
  traceEventsToSteps,
  type TracePhase,
} from '@/shared/foundation/subAgentTrace'
import type { ChatEvent, ThinkingStep } from '@/application/state/chatStore'
import { ThinkingBlock, ToolStepCard } from './StepBlocks'

export interface SubAgentReasoningProps {
  traceEvents?: ChatEvent[]
  phase: TracePhase

  running?: boolean

  defaultOpen?: boolean
  className?: string
}

export default function SubAgentReasoning({
  traceEvents,
  phase,
  running,
  defaultOpen = true,
  className,
}: SubAgentReasoningProps) {
  const steps = useMemo(
    () => traceEventsToSteps(traceEvents, phase),
    [traceEvents, phase],
  )

  const renderSteps = useMemo(() => {
    if (!running || steps.length === 0) return steps
    const out = steps.slice()
    for (let i = out.length - 1; i >= 0; i--) {
      if (out[i].kind === 'thinking') {
        out[i] = { ...(out[i] as ThinkingStep), streaming: true }
        break
      }
    }
    return out
  }, [steps, running])

  const [open, setOpen] = useState(defaultOpen)

  if (renderSteps.length === 0) {

    if (running) {
      return (
        <div
          className={cn(
            'flex items-center gap-1.5 px-1 text-[11px] text-muted-foreground',
            className,
          )}
        >
          <Loader2 className="h-3 w-3 animate-spin" />
          推理中…
        </div>
      )
    }
    return null
  }

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-fit items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground/70 hover:text-muted-foreground"
      >
        <ChevronRight
          className={cn(
            'h-3 w-3 shrink-0 transition-transform',
            open && 'rotate-90',
          )}
        />
        <Brain className="h-3 w-3 shrink-0" />
        <span>推理过程</span>
        <span className="font-mono text-[10px] font-normal normal-case tracking-normal text-muted-foreground/60">
          · {renderSteps.length} 步
        </span>
        {running && <Loader2 className="h-3 w-3 shrink-0 animate-spin" />}
      </button>

      {open && (
        <div className="flex flex-col gap-3 border-l border-border/60 pl-2.5">
          {renderSteps.map((step) => {
            if (step.kind === 'thinking') {
              return <ThinkingBlock key={step.id} step={step} />
            }
            if (step.kind === 'tool') {
              return <ToolStepCard key={step.id} step={step} />
            }
            return null
          })}
        </div>
      )}
    </div>
  )
}

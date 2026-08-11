

import { useMemo, useState } from 'react'
import {
  ArrowRightLeft,
  CheckCircle2,
  CircleEllipsis,
  HelpCircle,
  Loader2,
  MessageCircleQuestion,
  Send,
  Sparkles,
  XCircle,
} from 'lucide-react'

import { Button } from '@/ui/widgets/ui/button'
import { Textarea } from '@/ui/widgets/ui/textarea'
import { api } from '@/client/services/client'
import {
  useChatStore,
  type AskUserStep,
  type DelegateStep,
  type PipelineStep,
  type SubagentStep,
  type ThinkingStep,
  type TurnStep,
} from '@/application/state/chatStore'
import { cn } from '@/shared/foundation/utils'
import { toast } from '@/ui/widgets/ui/sonner'
import MarkdownRenderer from '@/ui/widgets/common/MarkdownRenderer'
import SquadCard from './steps/SquadCard'
import CouncilCard from './steps/CouncilCard'
import {
  ErrorBlock,
  NoticeRow,
  PretextBlock,
  ThinkingBlock,
  ToolStepCard,
  fmtDuration,
} from './steps/_shared/StepBlocks'

function StatusDot({ status }: { status: 'running' | 'success' | 'failed' | 'pending' }) {
  return (
    <span
      className={cn(
        'inline-block h-1.5 w-1.5 shrink-0 rounded-full',
        status === 'running' || status === 'pending'
          ? 'bg-secondary animate-pulse'
          : status === 'success'
            ? 'bg-emerald-500'
            : 'bg-destructive',
      )}
      aria-hidden
    />
  )
}

function DelegateRow({ step }: { step: DelegateStep }) {
  return (
    <div className="rounded-md border border-border bg-card-muted/60 px-3 py-2">
      <div className="flex items-center gap-2 text-[12px]">
        <ArrowRightLeft className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="text-muted-foreground">委派 →</span>
        <code className="rounded bg-muted/60 px-1 py-0.5 font-mono text-[11.5px] text-foreground">
          {step.persona || '?'}
        </code>
        <span className="ml-auto" />
        <StatusDot status={step.status} />
      </div>
      {step.task && (
        <div className="mt-1 line-clamp-2 text-[12px] text-foreground/90">
          {step.task}
        </div>
      )}
      {step.result && (
        <div className="mt-1.5 border-t border-border/70 pt-1.5 text-[11.5px] leading-relaxed text-muted-foreground line-clamp-3">
          {step.result}
        </div>
      )}
    </div>
  )
}

function SubagentRow({ step }: { step: SubagentStep }) {
  return (
    <div className="rounded-md border border-border bg-card-muted/60 px-3 py-2">
      <div className="flex items-center gap-2 text-[12px]">
        <MessageCircleQuestion className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="text-muted-foreground">请教 →</span>
        <code className="rounded bg-muted/60 px-1 py-0.5 font-mono text-[11.5px] text-foreground">
          {step.toAgent || '?'}
        </code>
        <span className="ml-auto" />
        <StatusDot status={step.status} />
      </div>
      {step.question && (
        <div className="mt-1 line-clamp-3 text-[11.5px] text-muted-foreground">
          {step.question}
        </div>
      )}
      {step.status === 'success' && (
        <div className="mt-2 border-t border-border/70 pt-2">
          <div className="flex items-center gap-2 text-[12px]">
            <Sparkles className="h-3.5 w-3.5 shrink-0 text-secondary" />
            <span className="text-muted-foreground">答复 ←</span>
            <code className="rounded bg-muted/60 px-1 py-0.5 font-mono text-[11.5px] text-foreground">
              {step.fromAgent || step.toAgent || '?'}
            </code>
          </div>
          {step.answer && (
            <div className="mt-1 line-clamp-3 text-[12px] leading-relaxed text-foreground/90">
              {step.answer}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function AskUserCard({ step }: { step: AskUserStep }) {
  const [draft, setDraft] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const markAnswered = useChatStore((s) => s.markAskUserAnswered)

  async function submit(text: string) {
    const trimmed = text.trim()
    if (!trimmed || submitting) return
    setSubmitting(true)
    try {
      await api.answerQuestion(step.questionId, trimmed)
      markAnswered(step.id, trimmed)
      toast.success('已提交回答，智能体继续推理')
    } catch (e) {
      toast.error(`提交失败：${(e as Error).message || e}`)
    } finally {
      setSubmitting(false)
    }
  }

  if (step.status === 'answered') {
    return (
      <div className="rounded-md border border-secondary/30 bg-secondary/[0.05] px-3 py-2">
        <div className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-secondary">
          <HelpCircle className="h-3 w-3" />
          已回答
        </div>
        <div className="mt-1 text-muted-foreground">
          {
}
          <MarkdownRenderer text={step.question || ''} compact />
        </div>
        <div className="mt-1.5 border-t border-secondary/20 pt-1.5 text-[12px] text-emerald-700 dark:text-emerald-400">
          ✓ 你的回答：{step.answer}
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-md border border-secondary/40 bg-secondary/[0.06] p-3">
      <div className="mb-1.5 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-secondary">
        <HelpCircle className="h-3 w-3" />
        等待你的回答
      </div>
      <div className="text-foreground">
        {}
        <MarkdownRenderer text={step.question || ''} compact />
      </div>

      {step.options && step.options.length > 0 && (
        <ol className="mt-2 space-y-0.5 text-[11.5px] text-muted-foreground">
          {step.options.map((opt, idx) => (
            <li key={opt} className="flex items-start gap-1">
              <span className="font-mono">{idx + 1}.</span>
              <button
                type="button"
                disabled={submitting}
                onClick={() => submit(opt)}
                className="text-left hover:text-foreground hover:underline"
              >
                {opt}
              </button>
            </li>
          ))}
        </ol>
      )}

      <div className="mt-2 flex items-end gap-2">
        <Textarea
          rows={2}
          placeholder="输入你的回答（Enter 提交，Shift+Enter 换行）…"
          className="min-h-[40px] flex-1 resize-none border-secondary/30 bg-card text-[12.5px]"
          value={draft}
          disabled={submitting}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit(draft)
            } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
              e.preventDefault()
              submit(draft)
            }
          }}
        />
        <Button
          size="icon"
          variant="default"
          className="h-9 w-9 shrink-0"
          disabled={!draft.trim() || submitting}
          onClick={() => submit(draft)}
          title="提交回答"
        >
          {submitting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>
    </div>
  )
}

function PipelineRow({ step }: { step: PipelineStep }) {
  const Icon =
    step.status === 'running'
      ? Loader2
      : step.status === 'success'
        ? CheckCircle2
        : XCircle
  const tone =
    step.status === 'running'
      ? 'text-secondary'
      : step.status === 'success'
        ? 'text-emerald-600 dark:text-emerald-400'
        : 'text-destructive'

  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-card-muted/60 px-3 py-1.5">
      <Icon
        className={cn(
          'h-3.5 w-3.5 shrink-0',
          tone,
          step.status === 'running' && 'animate-spin',
        )}
      />
      <span className="text-[12px] font-medium text-foreground">{step.title}</span>
      {step.runId && (
        <code className="font-mono text-[10px] text-muted-foreground">
          run={step.runId}
        </code>
      )}
      <span className="ml-auto" />
      {step.durationMs ? (
        <span className="shrink-0 font-mono text-[10.5px] text-muted-foreground">
          {fmtDuration(step.durationMs)}
        </span>
      ) : null}
    </div>
  )
}

export default function TurnSteps({
  steps,
  streaming,
}: {
  steps: TurnStep[]
  streaming?: boolean
}) {

  const compact = useMemo(() => {
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

    if (streaming && out.length > 0) {

      for (let i = out.length - 1; i >= 0; i--) {
        if (out[i].kind === 'thinking') {
          out[i] = { ...(out[i] as ThinkingStep), streaming: true }
          break
        }
      }
    }
    return out
  }, [steps, streaming])

  if (!compact.length && !streaming) return null

  return (
    <div className="flex flex-col gap-3">
      {compact.map((step) => {
        if (step.kind === 'thinking') {
          return <ThinkingBlock key={step.id} step={step} />
        }
        if (step.kind === 'pretext') {
          return <PretextBlock key={step.id} step={step} streaming={streaming} />
        }
        if (step.kind === 'tool') {
          return <ToolStepCard key={step.id} step={step} />
        }
        if (step.kind === 'ask_user') {
          return <AskUserCard key={step.id} step={step} />
        }
        if (step.kind === 'delegate') {
          return <DelegateRow key={step.id} step={step} />
        }
        if (step.kind === 'subagent') {
          return <SubagentRow key={step.id} step={step} />
        }
        if (step.kind === 'pipeline') {
          return <PipelineRow key={step.id} step={step} />
        }
        if (step.kind === 'squad') {
          return <SquadCard key={step.id} step={step} />
        }
        if (step.kind === 'council') {
          return <CouncilCard key={step.id} step={step} />
        }
        if (step.kind === 'notice') {
          return <NoticeRow key={step.id} step={step} />
        }
        if (step.kind === 'error') {
          return <ErrorBlock key={step.id} content={step.content} />
        }
        return null
      })}

      {streaming && (
        <div className="flex items-center gap-1.5 px-1 text-[11.5px] text-muted-foreground">
          <CircleEllipsis className="h-3 w-3 animate-pulse" />
          推理中…
        </div>
      )}
    </div>
  )
}



import { useEffect, useMemo, useRef } from 'react'
import { Check, Loader2, X } from 'lucide-react'

import type { ChatEvent } from '@/application/state/chatStore'
import { narrateEvents, type NarrationBlock } from '@/shared/foundation/reasoningNarrator'
import TypewriterMarkdown from '@/ui/widgets/common/TypewriterMarkdown'
import MarkdownRenderer from '@/ui/widgets/common/MarkdownRenderer'
import { cn } from '@/shared/foundation/utils'

interface Props {
  events: ChatEvent[]

  streaming: boolean
}

export default function ReasoningPane({ events, streaming }: Props) {

  const blocks = useMemo(() => narrateEvents(events), [events])

  const scrollRef = useRef<HTMLDivElement | null>(null)
  const followRef = useRef(true)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return

    const onScroll = () => {
      const distToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
      followRef.current = distToBottom < 100
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    if (!followRef.current) return
    const el = scrollRef.current
    if (!el) return
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight
    })
  }, [blocks, streaming])

  useEffect(() => {
    if (!streaming) return
    const el = scrollRef.current
    if (!el) return

    let rafId = 0
    let lastHeight = el.scrollHeight

    const tick = () => {
      if (!followRef.current) {
        rafId = requestAnimationFrame(tick)
        return
      }
      const h = el.scrollHeight
      if (h !== lastHeight) {
        lastHeight = h
        el.scrollTop = h
      }
      rafId = requestAnimationFrame(tick)
    }
    rafId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafId)
  }, [streaming])

  const lastNarrationIdx = useMemo(() => {
    for (let i = blocks.length - 1; i >= 0; i--) {
      if (blocks[i].kind === 'narration') return i
    }
    return -1
  }, [blocks])

  if (blocks.length === 0) {
    return (
      <div
        ref={scrollRef}
        className="flex h-full items-center justify-center px-4 py-10 text-center"
      >
        <div className="max-w-xs space-y-2">
          <p className="text-sm font-medium text-foreground">AI 还没开始思考</p>
          <p className="text-xs leading-relaxed text-muted-foreground">
            发送一条消息后，这里会用人话实时讲述 AI 的推理过程：
            读到了什么、为什么这么决策、下一步要做什么。
          </p>
        </div>
      </div>
    )
  }

  return (
    <div ref={scrollRef} className="flex h-full flex-col gap-1.5 overflow-y-auto px-1 py-3">
      {blocks.map((block, idx) => (
        <BlockRouter
          key={block.id}
          block={block}
          isLatestNarration={idx === lastNarrationIdx}
          streaming={streaming}
        />
      ))}
    </div>
  )
}

interface BlockProps {
  block: NarrationBlock
  isLatestNarration: boolean
  streaming: boolean
}

function BlockRouter({ block, isLatestNarration, streaming }: BlockProps) {
  switch (block.kind) {
    case 'narration':
      return (
        <NarrationCard
          block={block}
          isLatest={isLatestNarration}
          streaming={streaming}
        />
      )

    case 'action':
    case 'activity':
      return <ActivityRow block={block} />
    case 'subagent':
      return <SubagentRow block={block} />
    case 'group':
      return <GroupCard block={block} />
    case 'verdict':
      return <VerdictCard block={block} />
    case 'ask':
      return <AskCard block={block} />
    case 'warning':
      return <WarningCard block={block} />
    case 'error':
      return <ErrorCard block={block} />
    case 'final':
      return <FinalRow block={block} />
    case 'group_child':

      return <GroupChildRow block={block} />
    default:
      return null
  }
}

function NarrationCard({
  block,
  isLatest,
  streaming,
}: {
  block: NarrationBlock
  isLatest: boolean
  streaming: boolean
}) {
  const enableTypewriter = isLatest && streaming
  const isCausedBy = !!block.causedBy

  return (
    <div
      className={cn(
        'flex gap-2 px-3 py-1.5',
        isCausedBy && 'ml-6 rounded-md bg-muted/40 py-2.5',
      )}
    >
      {isCausedBy && <CausalityConnector />}
      <div className="flex-shrink-0 select-none text-base leading-6">{block.icon}</div>
      <div className="min-w-0 flex-1 text-[13.5px] leading-relaxed text-foreground">
        <TypewriterMarkdown
          text={block.text}
          streaming={enableTypewriter}
          compact
        />
      </div>
    </div>
  )
}

function CausalityConnector() {
  return (
    <span
      aria-hidden
      className="relative -ml-5 mr-1 mt-[2px] inline-block h-4 w-4 flex-shrink-0 text-muted-foreground"
    >
      <span className="absolute left-0 top-0 h-[10px] w-[2px] rounded-full bg-current opacity-50" />
      <span className="absolute left-0 top-[10px] h-[2px] w-[12px] rounded-full bg-current opacity-50" />
      <span className="absolute left-[10px] top-[6px] text-[12px] leading-none opacity-60">➜</span>
    </span>
  )
}

function ActivityRow({ block }: { block: NarrationBlock }) {
  const isRunning = block.status === 'running'
  const isFailed = block.status === 'failed'
  const count = block.toolCount || 1

  const summaryText =
    count <= 1
      ? `已${block.text}`
      : `已完成 ${count} 步操作`

  const tooltip =
    block.toolLabels && block.toolLabels.length > 1
      ? block.toolLabels.map((l, i) => `${i + 1}. ${l}`).join('\n')
      : undefined

  return (
    <div
      className={cn(
        'flex items-center gap-2 px-3 py-1.5 text-[12.5px] leading-relaxed',
        isRunning && 'text-muted-foreground',
        !isRunning && 'text-foreground/75',
      )}
      title={tooltip}
    >
      {isRunning && (
        <Loader2 className="h-3.5 w-3.5 flex-shrink-0 animate-spin text-sky-500" />
      )}
      {!isRunning && !isFailed && (
        <Check className="h-3.5 w-3.5 flex-shrink-0 text-emerald-600" />
      )}
      {isFailed && <X className="h-3.5 w-3.5 flex-shrink-0 text-rose-600" />}

      <span className={cn('min-w-0 truncate', isFailed && 'text-rose-700 dark:text-rose-300')}>
        {isRunning ? <>正在 {block.text}…</> : summaryText}
      </span>

      {}
      {isRunning && count > 1 && (
        <span className="flex-shrink-0 text-[11px] opacity-70">· 第 {count} 步</span>
      )}

      {}
      {!isRunning && (
        <>
          {block.totalDurationMs ? (
            <span className="flex-shrink-0 text-[11px] text-muted-foreground">
              · {formatDuration(block.totalDurationMs)}
            </span>
          ) : null}
          {(block.failedCount || 0) > 0 && (
            <span className="flex-shrink-0 text-[11px] text-rose-600">
              · {block.failedCount} 失败
            </span>
          )}
        </>
      )}
    </div>
  )
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m${Math.floor((ms % 60000) / 1000)}s`
}

function SubagentRow({ block }: { block: NarrationBlock }) {
  const isRunning = block.status === 'running'
  return (
    <div
      className={cn(
        'flex items-start gap-2 rounded-lg border-l-2 bg-card/60 px-3 py-2 text-[13px] leading-relaxed',
        isRunning && 'border-l-violet-500/60',
        block.status === 'success' && 'border-l-violet-500/40',
        block.status === 'failed' && 'border-l-rose-500/60',
      )}
    >
      <span className="mt-[1px] flex-shrink-0 select-none text-base leading-6">
        {block.icon}
      </span>
      <div className="min-w-0 flex-1 text-foreground/90">
        <MarkdownRenderer text={block.text} compact />
      </div>
      {isRunning && (
        <Loader2 className="mt-[3px] h-3.5 w-3.5 flex-shrink-0 animate-spin text-violet-500" />
      )}
    </div>
  )
}

function GroupCard({ block }: { block: NarrationBlock }) {
  const isRunning = block.status === 'running'
  return (
    <div
      className={cn(
        'rounded-xl border bg-card p-3 shadow-sm',
        isRunning && 'border-indigo-500/30',
        block.status === 'success' && 'border-indigo-500/40',
        block.status === 'failed' && 'border-rose-500/30',
      )}
    >
      <div className="flex items-start gap-2">
        <span className="mt-[1px] flex h-6 w-6 flex-shrink-0 select-none items-center justify-center text-base leading-6">
          {block.icon}
        </span>
        <div className="min-w-0 flex-1 text-[13.5px] font-medium leading-relaxed text-foreground">
          <MarkdownRenderer text={block.text} compact />
        </div>
        {isRunning && (
          <Loader2 className="mt-1 h-3.5 w-3.5 flex-shrink-0 animate-spin text-indigo-500" />
        )}
        {block.status === 'success' && (
          <span className="mt-1 flex-shrink-0 text-[11px] text-emerald-600">
            ✓{block.durationMs ? ` ${formatDuration(block.durationMs)}` : ''}
          </span>
        )}
        {block.status === 'failed' && (
          <span className="mt-1 flex-shrink-0 text-[11px] text-rose-600">✗ 失败</span>
        )}
      </div>

      {block.children && block.children.length > 0 && (
        <div className="mt-2.5 space-y-1.5 border-l-2 border-indigo-500/20 pl-3">
          {block.children.map((c) =>
            c.kind === 'verdict' ? (
              <div key={c.id} className="pt-1">
                <VerdictRow block={c} />
              </div>
            ) : (
              <GroupChildRow key={c.id} block={c} />
            ),
          )}
        </div>
      )}
    </div>
  )
}

function GroupChildRow({ block }: { block: NarrationBlock }) {
  return (
    <div className="flex items-start gap-2 text-[12.5px] leading-relaxed">
      <span className="mt-[1px] flex-shrink-0 select-none text-sm leading-5">{block.icon}</span>
      <div className="min-w-0 flex-1 text-foreground/80">
        <MarkdownRenderer text={block.text} compact />
      </div>
      {block.status && block.status !== 'running' && (
        <span
          className={cn(
            'flex-shrink-0 text-[11px]',
            block.status === 'success' && 'text-emerald-600',
            block.status === 'failed' && 'text-rose-600',
          )}
        >
          {block.status === 'success' ? '✓' : '✗'}
        </span>
      )}
    </div>
  )
}

function VerdictCard({ block }: { block: NarrationBlock }) {
  return (
    <div className="rounded-xl border border-indigo-900/30 bg-indigo-50/40 p-3 shadow-sm dark:bg-indigo-950/30">
      <VerdictRow block={block} />
    </div>
  )
}

function VerdictRow({ block }: { block: NarrationBlock }) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-[1px] flex h-6 w-6 flex-shrink-0 select-none items-center justify-center text-base leading-6">
        {block.icon}
      </span>
      <div className="min-w-0 flex-1 text-[13.5px] leading-relaxed text-indigo-900 dark:text-indigo-200">
        <MarkdownRenderer text={block.text} compact />
      </div>
    </div>
  )
}

function AskCard({ block }: { block: NarrationBlock }) {
  return (
    <div className="rounded-xl border-2 border-secondary/40 bg-secondary/10 p-3 shadow-sm">
      <div className="flex items-start gap-2">
        <span className="mt-[1px] flex h-6 w-6 flex-shrink-0 select-none items-center justify-center text-base leading-6">
          {block.icon}
        </span>
        <div className="min-w-0 flex-1 text-[13.5px] font-medium leading-relaxed text-foreground">
          <MarkdownRenderer text={block.text} compact />
          <p className="mt-1 text-[11.5px] font-normal text-muted-foreground">
            请在主对话区域回答
          </p>
        </div>
      </div>
    </div>
  )
}

function WarningCard({ block }: { block: NarrationBlock }) {
  return (
    <div className="rounded-xl border border-amber-500/40 bg-amber-50/40 p-3 shadow-sm dark:bg-amber-950/20">
      <div className="flex items-start gap-2">
        <span className="mt-[1px] flex h-6 w-6 flex-shrink-0 select-none items-center justify-center text-base leading-6">
          {block.icon}
        </span>
        <div className="min-w-0 flex-1 text-[12.5px] leading-relaxed text-amber-900 dark:text-amber-200">
          <MarkdownRenderer text={block.text} compact />
        </div>
      </div>
    </div>
  )
}

function ErrorCard({ block }: { block: NarrationBlock }) {
  return (
    <div className="rounded-xl border border-rose-500/40 bg-rose-50/40 p-3 shadow-sm dark:bg-rose-950/20">
      <div className="flex items-start gap-2">
        <span className="mt-[1px] flex h-6 w-6 flex-shrink-0 select-none items-center justify-center text-base leading-6">
          {block.icon}
        </span>
        <div className="min-w-0 flex-1 text-[13px] leading-relaxed text-rose-900 dark:text-rose-200">
          <MarkdownRenderer text={block.text} compact />
        </div>
      </div>
    </div>
  )
}

function FinalRow({ block }: { block: NarrationBlock }) {
  return (
    <div className="px-3 py-1.5 text-center text-[11.5px] italic text-muted-foreground">
      <span className="mr-1">{block.icon}</span>
      {block.text}
    </div>
  )
}



import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  CheckCircle2,
  Coins,
  Cpu,
  Hash,
  Hourglass,
  Loader2,
  MessageSquare,
  Sparkle,
  Timer,
  TriangleAlert,
  User,
} from 'lucide-react'

import type { ChatMessage } from '@/application/state/chatStore'
import { api } from '@/client/services/client'
import { Badge } from '@/ui/widgets/ui/badge'
import { useSessionsStore } from '@/application/state/sessionsStore'
import { cn } from '@/shared/foundation/utils'
import TurnSteps from './TurnSteps'
import TypewriterMarkdown from '@/ui/widgets/common/TypewriterMarkdown'

interface Props {
  message: ChatMessage
}

function formatRelative(ts: number, now: number): string {
  const diff = Math.max(0, now - ts)
  if (diff < 5_000) return '刚刚'
  if (diff < 60_000) return `${Math.floor(diff / 1000)} 秒前`
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分前`
  return new Date(ts).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

function fmtElapsedSeconds(ms: number): string {
  if (ms < 0) ms = 0

  return `${(ms / 1000).toFixed(1)}s`
}

function useRelativeNow(intervalMs: number, enabled: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!enabled) return
    const id = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(id)
  }, [enabled, intervalMs])
  return now
}

function UserAvatar() {
  return (
    <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-card-muted text-muted-foreground">
      <User className="h-3.5 w-3.5" />
    </div>
  )
}

function AssistantAvatar({ streaming }: { streaming?: boolean }) {

  if (streaming) {
    return (
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-secondary/40 bg-secondary/[0.10] text-secondary">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      </div>
    )
  }
  return (
    <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-card-muted text-muted-foreground">
      <Sparkle className="h-3.5 w-3.5" />
    </div>
  )
}

function AttachmentImage({
  projectId,
  img,
}: {
  projectId: string | null
  img: { previewUrl?: string; path: string; name?: string }
}) {
  const [src, setSrc] = useState(img.previewUrl || '')

  useEffect(() => {
    if (src || !projectId || !img.path) return
    let cancelled = false
    api
      .signFileUrl(projectId, img.path)
      .then((u) => {
        if (!cancelled) setSrc(u.url)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [src, projectId, img.path])

  if (!src) {
    return (
      <span
        className="inline-flex max-w-[220px] items-center gap-1 rounded border border-border bg-muted/60 px-1.5 py-0.5 text-[11px]"
        title={img.name}
      >
        <span className="truncate font-medium text-foreground">🖼️ {img.name}</span>
      </span>
    )
  }
  return (
    <a
      href={src}
      target="_blank"
      rel="noreferrer"
      className="block overflow-hidden rounded-lg border border-border bg-card shadow-sm transition hover:ring-2 hover:ring-secondary"
      title={img.name}
    >
      <img src={src} alt={img.name} className="block max-h-44 max-w-[260px] object-cover" />
    </a>
  )
}

function UserMessage({ message }: { message: ChatMessage }) {
  const now = useRelativeNow(15_000, true)
  const projectId = useSessionsStore((s) => s.projectId)
  const attachments = message.attachments || []
  const images = attachments.filter((a) => a.kind === 'image')
  const files = attachments.filter((a) => a.kind !== 'image')

  return (
    <div className="flex flex-row-reverse gap-3">
      <UserAvatar />
      <div className="flex max-w-[82%] min-w-[120px] flex-col items-end gap-1.5">
        <div className="flex items-center gap-1.5 text-[10.5px] text-muted-foreground/70">
          {message.source && (
            <span className="rounded border border-border/80 px-1.5 py-[1px] font-mono text-[9.5px] uppercase tracking-wider">
              {message.source}
            </span>
          )}
          <span className="text-[10.5px]">
            {formatRelative(message.createdAt, now)}
          </span>
          <span className="text-[12.5px] font-medium text-muted-foreground">
            你
          </span>
        </div>
        {images.length > 0 && (
          <div className="flex flex-wrap justify-end gap-1.5">
            {images.map((img) => (
              <AttachmentImage key={img.path} projectId={projectId} img={img} />
            ))}
          </div>
        )}
        {files.length > 0 && (
          <div className="flex flex-wrap justify-end gap-1">
            {files.map((f) => (
              <span
                key={f.path}
                className="inline-flex max-w-[220px] items-center gap-1 rounded border border-border bg-muted/60 px-1.5 py-0.5 text-[11px]"
                title={`${f.path} · ${f.size} bytes`}
              >
                <span className="truncate font-medium text-foreground">{f.name}</span>
              </span>
            ))}
          </div>
        )}
        {
}
        {message.text && message.text.trim() !== '[image]' && (
          <div className="rounded-2xl rounded-tr-md border border-primary bg-primary px-3.5 py-2.5 text-[13px] leading-[1.65] text-primary-foreground shadow-sm break-words whitespace-pre-wrap">
            {stripImagePlaceholdersForDisplay(message.text)}
          </div>
        )}
      </div>
    </div>
  )
}

function stripImagePlaceholdersForDisplay(text: string): string {
  return text
    .split('\n')
    .filter((line) => {
      const trimmed = line.trim()
      if (!trimmed) return true

      return !/^\[image(?::[^\]]+)?\]$/.test(trimmed)
    })
    .join('\n')
    .trim()
}

function statusTitle(message: ChatMessage): string {
  if (message.streaming) return '推理中'
  if (message.state === 'cancelled') return '已取消'
  if (message.state === 'error') return '失败'
  return '回复'
}

function MetricBadge({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Coins
  label: string
  value: string | number
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <Icon className="h-2.5 w-2.5 shrink-0" />
      <span className="text-muted-foreground/70">{label}</span>
      <span className="font-mono text-foreground/90">{value}</span>
    </span>
  )
}

function AssistantMessage({ message }: { message: ChatMessage }) {

  const elapsedNow = useRelativeNow(100, !!message.streaming)
  const elapsedMs = message.streaming
    ? Math.max(0, elapsedNow - message.createdAt)
    : message.stats?.durationMs ?? (message.finishedAt
      ? message.finishedAt - message.createdAt
      : 0)

  const nowSlow = useRelativeNow(15_000, true)

  const bodyRef = useRef<HTMLDivElement | null>(null)
  const [bodyWidth, setBodyWidth] = useState<number>(640)
  useLayoutEffect(() => {
    if (!bodyRef.current) return
    const el = bodyRef.current
    const ro = new ResizeObserver(() => {

      const w = el.clientWidth - 36
      if (w > 200) setBodyWidth(w)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const hasSteps = message.steps && message.steps.length > 0
  const hasText = !!message.text
  const isError = message.state === 'error'
  const isCancelled = message.state === 'cancelled'
  const showFinalReplyCard = message.streaming || hasText
  const showWaitingFinal = message.streaming && !hasText

  const showStats =
    !message.streaming &&
    message.stats &&
    (message.stats.totalTokens > 0 ||
      message.stats.modelCalls > 0 ||
      message.stats.toolCalls > 0)

  const titleTone = isError
    ? 'text-destructive'
    : isCancelled
      ? 'text-muted-foreground'
      : message.streaming
        ? 'text-secondary'
        : 'text-foreground'

  return (
    <div className="flex gap-3">
      <AssistantAvatar streaming={message.streaming} />
      <div ref={bodyRef} className="flex min-w-[120px] max-w-[88%] flex-1 flex-col gap-2">
        {}
        <div className="flex items-center gap-2">
          <span className={cn('text-[12.5px] font-medium', titleTone)}>
            {statusTitle(message)}
          </span>
          <span className="text-[10.5px] text-muted-foreground/70">
            {formatRelative(message.createdAt, nowSlow)}
          </span>
          <span className="ml-auto" />
          {message.streaming && (
            <span className="font-mono text-[10.5px] text-secondary">
              {fmtElapsedSeconds(elapsedMs)}
            </span>
          )}
        </div>

        {}
        {(hasSteps || message.streaming) && (
          <TurnSteps
            steps={message.steps}
            streaming={message.streaming && !hasText}
          />
        )}

        {}
        {showFinalReplyCard && (
          <div className="rounded-lg border border-border bg-card px-4 py-3 shadow-sm">
            <div className="mb-1.5 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
              <MessageSquare className="h-3 w-3" />
              回复
            </div>
            {showWaitingFinal ? (
              <div className="flex items-center gap-1.5 text-[12px] italic text-muted-foreground/80">
                <Hourglass className="h-3 w-3 animate-pulse" />
                等待最终回复…
              </div>
            ) : (
              <TypewriterMarkdown
                text={message.text}
                streaming={!!message.streaming}
                width={bodyWidth}
                fontSize={14}
                fontWeight={400}
                lineHeight={23}
              />
            )}
          </div>
        )}

        {}
        {isError && message.errorText && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/[0.06] px-3 py-2 text-[12px] text-destructive">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="leading-relaxed">{message.errorText}</span>
          </div>
        )}

        {}
        {isCancelled && (
          <div className="px-1 text-[11.5px] italic text-muted-foreground/80">
            推理已被取消
            {message.errorText ? ` · ${message.errorText}` : ''}
          </div>
        )}

        {}
        {showStats && message.stats && (
          <div className="mt-1 border-t border-border/70 pt-2">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10.5px] text-muted-foreground/80">
              <MetricBadge
                icon={Coins}
                label="tokens"
                value={fmtTokens(message.stats.totalTokens)}
              />
              {message.stats.totalTokens > 0 && (
                <span className="text-muted-foreground/70">
                  (in {fmtTokens(message.stats.inputTokens)} · out{' '}
                  {fmtTokens(message.stats.outputTokens)})
                </span>
              )}
              <MetricBadge
                icon={Cpu}
                label="模型"
                value={`${message.stats.modelCalls} 次`}
              />
              <MetricBadge
                icon={CheckCircle2}
                label="工具"
                value={`${message.stats.toolCalls} 次`}
              />
              <MetricBadge
                icon={Timer}
                label="耗时"
                value={fmtElapsedSeconds(message.stats.durationMs)}
              />
              <MetricBadge
                icon={Hash}
                label="轮次"
                value={message.stats.rounds}
              />
            </div>

            {}
            {Object.keys(message.stats.toolCounts || {}).length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {Object.entries(message.stats.toolCounts).map(([name, count]) => (
                  <Badge
                    key={name}
                    variant="outline"
                    className="h-4 gap-1 px-1.5 font-mono text-[10px] tabular-nums"
                  >
                    <span>{name}</span>
                    <span className="text-muted-foreground">×{count}</span>
                  </Badge>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default function MessageBubble({ message }: Props) {
  if (message.role === 'user') {
    return <UserMessage message={message} />
  }
  return <AssistantMessage message={message} />
}

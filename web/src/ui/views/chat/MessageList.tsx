

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowDown,
  FileSearch,
  FlaskConical,
  Loader2,
  MessageSquare,
  Microscope,
} from 'lucide-react'

import MessageBubble from './MessageBubble'
import type { ChatMessage } from '@/application/state/chatStore'
import { useSessionsStore } from '@/application/state/sessionsStore'
import { Button } from '@/ui/widgets/ui/button'
import { cn } from '@/shared/foundation/utils'

interface Props {
  messages: ChatMessage[]

  streaming?: boolean
  className?: string
  reserveRight?: boolean
}

const FOLLOW_THRESHOLD_PX = 100
const TOP_LOAD_THRESHOLD_PX = 100

const TOP_LOAD_COOLDOWN_MS = 800

const QUICK_PROMPTS = [
  {
    icon: FileSearch,
    title: '文献检索',
    hint: '"近 3 年关于胰腺癌早期诊断生物标志物的最新文献，提取关键证据"',
  },
  {
    icon: Microscope,
    title: '数据探索',
    hint: '"读取 cohort.csv，做描述性统计 + 关键指标分组对比 + 出图"',
  },
  {
    icon: FlaskConical,
    title: '方法论咨询',
    hint: '"我想做一个回顾性队列研究，给我列出关键设计要点与统计陷阱"',
  },
]

function EmptyState() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-[11px] font-medium text-muted-foreground">
        <MessageSquare className="h-3 w-3 text-secondary" />
        准备就绪 · 项目已加载
      </div>
      <h2 className="text-xl font-semibold tracking-tight text-foreground">
        你好，今天处理什么？
      </h2>
      <p className="mt-1 text-[13px] text-muted-foreground">
        下面是一些常见入手方向，点击直接复制到输入框（你可以再修改）。
      </p>

      <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3">
        {QUICK_PROMPTS.map((p) => {
          const Icon = p.icon
          return (
            <button
              key={p.title}
              type="button"
              onClick={() => {
                if (navigator.clipboard) {
                  navigator.clipboard.writeText(p.hint).catch(() => {})
                }
              }}
              className="group surface-card surface-card-hover flex flex-col items-start gap-2 rounded-xl p-4 text-left transition-all hover:border-secondary/40"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary/[0.10] text-secondary">
                <Icon className="h-4 w-4" />
              </div>
              <div className="text-[13px] font-semibold text-foreground">
                {p.title}
              </div>
              <div className="line-clamp-3 text-[11px] leading-relaxed text-muted-foreground">
                {p.hint}
              </div>
              <span className="mt-1 text-[10px] text-secondary/80 opacity-0 transition-opacity group-hover:opacity-100">
                已复制到剪贴板，粘贴到输入框即可
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default function MessageList({ messages, streaming, className, reserveRight }: Props) {
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const [following, setFollowing] = useState(true)

  const hasMoreOlder = useSessionsStore((s) => s.hasMoreOlder)
  const loadingOlder = useSessionsStore((s) => s.loadingOlder)
  const loadMoreOlder = useSessionsStore((s) => s.loadMoreOlder)
  const sessionId = useSessionsStore((s) => s.sessionId)

  const lastTopLoadAt = useRef(0)

  const preLoadHeightRef = useRef<number | null>(null)

  const contentSignal = useMemo(() => {
    const last = messages[messages.length - 1]
    const lastLen = last ? last.text.length + (last.steps?.length || 0) : 0
    return `${messages.length}:${lastLen}:${streaming ? 1 : 0}`
  }, [messages, streaming])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onScroll = () => {
      const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
      setFollowing(distanceToBottom <= FOLLOW_THRESHOLD_PX)

      if (
        sessionId &&
        hasMoreOlder &&
        !loadingOlder &&
        el.scrollTop < TOP_LOAD_THRESHOLD_PX &&
        Date.now() - lastTopLoadAt.current > TOP_LOAD_COOLDOWN_MS
      ) {
        lastTopLoadAt.current = Date.now()
        preLoadHeightRef.current = el.scrollHeight
        void loadMoreOlder()
      }
    }
    onScroll()
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [sessionId, hasMoreOlder, loadingOlder, loadMoreOlder])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return

    if (preLoadHeightRef.current != null) {
      const oldHeight = preLoadHeightRef.current
      preLoadHeightRef.current = null
      requestAnimationFrame(() => {
        const delta = el.scrollHeight - oldHeight
        if (delta > 0) {
          el.scrollTop = el.scrollTop + delta
        }
      })
      return
    }
    if (!following) return

    requestAnimationFrame(() => {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    })
  }, [contentSignal, following])

  function jumpToBottom() {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    setFollowing(true)
  }

  return (
    <div
      className={cn(
        'relative flex min-h-0 flex-1 flex-col',
        className,
      )}
    >
      <div
        ref={scrollRef}
        className={cn(
          'flex-1 overflow-y-auto scroll-smooth px-4 py-6 sm:px-8',
          reserveRight && 'lg:pr-[268px]',
        )}
      >
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="mx-auto flex max-w-4xl flex-col gap-6">
            {}
            {sessionId && hasMoreOlder && (
              <div className="-mt-2 mb-2 flex items-center justify-center text-[11px] text-muted-foreground">
                {loadingOlder ? (
                  <span className="inline-flex items-center gap-1.5">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    加载更早消息…
                  </span>
                ) : (
                  <span className="text-muted-foreground/70">
                    继续向上滚动加载更早消息
                  </span>
                )}
              </div>
            )}
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
          </div>
        )}
      </div>

      {}
      {!following && messages.length > 0 && (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center">
          <Button
            type="button"
            size="icon-sm"
            variant="secondary"
            onClick={jumpToBottom}
            className="pointer-events-auto h-8 w-8 rounded-full shadow-card-hover"
            title="跳到最新"
          >
            <ArrowDown className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  )
}

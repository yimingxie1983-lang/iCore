

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  Loader2,
  MessageSquare,
  MoreVertical,
  Pencil,
  Plus,
  Search,
  Trash2,
} from 'lucide-react'

import { useSessionsStore } from '@/application/state/sessionsStore'
import { useChatStore } from '@/application/state/chatStore'
import type { SessionMeta } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/ui/widgets/ui/dropdown-menu'
import { toast } from '@/ui/widgets/ui/sonner'
import { cn, parseBackendTime } from '@/shared/foundation/utils'

function formatTime(iso?: string | null): string {
  if (!iso) return ''
  try {

    const ms = parseBackendTime(iso)
    if (ms == null) return ''
    const d = new Date(ms)
    const now = new Date()
    const sameDay =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate()
    if (sameDay) {
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    const diffDays = Math.floor((now.getTime() - d.getTime()) / (24 * 3600 * 1000))
    if (diffDays < 7) return `${diffDays} 天前`
    return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
  } catch {
    return ''
  }
}

function SessionRow({
  item,
  active,
  running,
  onClick,
  onRename,
  onDelete,
}: {
  item: SessionMeta
  active: boolean

  running: boolean
  onClick: () => void
  onRename: () => void
  onDelete: () => void
}) {
  const displayTitle = item.title || '未命名会话'
  return (
    <div
      onClick={onClick}
      className={cn(
        'group relative cursor-pointer rounded-lg px-2.5 py-2 transition-colors',
        active ? 'bg-primary/[0.08] text-primary' : 'hover:bg-muted',
      )}
    >
      <div className="flex items-start gap-2">
        {running ? (
          <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-secondary" />
        ) : (
          <MessageSquare
            className={cn(
              'mt-0.5 h-3.5 w-3.5 shrink-0',
              active ? 'text-primary' : 'text-muted-foreground',
            )}
          />
        )}
        <div className="min-w-0 flex-1">
          <div
            className={cn(
              'truncate text-[13px] leading-tight',
              active ? 'font-semibold' : 'font-medium text-foreground',
            )}
          >
            {displayTitle}
          </div>
          {item.preview && (
            <div className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground">
              {item.preview}
            </div>
          )}
          <div className="mt-1 flex items-center gap-2 text-[10.5px] text-muted-foreground">
            {running && (
              <span className="font-medium text-secondary">推理中…</span>
            )}
            {item.message_count > 0 && (
              <span>{item.message_count} 条</span>
            )}
            {item.updated_at && <span>{formatTime(item.updated_at)}</span>}
          </div>
        </div>

        {}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              onClick={(e) => e.stopPropagation()}
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded opacity-0 transition-opacity hover:bg-muted group-hover:opacity-100"
            >
              <MoreVertical className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            onClick={(e) => e.stopPropagation()}
          >
            <DropdownMenuItem onSelect={onRename}>
              <Pencil className="mr-1.5 h-3.5 w-3.5" />
              重命名
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={onDelete}
              className="text-rose-600 focus:text-rose-700"
            >
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
              删除
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  )
}

export default function SessionsSidebar({
  projectId,
}: {
  projectId: string
}) {
  const [collapsed, setCollapsed] = useState(false)
  const [query, setQuery] = useState('')

  const list = useSessionsStore((s) => s.list)
  const listLoading = useSessionsStore((s) => s.listLoading)
  const listLoadingMore = useSessionsStore((s) => s.listLoadingMore)
  const listTotal = useSessionsStore((s) => s.listTotal)
  const sessionId = useSessionsStore((s) => s.sessionId)
  const liveSids = useSessionsStore((s) => s.liveSids)
  const loadSession = useSessionsStore((s) => s.loadSession)
  const startNewSession = useSessionsStore((s) => s.startNewSession)
  const renameSession = useSessionsStore((s) => s.renameSession)
  const deleteSession = useSessionsStore((s) => s.deleteSession)
  const refreshList = useSessionsStore((s) => s.refreshSessionList)
  const loadMoreSessions = useSessionsStore((s) => s.loadMoreSessions)

  const listScrollRef = useRef<HTMLDivElement | null>(null)
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  const hasMore = list.length < listTotal
  const canAutoLoadMore = hasMore && !query.trim()

  const activeSessionId = useChatStore((s) => s.activeSessionId)
  const activeStreaming = useChatStore((s) => s.streaming)
  const sessionSlots = useChatStore((s) => s.sessionSlots)

  const isRunning = (sid: string): boolean => {
    if (liveSids.includes(sid)) return true
    if (activeSessionId === sid && activeStreaming) return true
    const slot = sessionSlots[sid]
    return !!slot?.streaming
  }

  useEffect(() => {
    if (projectId) {
      void refreshList()
    }
  }, [projectId, refreshList])

  const refreshLiveSids = useSessionsStore((s) => s.refreshLiveSids)
  useEffect(() => {
    if (!projectId) return
    const timer = window.setInterval(() => {
      void refreshLiveSids()
    }, 10_000)
    return () => window.clearInterval(timer)
  }, [projectId, refreshLiveSids])

  useEffect(() => {
    const sentinel = sentinelRef.current
    const root = listScrollRef.current
    if (!sentinel || !root || !canAutoLoadMore) return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          void loadMoreSessions()
        }
      },
      { root, rootMargin: '120px' },
    )
    io.observe(sentinel)
    return () => io.disconnect()
  }, [canAutoLoadMore, loadMoreSessions, list.length])

  const filtered = useMemo(() => {
    if (!query.trim()) return list
    const q = query.trim().toLowerCase()
    return list.filter(
      (it) =>
        (it.title || '').toLowerCase().includes(q) ||
        (it.preview || '').toLowerCase().includes(q),
    )
  }, [list, query])

  async function onRename(item: SessionMeta) {
    const next = window.prompt('重命名会话', item.title || '')
    if (next == null) return
    const trimmed = next.trim()
    if (!trimmed) {
      toast.error('标题不能为空')
      return
    }
    if (trimmed === (item.title || '')) return
    try {
      await renameSession(item.session_id, trimmed)
      toast.success('已重命名')
    } catch (e: unknown) {
      toast.error(`重命名失败：${e instanceof Error ? e.message : '未知错误'}`)
    }
  }

  async function onDelete(item: SessionMeta) {
    if (
      !window.confirm(
        `确认删除会话「${item.title || '未命名会话'}」？此操作会物理删除 jsonl 文件，不可撤销。`,
      )
    ) {
      return
    }
    try {
      await deleteSession(item.session_id)
      toast.success('已删除')
    } catch (e: unknown) {
      toast.error(`删除失败：${e instanceof Error ? e.message : '未知错误'}`)
    }
  }

  if (collapsed) {
    return (
      <aside className="flex w-12 shrink-0 flex-col items-center gap-2 border-r border-border bg-card/50 py-3">
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setCollapsed(false)}
          title="展开会话抽屉"
        >
          <ChevronRight />
        </Button>
        <Button
          variant="secondary"
          size="icon-sm"
          onClick={startNewSession}
          title="新对话"
        >
          <Plus />
        </Button>
        <div className="mt-2 flex w-full flex-1 flex-col items-center gap-1 overflow-y-auto px-1">
          {list.slice(0, 12).map((it) => {
            const active = it.session_id === sessionId
            const initial = (it.title || '?').slice(0, 1)
            return (
              <button
                key={it.session_id}
                type="button"
                onClick={() => loadSession(it.session_id)}
                title={it.title || '未命名会话'}
                className={cn(
                  'flex h-7 w-7 items-center justify-center rounded-md text-[10.5px] font-semibold transition-colors',
                  active
                    ? 'bg-primary/[0.12] text-primary'
                    : 'bg-muted text-muted-foreground hover:bg-secondary/15 hover:text-secondary',
                  isRunning(it.session_id) && 'animate-pulse ring-2 ring-secondary/50',
                )}
              >
                {initial}
              </button>
            )
          })}
        </div>
      </aside>
    )
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-card/50">
      {}
      <div className="flex shrink-0 items-center gap-1.5 border-b border-border px-3 py-2.5">
        <Button
          variant="secondary"
          size="sm"
          className="flex-1 justify-start"
          onClick={startNewSession}
        >
          <Plus className="mr-1 h-3.5 w-3.5" />
          新对话
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setCollapsed(true)}
          title="折叠抽屉"
        >
          <ChevronLeft />
        </Button>
      </div>

      {}
      <div className="shrink-0 border-b border-border px-3 py-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索会话…"
            className="h-8 w-full rounded-md border border-border bg-card pl-7 pr-2 text-[12.5px] outline-none placeholder:text-muted-foreground focus:border-secondary/50"
          />
        </div>
      </div>

      {}
      <div
        ref={listScrollRef}
        className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2 py-2"
      >
        {listLoading && list.length === 0 && (
          <div className="flex items-center justify-center py-6 text-[11px] text-muted-foreground">
            <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
            加载中…
          </div>
        )}
        {!listLoading && filtered.length === 0 && (
          <div className="px-2 py-6 text-center text-[11px] text-muted-foreground">
            {query ? '没有匹配的会话' : '还没有会话，点上方「新对话」开始'}
          </div>
        )}
        {filtered.map((item) => (
          <SessionRow
            key={item.session_id}
            item={item}
            active={item.session_id === sessionId}
            running={isRunning(item.session_id)}
            onClick={() => loadSession(item.session_id)}
            onRename={() => onRename(item)}
            onDelete={() => onDelete(item)}
          />
        ))}

        {}
        {!query.trim() && hasMore && (
          <div
            ref={sentinelRef}
            className="flex items-center justify-center py-3 text-[11px] text-muted-foreground"
          >
            {listLoadingMore ? (
              <>
                <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
                加载更多…
              </>
            ) : (
              <span>下拉加载更多（{list.length}/{listTotal}）</span>
            )}
          </div>
        )}
        {query.trim() && hasMore && filtered.length > 0 && (
          <div className="px-2 py-3 text-center text-[11px] text-muted-foreground">
            仅在已加载的 {list.length} 个会话中搜索；清空搜索可继续加载更多
          </div>
        )}
      </div>
    </aside>
  )
}

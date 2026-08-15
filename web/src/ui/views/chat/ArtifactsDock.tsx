import { useEffect, useLayoutEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import { Files, PanelRightClose } from 'lucide-react'

import type { ChatMessage } from '@/application/state/chatStore'
import { api } from '@/client/services/client'
import {
  collectConversationArtifacts,
  type ConversationArtifact,
} from '@/shared/helpers/conversationArtifacts'
import { Button } from '@/ui/widgets/ui/button'
import { cn } from '@/shared/foundation/utils'

const STORAGE_KEY = 'icore.chat.artifactsDock.open'
const GAP = 12
const PANEL_WIDTH = 110
const DOCK_HOST_ID = 'icore-artifacts-dock'

function FileName({
  projectId,
  item,
}: {
  projectId: string
  item: ConversationArtifact
}) {
  const [url, setUrl] = useState('')

  useEffect(() => {
    let alive = true
    setUrl('')
    api
      .signFileUrl(projectId, item.path, true)
      .then((u) => {
        if (alive) setUrl(u.url)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [projectId, item.path])

  const className =
    'block truncate rounded px-1 py-0.5 text-[12px] leading-tight text-foreground hover:bg-muted'

  if (!url) {
    return (
      <div className={className} title={item.name}>
        {item.name}
      </div>
    )
  }

  return (
    <a href={url} download={item.name} className={className} title={item.name}>
      {item.name}
    </a>
  )
}

function HalfPane({
  title,
  items,
  projectId,
}: {
  title: string
  items: ConversationArtifact[]
  projectId: string
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="shrink-0 truncate px-1.5 py-1 text-[10.5px] font-medium text-muted-foreground">
        {title}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-0.5 pb-1">
        {items.map((item) => (
          <FileName key={item.id} projectId={projectId} item={item} />
        ))}
      </div>
    </div>
  )
}

function useClampedBox(anchorRef: RefObject<HTMLElement | null>, open: boolean) {
  const [box, setBox] = useState({ top: GAP, right: GAP, width: PANEL_WIDTH, height: 280 })

  useLayoutEffect(() => {
    const place = () => {
      const vw = window.innerWidth
      const vh = window.innerHeight
      const rect = anchorRef.current?.getBoundingClientRect()
      const right = rect ? Math.max(GAP, Math.round(vw - rect.right + GAP)) : GAP
      const width = Math.min(PANEL_WIDTH, Math.max(88, vw - right - GAP))
      const top = rect ? Math.max(GAP, Math.round(rect.top + GAP)) : GAP
      const height = Math.max(160, Math.min(Math.round(vh * 0.4), vh - top - GAP))
      setBox({ top, right, width, height })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    const node = anchorRef.current?.parentElement ?? anchorRef.current
    const ro = node ? new ResizeObserver(place) : null
    if (node) ro?.observe(node)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
      ro?.disconnect()
    }
  }, [anchorRef, open])

  return {
    ...box,
    width: Math.min(box.width, PANEL_WIDTH),
  }
}

interface Props {
  projectId: string
  messages: ChatMessage[]
  open: boolean
  onOpenChange: (open: boolean) => void
}

export default function ArtifactsDock({
  projectId,
  messages,
  open,
  onOpenChange,
}: Props) {
  const { submissions, artifacts } = useMemo(
    () => collectConversationArtifacts(messages),
    [messages],
  )
  const total = submissions.length + artifacts.length
  const anchorRef = useRef<HTMLDivElement>(null)
  const box = useClampedBox(anchorRef, open)
  const [host, setHost] = useState<HTMLElement | null>(null)

  useEffect(() => {
    const existing = document.getElementById(DOCK_HOST_ID)
    if (existing) existing.remove()
    const el = document.createElement('div')
    el.id = DOCK_HOST_ID
    document.body.appendChild(el)
    setHost(el)
    return () => {
      el.remove()
      setHost(null)
    }
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, open ? '1' : '0')
    } catch {
      /* ignore */
    }
  }, [open])

  const dock = open ? (
    <aside
      className="flex flex-col overflow-hidden rounded-xl border border-border bg-card/95 shadow-pop backdrop-blur"
      style={{
        position: 'fixed',
        top: box.top,
        right: box.right,
        width: box.width,
        height: box.height,
        zIndex: 40,
      }}
      aria-label="会话产物"
    >
      <div className="flex shrink-0 items-center gap-0.5 border-b border-border px-1 py-0.5">
        <Files className="h-3 w-3 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-foreground">
          产物
        </span>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="h-5 w-5"
          title="收起"
          onClick={() => onOpenChange(false)}
        >
          <PanelRightClose className="h-3 w-3" />
        </Button>
      </div>
      <HalfPane title="提交物" items={submissions} projectId={projectId} />
      <div className="shrink-0 border-t border-border" />
      <HalfPane title="产出物" items={artifacts} projectId={projectId} />
    </aside>
  ) : (
    <button
      type="button"
      onClick={() => onOpenChange(true)}
      className={cn(
        'inline-flex items-center gap-1 rounded-full border border-border bg-card/95 px-2 py-1 text-[11px] font-medium shadow-card backdrop-blur',
        total > 0
          ? 'text-foreground hover:border-secondary/40 hover:text-secondary'
          : 'text-muted-foreground hover:text-foreground',
      )}
      style={{
        position: 'fixed',
        top: box.top,
        right: box.right,
        zIndex: 40,
      }}
      title="查看提交物与产出物"
    >
      <Files className="h-3.5 w-3.5" />
      产物
      {total > 0 && (
        <span className="min-w-[1rem] rounded-full bg-muted px-1 text-center text-[10px] tabular-nums text-muted-foreground">
          {total}
        </span>
      )}
    </button>
  )

  return (
    <>
      <div
        ref={anchorRef}
        className="pointer-events-none absolute right-0 top-0 h-px w-px"
        aria-hidden
      />
      {host ? createPortal(dock, host) : null}
    </>
  )
}

export function readArtifactsDockOpen(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

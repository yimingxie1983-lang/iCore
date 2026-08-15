import { useEffect, useLayoutEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import { Download, Files, Loader2, PanelRightClose, Upload, Package } from 'lucide-react'

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
const PANEL_WIDTH = 220

function DownloadRow({
  projectId,
  item,
}: {
  projectId: string
  item: ConversationArtifact
}) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState(false)

  useEffect(() => {
    let alive = true
    setUrl('')
    setError(false)
    api
      .signFileUrl(projectId, item.path, true)
      .then((u) => {
        if (alive) setUrl(u.url)
      })
      .catch(() => {
        if (alive) setError(true)
      })
    return () => {
      alive = false
    }
  }, [projectId, item.path])

  if (error) {
    return (
      <div className="flex items-center gap-1.5 px-1 py-0.5 text-[12px] text-muted-foreground">
        <span className="min-w-0 flex-1 truncate" title={item.path}>
          {item.name}
        </span>
        <span className="shrink-0 text-[10px] text-destructive">链接失败</span>
      </div>
    )
  }

  if (!url) {
    return (
      <div className="flex items-center gap-1.5 px-1 py-0.5 text-[12px] text-muted-foreground">
        <span className="min-w-0 flex-1 truncate" title={item.path}>
          {item.name}
        </span>
        <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
      </div>
    )
  }

  return (
    <a
      href={url}
      download={item.name}
      className="flex items-center gap-1.5 rounded px-1 py-0.5 text-[12px] text-foreground transition-colors hover:bg-muted hover:text-secondary"
      title={item.name}
    >
      <span className="min-w-0 flex-1 truncate">{item.name}</span>
      <Download className="h-3 w-3 shrink-0 text-muted-foreground" />
    </a>
  )
}

function FileSection({
  title,
  icon: Icon,
  items,
  projectId,
}: {
  title: string
  icon: typeof Upload
  items: ConversationArtifact[]
  projectId: string
}) {
  return (
    <div>
      <div className="mb-0.5 flex items-center gap-1 px-1 text-[10.5px] font-medium text-muted-foreground">
        <Icon className="h-3 w-3" />
        {title}
      </div>
      <div className="flex flex-col">
        {items.map((item) => (
          <DownloadRow key={item.id} projectId={projectId} item={item} />
        ))}
      </div>
    </div>
  )
}

function useClampedBox(anchorRef: RefObject<HTMLElement | null>) {
  const [box, setBox] = useState({ top: GAP, right: GAP, width: PANEL_WIDTH, maxHeight: 280 })

  useLayoutEffect(() => {
    const place = () => {
      const vw = window.innerWidth
      const vh = window.innerHeight
      const rect = anchorRef.current?.getBoundingClientRect()
      const right = rect ? Math.max(GAP, Math.round(vw - rect.right + GAP)) : GAP
      const width = Math.min(PANEL_WIDTH, Math.max(148, vw - right - GAP))
      const top = rect ? Math.max(GAP, Math.round(rect.top + GAP)) : GAP
      const maxHeight = Math.max(96, Math.min(Math.round(vh * 0.4), vh - top - GAP))
      setBox({ top, right, width, maxHeight })
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
  }, [anchorRef])

  return box
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
  const box = useClampedBox(anchorRef)

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
        maxHeight: box.maxHeight,
        zIndex: 40,
      }}
      aria-label="会话产物"
    >
      <div className="flex shrink-0 items-center gap-1 border-b border-border px-2 py-1">
        <Files className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="flex-1 text-[12px] font-medium text-foreground">产物</span>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="h-6 w-6"
          title="收起"
          onClick={() => onOpenChange(false)}
        >
          <PanelRightClose className="h-3.5 w-3.5" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-1.5 py-1.5">
        {total === 0 ? (
          <div className="px-1 py-1 text-[11px] text-muted-foreground">暂无文件</div>
        ) : (
          <>
            {submissions.length > 0 && (
              <FileSection
                title="提交物"
                icon={Upload}
                items={submissions}
                projectId={projectId}
              />
            )}
            {artifacts.length > 0 && (
              <FileSection
                title="产出物"
                icon={Package}
                items={artifacts}
                projectId={projectId}
              />
            )}
          </>
        )}
      </div>
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
      {createPortal(dock, document.body)}
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

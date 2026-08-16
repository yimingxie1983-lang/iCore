import { useEffect, useMemo, useState } from 'react'
import { Download, Loader2, Package, Upload } from 'lucide-react'

import type { ChatMessage } from '@/application/state/chatStore'
import { api } from '@/client/services/client'
import {
  collectConversationArtifacts,
  type ConversationArtifact,
} from '@/shared/helpers/conversationArtifacts'
import { cn } from '@/shared/foundation/utils'

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
    if (!item.path) {
      setUrl('')
      setError(true)
      return
    }
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

  const className =
    'flex items-center gap-1.5 rounded px-1 py-0.5 text-[12px] leading-5'

  if (error || !item.path) {
    return (
      <div className={cn(className, 'text-muted-foreground')} title={item.name}>
        <span className="min-w-0 flex-1 truncate">{item.name}</span>
      </div>
    )
  }

  if (!url) {
    return (
      <div className={cn(className, 'text-muted-foreground')} title={item.name}>
        <span className="min-w-0 flex-1 truncate">{item.name}</span>
        <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
      </div>
    )
  }

  return (
    <a
      href={url}
      download={item.name}
      className={cn(
        className,
        'text-foreground transition-colors hover:bg-muted hover:text-secondary',
      )}
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
  empty,
}: {
  title: string
  icon: typeof Upload
  items: ConversationArtifact[]
  projectId: string
  empty: string
}) {
  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="mb-0.5 flex items-center gap-1 px-1 text-[11px] font-medium text-muted-foreground">
        <Icon className="h-3 w-3" />
        {title}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {items.length === 0 ? (
          <div className="px-1 py-1 text-[11px] text-muted-foreground">{empty}</div>
        ) : (
          items.map((item) => (
            <DownloadRow key={item.id} projectId={projectId} item={item} />
          ))
        )}
      </div>
    </section>
  )
}

export default function ArtifactsDock({
  projectId,
  messages,
}: {
  projectId: string
  messages: ChatMessage[]
}) {
  const { submissions, artifacts } = useMemo(
    () => collectConversationArtifacts(messages),
    [messages],
  )

  return (
    <aside
      className="pointer-events-auto absolute right-3 top-3 z-20 flex w-[240px] max-h-[min(52vh,calc(100%-1.5rem))] flex-col overflow-hidden rounded-xl border border-border bg-card/95 shadow-card backdrop-blur"
      aria-label="提交物与产出物"
    >
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden px-1.5 py-2">
        <FileSection
          title="提交物"
          icon={Upload}
          items={submissions}
          projectId={projectId}
          empty="暂无提交文件"
        />
        <div className="border-t border-border" />
        <FileSection
          title="产出物"
          icon={Package}
          items={artifacts}
          projectId={projectId}
          empty="暂无产出文件"
        />
      </div>
    </aside>
  )
}

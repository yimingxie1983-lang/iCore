import { useState } from 'react'
import { Download, Loader2, Package, Upload } from 'lucide-react'

import { api } from '@/client/services/client'
import type { ConversationArtifact } from '@/shared/helpers/conversationArtifacts'
import { toast } from '@/ui/widgets/ui/sonner'
import { cn } from '@/shared/foundation/utils'

function DownloadRow({
  projectId,
  item,
}: {
  projectId: string
  item: ConversationArtifact
}) {
  const [busy, setBusy] = useState(false)

  async function onDownload() {
    if (!item.path || busy) return
    setBusy(true)
    try {
      await api.downloadProjectFile(projectId, item.path, item.name)
    } catch (err) {
      toast.error(`无法下载 ${item.name}`, {
        description: err instanceof Error ? err.message : '文件不存在或后端未连接',
      })
    } finally {
      setBusy(false)
    }
  }

  const className =
    'flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left text-[12px] leading-5'

  if (!item.path) {
    return (
      <div className={cn(className, 'text-muted-foreground')} title={item.name}>
        <span className="min-w-0 flex-1 truncate">{item.name}</span>
      </div>
    )
  }

  return (
    <button
      type="button"
      onClick={() => void onDownload()}
      disabled={busy}
      className={cn(
        className,
        'text-foreground transition-colors hover:bg-muted hover:text-secondary disabled:opacity-60',
      )}
      title={`下载 ${item.name}`}
    >
      <span className="min-w-0 flex-1 truncate">{item.name}</span>
      {busy ? (
        <Loader2 className="h-3 w-3 shrink-0 animate-spin text-muted-foreground" />
      ) : (
        <Download className="h-3 w-3 shrink-0 text-muted-foreground" />
      )}
    </button>
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
    <section className="flex flex-col">
      <div className="mb-0.5 flex items-center gap-1 px-1 text-[11px] font-medium text-muted-foreground">
        <Icon className="h-3 w-3" />
        {title}
      </div>
      <div>
        {items.map((item) => (
          <DownloadRow key={item.id} projectId={projectId} item={item} />
        ))}
      </div>
    </section>
  )
}

export default function ArtifactsDock({
  projectId,
  submissions,
  artifacts,
}: {
  projectId: string
  submissions: ConversationArtifact[]
  artifacts: ConversationArtifact[]
}) {
  if (submissions.length === 0 && artifacts.length === 0) return null

  return (
    <aside
      className="pointer-events-auto absolute right-3 top-3 z-20 flex w-[240px] max-h-[min(52vh,calc(100%-1.5rem))] flex-col overflow-hidden rounded-xl border border-border bg-card/95 shadow-card backdrop-blur"
      aria-label="提交物与产出物"
    >
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto px-1.5 py-2">
        {submissions.length > 0 ? (
          <FileSection
            title="提交物"
            icon={Upload}
            items={submissions}
            projectId={projectId}
          />
        ) : null}
        {submissions.length > 0 && artifacts.length > 0 ? (
          <div className="border-t border-border" />
        ) : null}
        {artifacts.length > 0 ? (
          <FileSection
            title="产出物"
            icon={Package}
            items={artifacts}
            projectId={projectId}
          />
        ) : null}
      </div>
    </aside>
  )
}

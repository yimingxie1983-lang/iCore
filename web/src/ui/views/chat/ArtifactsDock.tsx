import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronRight,
  FileCode2,
  FileImage,
  FileJson,
  FileSpreadsheet,
  FileText,
  FileType,
  File as FileIcon,
  Files,
  Loader2,
  LocateFixed,
  Package,
  PanelRightClose,
  Upload,
} from 'lucide-react'

import type { ChatMessage } from '@/application/state/chatStore'
import {
  api,
  type FileRenderKind,
  type PresentedFile,
} from '@/client/services/client'
import {
  collectConversationArtifacts,
  toPresentedFile,
  type ConversationArtifact,
} from '@/shared/helpers/conversationArtifacts'
import PresentedFileCard from '@/ui/widgets/common/PresentedFileCard'
import { Button } from '@/ui/widgets/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/ui/widgets/ui/tabs'
import { useSessionsStore } from '@/application/state/sessionsStore'
import { cn } from '@/shared/foundation/utils'

const STORAGE_KEY = 'icore.chat.artifactsDock.open'

function fmtBytes(n: number): string {
  if (!n || n < 0) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function iconForKind(kind: FileRenderKind) {
  switch (kind) {
    case 'image':
      return FileImage
    case 'markdown':
      return FileText
    case 'code':
      return FileCode2
    case 'csv':
      return FileSpreadsheet
    case 'json':
      return FileJson
    case 'pdf':
      return FileType
    default:
      return FileIcon
  }
}

function useHydratedPresentedFile(
  projectId: string,
  item: ConversationArtifact | null,
): PresentedFile | null {
  const [file, setFile] = useState<PresentedFile | null>(null)

  useEffect(() => {
    if (!item) {
      setFile(null)
      return
    }
    const base = toPresentedFile(item)
    const needsText =
      (base.render_kind === 'markdown' ||
        base.render_kind === 'code' ||
        base.render_kind === 'json') &&
      !base.preview
    if (!needsText) {
      setFile(base)
      return
    }
    let alive = true
    setFile({ ...base, preview: undefined })
    api
      .previewFile(projectId, base.path, { maxLines: 80 })
      .then((resp) => {
        if (!alive) return
        if (resp.kind === 'text') {
          setFile({
            ...base,
            preview: resp.text,
            preview_truncated: resp.truncated,
            mime: base.mime || resp.mime,
            size: base.size || resp.size,
          })
        } else {
          setFile(base)
        }
      })
      .catch(() => {
        if (alive) setFile(base)
      })
    return () => {
      alive = false
    }
  }, [projectId, item?.id, item?.path, item?.presented?.preview, item?.presented?.render_kind])

  return file
}

function FileRow({
  item,
  active,
  onSelect,
}: {
  item: ConversationArtifact
  active: boolean
  onSelect: () => void
}) {
  const kind = toPresentedFile(item).render_kind
  const Icon = iconForKind(kind)
  const sizeLabel = fmtBytes(item.size)

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition-colors',
        active
          ? 'bg-primary/[0.08] ring-1 ring-primary/20'
          : 'hover:bg-muted/80',
      )}
      title={item.path}
    >
      <Icon
        className={cn(
          'mt-0.5 h-3.5 w-3.5 shrink-0',
          active ? 'text-primary' : 'text-muted-foreground',
        )}
      />
      <div className="min-w-0 flex-1">
        <div
          className={cn(
            'truncate text-[12.5px] leading-tight',
            active ? 'font-semibold text-primary' : 'font-medium text-foreground',
          )}
        >
          {item.name}
        </div>
        <div className="mt-0.5 flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
          {item.groupTitle && (
            <span className="max-w-[140px] truncate">{item.groupTitle}</span>
          )}
          {sizeLabel && <span className="shrink-0 tabular-nums">{sizeLabel}</span>}
        </div>
      </div>
    </button>
  )
}

function EmptyList({
  icon: Icon,
  title,
  hint,
}: {
  icon: typeof Upload
  title: string
  hint: string
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
      <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-xl bg-muted text-muted-foreground">
        <Icon className="h-4 w-4" />
      </div>
      <div className="text-[13px] font-medium text-foreground">{title}</div>
      <p className="mt-1 text-[11.5px] leading-relaxed text-muted-foreground">{hint}</p>
    </div>
  )
}

function ArtifactPreview({
  projectId,
  item,
}: {
  projectId: string
  item: ConversationArtifact
}) {
  const presented = useHydratedPresentedFile(projectId, item)

  function locateInChat() {
    const el = document.getElementById(`msg-${item.messageId}`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 items-center gap-1 border-b border-border px-2 py-1">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 gap-1 px-2 text-[11px]"
          title="在对话中定位"
          onClick={locateInChat}
        >
          <LocateFixed className="h-3.5 w-3.5" />
          定位到对话
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {presented ? (
          <PresentedFileCard projectId={projectId} file={presented} />
        ) : (
          <div className="flex items-center justify-center gap-1.5 py-8 text-[12px] text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            加载预览…
          </div>
        )}
      </div>
    </div>
  )
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
  const sessionId = useSessionsStore((s) => s.sessionId)

  const [tab, setTab] = useState<'submissions' | 'artifacts'>('artifacts')
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [pulse, setPulse] = useState(false)
  const prevArtifactCount = useRef(artifacts.length)
  const prevSubmissionCount = useRef(submissions.length)
  const prevSessionKey = useRef<string | null>(null)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, open ? '1' : '0')
    } catch {
      /* ignore */
    }
  }, [open])

  useEffect(() => {
    const key = `${projectId}:${sessionId || ''}`
    const sessionChanged = prevSessionKey.current !== key
    prevSessionKey.current = key
    if (sessionChanged) {
      setSelectedPath(null)
      setPulse(false)
      setTab(
        artifacts.length > 0 || submissions.length === 0
          ? 'artifacts'
          : 'submissions',
      )
      prevArtifactCount.current = artifacts.length
      prevSubmissionCount.current = submissions.length
      return
    }
    const grewArtifacts = artifacts.length > prevArtifactCount.current
    const grewSubmissions = submissions.length > prevSubmissionCount.current
    if (grewArtifacts) {
      setTab('artifacts')
      if (!open) setPulse(true)
    } else if (grewSubmissions) {
      if (!open) setPulse(true)
    }
    prevArtifactCount.current = artifacts.length
    prevSubmissionCount.current = submissions.length
  }, [artifacts.length, submissions.length, open, projectId, sessionId])

  useEffect(() => {
    if (open) setPulse(false)
  }, [open])

  const currentList = tab === 'submissions' ? submissions : artifacts
  const selected =
    currentList.find((f) => f.path === selectedPath) || currentList[0] || null

  useEffect(() => {
    if (!selectedPath && currentList[0]) {
      setSelectedPath(currentList[0].path)
    } else if (
      selectedPath &&
      currentList.length > 0 &&
      !currentList.some((f) => f.path === selectedPath)
    ) {
      setSelectedPath(currentList[0].path)
    }
  }, [currentList, selectedPath])

  if (!open) {
    return (
      <div className="pointer-events-none absolute inset-y-0 right-0 z-20 flex items-start pt-3 pr-3">
        <button
          type="button"
          onClick={() => onOpenChange(true)}
          className={cn(
            'pointer-events-auto inline-flex items-center gap-1.5 rounded-full border bg-card/95 px-2.5 py-1.5 text-[11.5px] font-medium shadow-pop backdrop-blur transition-colors',
            pulse
              ? 'border-secondary/50 text-secondary ring-2 ring-secondary/30'
              : total > 0
                ? 'border-border text-foreground hover:border-secondary/40 hover:text-secondary'
                : 'border-border text-muted-foreground hover:text-foreground',
          )}
          title="查看本会话提交物与产出物"
        >
          <Files className={cn('h-3.5 w-3.5', pulse && 'animate-pulse')} />
          <span>产物</span>
          {total > 0 && (
            <span
              className={cn(
                'min-w-[1.15rem] rounded-full px-1 text-center text-[10px] tabular-nums',
                pulse
                  ? 'bg-secondary text-secondary-foreground'
                  : 'bg-muted text-muted-foreground',
              )}
            >
              {total}
            </span>
          )}
        </button>
      </div>
    )
  }

  return (
    <aside
      className="absolute inset-y-2 right-2 z-20 flex w-[min(380px,calc(100%-1rem))] flex-col overflow-hidden rounded-2xl border border-border bg-card/95 shadow-pop backdrop-blur"
      aria-label="会话产物"
    >
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-2">
        <Package className="h-4 w-4 text-secondary" />
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold leading-tight text-foreground">
            会话产物
          </div>
          <div className="text-[10.5px] text-muted-foreground">
            提交 {submissions.length} · 产出 {artifacts.length}
          </div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          title="收起"
          onClick={() => onOpenChange(false)}
        >
          <PanelRightClose />
        </Button>
      </div>

      <Tabs
        value={tab}
        onValueChange={(v) => setTab(v as 'submissions' | 'artifacts')}
        className="flex min-h-0 flex-1 flex-col"
      >
        <TabsList className="mx-3 mt-2 grid grid-cols-2">
          <TabsTrigger value="submissions" className="gap-1.5">
            <Upload className="h-3.5 w-3.5" />
            提交物
            <span className="rounded-full bg-muted px-1.5 text-[10px] text-muted-foreground">
              {submissions.length}
            </span>
          </TabsTrigger>
          <TabsTrigger value="artifacts" className="gap-1.5">
            <Package className="h-3.5 w-3.5" />
            产出物
            <span className="rounded-full bg-muted px-1.5 text-[10px] text-muted-foreground">
              {artifacts.length}
            </span>
          </TabsTrigger>
        </TabsList>

        <TabsContent
          value="submissions"
          className="mt-0 flex min-h-0 flex-1 flex-col data-[state=inactive]:hidden"
        >
          <DockBody
            projectId={projectId}
            items={submissions}
            selected={tab === 'submissions' ? selected : null}
            emptyIcon={Upload}
            emptyTitle="还没有提交物"
            emptyHint="拖拽或粘贴到对话的文件会出现在这里，方便随时回看。"
            onSelect={(item) => setSelectedPath(item.path)}
          />
        </TabsContent>
        <TabsContent
          value="artifacts"
          className="mt-0 flex min-h-0 flex-1 flex-col data-[state=inactive]:hidden"
        >
          <DockBody
            projectId={projectId}
            items={artifacts}
            selected={tab === 'artifacts' ? selected : null}
            emptyIcon={Package}
            emptyTitle="还没有产出物"
            emptyHint="智能体用 present_file 交付的报告、图表、表格会汇总到这里。"
            onSelect={(item) => setSelectedPath(item.path)}
          />
        </TabsContent>
      </Tabs>
    </aside>
  )
}

function DockBody({
  projectId,
  items,
  selected,
  emptyIcon,
  emptyTitle,
  emptyHint,
  onSelect,
}: {
  projectId: string
  items: ConversationArtifact[]
  selected: ConversationArtifact | null
  emptyIcon: typeof Upload
  emptyTitle: string
  emptyHint: string
  onSelect: (item: ConversationArtifact) => void
}) {
  if (items.length === 0) {
    return (
      <EmptyList icon={emptyIcon} title={emptyTitle} hint={emptyHint} />
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="max-h-[38%] shrink-0 overflow-y-auto border-b border-border px-1.5 py-1">
        {items.map((item) => (
          <FileRow
            key={item.id}
            item={item}
            active={selected?.path === item.path}
            onSelect={() => onSelect(item)}
          />
        ))}
      </div>
      {selected ? (
        <ArtifactPreview projectId={projectId} item={selected} />
      ) : (
        <div className="flex flex-1 items-center justify-center text-[12px] text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            选择一个文件预览
            <ChevronRight className="h-3 w-3" />
          </span>
        </div>
      )}
    </div>
  )
}

export function readArtifactsDockOpen(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

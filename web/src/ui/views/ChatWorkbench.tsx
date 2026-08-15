

import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useDropzone } from 'react-dropzone'
import {
  Activity,
  AlertCircle,
  ArrowRight,
  ArrowUp,
  Brain,
  CheckCircle2,
  ChevronsUpDown,
  Eraser,
  FileText,
  FolderOpen,
  Gauge,
  Loader2,
  PanelRightOpen,
  Paperclip,
  Plus,
  RotateCw,
  Sparkles,
  StopCircle,
  Upload,
  X,
} from 'lucide-react'

import { api, type AttachedFileMeta, type Project } from '@/client/services/client'
import { streamChat } from '@/client/services/sse'
import { abortLiveSubForSession, useSessionsStore } from '@/application/state/sessionsStore'
import { useChatStore } from '@/application/state/chatStore'
import MessageList from './chat/MessageList'
import EventTimeline from './chat/EventTimeline'
import ReasoningPane from './chat/ReasoningPane'
import StatsPanel from './chat/StatsPanel'
import PersonaSwitcher from './chat/PersonaSwitcher'
import SessionsSidebar from './chat/SessionsSidebar'
import GlobalTraceDrawer from './chat/steps/_shared/GlobalTraceDrawer'

import { Button } from '@/ui/widgets/ui/button'
import { Textarea } from '@/ui/widgets/ui/textarea'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/ui/widgets/ui/popover'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/ui/widgets/ui/sheet'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/ui/widgets/ui/tabs'
import { Separator } from '@/ui/widgets/ui/separator'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/ui/widgets/ui/tooltip'
import CreateProjectDialog from '@/ui/widgets/common/CreateProjectDialog'
import { toast } from '@/ui/widgets/ui/sonner'
import { cn } from '@/shared/foundation/utils'

const MASTER_AGENT_ID = 'claw_master'

type AttachmentStatus = 'uploading' | 'success' | 'error'
type AttachmentKind = 'image' | 'file'

interface AttachmentItem {

  id: string

  file: File

  name: string

  size: number

  progress: number
  status: AttachmentStatus

  path?: string

  error?: string

  kind: AttachmentKind

  previewUrl?: string
}

const IMAGE_EXTS = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'])

function detectAttachmentKind(file: File): AttachmentKind {
  const mime = (file.type || '').toLowerCase()
  if (mime.startsWith('image/')) return 'image'
  const dot = file.name.lastIndexOf('.')
  if (dot >= 0) {
    const ext = file.name.slice(dot + 1).toLowerCase()
    if (IMAGE_EXTS.has(ext)) return 'image'
  }
  return 'file'
}

function humanSize(n: number): string {
  if (n < 0 || !Number.isFinite(n)) return '?'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = n
  let i = 0
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return i === 0 ? `${Math.round(size)} ${units[i]}` : `${size.toFixed(1)} ${units[i]}`
}

function AttachmentChip({
  item,
  onRetry,
  onRemove,
}: {
  item: AttachmentItem
  onRetry: (id: string) => void
  onRemove: (id: string) => void
}) {
  const statusClasses: Record<AttachmentStatus, string> = {
    uploading: 'border-border bg-muted/60',
    success: 'border-emerald-500/30 bg-emerald-50',
    error: 'border-rose-500/30 bg-rose-50',
  }
  const Icon =
    item.status === 'uploading'
      ? Loader2
      : item.status === 'error'
        ? AlertCircle
        : CheckCircle2
  const iconColor =
    item.status === 'uploading'
      ? 'text-muted-foreground animate-spin'
      : item.status === 'error'
        ? 'text-rose-600'
        : 'text-emerald-600'

  const isImage = item.kind === 'image' && !!item.previewUrl

  return (
    <div
      className={cn(
        'group relative inline-flex max-w-[260px] items-center gap-1.5 overflow-hidden rounded-lg border px-2 py-1 text-[11.5px]',
        statusClasses[item.status],
      )}
      title={item.error || item.path || item.name}
    >
      <Icon className={cn('h-3.5 w-3.5 shrink-0', iconColor)} />
      {isImage ? (
        <img
          src={item.previewUrl}
          alt={item.name}
          className="h-7 w-7 shrink-0 rounded object-cover ring-1 ring-border"
        />
      ) : (
        <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      )}
      <span className="min-w-0 flex-1 truncate font-medium text-foreground">{item.name}</span>
      <span className="shrink-0 text-[10.5px] text-muted-foreground">
        {item.status === 'uploading' ? `${item.progress}%` : humanSize(item.size)}
      </span>
      {item.status === 'error' && (
        <button
          type="button"
          onClick={() => onRetry(item.id)}
          className="shrink-0 rounded p-0.5 text-rose-600 transition-colors hover:bg-rose-100"
          title={`重试上传${item.error ? `：${item.error}` : ''}`}
        >
          <RotateCw className="h-3 w-3" />
        </button>
      )}
      <button
        type="button"
        onClick={() => onRemove(item.id)}
        className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        title="移除"
      >
        <X className="h-3 w-3" />
      </button>
      {item.status === 'uploading' && (
        <div
          className="absolute bottom-0 left-0 h-0.5 bg-secondary transition-all"
          style={{ width: `${item.progress}%` }}
        />
      )}
    </div>
  )
}

function DropOverlay({ visible }: { visible: boolean }) {
  if (!visible) return null
  return (
    <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center bg-secondary/10 backdrop-blur-[2px]">
      <div className="rounded-2xl border-2 border-dashed border-secondary/60 bg-card/95 px-8 py-6 text-center shadow-xl">
        <Upload className="mx-auto mb-2 h-8 w-8 text-secondary" />
        <div className="text-sm font-semibold text-foreground">释放鼠标上传到当前项目</div>
        <div className="mt-1 text-[12px] text-muted-foreground">
          文件会落到 workspace/uploads/，发送时自动告知 agent
        </div>
      </div>
    </div>
  )
}

function ProjectPicker({
  currentId,
  projects,
  onPick,
  onCreate,
}: {
  currentId: string
  projects: Project[]
  onPick: (id: string) => void
  onCreate: () => void
}) {
  const [open, setOpen] = useState(false)
  const current = projects.find((p) => p.id === currentId)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="group flex h-9 min-w-[220px] max-w-[320px] items-center gap-2 rounded-lg border border-border bg-card px-3 text-sm shadow-card transition-colors hover:border-secondary/50 hover:bg-muted/50"
        >
          <FolderOpen className="h-4 w-4 shrink-0 text-secondary" />
          <div className="flex min-w-0 flex-1 flex-col items-start text-left">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
              当前项目
            </span>
            <span className="w-full truncate text-[13px] font-medium leading-tight text-foreground">
              {current ? current.name : '（未选择项目）'}
            </span>
          </div>
          <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[320px] p-0" align="start">
        <div className="border-b border-border px-3 py-2">
          <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            切换项目（{projects.length}）
          </div>
        </div>
        <div className="max-h-[320px] overflow-y-auto py-1">
          {projects.length === 0 && (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">
              还没有项目，点击下方「新建项目」开始
            </div>
          )}
          {projects.map((p) => {
            const active = p.id === currentId
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => {
                  onPick(p.id)
                  setOpen(false)
                }}
                className={cn(
                  'flex w-full items-start gap-2.5 px-3 py-2 text-left transition-colors hover:bg-muted',
                  active && 'bg-primary/[0.04]',
                )}
              >
                <FolderOpen
                  className={cn(
                    'mt-0.5 h-4 w-4 shrink-0',
                    active ? 'text-primary' : 'text-muted-foreground',
                  )}
                />
                <div className="min-w-0 flex-1">
                  <div
                    className={cn(
                      'truncate text-sm leading-tight',
                      active ? 'font-semibold text-primary' : 'font-medium text-foreground',
                    )}
                  >
                    {p.name}
                  </div>
                  {p.description && (
                    <div className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground">
                      {p.description}
                    </div>
                  )}
                </div>
                {active && (
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-secondary" />
                )}
              </button>
            )
          })}
        </div>
        <Separator />
        <button
          type="button"
          onClick={() => {
            setOpen(false)
            onCreate()
          }}
          className="flex w-full items-center gap-2 px-3 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-primary/[0.06]"
        >
          <Plus className="h-4 w-4" />
          新建项目
        </button>
      </PopoverContent>
    </Popover>
  )
}

function ChatWorkbenchEmpty({
  projects,
  onPickProject,
  onCreate,
}: {
  projects: Project[]
  onPickProject: (id: string) => void
  onCreate: () => void
}) {
  const hasProjects = projects.length > 0

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-10">
      {}
      <div className="hero-surface rounded-2xl px-8 py-10 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/[0.08] text-primary">
          <Sparkles className="h-7 w-7" />
        </div>
        <h2 className="text-2xl font-semibold tracking-tight text-foreground">
          开始一段医学 AI 协作
        </h2>
        <p className="mx-auto mt-2 max-w-xl text-[13px] leading-relaxed text-muted-foreground">
          每个项目是一个独立的工作区（含 workspace / memory / logs）。
          {hasProjects ? '选择下方一个已有项目，或新建一个。' : '先创建你的第一个项目，再开始对话。'}
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          <Button size="lg" onClick={onCreate}>
            <Plus />
            {hasProjects ? '新建项目' : '创建第一个项目'}
          </Button>
        </div>
      </div>

      {}
      {hasProjects && (
        <div className="mt-6">
          <div className="mb-3 flex items-baseline justify-between">
            <h3 className="text-sm font-semibold text-foreground">最近的项目</h3>
            <span className="text-[11px] text-muted-foreground">点击进入对话</span>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {projects.slice(0, 6).map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => onPickProject(p.id)}
                className="group surface-card surface-card-hover flex items-start gap-3 rounded-xl p-4 text-left transition-all hover:border-secondary/40"
              >
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-secondary/[0.10] text-secondary">
                  <FolderOpen className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold text-foreground">
                    {p.name}
                  </div>
                  <div className="mt-0.5 line-clamp-2 text-[12px] text-muted-foreground">
                    {p.description || '—'}
                  </div>
                </div>
                <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-secondary" />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function ChatWorkbench() {
  const { projectId: paramProjectId } = useParams()
  const navigate = useNavigate()

  const [projectId, setProjectId] = useState<string>(paramProjectId || '')
  const [input, setInput] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [insightsOpen, setInsightsOpen] = useState(false)
  const abortRef = useRef<Map<string | null, AbortController>>(new Map())
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const sessionId = useSessionsStore((s) => s.sessionId)
  const setSessionsProject = useSessionsStore((s) => s.setProjectId)
  const acceptSessionStarted = useSessionsStore((s) => s.acceptSessionStarted)
  const refreshSessionList = useSessionsStore((s) => s.refreshSessionList)

  const [attachments, setAttachments] = useState<AttachmentItem[]>([])
  const updateAttachment = useCallback(
    (id: string, patch: Partial<AttachmentItem>) => {
      setAttachments((arr) =>
        arr.map((a) => (a.id === id ? { ...a, ...patch } : a)),
      )
    },
    [],
  )

  const uploadOne = useCallback(
    async (pid: string, item: AttachmentItem) => {
      try {
        const resp = await api.uploadAttachment(pid, item.file, (pct) =>
          updateAttachment(item.id, { progress: pct }),
        )
        updateAttachment(item.id, {
          status: 'success',
          progress: 100,
          path: resp.path,
          name: resp.name,
          size: resp.size,
          error: undefined,
        })
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : '上传失败'
        updateAttachment(item.id, { status: 'error', error: msg })
        toast.error(`上传失败：${item.name} · ${msg}`)
      }
    },
    [updateAttachment],
  )

  const handleFiles = useCallback(
    (files: File[]) => {
      if (!projectId) {
        toast.error('请先选择或新建一个项目，再拖拽文件')
        return
      }
      const fresh: AttachmentItem[] = files.map((f) => {
        const kind = detectAttachmentKind(f)
        return {
          id: `att_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`,
          file: f,
          name: f.name || 'unnamed',
          size: f.size,
          progress: 0,
          status: 'uploading',
          kind,
          previewUrl: kind === 'image' ? URL.createObjectURL(f) : undefined,
        }
      })
      if (fresh.length === 0) return
      setAttachments((arr) => [...arr, ...fresh])
      for (const item of fresh) {
        void uploadOne(projectId, item)
      }
    },
    [projectId, uploadOne],
  )

  const handleRetry = useCallback(
    (id: string) => {
      if (!projectId) return
      const target = attachments.find((a) => a.id === id)
      if (!target) return
      updateAttachment(id, { status: 'uploading', progress: 0, error: undefined })
      void uploadOne(projectId, target)
    },
    [attachments, projectId, updateAttachment, uploadOne],
  )

  const handleRemove = useCallback(
    async (id: string) => {
      const target = attachments.find((a) => a.id === id)
      if (!target) return
      if (target.status === 'success' && target.path) {
        if (!window.confirm(`确认从工作区删除「${target.name}」？此操作不可撤销。`)) {
          return
        }
        try {
          await api.deleteAttachment(projectId, target.path)
        } catch (e: unknown) {
          const msg = e instanceof Error ? e.message : '删除失败'
          toast.error(`删除失败：${msg}`)
          return
        }
      }

      if (target.previewUrl) {
        try {
          URL.revokeObjectURL(target.previewUrl)
        } catch {

        }
      }
      setAttachments((arr) => arr.filter((a) => a.id !== id))
    },
    [attachments, projectId],
  )

  const { getRootProps, isDragActive } = useDropzone({
    noClick: true,
    noKeyboard: true,
    multiple: true,
    onDrop: handleFiles,
    disabled: !projectId,
  })

  const hasUploading = attachments.some((a) => a.status === 'uploading')

  const messages = useChatStore((s) => s.messages)
  const events = useChatStore((s) => s.events)
  const stats = useChatStore((s) => s.stats)
  const streaming = useChatStore((s) => s.streaming)
  const pendingAskUserId = useChatStore((s) => s.pendingAskUserId)
  const pushUser = useChatStore((s) => s.pushUserMessage)
  const beginAssistant = useChatStore((s) => s.beginAssistantTurn)
  const finishAssistant = useChatStore((s) => s.finishAssistantTurn)
  const ingestEvent = useChatStore((s) => s.ingestEvent)
  const resetTurn = useChatStore((s) => s.resetTurn)
  const clearAll = useChatStore((s) => s.clearAll)

  const { data: projects } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.listProjects(),
  })

  useEffect(() => {

    if (paramProjectId && paramProjectId !== projectId) {
      setProjectId(paramProjectId)
    }
  }, [paramProjectId, projectId])

  useEffect(() => {
    void setSessionsProject(projectId || null)
  }, [projectId, setSessionsProject])

  function changeProject(pid: string) {
    setProjectId(pid)
    navigate(pid ? `/chat/${pid}` : `/chat`)
  }

  async function handleSend() {
    const text = input.trim()
    if (!text) return
    if (!projectId) {
      toast.error('请先选择或新建一个项目')
      return
    }
    if (streaming) return
    if (hasUploading) {
      toast.error('还有文件正在上传，请等待上传完成再发送')
      return
    }

    const successAttachments: AttachedFileMeta[] = attachments
      .filter((a) => a.status === 'success' && a.path)
      .map((a) => ({
        name: a.name,
        path: a.path as string,
        size: a.size,
        kind: a.kind,
      }))

    const userAttachmentsMeta = attachments
      .filter((a) => a.status === 'success' && a.path)
      .map((a) => ({
        name: a.name,
        path: a.path as string,
        size: a.size,
        kind: a.kind,
      }))

    setInput('')
    pushUser(text, 'portal', userAttachmentsMeta.length > 0 ? userAttachmentsMeta : undefined)

    for (const a of attachments) {
      if (a.previewUrl) {
        try { URL.revokeObjectURL(a.previewUrl) } catch {  }
      }
    }
    setAttachments([])

    resetTurn()
    const assistantId = beginAssistant()

    const streamSessionId = sessionId ?? null

    let boundSid: string | null = streamSessionId
    const ctrl = new AbortController()
    abortRef.current.set(streamSessionId, ctrl)

    const bindStreamSid = (sid: string) => {
      if (!sid) return
      boundSid = sid
      if (streamSessionId === null) {
        abortRef.current.delete(null)
        abortRef.current.set(sid, ctrl)
      }
    }

    let finalState: 'done' | 'cancelled' | 'error' = 'done'
    let finalErr: string | undefined

    try {
      for await (const ev of streamChat({
        projectId,
        message: text,
        sessionId: sessionId ?? null,
        forceNew: !sessionId,
        attachedFiles: successAttachments.length > 0 ? successAttachments : undefined,
        signal: ctrl.signal,
        onSessionId: bindStreamSid,
      })) {

        if (ev.type === 'session_started') {
          const sid = String((ev as Record<string, unknown>).session_id || '')
          const title = String((ev as Record<string, unknown>).title || '')
          if (sid) {
            acceptSessionStarted(sid, title || undefined)
            bindStreamSid(sid)
          }
          continue
        }
        ingestEvent(assistantId, ev)
        if (ev.type === 'error') {
          const errMsg = String((ev as any).error || (ev as any).content || '推理失败')
          if (errMsg.includes('取消')) {
            finalState = 'cancelled'
          } else {
            finalState = 'error'
          }
          finalErr = errMsg
          break
        }
        if (ev.type === 'done') break
      }
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        finalState = 'cancelled'
        finalErr = '用户中断了流'
      } else {
        finalState = 'error'
        finalErr = e?.message || String(e)
        ingestEvent(assistantId, { type: 'error', error: finalErr })
      }
    } finally {
      finishAssistant(assistantId, finalState, finalErr)

      if (abortRef.current.get(boundSid) === ctrl) {
        abortRef.current.delete(boundSid)
      }
      if (abortRef.current.get(streamSessionId) === ctrl) {
        abortRef.current.delete(streamSessionId)
      }

      if (projectId) {
        void refreshSessionList()
      }
    }
  }

  async function handleStop() {
    const currentSid = useSessionsStore.getState().sessionId
    const ctrl =
      abortRef.current.get(currentSid) ||
      abortRef.current.get(null)

    let cancelSid: string | null = currentSid
    if (!cancelSid) {
      for (const [sid, c] of abortRef.current.entries()) {
        if (c === ctrl && sid) {
          cancelSid = sid
          break
        }
      }
    }

    if (projectId && cancelSid) {
      try {
        await api.cancelSessionRun(projectId, cancelSid)
      } catch {

      }
    }

    if (ctrl) ctrl.abort()
    abortLiveSubForSession(cancelSid, true)
  }

  const allProjects = projects?.items || []
  const noProjectSelected = !projectId || !allProjects.find((p) => p.id === projectId)

  return (
    <div
      {...getRootProps({
        className:
          'relative flex min-h-0 flex-1 flex-col bg-background outline-none',
      })}
    >
      {}
      <DropOverlay visible={isDragActive && !!projectId} />

      {}
      <div className="flex shrink-0 items-center gap-3 border-b border-border bg-card/60 px-4 py-2.5 backdrop-blur">
        <ProjectPicker
          currentId={projectId}
          projects={allProjects}
          onPick={changeProject}
          onCreate={() => setCreateOpen(true)}
        />

        <PersonaSwitcher agentId={MASTER_AGENT_ID} />

        <div className="flex-1" />

        {streaming && (
          <span className="hidden items-center gap-1.5 rounded-full border border-secondary/30 bg-secondary/[0.08] px-2.5 py-1 text-[11px] font-medium text-secondary sm:inline-flex">
            <Loader2 className="h-3 w-3 animate-spin" />
            思考中… {stats.totalEvents > 0 && `· ${stats.totalEvents} 事件`}
          </span>
        )}

        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="outline" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus />
              新建项目
            </Button>
          </TooltipTrigger>
          <TooltipContent>在工作台直接新建项目（不离开页面）</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setInsightsOpen(true)}
              disabled={messages.length === 0 && events.length === 0}
            >
              <PanelRightOpen />
            </Button>
          </TooltipTrigger>
          <TooltipContent>查看链路监控 + Token 计费</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={clearAll}
              disabled={streaming || messages.length === 0}
            >
              <Eraser />
            </Button>
          </TooltipTrigger>
          <TooltipContent>清空全部消息与事件</TooltipContent>
        </Tooltip>
      </div>

      {}
      {noProjectSelected ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <ChatWorkbenchEmpty
            projects={allProjects}
            onPickProject={changeProject}
            onCreate={() => setCreateOpen(true)}
          />
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-row">
          {}
          <SessionsSidebar projectId={projectId} />

          <div className="flex min-h-0 flex-1 flex-col">
          {}
          <MessageList messages={messages} streaming={streaming} />

          {}
          <div className="shrink-0 border-t border-border bg-card/80 px-4 py-3 backdrop-blur sm:px-8 sm:pb-5">
            <div className="mx-auto max-w-4xl">
              <div className="surface-card flex flex-col gap-1.5 rounded-2xl p-2 shadow-card-hover focus-within:border-secondary/50 focus-within:ring-1 focus-within:ring-secondary/30">
                {
}
                {attachments.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 px-1 pt-0.5">
                    {attachments.map((a) => (
                      <AttachmentChip
                        key={a.id}
                        item={a}
                        onRetry={handleRetry}
                        onRemove={handleRemove}
                      />
                    ))}
                  </div>
                )}
                <div className="flex items-end gap-2">
                <Textarea
                  className="min-h-[48px] flex-1 resize-none border-0 bg-transparent px-3 py-2 text-[14px] shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                  rows={2}
                  placeholder={
                    pendingAskUserId
                      ? '智能体正在等你回答上方的问题…'
                      : streaming
                        ? '思考中，按 Esc 可中断…'
                        : '描述任务或提问（Enter 发送 · Shift+Enter 换行）'
                  }
                  value={input}

                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {

                    if (
                      e.key === 'Enter' &&
                      !e.shiftKey &&
                      !e.nativeEvent.isComposing
                    ) {

                      e.preventDefault()
                      handleSend()
                      return
                    }

                    if (e.key === 'Escape' && streaming) {
                      e.preventDefault()
                      handleStop()
                    }
                  }}

                  onPaste={(e) => {
                    const cb = e.clipboardData
                    if (!cb) return
                    const collected: File[] = []
                    if (cb.files && cb.files.length > 0) {
                      for (const f of Array.from(cb.files)) collected.push(f)
                    }
                    if (collected.length === 0 && cb.items) {
                      for (const item of Array.from(cb.items)) {
                        if (item.kind === 'file') {
                          const f = item.getAsFile()
                          if (f) collected.push(f)
                        }
                      }
                    }
                    if (collected.length === 0) return

                    e.preventDefault()
                    const tsBase = new Date()
                      .toISOString()
                      .replace(/[-:.TZ]/g, '')
                      .slice(0, 14)
                    const renamed = collected.map((f, idx) => {
                      const isGenericImage =
                        !f.name || f.name === 'image.png' || f.name === 'unknown'
                      if (!isGenericImage) return f
                      const ext = (f.type.split('/')[1] || 'bin').toLowerCase()
                      const suffix = collected.length > 1 ? `_${idx + 1}` : ''
                      return new File(
                        [f],
                        `paste_${tsBase}${suffix}.${ext}`,
                        { type: f.type },
                      )
                    })
                    handleFiles(renamed)
                  }}
                />
                {}
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    const files = Array.from(e.target.files || [])
                    if (files.length > 0) handleFiles(files)
                    e.target.value = ''
                  }}
                />
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-10 w-10 shrink-0 rounded-xl"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={!projectId || streaming}
                      title="附件（可拖拽到对话页）"
                    >
                      <Paperclip className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    点击选择或直接拖拽文件到对话页（落到 workspace/uploads/）
                  </TooltipContent>
                </Tooltip>
                {streaming ? (
                  <Button
                    variant="destructive"
                    size="icon"
                    className="h-10 w-10 shrink-0 rounded-xl"
                    onClick={handleStop}
                    title="停止 (Esc)"
                  >
                    <StopCircle />
                  </Button>
                ) : (
                  <Button
                    size="icon"
                    className="h-10 w-10 shrink-0 rounded-xl"
                    onClick={handleSend}
                    disabled={!input.trim() || hasUploading}
                    title={hasUploading ? '附件上传中，请稍候' : '发送 (Enter)'}
                  >
                    <ArrowUp className="h-4 w-4" />
                  </Button>
                )}
                </div>
              </div>
              <div className="mt-1.5 flex items-center justify-between px-2 text-[11px] text-muted-foreground">
                <span className="inline-flex items-center gap-2">
                  <span>
                    <kbd className="rounded border border-border bg-card px-1 font-mono text-[10px]">Enter</kbd> 发送
                    · <kbd className="rounded border border-border bg-card px-1 font-mono text-[10px]">Shift</kbd>
                    +<kbd className="rounded border border-border bg-card px-1 font-mono text-[10px]">Enter</kbd> 换行
                    {streaming && (
                      <>
                        · <kbd className="rounded border border-border bg-card px-1 font-mono text-[10px]">Esc</kbd> 停止
                      </>
                    )}
                  </span>
                  <span className="text-muted-foreground/70">
                    · 已收到 {events.length} 条事件
                    {stats.totalTokens > 0 && ` · ${stats.totalTokens.toLocaleString()} tokens`}
                    {attachments.length > 0 && (
                      <span
                        className={cn(
                          'ml-1',
                          hasUploading ? 'text-secondary' : 'text-emerald-600',
                        )}
                      >
                        · 附件 {attachments.filter((a) => a.status === 'success').length}/
                        {attachments.length} 就绪
                        {hasUploading && '（上传中…）'}
                      </span>
                    )}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => setInsightsOpen(true)}
                  disabled={messages.length === 0 && events.length === 0}
                  className="inline-flex items-center gap-1 text-muted-foreground transition-colors hover:text-secondary disabled:opacity-50"
                >
                  <Brain className="h-3 w-3" />
                  看 AI 的推理过程
                </button>
              </div>
            </div>
          </div>
          </div>
        </div>
      )}

      {}
      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />

      {}
      <Sheet open={insightsOpen} onOpenChange={setInsightsOpen}>
        <SheetContent side="right" className="flex w-full flex-col p-0 sm:max-w-md">
          <SheetHeader className="border-b border-border pb-3">
            <SheetTitle>对话洞察</SheetTitle>
            <SheetDescription>
              链路监控与 Token 计费实时同步，发送消息时自动刷新
            </SheetDescription>
          </SheetHeader>
          {}
          <Tabs defaultValue="reasoning" className="flex min-h-0 flex-1 flex-col">
            <TabsList className="mx-5 mt-3 grid grid-cols-3">
              <TabsTrigger value="reasoning" className="gap-1.5">
                <Brain className="h-3.5 w-3.5" />
                推理过程
              </TabsTrigger>
              <TabsTrigger value="timeline" className="gap-1.5">
                <Activity className="h-3.5 w-3.5" />
                链路监控
                <span className="ml-1 rounded-full bg-muted px-1.5 text-[10px] text-muted-foreground">
                  {events.length}
                </span>
              </TabsTrigger>
              <TabsTrigger value="stats" className="gap-1.5">
                <Gauge className="h-3.5 w-3.5" />
                Token 统计
              </TabsTrigger>
            </TabsList>
            <TabsContent value="reasoning" className="min-h-0 flex-1 overflow-hidden px-4 pb-4">
              <ReasoningPane events={events} streaming={streaming} />
            </TabsContent>
            <TabsContent value="timeline" className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
              <EventTimeline events={events} />
            </TabsContent>
            <TabsContent value="stats" className="min-h-0 flex-1 overflow-y-auto px-5 pb-4">
              <StatsPanel stats={stats} streaming={streaming} />
            </TabsContent>
          </Tabs>
        </SheetContent>
      </Sheet>

      {}
      <GlobalTraceDrawer />
    </div>
  )
}


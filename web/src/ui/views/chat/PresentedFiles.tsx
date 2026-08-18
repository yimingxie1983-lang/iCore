import { useEffect, useState, type MouseEvent } from 'react'
import {
  Download,
  Expand,
  FileSpreadsheet,
  FileText,
  Image as ImageIcon,
  Loader2,
  Package,
} from 'lucide-react'

import type {
  FilePresentation,
  FilePreviewResp,
  FileRenderKind,
  PresentedFile,
} from '@/client/services/client'
import { api } from '@/client/services/client'
import { inferRenderKind } from '@/shared/helpers/conversationArtifacts'
import MarkdownRenderer from '@/ui/widgets/common/MarkdownRenderer'
import { Button } from '@/ui/widgets/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/ui/widgets/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/ui/widgets/ui/table'
import { toast } from '@/ui/widgets/ui/sonner'
import { cn } from '@/shared/foundation/utils'

const KIND_LABEL: Record<FileRenderKind, string> = {
  image: '图片',
  markdown: '文档',
  code: '代码',
  csv: '表格',
  json: 'JSON',
  pdf: 'PDF',
  docx: 'Word',
  xlsx: 'Excel',
  pptx: 'PPT',
  download: '文件',
}

function fmtBytes(n?: number): string {
  if (!n || n <= 0) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function fenceLang(name: string): string {
  const ext = (name.split('.').pop() || '').toLowerCase()
  const map: Record<string, string> = {
    py: 'python',
    md: 'markdown',
    markdown: 'markdown',
    ts: 'ts',
    tsx: 'tsx',
    js: 'js',
    json: 'json',
    yml: 'yaml',
    yaml: 'yaml',
    r: 'r',
    sql: 'sql',
    sh: 'bash',
    bash: 'bash',
    txt: 'text',
    log: 'text',
  }
  return map[ext] || ext || 'text'
}

function KindIcon({ kind }: { kind: FileRenderKind }) {
  const className = 'h-3.5 w-3.5 shrink-0 text-muted-foreground'
  if (kind === 'image') return <ImageIcon className={className} />
  if (kind === 'csv' || kind === 'xlsx') return <FileSpreadsheet className={className} />
  if (kind === 'pdf' || kind === 'pptx' || kind === 'download') {
    return <Package className={className} />
  }
  return <FileText className={className} />
}

async function downloadFile(projectId: string, file: PresentedFile) {
  await api.downloadProjectFile(projectId, file.path, file.name)
}

function DownloadButton({
  projectId,
  file,
}: {
  projectId: string
  file: PresentedFile
}) {
  const [busy, setBusy] = useState(false)

  async function onDownload(event: MouseEvent) {
    event.stopPropagation()
    if (!file.path || busy) return
    setBusy(true)
    try {
      await downloadFile(projectId, file)
    } catch (err) {
      toast.error(`无法下载 ${file.name}`, {
        description: err instanceof Error ? err.message : '文件不存在或后端未连接',
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      onClick={(event) => void onDownload(event)}
      disabled={busy || !file.path}
      title={`下载 ${file.name}`}
    >
      {busy ? <Loader2 className="animate-spin" /> : <Download />}
    </Button>
  )
}

function useSignedUrl(projectId: string, path: string, enabled: boolean) {
  const [src, setSrc] = useState('')
  useEffect(() => {
    if (!enabled || !projectId || !path) return
    let alive = true
    setSrc('')
    api
      .signFileUrl(projectId, path, false)
      .then((u) => {
        if (alive) setSrc(u.url)
      })
      .catch(() => {
        if (alive) setSrc('')
      })
    return () => {
      alive = false
    }
  }, [enabled, projectId, path])
  return src
}

function ImagePreview({
  projectId,
  file,
  large,
}: {
  projectId: string
  file: PresentedFile
  large?: boolean
}) {
  const src = useSignedUrl(projectId, file.path, true)
  if (!src) {
    return (
      <div
        className={cn(
          'flex items-center justify-center rounded bg-muted/60 text-[12px] text-muted-foreground',
          large ? 'h-64' : 'h-36',
        )}
      >
        正在加载图片…
      </div>
    )
  }
  return (
    <img
      src={src}
      alt={file.name}
      className={cn(
        'w-full rounded object-contain',
        large ? 'max-h-[70vh]' : 'max-h-56',
      )}
    />
  )
}

function PdfPreview({
  projectId,
  file,
  large,
}: {
  projectId: string
  file: PresentedFile
  large?: boolean
}) {
  const src = useSignedUrl(projectId, file.path, true)
  if (!src) {
    return (
      <div className="rounded bg-muted/60 px-3 py-6 text-center text-[12px] text-muted-foreground">
        正在加载 PDF…
      </div>
    )
  }
  return (
    <iframe
      title={file.name}
      src={src}
      className={cn(
        'w-full rounded border border-border bg-card',
        large ? 'h-[70vh]' : 'h-64',
      )}
    />
  )
}

function TextSnippet({
  file,
  text,
  compact,
}: {
  file: PresentedFile
  text: string
  compact?: boolean
}) {
  if (file.render_kind === 'markdown') {
    return <MarkdownRenderer text={text} compact={compact} />
  }
  const lang = file.render_kind === 'json' ? 'json' : fenceLang(file.name)
  return <MarkdownRenderer text={'```' + lang + '\n' + text + '\n```'} compact={compact} />
}

function CsvTable({
  columns,
  rows,
}: {
  columns: string[]
  rows: string[][]
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          {columns.map((col, i) => (
            <TableHead key={`${col}:${i}`}>{col}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, i) => (
          <TableRow key={i}>
            {row.map((cell, j) => (
              <TableCell key={j} className="max-w-[240px] truncate font-mono text-[11.5px]">
                {cell}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function isOfficeKind(kind: FileRenderKind) {
  return kind === 'docx' || kind === 'xlsx' || kind === 'pptx'
}

function DocxView({
  preview,
  compact,
}: {
  preview: Extract<FilePreviewResp, { kind: 'docx' }>
  compact?: boolean
}) {
  const paras = compact ? preview.paragraphs.slice(0, 8) : preview.paragraphs
  const tables = compact ? preview.tables.slice(0, 1) : preview.tables
  return (
    <div className="space-y-3">
      {paras.map((p, i) => (
        <p key={i} className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground">
          {p}
        </p>
      ))}
      {tables.map((table, ti) => (
        <CsvTable
          key={ti}
          columns={table[0] || []}
          rows={table.slice(1)}
        />
      ))}
      {compact && (preview.paragraphs.length > 8 || preview.truncated) ? (
        <div className="text-[11px] text-muted-foreground">已截断，点击展开查看更多</div>
      ) : preview.truncated ? (
        <div className="text-[11px] text-muted-foreground">已截断</div>
      ) : null}
    </div>
  )
}

function XlsxView({
  preview,
  compact,
}: {
  preview: Extract<FilePreviewResp, { kind: 'xlsx' }>
  compact?: boolean
}) {
  const sheets = compact ? preview.sheets.slice(0, 1) : preview.sheets
  return (
    <div className="space-y-4">
      {sheets.map((sheet) => (
        <div key={sheet.name}>
          <div className="mb-1 text-[12px] font-medium text-foreground">{sheet.name}</div>
          <CsvTable
            columns={sheet.columns}
            rows={compact ? sheet.rows.slice(0, 8) : sheet.rows}
          />
          {sheet.truncated || (compact && sheet.rows.length > 8) ? (
            <div className="mt-1 text-[11px] text-muted-foreground">仅显示部分行</div>
          ) : null}
        </div>
      ))}
    </div>
  )
}

function PptxView({
  preview,
  compact,
}: {
  preview: Extract<FilePreviewResp, { kind: 'pptx' }>
  compact?: boolean
}) {
  const slides = compact ? preview.slides.slice(0, 2) : preview.slides
  return (
    <div className="space-y-2">
      {slides.map((slide) => (
        <div
          key={slide.index}
          className="rounded-md border border-border bg-card px-3 py-2"
        >
          <div className="text-[11px] text-muted-foreground">幻灯片 {slide.index}</div>
          <div className="text-[13px] font-medium text-foreground">{slide.title}</div>
          {slide.body ? (
            <div className="mt-1 whitespace-pre-wrap text-[12.5px] leading-relaxed text-muted-foreground">
              {compact ? slide.body.slice(0, 280) : slide.body}
            </div>
          ) : null}
        </div>
      ))}
      {compact && preview.slides.length > 2 ? (
        <div className="text-[11px] text-muted-foreground">
          共 {preview.slides.length} 页，点击展开查看全部
        </div>
      ) : null}
    </div>
  )
}

function OfficePreview({
  projectId,
  file,
  compact,
}: {
  projectId: string
  file: PresentedFile
  compact?: boolean
}) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [full, setFull] = useState<FilePreviewResp | null>(null)

  useEffect(() => {
    if (!projectId || !file.path) return
    let alive = true
    setLoading(true)
    setError('')
    api
      .previewFile(projectId, file.path)
      .then((resp) => {
        if (alive) setFull(resp)
      })
      .catch((err) => {
        if (alive) setError(err instanceof Error ? err.message : '无法加载预览')
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [projectId, file.path])

  if (loading) {
    return (
      <div
        className={cn(
          'flex items-center gap-2 text-[12px] text-muted-foreground',
          compact ? 'py-3' : 'py-8 text-[13px]',
        )}
      >
        <Loader2 className="h-4 w-4 animate-spin" />
        正在解析 Office 文件…
      </div>
    )
  }
  if (full?.kind === 'docx') return <DocxView preview={full} compact={compact} />
  if (full?.kind === 'xlsx') return <XlsxView preview={full} compact={compact} />
  if (full?.kind === 'pptx') return <PptxView preview={full} compact={compact} />
  if (full?.kind === 'text' && full.text) {
    return <TextSnippet file={file} text={full.text} compact={compact} />
  }
  if (error) {
    if (file.preview) {
      return (
        <div>
          <TextSnippet file={{ ...file, render_kind: 'markdown' }} text={file.preview} compact={compact} />
          <div className="mt-1 text-[11px] text-muted-foreground">{error}</div>
        </div>
      )
    }
    return <div className="text-[12px] text-muted-foreground">{error}</div>
  }
  if (file.preview) {
    return <TextSnippet file={{ ...file, render_kind: 'markdown' }} text={file.preview} compact={compact} />
  }
  return <div className="text-[12px] text-muted-foreground">无法预览该 Office 文件，请下载后查看。</div>
}

function InlineBody({ projectId, file }: { projectId: string; file: PresentedFile }) {
  if (file.render_kind === 'image') {
    return <ImagePreview projectId={projectId} file={file} />
  }
  if (file.render_kind === 'pdf') {
    return <PdfPreview projectId={projectId} file={file} />
  }
  if (isOfficeKind(file.render_kind)) {
    return (
      <div className="max-h-56 overflow-auto">
        <OfficePreview projectId={projectId} file={file} compact />
      </div>
    )
  }
  if (file.preview) {
    return (
      <div className="max-h-56 overflow-auto">
        <TextSnippet file={file} text={file.preview} compact />
        {file.preview_truncated ? (
          <div className="mt-1 text-[11px] text-muted-foreground">已截断，点击展开查看更多</div>
        ) : null}
      </div>
    )
  }
  if (file.render_kind === 'download') {
    return (
      <div className="text-[12px] text-muted-foreground">
        该文件适合直接下载。点文件名或展开可尝试预览。
      </div>
    )
  }
  return (
    <div className="text-[12px] text-muted-foreground">
      点击展开从服务器加载预览。
    </div>
  )
}

function DialogBody({
  projectId,
  file,
}: {
  projectId: string
  file: PresentedFile
}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [full, setFull] = useState<FilePreviewResp | null>(null)

  const needsFetch =
    file.render_kind === 'markdown' ||
    file.render_kind === 'code' ||
    file.render_kind === 'json' ||
    file.render_kind === 'csv'

  useEffect(() => {
    if (!needsFetch || !projectId || !file.path) return
    let alive = true
    setLoading(true)
    setError('')
    api
      .previewFile(projectId, file.path)
      .then((resp) => {
        if (alive) setFull(resp)
      })
      .catch((err) => {
        if (alive) {
          setError(err instanceof Error ? err.message : '无法加载预览')
        }
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [needsFetch, projectId, file.path])

  if (file.render_kind === 'image') {
    return <ImagePreview projectId={projectId} file={file} large />
  }
  if (file.render_kind === 'pdf') {
    return <PdfPreview projectId={projectId} file={file} large />
  }
  if (isOfficeKind(file.render_kind)) {
    return <OfficePreview projectId={projectId} file={file} />
  }
  if (loading) {
    return (
      <div className="flex items-center gap-2 px-1 py-8 text-[13px] text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        正在加载预览…
      </div>
    )
  }
  if (full?.kind === 'csv') {
    return (
      <div className="max-h-[70vh] overflow-auto">
        <CsvTable columns={full.columns} rows={full.rows} />
        {full.truncated ? (
          <div className="mt-2 text-[11px] text-muted-foreground">仅显示部分行</div>
        ) : null}
      </div>
    )
  }
  if (full?.kind === 'text') {
    return (
      <div className="max-h-[70vh] overflow-auto">
        <TextSnippet file={file} text={full.text} />
        {full.truncated ? (
          <div className="mt-2 text-[11px] text-muted-foreground">已截断</div>
        ) : null}
      </div>
    )
  }
  if (error) {
    if (file.preview) {
      return (
        <div className="max-h-[70vh] overflow-auto">
          <TextSnippet file={file} text={file.preview} />
          <div className="mt-2 text-[11px] text-muted-foreground">{error}</div>
        </div>
      )
    }
    return (
      <div className="px-1 py-6 text-[13px] text-muted-foreground">
        {error}。请改用下载。
      </div>
    )
  }
  if (file.preview) {
    return (
      <div className="max-h-[70vh] overflow-auto">
        <TextSnippet file={file} text={file.preview} />
      </div>
    )
  }
  return (
    <div className="px-1 py-6 text-[13px] text-muted-foreground">
      该文件无法在线预览，请下载后查看。
    </div>
  )
}

export function FilePreviewDialog({
  projectId,
  file: raw,
  open,
  onOpenChange,
}: {
  projectId: string
  file: PresentedFile | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  if (!raw) return null
  const file: PresentedFile = {
    ...raw,
    render_kind: inferRenderKind(raw.name || raw.path, raw.render_kind),
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[88vh] w-[min(52rem,calc(100vw-1.5rem))] max-w-none flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="flex flex-row items-start gap-3 border-b border-border px-5 py-3 pr-12">
          <div className="min-w-0 flex-1">
            <DialogTitle className="truncate text-[15px]">{file.name}</DialogTitle>
            <DialogDescription>
              {[KIND_LABEL[file.render_kind], fmtBytes(file.size)].filter(Boolean).join(' · ')}
            </DialogDescription>
          </div>
          <DownloadButton projectId={projectId} file={file} />
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-auto px-5 py-3">
          {open ? <DialogBody projectId={projectId} file={file} /> : null}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function FileCard({
  projectId,
  file: raw,
}: {
  projectId: string
  file: PresentedFile
}) {
  const file: PresentedFile = {
    ...raw,
    render_kind: inferRenderKind(raw.name || raw.path, raw.render_kind),
  }
  const [open, setOpen] = useState(false)
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card-muted/50">
      <div className="flex items-center gap-2 border-b border-border/70 px-3 py-1.5">
        <KindIcon kind={file.render_kind} />
        <button
          type="button"
          className="min-w-0 flex-1 text-left"
          onClick={() => setOpen(true)}
          title={`预览 ${file.name}`}
        >
          <div className="truncate text-[13px] font-medium text-foreground">{file.name}</div>
          <div className="text-[10.5px] text-muted-foreground">
            {[KIND_LABEL[file.render_kind], fmtBytes(file.size)].filter(Boolean).join(' · ')}
          </div>
        </button>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={() => setOpen(true)}
          title={`预览 ${file.name}`}
        >
          <Expand />
        </Button>
        <DownloadButton projectId={projectId} file={file} />
      </div>
      <div className="px-3 py-2">
        <InlineBody projectId={projectId} file={file} />
      </div>
      <FilePreviewDialog
        projectId={projectId}
        file={file}
        open={open}
        onOpenChange={setOpen}
      />
    </div>
  )
}

export default function PresentedFilesBlock({
  projectId,
  groups,
}: {
  projectId: string
  groups: FilePresentation[]
}) {
  if (!groups.length) return null
  return (
    <div className="space-y-3">
      {groups.map((group, index) => (
        <section key={`${group.title || 'files'}:${index}`} className="space-y-2">
          {(group.title || group.description) && (
            <div className="px-0.5">
              {group.title ? (
                <div className="text-[12.5px] font-semibold text-foreground">{group.title}</div>
              ) : null}
              {group.description ? (
                <div className="text-[11.5px] text-muted-foreground">{group.description}</div>
              ) : null}
            </div>
          )}
          <div className="space-y-2">
            {group.files.map((file) => (
              <FileCard
                key={file.path || file.name}
                projectId={projectId}
                file={file}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

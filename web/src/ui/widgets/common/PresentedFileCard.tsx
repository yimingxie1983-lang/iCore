

import { useEffect, useState } from 'react'
import {
  Download,
  ExternalLink,
  FileCode2,
  FileImage,
  FileJson,
  FileSpreadsheet,
  FileText,
  FileType,
  File as FileIcon,
  Loader2,
  Maximize2,
} from 'lucide-react'

import { api, type FilePreviewResp, type PresentedFile } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import MarkdownRenderer from '@/ui/widgets/common/MarkdownRenderer'
import { cn } from '@/shared/foundation/utils'

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function iconFor(file: PresentedFile) {
  switch (file.render_kind) {
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

function langFromName(name: string): string {
  const ext = (name.split('.').pop() || '').toLowerCase()
  const MAP: Record<string, string> = {
    py: 'python',
    js: 'javascript',
    ts: 'typescript',
    tsx: 'tsx',
    jsx: 'javascript',
    sh: 'bash',
    bash: 'bash',
    zsh: 'bash',
    r: 'r',
    sql: 'sql',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    md: 'markdown',
    markdown: 'markdown',
    txt: '',
    log: '',
  }
  return MAP[ext] ?? ''
}

interface CardProps {
  projectId: string
  file: PresentedFile
}

export default function PresentedFileCard({ projectId, file }: CardProps) {
  const Icon = iconFor(file)
  const [signed, setSigned] = useState<{ raw?: string; download?: string }>({})

  useEffect(() => {
    let cancelled = false
    setSigned({})
    api
      .signFileUrl(projectId, file.path)
      .then((u) => {
        if (!cancelled) setSigned((s) => ({ ...s, raw: u.url }))
      })
      .catch(() => {})
    api
      .signFileUrl(projectId, file.path, true)
      .then((u) => {
        if (!cancelled) setSigned((s) => ({ ...s, download: u.url }))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [projectId, file.path])

  const rawUrl = signed.raw
  const downloadUrl = signed.download

  return (
    <div className="not-prose rounded-lg border border-border bg-card shadow-sm">
      {}
      <div className="flex items-center gap-2 border-b border-border bg-card-muted px-3 py-1.5">
        <Icon className="h-3.5 w-3.5 shrink-0 text-secondary" />
        <span className="truncate font-mono text-[11.5px] font-medium text-foreground">
          {file.name}
        </span>
        <span className="shrink-0 font-mono text-[10.5px] text-muted-foreground/80">
          {fmtBytes(file.size)}
        </span>
        <span className="shrink-0 rounded border border-border/80 px-1 py-[1px] font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
          {file.render_kind}
        </span>
        <span className="flex-1" />
        <Button
          asChild
          variant="ghost"
          size="icon-sm"
          className="h-6 w-6"
          title="在新标签打开"
        >
          <a
            href={rawUrl}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => {
              if (!rawUrl) e.preventDefault()
            }}
          >
            <ExternalLink className="h-3 w-3" />
          </a>
        </Button>
        <Button
          asChild
          variant="ghost"
          size="icon-sm"
          className="h-6 w-6"
          title="下载"
        >
          <a
            href={downloadUrl}
            download
            onClick={(e) => {
              if (!downloadUrl) e.preventDefault()
            }}
          >
            <Download className="h-3 w-3" />
          </a>
        </Button>
      </div>

      {}
      {rawUrl ? (
        <PreviewBody projectId={projectId} file={file} rawUrl={rawUrl} />
      ) : (
        <div className="flex items-center justify-center p-6 text-xs text-muted-foreground">
          正在生成访问链接…
        </div>
      )}
    </div>
  )
}

function PreviewBody({
  projectId,
  file,
  rawUrl,
}: {
  projectId: string
  file: PresentedFile
  rawUrl: string
}) {
  switch (file.render_kind) {
    case 'image':
      return <ImagePreview rawUrl={rawUrl} name={file.name} />
    case 'markdown':
      return <MarkdownPreview file={file} />
    case 'code':
      return <CodePreview file={file} />
    case 'csv':
      return <CsvPreview projectId={projectId} file={file} />
    case 'json':
      return <JsonPreview file={file} />
    case 'pdf':
      return <PdfPreview rawUrl={rawUrl} />
    case 'download':
    default:
      return <DownloadHint file={file} rawUrl={rawUrl} />
  }
}

function ImagePreview({ rawUrl, name }: { rawUrl: string; name: string }) {
  return (
    <div className="flex max-h-[400px] items-center justify-center overflow-hidden bg-muted/30 p-2">
      {}
      <a href={rawUrl} target="_blank" rel="noopener noreferrer" title="点击打开原图">
        <img
          src={rawUrl}
          alt={name}
          loading="lazy"
          className="max-h-[380px] max-w-full rounded object-contain"
        />
      </a>
    </div>
  )
}

function MarkdownPreview({ file }: { file: PresentedFile }) {
  const text = file.preview || ''
  if (!text) {
    return <EmptyPreview msg="(空文件)" />
  }
  return (
    <div className="max-h-[400px] overflow-auto px-4 py-2">
      <MarkdownRenderer text={text} compact />
      {file.preview_truncated && <TruncatedFooter />}
    </div>
  )
}

function CodePreview({ file }: { file: PresentedFile }) {
  const text = file.preview || ''
  const lang = langFromName(file.name)
  if (!text) {
    return <EmptyPreview msg="(空文件)" />
  }

  const md = '```' + lang + '\n' + text + '\n```'
  return (
    <div className="max-h-[400px] overflow-auto px-2 py-1.5">
      <MarkdownRenderer text={md} compact />
      {file.preview_truncated && <TruncatedFooter />}
    </div>
  )
}

function JsonPreview({ file }: { file: PresentedFile }) {
  const text = file.preview || ''
  if (!text) return <EmptyPreview msg="(空文件)" />

  let pretty = text
  try {
    pretty = JSON.stringify(JSON.parse(text), null, 2)
  } catch {

  }
  const md = '```json\n' + pretty + '\n```'
  return (
    <div className="max-h-[400px] overflow-auto px-2 py-1.5">
      <MarkdownRenderer text={md} compact />
      {file.preview_truncated && <TruncatedFooter />}
    </div>
  )
}

function CsvPreview({
  projectId,
  file,
}: {
  projectId: string
  file: PresentedFile
}) {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<{ columns: string[]; rows: string[][]; truncated: boolean } | null>(null)
  const [err, setErr] = useState<string>('')

  useEffect(() => {
    let alive = true
    setLoading(true)
    api
      .previewFile(projectId, file.path, { maxLines: 50 })
      .then((resp) => {
        if (!alive) return
        if (resp.kind !== 'csv') {
          setErr('返回类型不是 csv')
          return
        }
        setData({
          columns: resp.columns,
          rows: resp.rows,
          truncated: resp.truncated,
        })
      })
      .catch((e) => {
        if (!alive) return
        setErr(e instanceof Error ? e.message : String(e))
      })
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [projectId, file.path])

  if (loading) {
    return (
      <div className="flex items-center gap-2 px-4 py-3 text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        <span className="text-[12px]">解析表格中…</span>
      </div>
    )
  }
  if (err || !data) {
    return (
      <div className="px-4 py-3 text-[12px] text-destructive">
        解析失败：{err || '未知错误'}
      </div>
    )
  }
  if (data.columns.length === 0) {
    return <EmptyPreview msg="(空表)" />
  }
  return (
    <div className="max-h-[400px] overflow-auto">
      <table className="w-full border-collapse text-[12px]">
        <thead className="sticky top-0 bg-card-muted">
          <tr>
            {data.columns.map((c, i) => (
              <th
                key={i}
                className="border-b border-border px-2 py-1 text-left font-semibold text-foreground"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row, i) => (
            <tr key={i} className="border-b border-border last:border-b-0 even:bg-muted/30">
              {row.map((cell, j) => (
                <td key={j} className="px-2 py-1 align-top text-foreground/90">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {data.truncated && (
        <div className="border-t border-border bg-card-muted px-3 py-1 text-[11px] text-muted-foreground">
          已展示前 {data.rows.length} 行，下载完整文件查看全部数据
        </div>
      )}
    </div>
  )
}

function PdfPreview({ rawUrl }: { rawUrl: string }) {

  return (
    <div className="overflow-hidden bg-muted/30">
      <iframe
        src={rawUrl}
        title="PDF 预览"
        className="block h-[500px] w-full border-0"
      />
    </div>
  )
}

function DownloadHint({ file, rawUrl }: { file: PresentedFile; rawUrl: string }) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <div className="text-[12px] text-muted-foreground">
          浏览器无法直接预览此类型文件（{file.mime || '二进制'}），请下载后查看。
        </div>
      </div>
      <Button asChild variant="outline" size="sm" className="shrink-0 gap-1.5">
        <a href={rawUrl} download>
          <Download className="h-3 w-3" />
          下载
        </a>
      </Button>
    </div>
  )
}

function EmptyPreview({ msg }: { msg: string }) {
  return (
    <div className="px-4 py-3 text-[12px] italic text-muted-foreground">{msg}</div>
  )
}

function TruncatedFooter() {
  return (
    <div className="mt-1 flex items-center gap-1 border-t border-border/60 pt-1 text-[11px] text-muted-foreground/80">
      <Maximize2 className="h-2.5 w-2.5" />
      <span>已截断；下载完整文件查看全文</span>
    </div>
  )
}

interface GroupProps {
  projectId: string
  title?: string
  description?: string
  files: PresentedFile[]
}

export function PresentedFileGroup({ projectId, title, description, files }: GroupProps) {
  if (!files || files.length === 0) return null
  return (
    <div className="space-y-2 rounded-lg border border-secondary/30 bg-secondary/[0.04] px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-secondary">
        <FileText className="h-3 w-3" />
        附件{title ? ` · ${title}` : `（${files.length} 个）`}
      </div>
      {description && (
        <p className="text-[12px] leading-relaxed text-muted-foreground">
          {description}
        </p>
      )}
      <div
        className={cn(
          'grid gap-2',
          files.length === 1 ? 'grid-cols-1' : 'grid-cols-1 md:grid-cols-2',
        )}
      >
        {files.map((f, i) => (
          <PresentedFileCard key={`${f.path}-${i}`} projectId={projectId} file={f} />
        ))}
      </div>
    </div>
  )
}

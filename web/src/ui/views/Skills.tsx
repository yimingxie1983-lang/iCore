

import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  BookText,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  FileText,
  Library,
  Pin,
  PinOff,
  RefreshCcw,
  Search,
  Sparkles,
  UploadCloud,
} from 'lucide-react'

import { api, type SkillBrief, type SkillDetail } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import { Input } from '@/ui/widgets/ui/input'
import { Badge } from '@/ui/widgets/ui/badge'
import { Skeleton } from '@/ui/widgets/ui/skeleton'
import { Switch } from '@/ui/widgets/ui/switch'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/ui/widgets/ui/sheet'
import { ScrollArea } from '@/ui/widgets/ui/scroll-area'
import { toast } from '@/ui/widgets/ui/sonner'

import PageHeader from '@/ui/widgets/common/PageHeader'
import StatCard from '@/ui/widgets/common/StatCard'
import EmptyState from '@/ui/widgets/common/EmptyState'
import { cn } from '@/shared/foundation/utils'

function UploadDropzone({
  onUpload,
  uploading,
}: {
  onUpload: (file: File) => void
  uploading: boolean
}) {
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = (file?: File | null) => {
    if (!file) return
    const fn = file.name.toLowerCase()
    if (!fn.endsWith('.zip') && !fn.endsWith('.md')) {
      toast.error('暂仅支持 .zip 或 .md', {
        description: `收到的是 ${file.name}`,
      })
      return
    }
    onUpload(file)
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => !uploading && inputRef.current?.click()}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && !uploading) {
          e.preventDefault()
          inputRef.current?.click()
        }
      }}
      onDragOver={(e) => {
        e.preventDefault()
        setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        if (uploading) return
        handleFile(e.dataTransfer.files?.[0])
      }}
      className={cn(
        'group relative flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-6 text-center transition',
        dragOver
          ? 'border-primary/60 bg-primary/[0.04]'
          : 'border-border bg-card/40 hover:border-primary/30 hover:bg-card',
        uploading && 'pointer-events-none opacity-60',
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".zip,.md"
        className="hidden"
        onChange={(e) => handleFile(e.target.files?.[0] || null)}
      />
      <div
        className={cn(
          'mb-2 flex h-11 w-11 items-center justify-center rounded-xl',
          dragOver
            ? 'bg-primary/10 text-primary'
            : 'bg-muted text-muted-foreground group-hover:bg-primary/[0.08] group-hover:text-primary',
        )}
      >
        <UploadCloud className="h-5 w-5" />
      </div>
      <div className="text-[13.5px] font-medium text-foreground">
        {uploading ? '上传中…' : '拖拽 .zip 或 SKILL.md 到这里，或点击选择文件'}
      </div>
      <div className="mt-1 text-[12px] text-muted-foreground">
        上传后立即生效；落地在
        <code className="mx-1 font-mono text-[11px]">library/skills/uploads/</code>
      </div>
    </div>
  )
}

function SkillCard({
  s,
  onOpen,
  onTogglePin,
  pinning,
}: {
  s: SkillBrief
  onOpen: () => void
  onTogglePin: () => void
  pinning: boolean
}) {
  return (
    <div
      className={cn(
        'surface-card surface-card-hover group relative flex flex-col rounded-xl p-4 transition-all',
        s.pinned ? 'border-secondary/60 bg-secondary/[0.03]' : 'hover:border-secondary/30',
      )}
    >
      {s.pinned && (
        <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-secondary/15 px-1.5 py-0.5 text-[10px] font-medium text-secondary">
          <Pin className="h-2.5 w-2.5" />
          pinned
        </span>
      )}

      <div className="mb-2 flex items-center gap-2">
        <FileText className="h-4 w-4 shrink-0 text-secondary" />
        <h3 className="min-w-0 truncate text-[13.5px] font-semibold tracking-tight">
          {s.name || s.id}
        </h3>
      </div>

      <p className="mb-3 line-clamp-3 min-h-[3lh] text-[12px] leading-relaxed text-muted-foreground">
        {s.description || '（无描述）'}
      </p>

      <div className="mb-3 flex flex-wrap gap-1">
        {s.tools.slice(0, 4).map((t) => (
          <Badge key={t} variant="outline" className="h-4 px-1.5 text-[10px] font-normal">
            {t}
          </Badge>
        ))}
      </div>

      <div className="mt-auto flex items-center justify-between border-t border-border pt-2">
        <code className="truncate font-mono text-[10.5px] text-muted-foreground">
          {s.id}
        </code>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            disabled={pinning}
            onClick={(e) => {
              e.stopPropagation()
              onTogglePin()
            }}
            title={s.pinned ? '取消 pin' : '设为 pin（始终装入 L1）'}
            className="h-7 px-2"
          >
            {s.pinned ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
          </Button>
          <Button variant="outline" size="sm" onClick={onOpen} className="h-7 px-2 text-[11px]">
            详情
          </Button>
        </div>
      </div>
    </div>
  )
}

function SkillDetailSheet({
  skillId,
  open,
  onOpenChange,
  onTogglePin,
}: {
  skillId: string | null
  open: boolean
  onOpenChange: (v: boolean) => void
  onTogglePin: (id: string, currentPinned: boolean) => void
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['skill-detail', skillId],
    queryFn: () => api.getSkill(skillId as string),
    enabled: !!skillId && open,
    staleTime: 60_000,
  })

  const detail = data as SkillDetail | undefined

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-[640px] flex flex-col p-0">
        <SheetHeader className="border-b border-border px-6 py-4">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-secondary/[0.08] text-secondary">
              <FileText className="h-[18px] w-[18px]" />
            </div>
            <div className="min-w-0 flex-1">
              <SheetTitle className="truncate text-[15px]">
                {detail?.name || skillId || '加载中…'}
              </SheetTitle>
              <SheetDescription className="mt-0.5">
                <code className="font-mono text-[11px]">{skillId}</code>
                {detail?.group && (
                  <Badge variant="muted" className="ml-2 h-4 px-1.5 text-[10px] font-normal">
                    {detail.group}
                  </Badge>
                )}
              </SheetDescription>
            </div>
            {detail && (
              <Button
                variant={detail.pinned ? 'ghost' : 'outline'}
                size="sm"
                onClick={() => onTogglePin(detail.id, detail.pinned)}
                className="shrink-0"
              >
                {detail.pinned ? (
                  <>
                    <PinOff className="h-3.5 w-3.5" />
                    取消 pin
                  </>
                ) : (
                  <>
                    <Pin className="h-3.5 w-3.5" />
                    pin
                  </>
                )}
              </Button>
            )}
          </div>
        </SheetHeader>

        // list empty state
        <ScrollArea className="flex-1 px-6 py-4">
          {isLoading || !detail ? (
            <div className="space-y-3">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          ) : (
            <div className="space-y-5">
              {}
              <div>
                <div className="mb-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  描述
                </div>
                <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground">
                  {detail.description || '（无）'}
                </p>
              </div>

              {}
              {detail.tools.length > 0 && (
                <div>
                  <div className="mb-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                    推断工具
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {detail.tools.map((t) => (
                      <Badge key={t} variant="outline" className="h-5 px-1.5 text-[11px] font-normal">
                        {t}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {}
              {Object.keys(detail.original_frontmatter || {}).length > 0 && (
                <div>
                  <div className="mb-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                    SKILL.md frontmatter
                  </div>
                  <pre className="overflow-x-auto rounded-lg bg-muted/50 px-3 py-2 text-[11.5px] leading-relaxed">
{JSON.stringify(detail.original_frontmatter, null, 2)}
                  </pre>
                </div>
              )}

              {}
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                    SKILL.md 全文
                  </div>
                  <code className="font-mono text-[10.5px] text-muted-foreground">
                    {detail.full_prompt.length} chars
                  </code>
                </div>
                <div className="prose prose-sm max-w-none rounded-lg border border-border bg-card/60 px-3 py-3 text-[12.5px] leading-relaxed">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {detail.full_prompt || '_（无正文）_'}
                  </ReactMarkdown>
                </div>
              </div>

              {}
              {detail.source_file && (
                <div className="text-[11px] text-muted-foreground">
                  源文件：
                  <code className="ml-1 break-all font-mono">{detail.source_file}</code>
                </div>
              )}
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}

function Pagination({
  page,
  totalPages,
  pageSize,
  rangeStart,
  rangeEnd,
  totalFiltered,
  totalAll,
  pageSizeOptions,
  onPageChange,
  onPageSizeChange,
  isLoading,
}: {
  page: number
  totalPages: number
  pageSize: number
  rangeStart: number
  rangeEnd: number
  totalFiltered: number
  totalAll: number
  pageSizeOptions: number[]
  onPageChange: (p: number) => void
  onPageSizeChange: (n: number) => void
  isLoading: boolean
}) {
  const goto = (p: number) => onPageChange(Math.min(Math.max(1, p), totalPages))
  const atFirst = page <= 1
  const atLast = page >= totalPages

  return (
    <div className="surface-card flex flex-wrap items-center justify-between gap-3 rounded-xl px-4 py-2.5">
      <div className="text-[12px] text-muted-foreground">
        {totalFiltered === 0 ? (
          <>无匹配</>
        ) : (
          <>
            <span className="font-medium text-foreground">{rangeStart}–{rangeEnd}</span>
            <span className="mx-1">/</span>
            <span>{totalFiltered}</span>
            {totalFiltered !== totalAll && (
              <span className="ml-1 text-muted-foreground/70">（全集 {totalAll}）</span>
            )}
          </>
        )}
      </div>
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
          每页
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="h-7 rounded-md border border-border bg-card px-1.5 text-[12px]"
          >
            {pageSizeOptions.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            disabled={atFirst || isLoading}
            onClick={() => goto(1)}
            title="第一页"
          >
            <ChevronsLeft className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            disabled={atFirst || isLoading}
            onClick={() => goto(page - 1)}
            title="上一页"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>
          <span className="px-2 text-[12px] tabular-nums text-muted-foreground">
            <span className="font-medium text-foreground">{page}</span>
            <span className="mx-1">/</span>
            <span>{totalPages}</span>
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            disabled={atLast || isLoading}
            onClick={() => goto(page + 1)}
            title="下一页"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            disabled={atLast || isLoading}
            onClick={() => goto(totalPages)}
            title="最后一页"
          >
            <ChevronsRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  )
}

const PAGE_SIZE_OPTIONS = [30, 60, 120, 240]
const DEFAULT_PAGE_SIZE = 60

export default function Skills() {
  const qc = useQueryClient()
  const [query, setQuery] = useState('')
  const [group, setGroup] = useState('')
  const [pinnedOnly, setPinnedOnly] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE)

  useEffect(() => {
    setPage(1)
  }, [query, group, pinnedOnly, pageSize])

  const skillsQ = useQuery({
    queryKey: ['skills', { query, group, pinnedOnly, page, pageSize }],
    queryFn: () =>
      api.listSkills({
        query,
        group,
        pinned_only: pinnedOnly,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      }),
    refetchOnWindowFocus: false,
    staleTime: 15_000,
    placeholderData: (prev) => prev,
  })

  const refreshMut = useMutation({
    mutationFn: () => api.refreshSkills(),
    onSuccess: (r) => {
      toast.success(`已重扫（${r.total} 条 / ${r.duration_ms}ms）`)
      qc.invalidateQueries({ queryKey: ['skills'] })
    },
    onError: (e: Error) => toast.error('重扫失败', { description: e.message }),
  })

  const uploadMut = useMutation({
    mutationFn: (file: File) => api.uploadSkill(file),
    onSuccess: (r) => {
      toast.success(
        r.new_skills > 0
          ? `已上传 ✚${r.new_skills} 条 skill（共 ${r.total_after}）`
          : `上传完成（无新增，可能 id 撞库）`,
        { description: r.message },
      )
      qc.invalidateQueries({ queryKey: ['skills'] })
    },
    onError: (e: Error) => toast.error('上传失败', { description: e.message }),
  })

  const pinMut = useMutation({
    mutationFn: ({ id, pinned }: { id: string; pinned: boolean }) =>
      pinned ? api.unpinSkill(id) : api.pinSkill(id),
    onSuccess: (_data, vars) => {
      toast.success(vars.pinned ? '已取消 pin' : '已 pin', {
        description: `id=${vars.id}`,
      })
      qc.invalidateQueries({ queryKey: ['skills'] })
      qc.invalidateQueries({ queryKey: ['skill-detail', vars.id] })
    },
    onError: (e: Error) => toast.error('操作失败', { description: e.message }),
  })

  const grouped = useMemo(() => {
    const m = new Map<string, SkillBrief[]>()
    for (const it of skillsQ.data?.items || []) {
      const arr = m.get(it.group) || []
      arr.push(it)
      m.set(it.group, arr)
    }
    return Array.from(m.entries()).sort(([a], [b]) => a.localeCompare(b))
  }, [skillsQ.data?.items])

  const pinnedCount = skillsQ.data?.pinned_ids.length ?? 0
  const totalAll = skillsQ.data?.total_all ?? 0
  const totalFiltered = skillsQ.data?.total_filtered ?? 0
  const groupsCount = skillsQ.data?.groups.length ?? 0
  const totalPages = Math.max(1, Math.ceil(totalFiltered / pageSize))

  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [totalPages, page])

  const rangeStart = totalFiltered === 0 ? 0 : (page - 1) * pageSize + 1
  const rangeEnd = Math.min(page * pageSize, totalFiltered)

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 p-6 lg:p-8">
        <PageHeader
          icon={Library}
          title="技能库（Skill）"
          description={
            <>
              兼容 Anthropic <code className="font-mono text-[11.5px]">SKILL.md</code>{' '}
              格式的外部方法论生态：拖拽上传 zip / 单文件 → 立即可被对话模型按需激活。
              内部 Craft 走代码仓库管理，不在此页面。
            </>
          }
          actions={
            <Button
              variant="outline"
              size="sm"
              onClick={() => refreshMut.mutate()}
              disabled={refreshMut.isPending}
            >
              <RefreshCcw className={cn('h-3.5 w-3.5', refreshMut.isPending && 'animate-spin')} />
              重扫
            </Button>
          }
          stats={
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <StatCard
                icon={BookText}
                iconTone="primary"
                label="总数"
                value={skillsQ.isLoading ? '…' : totalAll}
                hint="library/skills/**/SKILL.md"
              />
              <StatCard
                icon={Pin}
                iconTone="secondary"
                label="已 pin"
                value={skillsQ.isLoading ? '…' : pinnedCount}
                hint="始终装入 L1 listing"
              />
              <StatCard
                icon={Sparkles}
                iconTone="accent"
                label="分组数"
                value={skillsQ.isLoading ? '…' : groupsCount}
                hint="按目录自动分类"
              />
            </div>
          }
        />

        {}
        <UploadDropzone onUpload={(f) => uploadMut.mutate(f)} uploading={uploadMut.isPending} />

        {}
        <div className="surface-card flex flex-wrap items-center gap-3 rounded-xl p-3">
          <div className="relative min-w-[240px] flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜 id / 名称 / 描述（如：alignment / HPO）"
              className="h-9 pl-7 text-[12.5px]"
            />
          </div>
          <select
            value={group}
            onChange={(e) => setGroup(e.target.value)}
            className="h-9 rounded-md border border-border bg-card px-2 text-[12.5px]"
          >
            <option value="">所有分组（{groupsCount}）</option>
            {(skillsQ.data?.groups || []).map((g) => (
              <option key={g.name} value={g.name}>
                {g.name} ({g.count})
              </option>
            ))}
          </select>
          <div className="flex items-center gap-2">
            <Switch
              id="pinned-only"
              checked={pinnedOnly}
              onCheckedChange={setPinnedOnly}
            />
            <label htmlFor="pinned-only" className="cursor-pointer text-[12.5px] text-muted-foreground">
              只看已 pin
            </label>
          </div>
        </div>

        {}
        {!skillsQ.isLoading && totalFiltered > 0 && (
          <Pagination
            page={page}
            totalPages={totalPages}
            pageSize={pageSize}
            rangeStart={rangeStart}
            rangeEnd={rangeEnd}
            totalFiltered={totalFiltered}
            totalAll={totalAll}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
            isLoading={skillsQ.isFetching}
          />
        )}

        {}
        {skillsQ.isLoading ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-32 w-full rounded-xl" />
            ))}
          </div>
        ) : grouped.length === 0 ? (
          <EmptyState
            icon={Library}
            title={query || group || pinnedOnly ? '无匹配 skill' : '技能库为空'}
            description={
              query || group || pinnedOnly
                ? '换个关键词或清空筛选试试'
                : '把 zip 拖到上方上传区即可'
            }
          />
        ) : (
          <div
            className={cn(
              'flex flex-col gap-6 transition-opacity',
              skillsQ.isFetching && 'opacity-60',
            )}
          >
            {grouped.map(([gname, items]) => (
              <div key={gname}>
                <div className="mb-2 flex items-baseline gap-2">
                  <h2 className="text-[14px] font-semibold tracking-tight">{gname}</h2>
                  <span className="text-[11px] text-muted-foreground">
                    本页 {items.length} 条
                  </span>
                  {items.some((x) => x.pinned) && (
                    <Badge variant="muted" className="h-4 px-1.5 text-[10px] font-normal">
                      <CheckCircle2 className="mr-0.5 h-2.5 w-2.5" />
                      含 pin
                    </Badge>
                  )}
                </div>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
                  {items.map((s) => (
                    <SkillCard
                      key={s.id}
                      s={s}
                      onOpen={() => setOpenId(s.id)}
                      onTogglePin={() =>
                        pinMut.mutate({ id: s.id, pinned: s.pinned })
                      }
                      pinning={pinMut.isPending}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {}
        {!skillsQ.isLoading && totalPages > 1 && (
          <Pagination
            page={page}
            totalPages={totalPages}
            pageSize={pageSize}
            rangeStart={rangeStart}
            rangeEnd={rangeEnd}
            totalFiltered={totalFiltered}
            totalAll={totalAll}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
            isLoading={skillsQ.isFetching}
          />
        )}
      </div>

      <SkillDetailSheet
        skillId={openId}
        open={!!openId}
        onOpenChange={(v) => !v && setOpenId(null)}
        onTogglePin={(id, pinned) => pinMut.mutate({ id, pinned })}
      />
    </div>
  )
}

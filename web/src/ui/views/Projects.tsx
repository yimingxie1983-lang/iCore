

import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ColumnDef } from '@tanstack/react-table'
import {
  ArrowRight,
  CalendarClock,
  Clock3,
  FolderOpen,
  FolderPlus,
  LayoutGrid,
  Plus,
  Search,
  Settings2,
  Share2,
  Sparkles,
  Store,
  Trash2,
  TrendingUp,
} from 'lucide-react'

import { api, type Project } from '@/client/services/client'
import { useHasPermission } from '@/application/state/authStore'
import { Button } from '@/ui/widgets/ui/button'
import { Input } from '@/ui/widgets/ui/input'
import { Skeleton } from '@/ui/widgets/ui/skeleton'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/ui/widgets/ui/alert-dialog'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/ui/widgets/ui/tooltip'
import { ToggleGroup, ToggleGroupItem } from '@/ui/widgets/ui/toggle-group'
import { DataTable } from '@/ui/widgets/ui/data-table'
import { toast } from '@/ui/widgets/ui/sonner'

import PageHeader from '@/ui/widgets/common/PageHeader'
import StatCard from '@/ui/widgets/common/StatCard'
import EmptyState from '@/ui/widgets/common/EmptyState'
import CreateProjectDialog from '@/ui/widgets/common/CreateProjectDialog'
import ShareProjectDialog from '@/ui/widgets/common/ShareProjectDialog'
import { cn, parseBackendTime } from '@/shared/foundation/utils'

type ViewMode = 'grid' | 'table'

function fmtDate(s?: string): string {
  if (!s) return '—'
  try {
    const ms = parseBackendTime(s)
    if (ms == null) return s
    return new Date(ms).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return s
  }
}

function fmtRelative(s?: string): string {
  if (!s) return '—'
  try {
    const t = parseBackendTime(s) ?? new Date(s).getTime()
    const diff = Date.now() - t
    if (diff < 60_000) return '刚刚'
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
    if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`
    return new Date(t).toLocaleDateString('zh-CN')
  } catch {
    return s
  }
}

// card render
function ProjectCard({
  p,
  onOpen,
  onDelete,
  onShare,
  onTogglePublish,
  sharingOn,
  canPublish,
}: {
  p: Project
  onOpen: () => void
  onDelete: () => void
  onShare: () => void
  onTogglePublish: () => void
  sharingOn: boolean
  canPublish: boolean
}) {

  const canManage = p.role === 'owner'
  const published = p.visibility === 'market'
  return (
    <div className="surface-card surface-card-hover group relative flex flex-col rounded-xl p-5 transition-all hover:border-secondary/40">
      <div className="mb-3 flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-secondary/[0.10] text-secondary">
          <FolderOpen className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-[15px] font-semibold leading-tight tracking-tight text-foreground">
            {p.name}
          </h3>
          <div className="mt-0.5 flex items-center gap-1.5 truncate font-mono text-[10.5px] text-muted-foreground">
            {p.id}
            {sharingOn && published && (
              <span className="rounded bg-secondary/15 px-1 py-0.5 font-sans text-[9px] font-medium text-secondary">
                已发布
              </span>
            )}
          </div>
        </div>
      </div>

      <p className="mb-4 line-clamp-3 min-h-[3lh] text-[12.5px] leading-relaxed text-muted-foreground">
        {p.description || <span className="italic">未填写描述</span>}
      </p>

      <div className="mt-auto flex items-center justify-between border-t border-border pt-3">
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Clock3 className="h-3 w-3" />
          {fmtRelative(p.updated_at)}
        </div>
        <div className="flex items-center gap-1">
          {canManage && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon-sm" onClick={onShare}>
                  <Share2 />
                </Button>
              </TooltipTrigger>
              <TooltipContent>共享 / 成员</TooltipContent>
            </Tooltip>
          )}
          {canManage && sharingOn && canPublish && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className={published ? 'text-secondary' : ''}
                  onClick={onTogglePublish}
                >
                  <Store />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{published ? '从市场撤下' : '发布到共享市场'}</TooltipContent>
            </Tooltip>
          )}
          {canManage && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                  onClick={onDelete}
                >
                  <Trash2 />
                </Button>
              </TooltipTrigger>
              <TooltipContent>删除项目</TooltipContent>
            </Tooltip>
          )}
          <Button size="sm" variant="ghost" className="gap-1 text-secondary" onClick={onOpen}>
            进入对话
            <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function Projects() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.listProjects(),
  })

  const { data: features } = useQuery({
    queryKey: ['features'],
    queryFn: () => api.getFeatures(),
    staleTime: 60_000,
    retry: 0,
  })
  const sharingOn = !!features?.project_sharing
  const canPublish = useHasPermission('project.publish')

  const togglePublishMut = useMutation({
    mutationFn: (p: Project) =>
      p.visibility === 'market'
        ? api.unpublishProject(p.id)
        : api.publishProject(p.id, 'viewer'),
    onSuccess: (_r, p) => {
      toast.success(p.visibility === 'market' ? '已从市场撤下' : '已发布到共享市场')
      qc.invalidateQueries({ queryKey: ['projects'] })
      qc.invalidateQueries({ queryKey: ['market'] })
    },
    onError: (e: Error) => toast.error('操作失败', { description: e.message }),
  })

  const [view, setView] = useState<ViewMode>('grid')
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [deleting, setDeleting] = useState<Project | null>(null)
  const [sharing, setSharing] = useState<Project | null>(null)

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteProject(id),
    onSuccess: () => {
      toast.success('项目已删除')
      setDeleting(null)
      qc.invalidateQueries({ queryKey: ['projects'] })
    },
    onError: (e: Error) => toast.error('删除失败', { description: e.message }),
  })

  const items = data?.items || []
  const filtered = useMemo(() => {
    if (!search.trim()) return items
    const q = search.toLowerCase()
    return items.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        (p.description || '').toLowerCase().includes(q) ||
        p.id.toLowerCase().includes(q),
    )
  }, [items, search])

  const kpis = useMemo(() => {
    const now = Date.now()
    const total = items.length
    const newThisWeek = items.filter((p) => {
      const t = parseBackendTime(p.created_at)
      return t != null && now - t < 7 * 86_400_000
    }).length
    const activeIn24h = items.filter((p) => {
      const t = parseBackendTime(p.updated_at)
      return t != null && now - t < 86_400_000
    }).length
    return { total, newThisWeek, activeIn24h }
  }, [items])

  const columns = useMemo<ColumnDef<Project>[]>(
    () => [
      {
        accessorKey: 'name',
        header: '项目',
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <FolderOpen className="h-3.5 w-3.5 text-secondary" />
            <span className="font-semibold text-foreground">{row.original.name}</span>
            <code className="font-mono text-[10px] text-muted-foreground">
              {row.original.id.slice(0, 8)}
            </code>
          </div>
        ),
      },
      {
        accessorKey: 'description',
        header: '描述',
        cell: ({ row }) => (
          <span className="line-clamp-1 text-[13px] text-muted-foreground">
            {row.original.description || '—'}
          </span>
        ),
      },
      {
        accessorKey: 'updated_at',
        header: '更新',
        size: 170,
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className="text-[12px]">{fmtRelative(row.original.updated_at)}</span>
            <span className="text-[10px] text-muted-foreground">
              {fmtDate(row.original.updated_at)}
            </span>
          </div>
        ),
      },
      {
        id: 'actions',
        header: '操作',
        size: 150,
        enableSorting: false,
        cell: ({ row }) => {
          const canManage = row.original.role === 'owner'
          return (
            <div className="flex items-center gap-1">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => navigate(`/chat/${row.original.id}`)}
                  >
                    <ArrowRight />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>进入对话</TooltipContent>
              </Tooltip>
              {canManage && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => setSharing(row.original)}
                    >
                      <Share2 />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>共享 / 成员</TooltipContent>
                </Tooltip>
              )}
              {canManage && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                      onClick={() => setDeleting(row.original)}
                    >
                      <Trash2 />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>删除项目</TooltipContent>
                </Tooltip>
              )}
            </div>
          )
        },
      },
    ],
    [navigate],
  )

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 p-6 lg:p-8">
        <PageHeader
          icon={FolderOpen}
          title="项目管理"
          description="每个项目是一个独立的工作区，包含 workspace / memory / logs / docs/plans。"
          actions={
            <>
              <Button variant="outline" asChild>
                <Link to="/projects/new">
                  <Settings2 />
                  完整新建
                </Link>
              </Button>
              <Button onClick={() => setCreateOpen(true)}>
                <Plus />
                快速新建
              </Button>
            </>
          }
          stats={
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <StatCard
                icon={FolderOpen}
                iconTone="primary"
                label="项目总数"
                value={isLoading ? '…' : kpis.total}
                hint="包含所有创建过的项目"
              />
              <StatCard
                icon={Sparkles}
                iconTone="secondary"
                label="本周新建"
                value={isLoading ? '…' : kpis.newThisWeek}
                hint="过去 7 天"
              />
              <StatCard
                icon={TrendingUp}
                iconTone="accent"
                label="24h 内活跃"
                value={isLoading ? '…' : kpis.activeIn24h}
                hint="基于 updated_at"
              />
            </div>
          }
        />

        {}
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[220px] max-w-md">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="h-9 pl-8"
              placeholder="按名称 / 描述 / ID 搜索…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="flex-1" />
          <ToggleGroup
            type="single"
            value={view}
            onValueChange={(v) => v && setView(v as ViewMode)}
            className="h-9"
          >
            <ToggleGroupItem value="grid" size="sm" aria-label="卡片视图">
              <LayoutGrid />
              <span className="hidden sm:inline">卡片</span>
            </ToggleGroupItem>
            <ToggleGroupItem value="table" size="sm" aria-label="表格视图">
              <CalendarClock />
              <span className="hidden sm:inline">表格</span>
            </ToggleGroupItem>
          </ToggleGroup>
        </div>

        {}
        {isLoading ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-44 w-full rounded-xl" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={FolderPlus}
            title="还没有项目"
            description="项目是一切工作的起点。创建你的第一个项目（只需一个名字）后即可开始对话。"
            action={
              <Button onClick={() => setCreateOpen(true)}>
                <Plus />
                创建第一个项目
              </Button>
            }
            secondaryAction={
              <Button variant="outline" asChild>
                <Link to="/projects/new">完整创建（更多字段）</Link>
              </Button>
            }
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            compact
            icon={Search}
            title={`没有匹配「${search}」的项目`}
            description="试试只输入项目名的一部分，或清空搜索查看全部。"
            action={
              <Button variant="outline" size="sm" onClick={() => setSearch('')}>
                清空搜索
              </Button>
            }
          />
        ) : view === 'grid' ? (
          <div
            className={cn(
              'grid grid-cols-1 gap-4 md:grid-cols-2',
              filtered.length >= 3 && 'lg:grid-cols-3',
            )}
          >
            {filtered.map((p) => (
              <ProjectCard
                key={p.id}
                p={p}
                onOpen={() => navigate(`/chat/${p.id}`)}
                onDelete={() => setDeleting(p)}
                onShare={() => setSharing(p)}
                onTogglePublish={() => togglePublishMut.mutate(p)}
                sharingOn={sharingOn}
                canPublish={canPublish}
              />
            ))}
          </div>
        ) : (
          <DataTable columns={columns} data={filtered} emptyText="无匹配项目" />
        )}
      </div>

      {}
      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />

      {sharing && (
        <ShareProjectDialog
          projectId={sharing.id}
          projectName={sharing.name}
          open={!!sharing}
          onOpenChange={(o) => !o && setSharing(null)}
        />
      )}

      <AlertDialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除项目「{deleting?.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              此操作不可恢复。项目的工作区目录与记忆文件不会被自动清理（出于安全考虑），
              但所有数据库记录与对话历史会立即丢失。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleting && deleteMut.mutate(deleting.id)}
              disabled={deleteMut.isPending}
            >
              {deleteMut.isPending ? '删除中…' : '确认删除'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

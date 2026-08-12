import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ColumnDef } from '@tanstack/react-table'
import { ChevronLeft, ChevronRight, FolderKanban, Pause, Play, Snowflake, Sun, Trash2 } from 'lucide-react'

import { api, type AdminProject } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import { Input } from '@/ui/widgets/ui/input'
import { Badge } from '@/ui/widgets/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/ui/widgets/ui/select'
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
import { DataTable } from '@/ui/widgets/ui/data-table'
import { toast } from '@/ui/widgets/ui/sonner'
import PageHeader from '@/ui/widgets/common/PageHeader'
import { parseBackendTime } from '@/shared/foundation/utils'

const PAGE_SIZE = 20

function fmtDate(s?: string | null): string {
  if (!s) return '—'
  const ms = parseBackendTime(s)
  if (ms == null) return s
  return new Date(ms).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function StatusBadge({ status }: { status: AdminProject['status'] }) {
  if (status === 'paused') {
    return (
      <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-amber-700">
        已暂停
      </Badge>
    )
  }
  if (status === 'frozen') {
    return (
      <Badge variant="outline" className="border-slate-500/40 bg-slate-500/10 text-slate-600">
        已冻结
      </Badge>
    )
  }
  return (
    <Badge variant="outline" className="border-emerald-500/40 bg-emerald-500/10 text-emerald-700">
      正常
    </Badge>
  )
}

export default function AdminProjects() {
  const qc = useQueryClient()
  const [q, setQ] = useState('')
  const [owner, setOwner] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [running, setRunning] = useState<'all' | 'true' | 'false'>('all')
  const [status, setStatus] = useState<'all' | 'active' | 'paused' | 'frozen'>('all')
  const [offset, setOffset] = useState(0)
  const [deleteTarget, setDeleteTarget] = useState<AdminProject | null>(null)

  useEffect(() => {
    setOffset(0)
  }, [q, owner, dateFrom, dateTo, running, status])

  const params = useMemo(
    () => ({
      q: q.trim() || undefined,
      owner: owner.trim() || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      running: running === 'all' ? undefined : running === 'true',
      status: status === 'all' ? undefined : status,
      limit: PAGE_SIZE,
      offset,
    }),
    [q, owner, dateFrom, dateTo, running, status, offset],
  )

  const { data, isLoading } = useQuery({
    queryKey: ['admin-projects', params],
    queryFn: () => api.adminListProjects(params),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['admin-projects'] })

  const changeStatus = useMutation({
    mutationFn: (input: {
      id: string
      action: 'pause' | 'resume' | 'freeze' | 'unfreeze'
    }) => {
      if (input.action === 'pause') return api.adminPauseProject(input.id)
      if (input.action === 'resume') return api.adminResumeProject(input.id)
      if (input.action === 'freeze') return api.adminFreezeProject(input.id)
      return api.adminUnfreezeProject(input.id)
    },
    onSuccess: () => {
      invalidate()
      toast.success('操作成功')
    },
    onError: (err: Error) => toast.error(err.message || '操作失败'),
  })

  const doDelete = useMutation({
    mutationFn: (id: string) => api.adminDeleteProject(id),
    onSuccess: () => {
      invalidate()
      setDeleteTarget(null)
      toast.success('项目已删除')
    },
    onError: (err: Error) => toast.error(err.message || '删除失败'),
  })

  const columns = useMemo<ColumnDef<AdminProject>[]>(
    () => [
      {
        accessorKey: 'name',
        header: '项目',
        cell: ({ row }) => (
          <div className="min-w-0">
            <div className="font-medium text-foreground">{row.original.name}</div>
            <div className="max-w-[260px] truncate text-xs text-muted-foreground">
              {row.original.description || '—'}
            </div>
          </div>
        ),
      },
      {
        accessorKey: 'owner_username',
        header: '创建者',
        cell: ({ row }) =>
          row.original.owner_display_name || row.original.owner_username || '—',
      },
      {
        accessorKey: 'created_at',
        header: '创建时间',
        cell: ({ row }) => fmtDate(row.original.created_at),
      },
      {
        accessorKey: 'status',
        header: '状态',
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        accessorKey: 'running',
        header: '运行中',
        cell: ({ row }) =>
          row.original.running ? (
            <Badge className="gap-1 border-emerald-500/40 bg-emerald-500/10 text-emerald-700">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
              运行中 · {row.original.running_sessions}
            </Badge>
          ) : (
            <span className="text-xs text-muted-foreground">未运行</span>
          ),
      },
      {
        id: 'actions',
        header: '操作',
        cell: ({ row }) => {
          const p = row.original
          return (
            <div className="flex items-center gap-1">
              {p.status === 'active' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => changeStatus.mutate({ id: p.id, action: 'pause' })}
                >
                  <Pause className="h-3.5 w-3.5" /> 暂停
                </Button>
              )}
              {p.status === 'paused' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => changeStatus.mutate({ id: p.id, action: 'resume' })}
                >
                  <Play className="h-3.5 w-3.5" /> 恢复
                </Button>
              )}
              {p.status !== 'frozen' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => changeStatus.mutate({ id: p.id, action: 'freeze' })}
                >
                  <Snowflake className="h-3.5 w-3.5" /> 冻结
                </Button>
              )}
              {p.status === 'frozen' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => changeStatus.mutate({ id: p.id, action: 'unfreeze' })}
                >
                  <Sun className="h-3.5 w-3.5" /> 解冻
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive"
                onClick={() => setDeleteTarget(p)}
              >
                <Trash2 className="h-3.5 w-3.5" /> 删除
              </Button>
            </div>
          )
        },
      },
    ],
    [changeStatus],
  )

  const total = data?.total ?? 0
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + PAGE_SIZE, total)
  const canPrev = offset > 0
  const canNext = offset + PAGE_SIZE < total

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 lg:p-6">
      <PageHeader
        title="项目管理"
        description="查看系统内全部项目，按创建者、日期、名称与运行状态筛选；可暂停运行、冻结或删除项目。"
        icon={FolderKanban}
      />

      <div className="flex flex-wrap items-end gap-3 rounded-lg border bg-card p-3">
        <div className="flex min-w-[180px] flex-col gap-1">
          <label className="text-xs text-muted-foreground">名称</label>
          <Input placeholder="搜索项目名称" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="flex min-w-[140px] flex-col gap-1">
          <label className="text-xs text-muted-foreground">创建者</label>
          <Input
            placeholder="用户名 / 显示名"
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
          />
        </div>
        <div className="flex min-w-[140px] flex-col gap-1">
          <label className="text-xs text-muted-foreground">创建日期从</label>
          <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div className="flex min-w-[140px] flex-col gap-1">
          <label className="text-xs text-muted-foreground">创建日期至</label>
          <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
        <div className="flex min-w-[130px] flex-col gap-1">
          <label className="text-xs text-muted-foreground">运行状态</label>
          <Select
            value={running}
            onValueChange={(v) => setRunning(v as 'all' | 'true' | 'false')}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部</SelectItem>
              <SelectItem value="true">运行中</SelectItem>
              <SelectItem value="false">未运行</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex min-w-[130px] flex-col gap-1">
          <label className="text-xs text-muted-foreground">项目状态</label>
          <Select
            value={status}
            onValueChange={(v) =>
              setStatus(v as 'all' | 'active' | 'paused' | 'frozen')
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部</SelectItem>
              <SelectItem value="active">正常</SelectItem>
              <SelectItem value="paused">已暂停</SelectItem>
              <SelectItem value="frozen">已冻结</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <DataTable
          columns={columns}
          data={data?.items ?? []}
          isLoading={isLoading}
          emptyText="暂无匹配的项目"
          pageSize={Math.max(data?.items.length ?? 0, 1)}
        />
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 text-xs text-muted-foreground">
          <span>
            共 {total} 条 · 第 {from}-{to} 条
          </span>
          <div className="flex gap-1.5">
            <Button
              variant="outline"
              size="sm"
              disabled={!canPrev}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              <ChevronLeft className="h-3.5 w-3.5" /> 上一页
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!canNext}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              下一页 <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除项目</AlertDialogTitle>
            <AlertDialogDescription>
              确定删除项目「{deleteTarget?.name}」吗？该操作会级联删除成员、会话、历史与日志，且不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground"
              onClick={() => deleteTarget && doDelete.mutate(deleteTarget.id)}
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ChevronLeft,
  ChevronRight,
  Download,
  RefreshCw,
  ScrollText,
  Search,
} from 'lucide-react'

import { api, type AuthEventFilters, type AuthEventItem } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/ui/widgets/ui/card'
import { Badge } from '@/ui/widgets/ui/badge'
import { Input } from '@/ui/widgets/ui/input'
import { toast } from '@/ui/widgets/ui/sonner'
import { parseBackendTime } from '@/shared/foundation/utils'

const EVENT_LABELS: Record<string, string> = {
  register: '注册',
  login_success: '登录成功',
  login_failed: '登录失败',
  login_locked: '登录锁定',
  password_changed: '修改密码',
  password_reset_requested: '申请重置密码',
  password_reset: '重置密码',
  password_reset_mail_failed: '重置邮件发送失败',
  password_reset_requested_unknown: '申请重置（账号未知）',
  verify_email_sent: '发送验证邮件',
  admin_create_user: '管理员建号',
  admin_update_user: '管理员改用户',
  admin_delete_user: '管理员删号',
}

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const
const EMPTY_FILTERS: AuthEventFilters = {}

function eventLabel(t: string): string {
  return EVENT_LABELS[t] || t
}

function fmtTime(raw: unknown): string {
  const ms = parseBackendTime(raw as string | number | null | undefined)
  if (ms == null) return '—'
  return new Date(ms).toLocaleString('zh-CN', { hour12: false })
}

function eventVariant(t: string): 'destructive' | 'secondary' | 'outline' | 'warning' {
  if (t.includes('failed') || t.includes('locked') || t.includes('unknown')) return 'destructive'
  if (t.includes('success')) return 'secondary'
  if (t.includes('password')) return 'warning'
  return 'outline'
}

const PAGE_BTN =
  'flex items-center gap-0.5 rounded-md border border-border px-2 py-1 text-[12px] ' +
  'transition-colors disabled:cursor-not-allowed disabled:opacity-40 enabled:hover:bg-muted'

export default function AuthEvents() {
  const [username, setUsername] = useState('')
  const [ip, setIp] = useState('')
  const [eventType, setEventType] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [applied, setApplied] = useState<AuthEventFilters>(EMPTY_FILTERS)
  const [limit, setLimit] = useState(50)
  const [offset, setOffset] = useState(0)
  const [exporting, setExporting] = useState(false)

  const { data, isError, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['admin-auth-events', applied, limit, offset],
    queryFn: () => api.listAuthEvents({ limit, offset, ...applied }),
    refetchInterval: 30_000,
  })

  const total = data?.total ?? 0

  useEffect(() => {
    if (total === 0) {
      if (offset !== 0) setOffset(0)
      return
    }
    const maxOffset = Math.max(0, Math.ceil(total / Math.max(1, limit)) - 1) * limit
    if (offset > maxOffset) setOffset(maxOffset)
  }, [total, limit, offset])

  const applyFilters = () => {
    setApplied({
      username: username.trim(),
      ip: ip.trim(),
      event_type: eventType,
      start,
      end,
    })
    setOffset(0)
  }

  const resetFilters = () => {
    setUsername('')
    setIp('')
    setEventType('')
    setStart('')
    setEnd('')
    setApplied(EMPTY_FILTERS)
    setOffset(0)
  }

  const changeLimit = (n: number) => {
    setLimit(n)
    setOffset(0)
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const blob = await api.exportAuthEvents(applied)
      const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '')
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `auth-events-${stamp}.csv`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      toast.success('导出成功')
    } catch {
      toast.error('导出失败，请重试')
    } finally {
      setExporting(false)
    }
  }

  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + limit, total)
  const page = total === 0 ? 0 : Math.floor(offset / limit) + 1
  const pages = Math.max(1, Math.ceil(total / Math.max(1, limit)))
  const canPrev = offset > 0
  const canNext = offset + limit < total

  return (
    <div className="mx-auto w-full max-w-6xl space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold text-foreground">
            <ScrollText className="h-5 w-5 text-muted-foreground" />
            安全日志
          </h1>
          <p className="text-xs text-muted-foreground">
            登录、锁定、改密、重置与管理员操作审计。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={exporting || isFetching} onClick={handleExport}>
            <Download className="h-3.5 w-3.5" />
            {exporting ? '导出中…' : '导出'}
          </Button>
          <Button variant="outline" size="sm" disabled={isFetching} onClick={() => refetch()}>
            <RefreshCw className={isFetching ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
            刷新
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="pt-4">
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              applyFilters()
            }}
          >
            <div className="flex flex-col gap-1">
              <label className="text-[11px] text-muted-foreground">用户名</label>
              <Input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="模糊匹配"
                className="h-8 w-36"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[11px] text-muted-foreground">来源 IP</label>
              <Input
                value={ip}
                onChange={(e) => setIp(e.target.value)}
                placeholder="模糊匹配"
                className="h-8 w-36 font-mono"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[11px] text-muted-foreground">事件类型</label>
              <select
                value={eventType}
                onChange={(e) => setEventType(e.target.value)}
                className="h-8 rounded-md border border-input bg-background px-2 text-[12px] text-foreground outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">全部</option>
                {Object.entries(EVENT_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[11px] text-muted-foreground">开始日期</label>
              <input
                type="date"
                value={start}
                max={end || undefined}
                onChange={(e) => setStart(e.target.value)}
                className="h-8 rounded-md border border-input bg-background px-2 text-[12px] text-foreground outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[11px] text-muted-foreground">结束日期</label>
              <input
                type="date"
                value={end}
                min={start || undefined}
                onChange={(e) => setEnd(e.target.value)}
                className="h-8 rounded-md border border-input bg-background px-2 text-[12px] text-foreground outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div className="flex items-center gap-2">
              <Button type="submit" size="sm" disabled={isFetching}>
                <Search className="h-3.5 w-3.5" />
                查询
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={resetFilters}>
                重置
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            共 {total} 条事件
            {Object.values(applied).some(Boolean) ? '（已筛选）' : ''}
          </CardTitle>
          <label className="flex items-center gap-1 text-[12px] text-muted-foreground">
            每页
            <select
              value={limit}
              onChange={(e) => changeLimit(Number(e.target.value))}
              className="rounded-md border border-border bg-background px-1.5 py-1 text-[12px] text-foreground outline-none"
            >
              {PAGE_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            条
          </label>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-col gap-3">
          <div className="max-h-[520px] min-h-0 overflow-auto rounded-lg border border-border">
            <table className="w-full min-w-[720px] text-left text-[12px]">
              <thead className="sticky top-0 z-10 bg-muted/95 text-[11px] uppercase tracking-wider text-muted-foreground backdrop-blur">
                <tr className="border-b border-border">
                  <th className="px-3 py-2.5 font-medium">时间</th>
                  <th className="px-3 py-2.5 font-medium">用户</th>
                  <th className="px-3 py-2.5 font-medium">事件</th>
                  <th className="px-3 py-2.5 font-medium">来源 IP</th>
                  <th className="px-3 py-2.5 font-medium">详情</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center text-xs text-muted-foreground">
                      加载中…
                    </td>
                  </tr>
                ) : isError ? (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center text-xs text-destructive">
                      加载失败
                    </td>
                  </tr>
                ) : (data?.items ?? []).length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center text-xs text-muted-foreground">
                      暂无事件
                    </td>
                  </tr>
                ) : (
                  (data?.items ?? []).map((e: AuthEventItem) => (
                    <tr
                      key={e.id}
                      className="border-b border-border/60 last:border-0 hover:bg-muted/30"
                    >
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px] text-muted-foreground">
                        {fmtTime(e.created_at)}
                      </td>
                      <td className="px-3 py-2 font-medium">{e.username || '—'}</td>
                      <td className="px-3 py-2">
                        <Badge variant={eventVariant(e.event_type)}>{eventLabel(e.event_type)}</Badge>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px] text-muted-foreground">
                        {e.ip || '—'}
                      </td>
                      <td className="max-w-[280px] truncate px-3 py-2 text-muted-foreground">
                        {e.detail || '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 text-[12px] text-muted-foreground">
            <span>
              {total === 0
                ? '共 0 条'
                : `共 ${total} 条 · 第 ${from}-${to} 条 · ${page}/${pages} 页`}
            </span>
            <div className="flex gap-1.5">
              <button
                type="button"
                className={PAGE_BTN}
                disabled={!canPrev}
                onClick={() => setOffset(Math.max(0, offset - limit))}
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                上一页
              </button>
              <button
                type="button"
                className={PAGE_BTN}
                disabled={!canNext}
                onClick={() => setOffset(offset + limit)}
              >
                下一页
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

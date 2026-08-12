import { useQuery } from '@tanstack/react-query'
import { RefreshCw, ScrollText } from 'lucide-react'

import { api, type AuthEventItem } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/ui/widgets/ui/card'
import { Badge } from '@/ui/widgets/ui/badge'
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

export default function AuthEvents() {
  const { data, isError, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['admin-auth-events'],
    queryFn: () => api.listAuthEvents({ limit: 100 }),
    refetchInterval: 30_000,
  })

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 p-4 sm:p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold text-foreground">
            <ScrollText className="h-5 w-5 text-muted-foreground" />
            安全日志
          </h1>
          <p className="text-xs text-muted-foreground">
            登录、锁定、改密、重置与管理员操作审计（最近 100 条）。
          </p>
        </div>
        <Button variant="outline" size="sm" disabled={isFetching} onClick={() => refetch()}>
          <RefreshCw className={isFetching ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
          刷新
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">
            共 {data?.total ?? 0} 条事件
          </CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {isLoading ? (
            <p className="py-6 text-center text-xs text-muted-foreground">加载中…</p>
          ) : isError ? (
            <p className="py-6 text-center text-xs text-destructive">加载失败</p>
          ) : (
            <table className="w-full min-w-[680px] text-left text-[12px]">
              <thead>
                <tr className="border-b border-border text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="pb-2 pr-3 font-medium">时间</th>
                  <th className="pb-2 pr-3 font-medium">用户</th>
                  <th className="pb-2 pr-3 font-medium">事件</th>
                  <th className="pb-2 pr-3 font-medium">来源 IP</th>
                  <th className="pb-2 font-medium">详情</th>
                </tr>
              </thead>
              <tbody>
                {(data?.items ?? []).map((e: AuthEventItem) => (
                  <tr key={e.id} className="border-b border-border/60 last:border-0">
                    <td className="whitespace-nowrap py-2 pr-3 font-mono text-[11px] text-muted-foreground">
                      {fmtTime(e.created_at)}
                    </td>
                    <td className="py-2 pr-3 font-medium">{e.username || '—'}</td>
                    <td className="py-2 pr-3">
                      <Badge variant={eventVariant(e.event_type)}>{eventLabel(e.event_type)}</Badge>
                    </td>
                    <td className="py-2 pr-3 font-mono text-[11px] text-muted-foreground">
                      {e.ip || '—'}
                    </td>
                    <td className="max-w-[260px] truncate py-2 text-muted-foreground">
                      {e.detail || '—'}
                    </td>
                  </tr>
                ))}
                {(data?.items ?? []).length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-xs text-muted-foreground">
                      暂无事件
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

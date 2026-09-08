import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link2, QrCode, RefreshCw, Smartphone, Trash2 } from 'lucide-react'

import { api } from '@/client/services/client'
import { Badge } from '@/ui/widgets/ui/badge'
import { Button } from '@/ui/widgets/ui/button'
import { Separator } from '@/ui/widgets/ui/separator'

export default function WechatChannel() {
  const qc = useQueryClient()
  const [projectId, setProjectId] = useState('')
  const [lastCode, setLastCode] = useState<{
    code: string
    instruction: string
    expires_in: number
    project_name?: string
  } | null>(null)

  const statusQ = useQuery({
    queryKey: ['wechat-channel-status'],
    queryFn: () => api.wechatChannelStatus(),
  })
  const projectsQ = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.listProjects(),
  })
  const bindingsQ = useQuery({
    queryKey: ['wechat-bindings'],
    queryFn: () => api.wechatBindings(),
  })

  const projects = useMemo(() => {
    const raw = projectsQ.data
    if (raw && typeof raw === 'object' && Array.isArray(raw.items)) {
      return raw.items
    }
    return [] as Array<{ id: string; name: string }>
  }, [projectsQ.data])

  const createMut = useMutation({
    mutationFn: () =>
      api.createWechatBindCode({
        project_id: projectId,
        permissions_mode: 'ask',
      }),
    onSuccess: (data) => {
      setLastCode({
        code: data.code,
        instruction: data.instruction,
        expires_in: data.expires_in,
        project_name: data.project_name,
      })
      qc.invalidateQueries({ queryKey: ['wechat-bindings'] })
    },
  })

  const unbindMut = useMutation({
    mutationFn: (scopeId: string) => api.deleteWechatBinding(scopeId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wechat-bindings'] }),
  })

  const status = statusQ.data
  const bindings = bindingsQ.data?.items || []

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">微信渠道</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          本机桥模式：在电脑运行微信助手，手机微信发消息即可驱动 iCore 项目 Agent。
        </p>
      </div>

      <section className="rounded-lg border border-border/70 bg-card/40 p-4">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Smartphone className="h-4 w-4" />
          通道状态
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-sm">
          <Badge variant={status?.enabled ? 'default' : 'secondary'}>
            {status?.enabled ? '已启用' : '未启用'}
          </Badge>
          <Badge variant="outline">模式 {status?.mode || 'desktop'}</Badge>
          <Badge variant="outline">
            进度推送 {status?.progress_to_chat ? '开' : '关'}
          </Badge>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">{status?.hint}</p>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
          <li>
            本机登录 Bot：<code className="rounded bg-muted px-1">icore wechat login</code>
          </li>
          <li>
            启动桥接：<code className="rounded bg-muted px-1">icore wechat serve</code>
          </li>
          <li>下方生成绑定码，微信发送 <code className="rounded bg-muted px-1">/bind 码</code></li>
        </ol>
      </section>

      <section className="rounded-lg border border-border/70 bg-card/40 p-4">
        <div className="flex items-center gap-2 text-sm font-medium">
          <QrCode className="h-4 w-4" />
          个人扫码绑定
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          绑定码约 {status?.bind_code_ttl_seconds || 600} 秒有效，一人一绑到指定项目。
        </p>
        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex flex-1 flex-col gap-1 text-sm">
            <span className="text-muted-foreground">选择项目</span>
            <select
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
            >
              <option value="">请选择…</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.id})
                </option>
              ))}
            </select>
          </label>
          <Button
            disabled={!projectId || createMut.isPending}
            onClick={() => createMut.mutate()}
          >
            {createMut.isPending ? '生成中…' : '生成绑定码'}
          </Button>
        </div>
        {createMut.isError && (
          <p className="mt-2 text-sm text-destructive">
            {(createMut.error as Error)?.message || '生成失败'}
          </p>
        )}
        {lastCode && (
          <div className="mt-4 rounded-md border border-dashed border-border bg-muted/30 p-4">
            <div className="text-xs text-muted-foreground">绑定码（请在微信发送）</div>
            <div className="mt-1 font-mono text-2xl tracking-[0.2em]">{lastCode.code}</div>
            <p className="mt-2 text-sm">{lastCode.instruction}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              项目：{lastCode.project_name || projectId} · 约 {lastCode.expires_in}s 内有效
            </p>
          </div>
        )}
      </section>

      <section className="rounded-lg border border-border/70 bg-card/40 p-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Link2 className="h-4 w-4" />
            我的绑定
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => qc.invalidateQueries({ queryKey: ['wechat-bindings'] })}
          >
            <RefreshCw className="mr-1 h-3.5 w-3.5" />
            刷新
          </Button>
        </div>
        <Separator className="my-3" />
        {bindings.length === 0 ? (
          <p className="text-sm text-muted-foreground">暂无绑定。生成绑定码后在微信完成 /bind。</p>
        ) : (
          <ul className="space-y-2">
            {bindings.map((b) => (
              <li
                key={b.id}
                className="flex items-center justify-between gap-3 rounded-md border border-border/60 px-3 py-2 text-sm"
              >
                <div className="min-w-0">
                  <div className="truncate font-medium">项目 {b.project_id}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    微信 {b.external_scope_id} · 会话 {b.session_id || '新'} · {b.permissions_mode}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="shrink-0 text-destructive"
                  disabled={unbindMut.isPending}
                  onClick={() => unbindMut.mutate(b.external_scope_id)}
                  title="解绑"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

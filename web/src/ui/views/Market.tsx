

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Share2, Store, Inbox, Send, Check, X } from 'lucide-react'

import { api, type MarketItem, type AccessRequest } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import { Badge } from '@/ui/widgets/ui/badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/ui/widgets/ui/tabs'
import { toast } from '@/ui/widgets/ui/sonner'

const STATUS_LABEL: Record<string, string> = {
  pending: '待审批',
  approved: '已通过',
  rejected: '已拒绝',
  cancelled: '已取消',
}

const RELATION_LABEL: Record<string, string> = {
  owner: '我的项目',
  member: '已加入',
  pending: '申请中',
  none: '',
}

export default function Market() {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto p-6">
      <div className="mb-4">
        <h2 className="flex items-center gap-2 text-base font-semibold text-foreground">
          <Share2 className="h-4 w-4 text-secondary" />
          共享市场
        </h2>
        <p className="mt-0.5 text-[12px] text-muted-foreground">
          发现其他人发布的项目并申请协作；你发布的项目收到的申请可在「待我审批」处理。
        </p>
      </div>

      <Tabs defaultValue="browse" className="flex min-h-0 flex-1 flex-col">
        <TabsList>
          <TabsTrigger value="browse">
            <Store className="h-3.5 w-3.5" /> 浏览市场
          </TabsTrigger>
          <TabsTrigger value="mine">
            <Send className="h-3.5 w-3.5" /> 我的申请
          </TabsTrigger>
          <TabsTrigger value="incoming">
            <Inbox className="h-3.5 w-3.5" /> 待我审批
          </TabsTrigger>
        </TabsList>

        <TabsContent value="browse" className="mt-3">
          <BrowseTab />
        </TabsContent>
        <TabsContent value="mine" className="mt-3">
          <MyRequestsTab />
        </TabsContent>
        <TabsContent value="incoming" className="mt-3">
          <IncomingTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function BrowseTab() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['market'],
    queryFn: () => api.browseMarket(),
  })
  const [busyId, setBusyId] = useState<string | null>(null)

  const apply = async (m: MarketItem) => {
    setBusyId(m.project_id)
    try {
      await api.applyMarket(m.project_id)
      toast.success('申请已提交，等待项目所有者审批')
      qc.invalidateQueries({ queryKey: ['market'] })
      qc.invalidateQueries({ queryKey: ['my-access-requests'] })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '申请失败')
    } finally {
      setBusyId(null)
    }
  }

  if (isLoading) return <Loading />
  const items = data?.items || []
  if (items.length === 0) return <Empty text="市场里还没有已发布的项目。" />

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {items.map((m) => (
        <div key={m.project_id} className="flex flex-col rounded-xl border border-border bg-card p-4">
          <div className="mb-1 flex items-start justify-between gap-2">
            <span className="text-[14px] font-semibold text-foreground">{m.name}</span>
            {RELATION_LABEL[m.my_status] && (
              <Badge variant="outline" className="shrink-0 text-[10px]">
                {RELATION_LABEL[m.my_status]}
              </Badge>
            )}
          </div>
          <p className="mb-3 line-clamp-2 min-h-[2lh] text-[12px] text-muted-foreground">
            {m.description || '（无描述）'}
          </p>
          <div className="mb-3 text-[11px] text-muted-foreground">
            所有者：{m.owner_name || '—'} · 默认授予：
            {m.market_default_role === 'editor' ? '读写' : '只读'}
          </div>
          <div className="mt-auto">
            {m.my_status === 'none' ? (
              <Button
                size="sm"
                className="w-full"
                disabled={busyId === m.project_id}
                onClick={() => apply(m)}
              >
                申请访问
              </Button>
            ) : (
              <Button size="sm" variant="outline" className="w-full" disabled>
                {m.my_status === 'pending'
                  ? '申请中…'
                  : m.my_status === 'member'
                    ? '已加入'
                    : '我的项目'}
              </Button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function MyRequestsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ['my-access-requests'],
    queryFn: () => api.myAccessRequests(),
  })
  if (isLoading) return <Loading />
  const items = data?.items || []
  if (items.length === 0) return <Empty text="你还没有提交过访问申请。" />
  return <RequestTable items={items} />
}

function IncomingTab() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['incoming-access-requests'],
    queryFn: () => api.incomingAccessRequests(),
  })
  const [busy, setBusy] = useState<number | null>(null)

  const decide = async (id: number, approve: boolean) => {
    setBusy(id)
    try {
      if (approve) await api.approveAccessRequest(id)
      else await api.rejectAccessRequest(id)
      toast.success(approve ? '已通过申请' : '已拒绝申请')
      qc.invalidateQueries({ queryKey: ['incoming-access-requests'] })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '操作失败')
    } finally {
      setBusy(null)
    }
  }

  if (isLoading) return <Loading />
  const items = data?.items || []
  if (items.length === 0) return <Empty text="暂无待审批的申请。" />

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-[12px] text-muted-foreground">
          <tr>
            <th className="px-4 py-2.5 text-left font-medium">项目</th>
            <th className="px-4 py-2.5 text-left font-medium">申请人</th>
            <th className="px-4 py-2.5 text-left font-medium">申请权限</th>
            <th className="px-4 py-2.5 text-left font-medium">留言</th>
            <th className="px-4 py-2.5 text-right font-medium">操作</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((r) => (
            <tr key={r.id} className="hover:bg-muted/30">
              <td className="px-4 py-2.5 font-medium text-foreground">{r.project_name}</td>
              <td className="px-4 py-2.5 text-muted-foreground">{r.requester_name}</td>
              <td className="px-4 py-2.5">
                <Badge variant="outline">
                  {r.requested_role === 'editor' ? '读写' : '只读'}
                </Badge>
              </td>
              <td className="px-4 py-2.5 text-muted-foreground">{r.note || '—'}</td>
              <td className="px-4 py-2.5">
                <div className="flex justify-end gap-1">
                  <Button
                    size="sm"
                    disabled={busy === r.id}
                    onClick={() => decide(r.id, true)}
                  >
                    <Check className="h-3.5 w-3.5" /> 通过
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="text-destructive hover:text-destructive"
                    disabled={busy === r.id}
                    onClick={() => decide(r.id, false)}
                  >
                    <X className="h-3.5 w-3.5" /> 拒绝
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RequestTable({ items }: { items: AccessRequest[] }) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-[12px] text-muted-foreground">
          <tr>
            <th className="px-4 py-2.5 text-left font-medium">项目</th>
            <th className="px-4 py-2.5 text-left font-medium">申请权限</th>
            <th className="px-4 py-2.5 text-left font-medium">状态</th>
            <th className="px-4 py-2.5 text-left font-medium">留言</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((r) => (
            <tr key={r.id} className="hover:bg-muted/30">
              <td className="px-4 py-2.5 font-medium text-foreground">{r.project_name}</td>
              <td className="px-4 py-2.5">
                <Badge variant="outline">
                  {r.requested_role === 'editor' ? '读写' : '只读'}
                </Badge>
              </td>
              <td className="px-4 py-2.5">
                <span
                  className={
                    r.status === 'approved'
                      ? 'text-emerald-600'
                      : r.status === 'rejected'
                        ? 'text-destructive'
                        : 'text-muted-foreground'
                  }
                >
                  {STATUS_LABEL[r.status] || r.status}
                </span>
              </td>
              <td className="px-4 py-2.5 text-muted-foreground">{r.note || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Loading() {
  return <div className="py-8 text-center text-muted-foreground">加载中…</div>
}

function Empty({ text }: { text: string }) {
  return <div className="py-10 text-center text-[13px] text-muted-foreground">{text}</div>
}

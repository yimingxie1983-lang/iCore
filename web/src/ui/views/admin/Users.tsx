

import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Pencil,
  Trash2,
  ShieldCheck,
  User as UserIcon,
  UserPlus,
  Coins,
  FolderKey,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'

import { api, type AuthUser } from '@/client/services/client'
import { useAuthStore } from '@/application/state/authStore'
import { Button } from '@/ui/widgets/ui/button'
import { Input } from '@/ui/widgets/ui/input'
import { Label } from '@/ui/widgets/ui/label'
import { Switch } from '@/ui/widgets/ui/switch'
import { Separator } from '@/ui/widgets/ui/separator'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/ui/widgets/ui/dialog'
import {
  formatCredits,
  formatCNY,
  TransactionsTable,
  TxPagination,
  TX_PAGE_SIZE,
} from '@/ui/views/Credits'
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
import { Badge } from '@/ui/widgets/ui/badge'
import { toast } from '@/ui/widgets/ui/sonner'

const USER_PAGE_SIZE = 20
const USER_PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const

function UsersPagination({
  total,
  limit,
  offset,
  onOffset,
  onLimit,
  pageSizeOptions,
}: {
  total: number
  limit: number
  offset: number
  onOffset: (next: number) => void
  onLimit: (next: number) => void
  pageSizeOptions: readonly number[]
}) {
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + limit, total)
  const canPrev = offset > 0
  const canNext = offset + limit < total
  const page = total === 0 ? 0 : Math.floor(offset / limit) + 1
  const pages = Math.max(1, Math.ceil(total / Math.max(1, limit)))
  const btn =
    'flex items-center gap-0.5 rounded-md border border-border px-2 py-1 text-[12px] ' +
    'transition-colors disabled:cursor-not-allowed disabled:opacity-40 ' +
    'enabled:hover:bg-muted'
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 text-[12px] text-muted-foreground">
      <div className="flex flex-wrap items-center gap-2">
        <span>
          {total === 0
            ? '共 0 条'
            : `共 ${total} 条 · 第 ${from}-${to} 条 · ${page}/${pages} 页`}
        </span>
        <label className="flex items-center gap-1">
          每页
          <select
            value={limit}
            onChange={(e) => onLimit(Number(e.target.value))}
            className="rounded-md border border-border bg-background px-1.5 py-1 text-[12px] text-foreground outline-none"
          >
            {pageSizeOptions.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          条
        </label>
      </div>
      <div className="flex gap-1.5">
        <button
          type="button"
          className={btn}
          disabled={!canPrev}
          onClick={() => onOffset(Math.max(0, offset - limit))}
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          上一页
        </button>
        <button
          type="button"
          className={btn}
          disabled={!canNext}
          onClick={() => onOffset(offset + limit)}
        >
          下一页
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

export default function AdminUsers() {
  const qc = useQueryClient()
  const meId = useAuthStore((s) => s.user?.id)

  const { data, isLoading } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => api.listUsers(),
  })

  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<AuthUser | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AuthUser | null>(null)
  const [creditsTarget, setCreditsTarget] = useState<AuthUser | null>(null)
  const [grantTarget, setGrantTarget] = useState<AuthUser | null>(null)
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [limit, setLimit] = useState<number>(USER_PAGE_SIZE)

  const refresh = () => qc.invalidateQueries({ queryKey: ['admin-users'] })

  const allItems = data?.items ?? []
  const q = query.trim().toLowerCase()
  const filtered = q
    ? allItems.filter((u) => {
        const hay = [u.username, u.display_name, u.email, u.role, u.status]
          .filter(Boolean)
          .join(' ')
          .toLowerCase()
        return hay.includes(q)
      })
    : allItems
  const total = filtered.length

  useEffect(() => {
    if (total === 0) {
      if (offset !== 0) setOffset(0)
      return
    }
    const maxOffset = Math.max(0, (Math.ceil(total / limit) - 1) * limit)
    if (offset > maxOffset) setOffset(maxOffset)
  }, [total, limit, offset])

  const changeQuery = (v: string) => {
    setQuery(v)
    setOffset(0)
  }
  const changeLimit = (n: number) => {
    setLimit(n)
    setOffset(0)
  }
  const visibleItems = filtered.slice(offset, offset + limit)

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden p-4 sm:p-6">
      <div className="mb-3 flex shrink-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-foreground">用户管理</h2>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            管理多用户账号、角色与启用状态
            {data ? ` · 共 ${data.total} 人` : ''}
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)} className="shrink-0 self-start sm:self-auto">
          <Plus className="h-4 w-4" />
          新建用户
        </Button>
      </div>

      {}
      <div className="mb-3 shrink-0">
        <RegistrationToggle />
      </div>

      <div className="mb-2 flex shrink-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <Input
          value={query}
          onChange={(e) => changeQuery(e.target.value)}
          placeholder="搜索用户名 / 显示名 / 邮箱…"
          className="h-9 max-w-sm"
        />
        {q && (
          <span className="text-[12px] text-muted-foreground">
            筛选后 {total} 人
          </span>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-card">
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="sticky top-0 z-10 bg-muted/95 text-[12px] text-muted-foreground backdrop-blur">
              <tr>
                <th className="px-4 py-2.5 text-left font-medium">用户名</th>
                <th className="px-4 py-2.5 text-left font-medium">显示名</th>
                <th className="hidden px-4 py-2.5 text-left font-medium md:table-cell">邮箱</th>
                <th className="px-4 py-2.5 text-left font-medium">角色</th>
                <th className="px-4 py-2.5 text-left font-medium">状态</th>
                <th className="px-4 py-2.5 text-right font-medium">积分余额</th>
                <th className="px-4 py-2.5 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading && (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-muted-foreground">
                    加载中…
                  </td>
                </tr>
              )}
              {!isLoading &&
                visibleItems.map((u) => (
                  <tr key={u.id} className="hover:bg-muted/30">
                    <td className="px-4 py-2.5 font-medium text-foreground">
                      {u.username}
                      {u.id === meId && (
                        <span className="ml-1.5 text-[11px] text-muted-foreground">（你）</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-muted-foreground">{u.display_name}</td>
                    <td className="hidden px-4 py-2.5 text-muted-foreground md:table-cell">
                      {u.email || '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      {u.role === 'admin' ? (
                        <Badge className="gap-1 bg-secondary/15 text-secondary">
                          <ShieldCheck className="h-3 w-3" /> 管理员
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="gap-1">
                          <UserIcon className="h-3 w-3" /> 普通用户
                        </Badge>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      {u.status === 'active' ? (
                        <span className="text-emerald-600">启用</span>
                      ) : (
                        <span className="text-destructive">已禁用</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <span
                        className={
                          'font-mono text-[13px] font-semibold ' +
                          ((u.credits_balance ?? 0) <= 0
                            ? 'text-destructive'
                            : 'text-foreground')
                        }
                      >
                        {formatCredits(u.credits_balance ?? 0)}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          title="积分充值 / 明细"
                          onClick={() => setCreditsTarget(u)}
                        >
                          <Coins className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          title="项目授权"
                          onClick={() => setGrantTarget(u)}
                        >
                          <FolderKey className="h-3.5 w-3.5" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditTarget(u)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-destructive hover:text-destructive"
                          disabled={u.id === meId}
                          onClick={() => setDeleteTarget(u)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              {!isLoading && total === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-muted-foreground">
                    {q ? '没有匹配的用户' : '暂无用户'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="shrink-0 border-t border-border bg-card px-4 py-2">
          <UsersPagination
            total={total}
            limit={limit}
            offset={offset}
            onOffset={setOffset}
            onLimit={changeLimit}
            pageSizeOptions={USER_PAGE_SIZE_OPTIONS}
          />
        </div>
      </div>

      {createOpen && (
        <CreateUserDialog
          onClose={() => setCreateOpen(false)}
          onDone={() => {
            setCreateOpen(false)
            refresh()
          }}
        />
      )}

      {editTarget && (
        <EditUserDialog
          user={editTarget}
          isSelf={editTarget.id === meId}
          onClose={() => setEditTarget(null)}
          onDone={() => {
            setEditTarget(null)
            refresh()
          }}
        />
      )}

      {creditsTarget && (
        <CreditsDialog
          user={creditsTarget}
          onClose={() => setCreditsTarget(null)}
          onChanged={refresh}
        />
      )}

      {grantTarget && (
        <GrantProjectDialog
          user={grantTarget}
          onClose={() => setGrantTarget(null)}
        />
      )}

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除用户</AlertDialogTitle>
            <AlertDialogDescription>
              确定删除用户「{deleteTarget?.username}」？该用户的项目授权会一并移除，
              其拥有的项目不会被删除（仍可由管理员接管）。此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={async () => {
                if (!deleteTarget) return
                try {
                  await api.deleteUser(deleteTarget.id)
                  toast.success('已删除用户')
                  refresh()
                } catch (e) {
                  toast.error(e instanceof Error ? e.message : '删除失败')
                } finally {
                  setDeleteTarget(null)
                }
              }}
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function RegistrationToggle() {
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['registration-setting'],
    queryFn: () => api.getRegistrationSetting(),
  })
  const allow = !!data?.allow_registration

  const onToggle = async (next: boolean) => {
    setBusy(true)
    try {
      await api.setRegistrationSetting(next)

      qc.setQueryData(['registration-setting'], { allow_registration: next })
      qc.invalidateQueries({ queryKey: ['registration-status'] })
      toast.success(next ? '已开放自助注册' : '已关闭自助注册')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '切换失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex items-center justify-between rounded-xl border border-border bg-card px-4 py-3">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
          <UserPlus className="h-4 w-4 text-muted-foreground" />
        </div>
        <div>
          <div className="text-sm font-medium text-foreground">自助注册</div>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            {allow
              ? '已开放：登录页对所有人显示"注册"入口。'
              : '已关闭：仅管理员可在此建号，登录页不显示注册入口。'}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-[12px] text-muted-foreground">
          {isLoading ? '读取中…' : allow ? '开启' : '关闭'}
        </span>
        <Switch
          checked={allow}
          disabled={isLoading || busy}
          onCheckedChange={onToggle}
          aria-label="自助注册开关"
        />
      </div>
    </div>
  )
}

function CreateUserDialog(props: { onClose: () => void; onDone: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<'user' | 'admin'>('user')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!username.trim() || password.length < 6) {
      toast.error('用户名必填，密码至少 6 位')
      return
    }
    setBusy(true)
    try {
      await api.createUser({
        username: username.trim(),
        password,
        display_name: displayName.trim() || undefined,
        email: email.trim() || undefined,
        role,
      })
      toast.success('用户已创建')
      props.onDone()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '创建失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && props.onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新建用户</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Field label="用户名">
            <Input value={username} onChange={(e) => setUsername(e.target.value)} />
          </Field>
          <Field label="密码（≥6 位）">
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Field label="显示名（可选）">
            <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </Field>
          <Field label="邮箱（可选）">
            <Input value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="角色">
            <Select value={role} onValueChange={(v) => setRole(v as 'user' | 'admin')}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="user">普通用户</SelectItem>
                <SelectItem value="admin">管理员</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={props.onClose}>
            取消
          </Button>
          <Button onClick={submit} disabled={busy}>
            {busy ? '创建中…' : '创建'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function EditUserDialog(props: {
  user: AuthUser
  isSelf: boolean
  onClose: () => void
  onDone: () => void
}) {
  const { user, isSelf } = props
  const [displayName, setDisplayName] = useState(user.display_name)
  const [email, setEmail] = useState(user.email)
  const [role, setRole] = useState<'user' | 'admin'>(
    user.role === 'admin' ? 'admin' : 'user',
  )
  const [status, setStatus] = useState<'active' | 'disabled'>(
    user.status === 'disabled' ? 'disabled' : 'active',
  )
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (password && password.length < 6) {
      toast.error('新密码至少 6 位')
      return
    }
    setBusy(true)
    try {
      await api.updateUser(user.id, {
        display_name: displayName,
        email,
        role,
        status,
        password: password || undefined,
      })
      toast.success('已保存')
      props.onDone()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && props.onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>编辑用户 · {user.username}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Field label="显示名">
            <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </Field>
          <Field label="邮箱">
            <Input value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="角色">
            <Select
              value={role}
              onValueChange={(v) => setRole(v as 'user' | 'admin')}
              disabled={isSelf}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="user">普通用户</SelectItem>
                <SelectItem value="admin">管理员</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="状态">
            <Select
              value={status}
              onValueChange={(v) => setStatus(v as 'active' | 'disabled')}
              disabled={isSelf}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="active">启用</SelectItem>
                <SelectItem value="disabled">禁用</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field label="重置密码（留空不改）">
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="如需重置，输入新密码"
            />
          </Field>

          {}
          {role !== 'admin' && <UserRolesPicker userId={user.id} />}

          {isSelf && (
            <p className="text-[11px] text-muted-foreground">
              不能修改自己的角色或禁用自己，以免把自己锁在门外。
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={props.onClose}>
            取消
          </Button>
          <Button onClick={submit} disabled={busy}>
            {busy ? '保存中…' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Field(props: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{props.label}</Label>
      {props.children}
    </div>
  )
}

function UserRolesPicker({ userId }: { userId: string }) {
  const { data: allRoles } = useQuery({
    queryKey: ['roles'],
    queryFn: () => api.listRoles(),
  })
  const { data: userRoles } = useQuery({
    queryKey: ['user-roles', userId],
    queryFn: () => api.getUserRoles(userId),
  })

  const [selected, setSelected] = useState<Set<string> | null>(null)
  const [busy, setBusy] = useState(false)

  const current = selected ?? new Set((userRoles?.items || []).map((r) => r.id))

  const toggle = async (rid: string) => {
    const next = new Set(current)
    if (next.has(rid)) next.delete(rid)
    else next.add(rid)
    setSelected(next)
    setBusy(true)
    try {
      await api.setUserRoles(userId, [...next])
      toast.success('角色已更新')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '更新失败')
      setSelected(null)
    } finally {
      setBusy(false)
    }
  }

  const roles = allRoles?.items || []
  return (
    <div className="space-y-1.5">
      <Label>自定义角色（决定菜单与操作权限）</Label>
      {roles.length === 0 ? (
        <p className="text-[12px] text-muted-foreground">
          还没有角色，先到「角色管理」创建。未分配角色的用户默认拥有基础业务权限。
        </p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {roles.map((r) => {
            const on = current.has(r.id)
            return (
              <button
                key={r.id}
                type="button"
                disabled={busy}
                onClick={() => toggle(r.id)}
                className={
                  'rounded-full border px-2.5 py-1 text-[12px] transition-colors ' +
                  (on
                    ? 'border-secondary bg-secondary/15 text-secondary'
                    : 'border-border text-muted-foreground hover:bg-muted')
                }
                title={r.description}
              >
                {r.name}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function GrantProjectDialog(props: {
  user: AuthUser
  onClose: () => void
}) {
  const { user } = props
  const { data: projects } = useQuery({
    queryKey: ['admin-all-projects'],
    queryFn: () => api.listProjects(),
  })
  const [projectId, setProjectId] = useState('')
  const [role, setRole] = useState<'editor' | 'viewer'>('viewer')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!projectId) {
      toast.error('请选择要授权的项目')
      return
    }
    setBusy(true)
    try {
      await api.adminGrantProject(projectId, { username: user.username, role })
      toast.success(`已把项目授权给 ${user.username}`)
      props.onClose()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '授权失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && props.onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>项目授权 · {user.username}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Field label="选择项目">
            <Select value={projectId} onValueChange={setProjectId}>
              <SelectTrigger>
                <SelectValue placeholder="选择一个项目" />
              </SelectTrigger>
              <SelectContent>
                {(projects?.items || []).map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="授予权限">
            <Select value={role} onValueChange={(v) => setRole(v as 'editor' | 'viewer')}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="viewer">只读</SelectItem>
                <SelectItem value="editor">读写</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <p className="text-[11px] text-muted-foreground">
            授权后该用户可在「项目」列表看到此项目。此入口不受"共享市场"开关限制。
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={props.onClose}>
            取消
          </Button>
          <Button onClick={submit} disabled={busy}>
            {busy ? '授权中…' : '授权'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function CreditsDialog(props: {
  user: AuthUser
  onClose: () => void
  onChanged: () => void
}) {
  const { user } = props
  const qc = useQueryClient()

  const [offset, setOffset] = useState(0)
  const [limit, setLimit] = useState<number>(TX_PAGE_SIZE)

  const { data: bal } = useQuery({
    queryKey: ['admin-user-credits', user.id],
    queryFn: () => api.getUserCredits(user.id),
  })
  const { data: txs } = useQuery({
    queryKey: ['admin-user-tx', user.id, offset, limit],
    queryFn: () =>
      api.getUserCreditTransactions(user.id, { limit, offset }),
  })

  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const refreshAll = () => {
    setOffset(0)
    qc.invalidateQueries({ queryKey: ['admin-user-credits', user.id] })
    qc.invalidateQueries({ queryKey: ['admin-user-tx', user.id] })
    props.onChanged()
  }

  const doRecharge = async () => {
    const amt = parseInt(amount)
    if (!amt || amt <= 0) {
      toast.error('请输入正整数充值积分')
      return
    }
    setBusy(true)
    try {
      await api.rechargeUser(user.id, { amount: amt, reason: reason.trim() || undefined })
      toast.success(`已充值 ${formatCredits(amt)} 积分`)
      setAmount('')
      setReason('')
      refreshAll()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '充值失败')
    } finally {
      setBusy(false)
    }
  }

  const doAdjust = async (sign: 1 | -1) => {
    const amt = parseInt(amount)
    if (!amt || amt <= 0) {
      toast.error('请输入调整积分数（正整数）')
      return
    }
    setBusy(true)
    try {
      await api.adjustUser(user.id, { delta: sign * amt, reason: reason.trim() || undefined })
      toast.success(`已${sign > 0 ? '增加' : '扣减'} ${formatCredits(amt)} 积分`)
      setAmount('')
      setReason('')
      refreshAll()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '调整失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && props.onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>积分管理 · {user.username}</DialogTitle>
        </DialogHeader>

        {}
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-lg border border-border bg-muted/30 p-3">
            <div className="text-[11px] text-muted-foreground">当前余额</div>
            <div className="mt-0.5 font-mono text-xl font-bold text-primary">
              {formatCredits(bal?.balance ?? user.credits_balance ?? 0)}
            </div>
          </div>
          <div className="rounded-lg border border-border bg-muted/30 p-3">
            <div className="text-[11px] text-muted-foreground">累计消费</div>
            <div className="mt-0.5 font-mono text-xl font-bold text-foreground">
              {formatCredits(bal?.total_consumed ?? 0)}
            </div>
          </div>
          <div className="rounded-lg border border-border bg-muted/30 p-3">
            <div className="text-[11px] text-muted-foreground">累计成本</div>
            <div className="mt-0.5 font-mono text-xl font-bold text-foreground">
              {formatCNY(bal?.total_cost_cny ?? 0)}
            </div>
          </div>
        </div>

        {}
        <div className="space-y-2 rounded-lg border border-border p-3">
          <div className="flex gap-2">
            <div className="flex-1">
              <Label className="text-[12px]">积分数</Label>
              <Input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="如 50000"
                className="mt-1 h-9"
              />
            </div>
            <div className="flex-[2]">
              <Label className="text-[12px]">备注（可选）</Label>
              <Input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="充值 / 调整说明"
                className="mt-1 h-9"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <Button className="flex-1" disabled={busy} onClick={doRecharge}>
              充值
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => doAdjust(1)}
            >
              手动 +
            </Button>
            <Button
              variant="outline"
              className="text-destructive hover:text-destructive"
              disabled={busy}
              onClick={() => doAdjust(-1)}
            >
              手动 −
            </Button>
          </div>
        </div>

        <Separator />

        {}
        <div className="max-h-[320px] overflow-y-auto">
          <TransactionsTable items={txs?.items ?? []} />
        </div>
        <TxPagination
          total={txs?.total ?? 0}
          limit={limit}
          offset={offset}
          onOffset={setOffset}
          onLimit={(n) => {
            setLimit(n)
            setOffset(0)
          }}
        />

        <DialogFooter>
          <Button variant="outline" onClick={props.onClose}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

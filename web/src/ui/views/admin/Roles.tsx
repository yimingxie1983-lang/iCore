

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2, ShieldCheck, Lock } from 'lucide-react'

import { api, type Role } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import { Input } from '@/ui/widgets/ui/input'
import { Label } from '@/ui/widgets/ui/label'
import { Badge } from '@/ui/widgets/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/ui/widgets/ui/dialog'
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
import { toast } from '@/ui/widgets/ui/sonner'

export default function AdminRoles() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['roles'],
    queryFn: () => api.listRoles(),
  })

  const [editTarget, setEditTarget] = useState<Role | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Role | null>(null)

  const refresh = () => qc.invalidateQueries({ queryKey: ['roles'] })

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-foreground">角色管理</h2>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            自定义 RBAC：为角色勾选菜单与操作权限，再到「用户管理」把角色分配给用户。
            管理员（admin）恒拥有全部权限，不受此处约束。
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" />
          新建角色
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {isLoading && (
          <div className="col-span-full py-8 text-center text-muted-foreground">
            加载中…
          </div>
        )}
        {(data?.items || []).map((r) => (
          <div
            key={r.id}
            className="flex flex-col rounded-xl border border-border bg-card p-4"
          >
            <div className="mb-2 flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-secondary" />
                <span className="text-[14px] font-semibold text-foreground">
                  {r.name}
                </span>
                {r.is_system && (
                  <Badge variant="outline" className="gap-1 text-[10px]">
                    <Lock className="h-2.5 w-2.5" /> 系统
                  </Badge>
                )}
              </div>
              <div className="flex gap-1">
                <Button size="icon-sm" variant="ghost" onClick={() => setEditTarget(r)}>
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  className="text-destructive hover:text-destructive"
                  disabled={r.is_system}
                  title={r.is_system ? '系统角色不可删除' : '删除角色'}
                  onClick={() => setDeleteTarget(r)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
            <p className="mb-3 line-clamp-2 min-h-[2lh] text-[12px] text-muted-foreground">
              {r.description || '（无描述）'}
            </p>
            <div className="mt-auto text-[11px] text-muted-foreground">
              权限点：{r.permissions.length} 个
            </div>
          </div>
        ))}
        {data && data.items.length === 0 && !isLoading && (
          <div className="col-span-full py-8 text-center text-muted-foreground">
            还没有角色，点右上角新建。
          </div>
        )}
      </div>

      {createOpen && (
        <RoleDialog
          onClose={() => setCreateOpen(false)}
          onDone={() => {
            setCreateOpen(false)
            refresh()
          }}
        />
      )}
      {editTarget && (
        <RoleDialog
          role={editTarget}
          onClose={() => setEditTarget(null)}
          onDone={() => {
            setEditTarget(null)
            refresh()
          }}
        />
      )}

      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除角色「{deleteTarget?.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              删除后，绑定了该角色的用户会失去由此角色带来的权限。此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={async () => {
                if (!deleteTarget) return
                try {
                  await api.deleteRole(deleteTarget.id)
                  toast.success('角色已删除')
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

function RoleDialog(props: {
  role?: Role
  onClose: () => void
  onDone: () => void
}) {
  const { role } = props
  const isEdit = !!role
  const [name, setName] = useState(role?.name || '')
  const [description, setDescription] = useState(role?.description || '')
  const [perms, setPerms] = useState<Set<string>>(new Set(role?.permissions || []))
  const [busy, setBusy] = useState(false)

  const { data: catalog } = useQuery({
    queryKey: ['perm-catalog'],
    queryFn: () => api.getPermissionCatalog(),
  })

  const toggle = (key: string) => {
    setPerms((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const submit = async () => {
    if (!name.trim()) {
      toast.error('请输入角色名')
      return
    }
    setBusy(true)
    try {
      if (isEdit && role) {
        await api.updateRole(role.id, {
          name: name.trim(),
          description,
          permissions: [...perms],
        })
      } else {
        await api.createRole({
          name: name.trim(),
          description,
          permissions: [...perms],
        })
      }
      toast.success(isEdit ? '角色已保存' : '角色已创建')
      props.onDone()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && props.onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? `编辑角色 · ${role?.name}` : '新建角色'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>角色名</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>描述（可选）</Label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>权限点</Label>
            <div className="max-h-[46vh] space-y-4 overflow-y-auto rounded-lg border border-border p-3">
              {(catalog?.groups || []).map((g) => (
                <div key={g.group}>
                  <div className="mb-1.5 text-[12px] font-semibold text-foreground">
                    {g.label}
                    <span className="ml-1.5 font-normal text-muted-foreground">
                      {g.desc}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {g.items.map((it) => {
                      const on = perms.has(it.key)
                      return (
                        <button
                          key={it.key}
                          type="button"
                          onClick={() => toggle(it.key)}
                          className={
                            'rounded-full border px-2.5 py-1 text-[12px] transition-colors ' +
                            (on
                              ? 'border-secondary bg-secondary/15 text-secondary'
                              : 'border-border text-muted-foreground hover:bg-muted')
                          }
                        >
                          {it.label}
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              已选 {perms.size} 个权限点。菜单键控制侧边栏可见性，操作键控制后台操作放行。
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={props.onClose}>
            取消
          </Button>
          <Button onClick={submit} disabled={busy}>
            {busy ? '保存中…' : isEdit ? '保存' : '创建'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

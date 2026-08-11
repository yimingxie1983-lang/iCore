

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2, UserPlus } from 'lucide-react'

import { api, type ProjectMember } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import { Input } from '@/ui/widgets/ui/input'
import { Label } from '@/ui/widgets/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/ui/widgets/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/ui/widgets/ui/select'
import { toast } from '@/ui/widgets/ui/sonner'

interface Props {
  projectId: string
  projectName: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export default function ShareProjectDialog({
  projectId,
  projectName,
  open,
  onOpenChange,
}: Props) {
  const qc = useQueryClient()
  const [username, setUsername] = useState('')
  const [role, setRole] = useState<'editor' | 'viewer'>('editor')
  const [busy, setBusy] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['project-members', projectId],
    queryFn: () => api.listProjectMembers(projectId),
    enabled: open,
  })

  const refresh = () =>
    qc.invalidateQueries({ queryKey: ['project-members', projectId] })

  const onAdd = async () => {
    const u = username.trim()
    if (!u) {
      toast.error('请输入要共享的用户名')
      return
    }
    setBusy(true)
    try {
      await api.addProjectMember(projectId, { username: u, role })
      toast.success(`已共享给 ${u}`)
      setUsername('')
      refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '添加失败')
    } finally {
      setBusy(false)
    }
  }

  const onRemove = async (m: ProjectMember) => {
    try {
      await api.removeProjectMember(projectId, m.user_id)
      toast.success(`已移除 ${m.username}`)
      refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '移除失败')
    }
  }

  const onChangeRole = async (m: ProjectMember, next: 'editor' | 'viewer') => {
    if (next === m.role) return
    try {
      await api.updateProjectMember(projectId, m.user_id, next)
      toast.success(`已把 ${m.username} 设为${next === 'editor' ? '读写' : '只读'}`)
      refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '修改失败')
    }
  }

  const members = data?.items || []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>共享项目 · {projectName}</DialogTitle>
          <DialogDescription>
            把项目共享给其他用户协作。读写成员可发对话、传文件；只读成员仅能查看会话与消息。
          </DialogDescription>
        </DialogHeader>

        {}
        <div className="flex items-end gap-2">
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="share-username">用户名</Label>
            <Input
              id="share-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="对方的登录用户名"
              onKeyDown={(e) => {
                if (e.key === 'Enter') onAdd()
              }}
            />
          </div>
          <div className="w-28 space-y-1.5">
            <Label>权限</Label>
            <Select value={role} onValueChange={(v) => setRole(v as 'editor' | 'viewer')}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="editor">读写</SelectItem>
                <SelectItem value="viewer">只读</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button onClick={onAdd} disabled={busy}>
            <UserPlus className="h-4 w-4" />
            添加
          </Button>
        </div>

        {}
        <div className="mt-2 max-h-64 overflow-y-auto rounded-lg border border-border">
          {isLoading ? (
            <div className="px-4 py-6 text-center text-[12px] text-muted-foreground">
              加载中…
            </div>
          ) : members.length === 0 ? (
            <div className="px-4 py-6 text-center text-[12px] text-muted-foreground">
              还没有共享给任何人。添加成员后他们就能在「项目」列表里看到此项目。
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {members.map((m) => (
                <li key={m.user_id} className="flex items-center gap-3 px-3 py-2.5">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-muted text-[11px] font-semibold text-foreground">
                    {(m.display_name || m.username).slice(0, 1).toUpperCase()}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-medium text-foreground">
                      {m.display_name || m.username}
                    </div>
                    <div className="truncate text-[11px] text-muted-foreground">
                      @{m.username}
                    </div>
                  </div>
                  <Select
                    value={m.role === 'viewer' ? 'viewer' : 'editor'}
                    onValueChange={(v) => onChangeRole(m, v as 'editor' | 'viewer')}
                  >
                    <SelectTrigger className="h-8 w-24 shrink-0">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="editor">读写</SelectItem>
                      <SelectItem value="viewer">只读</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                    onClick={() => onRemove(m)}
                  >
                    <Trash2 />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

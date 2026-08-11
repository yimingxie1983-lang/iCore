

import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'

import { api, type Project } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import { Input } from '@/ui/widgets/ui/input'
import { Label } from '@/ui/widgets/ui/label'
import { Textarea } from '@/ui/widgets/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/ui/widgets/ui/dialog'
import { toast } from '@/ui/widgets/ui/sonner'

interface CreateProjectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void

  navigateAfterCreate?: boolean

  onCreated?: (project: Project) => void
}

export default function CreateProjectDialog({
  open,
  onOpenChange,
  navigateAfterCreate = true,
  onCreated,
}: CreateProjectDialogProps) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [form, setForm] = useState({ name: '', description: '' })

  useEffect(() => {
    if (!open) {
      const t = setTimeout(() => setForm({ name: '', description: '' }), 200)
      return () => clearTimeout(t)
    }
  }, [open])

  const mut = useMutation({
    mutationFn: () => api.createProject(form),
    onSuccess: (proj) => {
      toast.success(`项目「${proj.name}」已创建`)
      qc.invalidateQueries({ queryKey: ['projects'] })
      onOpenChange(false)
      onCreated?.(proj)
      if (navigateAfterCreate) {
        navigate(`/chat/${proj.id}`)
      }
    },
    onError: (e: Error) => toast.error('创建失败', { description: e.message }),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新建项目</DialogTitle>
          <DialogDescription>
            填一个名字就能开始对话。需要数据目录 / 初始人格等更多字段，
            请用「
            <Link
              to="/projects/new"
              className="text-secondary underline underline-offset-2 hover:text-secondary/80"
              onClick={() => onOpenChange(false)}
            >
              完整创建页
            </Link>
            」。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-1">
          <div className="grid gap-1.5">
            <Label htmlFor="cpd-name">
              项目名称 <span className="text-destructive">*</span>
            </Label>
            <Input
              id="cpd-name"
              autoFocus
              value={form.name}
              placeholder="例如：胰腺癌随访项目-2026"
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && form.name.trim() && !mut.isPending) {
                  e.preventDefault()
                  mut.mutate()
                }
              }}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="cpd-desc">项目描述</Label>
            <Textarea
              id="cpd-desc"
              rows={3}
              value={form.description}
              placeholder="一句话说明项目目标 / 数据来源 / 关键问题"
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button disabled={!form.name.trim() || mut.isPending} onClick={() => mut.mutate()}>
            <Sparkles />
            {mut.isPending ? '创建中…' : '创建并进入对话'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

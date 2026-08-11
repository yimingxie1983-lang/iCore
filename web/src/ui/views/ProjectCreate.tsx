

import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  CheckCircle2,
  Database,
  FlaskConical,
  FolderOpen,
  FolderPlus,
  Info,
  Microscope,
  Sparkles,
  Stethoscope,
  Wand2,
} from 'lucide-react'

import { api } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import { Input } from '@/ui/widgets/ui/input'
import { Label } from '@/ui/widgets/ui/label'
import { Textarea } from '@/ui/widgets/ui/textarea'
import { Badge } from '@/ui/widgets/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/ui/widgets/ui/select'
import { Separator } from '@/ui/widgets/ui/separator'
import { toast } from '@/ui/widgets/ui/sonner'
import { cn } from '@/shared/foundation/utils'

interface Template {
  id: string
  title: string
  icon: React.ComponentType<{ className?: string }>
  tone: 'primary' | 'secondary' | 'accent' | 'success'
  name: string
  description: string
}

const TEMPLATES: Template[] = [
  {
    id: 'cohort',
    title: '临床队列分析',
    icon: Stethoscope,
    tone: 'primary',
    name: '临床队列项目-未命名',
    description:
      '【数据】CSV/Excel 病例表（去标识化）\n【目标】描述性统计 + 关键指标对比 + 出图\n【关注】生存分析、亚组差异、缺失值处理',
  },
  {
    id: 'omics',
    title: '组学数据探索',
    icon: Microscope,
    tone: 'secondary',
    name: '组学探索项目-未命名',
    description:
      '【数据】GEO / TCGA / 自有测序矩阵\n【目标】差异表达 / 富集 / 聚类\n【关注】批次效应、归一化、可视化',
  },
  {
    id: 'literature',
    title: '文献综述整理',
    icon: FlaskConical,
    tone: 'accent',
    name: '文献综述-未命名',
    description:
      '【范围】PubMed/Europe PMC/bioRxiv 近 5 年\n【目标】关键证据提取 + 综述 outline 草稿\n【关注】证据等级、矛盾点、可重复性',
  },
]

const TONE_BG: Record<Template['tone'], string> = {
  primary: 'bg-primary/[0.08] text-primary',
  secondary: 'bg-secondary/[0.12] text-secondary',
  accent: 'bg-accent/[0.14] text-accent',
  success: 'bg-emerald-500/[0.12] text-emerald-700',
}

export default function ProjectCreate() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [form, setForm] = useState({
    name: '',
    description: '',
    dataDir: '',
    personaId: '',
  })
  const [templateId, setTemplateId] = useState<string | null>(null)

  const { data: personasResp } = useQuery({
    queryKey: ['personas'],
    queryFn: () => api.listPersonas(),
    staleTime: 5 * 60_000,
  })
  const personas = personasResp?.items || []
  const defaultPersonaId = personasResp?.default_id || ''

  const createMut = useMutation({
    mutationFn: async () => {
      const extra: string[] = []
      if (form.dataDir.trim()) extra.push(`【数据目录】${form.dataDir.trim()}`)
      if (form.personaId) {
        const p = personas.find((x) => x.id === form.personaId)
        if (p) extra.push(`【默认人格】${p.name} (${p.id})`)
      }
      const description = [form.description.trim(), ...extra].filter(Boolean).join('\n\n')

      const proj = await api.createProject({
        name: form.name.trim(),
        description,
      })

      if (form.personaId && form.personaId !== defaultPersonaId) {
        try {
          await api.switchAgentPersona('claw_master', form.personaId)
        } catch (e) {
          toast.warning('人格切换失败', { description: String(e) })
        }
      }
      return proj
    },
    onSuccess: (proj) => {
      toast.success(`项目「${proj.name}」已创建`)
      qc.invalidateQueries({ queryKey: ['projects'] })
      navigate(`/chat/${proj.id}`)
    },
    onError: (e: Error) => toast.error('创建失败', { description: e.message }),
  })

  const canSubmit = useMemo(
    () => form.name.trim().length > 0 && !createMut.isPending,
    [form.name, createMut.isPending],
  )

  function applyTemplate(t: Template) {
    setTemplateId(t.id)
    setForm((f) => ({
      ...f,
      name: f.name || t.name,
      description: t.description,
    }))
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 p-6 lg:p-8">
        {}
        <div className="flex items-start gap-3">
          <Button variant="ghost" size="icon-sm" asChild className="mt-1">
            <Link to="/projects">
              <ArrowLeft />
            </Link>
          </Button>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1 text-[12px] text-muted-foreground">
              <Link to="/projects" className="hover:text-secondary">
                项目
              </Link>
              <span>/</span>
              <span className="text-foreground">新建</span>
            </div>
            <h1 className="mt-1 text-xl font-semibold tracking-tight lg:text-2xl">
              新建项目
            </h1>
            <p className="mt-1 text-[13px] text-muted-foreground">
              比快速弹窗多了模板、数据目录、默认人格等字段；填完会创建工作区并跳转到对话工作台。
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_320px]">
          {}
          <div className="flex flex-col gap-4">
            {}
            <div className="surface-card rounded-xl">
              <div className="flex items-center justify-between p-4 pb-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-accent" />
                  <h3 className="text-sm font-semibold">从模板开始</h3>
                  <Badge variant="muted" className="h-4 px-1.5 text-[10px] font-normal">
                    可选
                  </Badge>
                </div>
                <span className="text-[11px] text-muted-foreground">
                  点击套用描述模板，再按需修改
                </span>
              </div>
              <Separator />
              <div className="grid grid-cols-1 gap-2 p-3 md:grid-cols-3">
                {TEMPLATES.map((t) => {
                  const Icon = t.icon
                  const active = templateId === t.id
                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => applyTemplate(t)}
                      className={cn(
                        'group flex items-start gap-3 rounded-lg border p-3 text-left transition-all',
                        active
                          ? 'border-secondary bg-secondary/[0.04]'
                          : 'border-border hover:border-secondary/40 hover:bg-muted/40',
                      )}
                    >
                      <div
                        className={cn(
                          'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
                          TONE_BG[t.tone],
                        )}
                      >
                        <Icon className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-[13px] font-semibold">{t.title}</div>
                        <div className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">
                          {t.description.split('\n')[0]}
                        </div>
                      </div>
                      {active && (
                        <CheckCircle2 className="h-4 w-4 shrink-0 text-secondary" />
                      )}
                    </button>
                  )
                })}
              </div>
            </div>

            {}
            <div className="surface-card rounded-xl p-5">
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <FolderPlus className="h-4 w-4 text-primary" />
                基础信息
              </h3>
              <div className="grid gap-4">
                <div className="grid gap-1.5">
                  <Label htmlFor="name">
                    项目名称 <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="name"
                    value={form.name}
                    placeholder="例如：胰腺癌随访队列-2026"
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  />
                  <p className="text-[11px] text-muted-foreground">
                    建议带年份或关键词，便于在项目列表里快速识别
                  </p>
                </div>

                <div className="grid gap-1.5">
                  <Label htmlFor="desc">项目描述</Label>
                  <Textarea
                    id="desc"
                    rows={6}
                    value={form.description}
                    placeholder="说明项目目标 / 数据来源 / 关键问题 / 风险点"
                    onChange={(e) =>
                      setForm((f) => ({ ...f, description: e.target.value }))
                    }
                  />
                  <p className="text-[11px] text-muted-foreground">
                    这段会作为项目"门面"，并在对话首轮被注入到上下文里给智能体看
                  </p>
                </div>
              </div>
            </div>

            {}
            <div className="surface-card rounded-xl p-5">
              <div className="mb-1 flex items-center gap-2">
                <Wand2 className="h-4 w-4 text-secondary" />
                <h3 className="text-sm font-semibold">进阶配置</h3>
                <Badge variant="muted" className="h-4 px-1.5 text-[10px] font-normal">
                  可选
                </Badge>
              </div>
              <p className="mb-4 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <Info className="h-3 w-3" />
                v0.1 后端 schema 暂不支持原生字段，这里会拼到描述末尾 + 启动后自动切人格
              </p>
              <div className="grid gap-4">
                <div className="grid gap-1.5">
                  <Label htmlFor="data-dir">
                    <Database className="mr-1 inline h-3 w-3" />
                    数据目录
                  </Label>
                  <Input
                    id="data-dir"
                    value={form.dataDir}
                    placeholder="例如：D:/research/pancreas-2026/raw"
                    onChange={(e) => setForm((f) => ({ ...f, dataDir: e.target.value }))}
                  />
                  <p className="text-[11px] text-muted-foreground">
                    绝对路径或相对 workspace 的路径都可以
                  </p>
                </div>

                <div className="grid gap-1.5">
                  <Label>
                    <Sparkles className="mr-1 inline h-3 w-3" />
                    默认人格
                  </Label>
                  <Select
                    value={form.personaId}
                    onValueChange={(v) => setForm((f) => ({ ...f, personaId: v }))}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="使用系统默认人格" />
                    </SelectTrigger>
                    <SelectContent>
                      {personas.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          <span className="inline-flex items-center gap-2">
                            <span>{p.icon || '🦀'}</span>
                            <span className="font-medium">{p.name}</span>
                            {p.id === defaultPersonaId && (
                              <Badge variant="muted" className="ml-1 h-4 px-1 text-[10px]">
                                默认
                              </Badge>
                            )}
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-[11px] text-muted-foreground">
                    选择后会立刻给 <code className="font-mono">claw_master</code> 切到该人格
                  </p>
                </div>
              </div>
            </div>
          </div>

          {}
          <div className="lg:sticky lg:top-6 lg:self-start">
            <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              实时预览
            </div>
            <div className="mt-2 surface-card surface-card-hover rounded-xl p-5">
              <div className="mb-3 flex items-start gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-secondary/[0.10] text-secondary">
                  <FolderOpen className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <h4 className="truncate text-[14px] font-semibold tracking-tight">
                    {form.name.trim() || '（未命名项目）'}
                  </h4>
                  <div className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground">
                    ID 将在创建时生成
                  </div>
                </div>
              </div>
              <p className="mb-3 line-clamp-6 text-[12px] leading-relaxed text-muted-foreground whitespace-pre-line">
                {form.description.trim() || (
                  <span className="italic">（未填写描述）</span>
                )}
              </p>

              {(form.dataDir || form.personaId) && (
                <>
                  <Separator className="my-3" />
                  <div className="space-y-1.5">
                    {form.dataDir && (
                      <div className="flex items-center gap-1.5 text-[11px]">
                        <Database className="h-3 w-3 text-muted-foreground" />
                        <code className="truncate font-mono text-[10.5px]">{form.dataDir}</code>
                      </div>
                    )}
                    {form.personaId && (
                      <div className="flex items-center gap-1.5 text-[11px]">
                        <Sparkles className="h-3 w-3 text-muted-foreground" />
                        <span>
                          人格:{' '}
                          {personas.find((p) => p.id === form.personaId)?.name ||
                            form.personaId}
                        </span>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>

            <div className="mt-4 flex gap-2">
              <Button
                variant="outline"
                onClick={() => navigate('/projects')}
                className="flex-1"
              >
                取消
              </Button>
              <Button
                disabled={!canSubmit}
                onClick={() => createMut.mutate()}
                className="flex-1"
              >
                <Sparkles />
                {createMut.isPending ? '创建中…' : '创建'}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

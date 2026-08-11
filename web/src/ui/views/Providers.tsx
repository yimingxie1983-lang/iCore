

import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Globe,
  KeyRound,
  Network,
  Pencil,
  Plus,
  PowerOff,
  Trash2,
} from 'lucide-react'

import { api, type ModelInfo, type Provider, type ProviderUpsert } from '@/client/services/client'
import { useAuthStore } from '@/application/state/authStore'
import { Badge } from '@/ui/widgets/ui/badge'
import { Button } from '@/ui/widgets/ui/button'
import { Input } from '@/ui/widgets/ui/input'
import { Label } from '@/ui/widgets/ui/label'
import { Skeleton } from '@/ui/widgets/ui/skeleton'
import { Switch } from '@/ui/widgets/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogFooter,
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

import PageHeader from '@/ui/widgets/common/PageHeader'
import StatCard from '@/ui/widgets/common/StatCard'
import EmptyState from '@/ui/widgets/common/EmptyState'
import { cn } from '@/shared/foundation/utils'

const BRAND_BAR: Record<string, string> = {
  qwen: 'from-violet-500 to-orange-400',
  deepseek: 'from-blue-600 to-cyan-500',
  openai: 'from-emerald-500 to-teal-500',
  anthropic: 'from-amber-500 to-orange-500',
  gemini: 'from-blue-500 to-purple-500',
  zhipu: 'from-sky-500 to-indigo-500',
  kimi: 'from-fuchsia-500 to-purple-500',
  moonshot: 'from-fuchsia-500 to-purple-500',
}

const ROLE_OPTIONS = ['general', 'fast', 'complex', 'vision'] as const

function brandBarOf(id: string): string {
  const key = id.toLowerCase()
  for (const brand of Object.keys(BRAND_BAR)) {
    if (key.includes(brand)) return BRAND_BAR[brand]
  }
  return 'from-slate-400 to-slate-600'
}

function modelRoleClass(role: string): string {
  switch (role) {
    case 'complex':
      return 'bg-primary/10 text-primary border-primary/20'
    case 'general':
      return 'bg-secondary/10 text-secondary border-secondary/20'
    case 'fast':
      return 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20'
    case 'vision':
      return 'bg-violet-500/10 text-violet-700 border-violet-500/20'
    default:
      return 'bg-muted text-muted-foreground border-border'
  }
}

function hasApiKey(p: Provider): boolean {
  return !!p.api_key_preview
}

function ProviderCard({
  p,
  isAdmin,
  onEdit,
  onDelete,
  onToggle,
  toggleBusy,
}: {
  p: Provider
  isAdmin: boolean
  onEdit: () => void
  onDelete: () => void
  onToggle: (next: boolean) => void
  toggleBusy: boolean
}) {
  const keyed = hasApiKey(p)
  return (
    <div
      className={cn(
        'surface-card surface-card-hover relative flex flex-col overflow-hidden rounded-xl transition-all',
        !p.enabled && 'opacity-65',
      )}
    >
      {}
      <div className={cn('h-1 bg-gradient-to-r', brandBarOf(p.id))} />

      <div className="flex flex-col gap-4 p-5">
        {}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="truncate text-[15px] font-semibold tracking-tight">{p.name}</h3>
              {!p.enabled && (
                <Badge variant="muted" className="h-4 px-1.5 text-[10px] font-normal">
                  已禁用
                </Badge>
              )}
            </div>
            <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
              <code className="font-mono">{p.id}</code>
              <span>·</span>
              <span>优先级 {p.priority}</span>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Switch
              checked={p.enabled}
              disabled={!isAdmin || toggleBusy}
              onCheckedChange={onToggle}
              aria-label="启用开关"
            />
            {isAdmin && (
              <>
                <Button size="sm" variant="ghost" onClick={onEdit} aria-label="编辑">
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive hover:text-destructive"
                  onClick={onDelete}
                  aria-label="删除"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </>
            )}
          </div>
        </div>

        {}
        <div className="space-y-1">
          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <Globe className="h-3 w-3" />
            <span>base_url</span>
          </div>
          <div className="break-all rounded-md bg-muted/50 px-2 py-1 font-mono text-[11.5px]">
            {p.base_url}
          </div>
        </div>

        {}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[11px]">
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <KeyRound className="h-3 w-3" />
              <span>API Key</span>
            </div>
            {keyed ? (
              <Badge variant="success" className="h-4 px-1.5 text-[10px] font-normal">
                <CheckCircle2 className="mr-0.5 h-2.5 w-2.5" />
                已配置
              </Badge>
            ) : (
              <Badge variant="warning" className="h-4 px-1.5 text-[10px] font-normal">
                <AlertTriangle className="mr-0.5 h-2.5 w-2.5" />
                未配置
              </Badge>
            )}
          </div>
          <div
            className={cn(
              'rounded-md px-2 py-1 font-mono text-[11.5px]',
              keyed
                ? 'bg-emerald-500/[0.06] text-emerald-700'
                : 'bg-amber-500/[0.08] text-amber-700',
            )}
          >
            {keyed
              ? p.api_key_preview
              : `通过环境变量 ${p.id.toUpperCase()}_API_KEY 注入`}
          </div>
        </div>

        {}
        <div>
          <div className="mb-1.5 flex items-center justify-between text-[11px] text-muted-foreground">
            <div className="flex items-center gap-1.5">
              <Cpu className="h-3 w-3" />
              <span>可用模型</span>
            </div>
            <span>{p.models?.length || 0} 个</span>
          </div>
          <div className="flex flex-wrap gap-1">
            {(p.models || []).map((m, idx) => (
              <span
                key={`${m.id}-${idx}`}
                className={cn(
                  'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 font-mono text-[10.5px]',
                  modelRoleClass(m.role),
                )}
              >
                <span className="font-semibold">{m.id}</span>
                <span className="opacity-70">·</span>
                <span className="font-normal">{m.role}</span>
              </span>
            ))}
            {(p.models || []).length === 0 && (
              <span className="text-[11px] text-muted-foreground">未配置模型</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Providers() {
  const qc = useQueryClient()
  const isAdmin = useAuthStore((s) => s.isAdmin)

  const { data, isLoading } = useQuery({
    queryKey: ['providers'],
    queryFn: () => api.listProviders(),
  })

  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Provider | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Provider | null>(null)

  const refresh = () => qc.invalidateQueries({ queryKey: ['providers'] })

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api.updateProvider(id, { enabled }),
    onSuccess: (_r, v) => {
      toast.success(v.enabled ? '已启用供应商' : '已禁用供应商')
      refresh()
    },
    onError: (e: Error) => toast.error('操作失败', { description: e.message }),
  })

  const items = data?.items || []

  const kpis = useMemo(() => {
    const total = items.length
    const enabled = items.filter((p) => p.enabled).length
    const missingKey = items.filter((p) => !hasApiKey(p)).length
    const totalModels = items.reduce((acc, p) => acc + (p.models?.length || 0), 0)
    return { total, enabled, missingKey, totalModels }
  }, [items])

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 p-6 lg:p-8">
        <PageHeader
          icon={Network}
          title="模型供应商"
          description={
            <>
              统一走 OpenAI 兼容协议（base_url + api_key + models）。
              {isAdmin
                ? ' 管理员可在此增删改，改动写入 data/providers.yaml 并即时热更路由。'
                : ' 当前账号为只读，需要管理员权限才能修改。'}
              {' '}线上建议通过环境变量注入 API Key。
            </>
          }
          actions={
            isAdmin ? (
              <Button onClick={() => setCreateOpen(true)}>
                <Plus className="h-4 w-4" />
                新增供应商
              </Button>
            ) : undefined
          }
          stats={
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatCard
                icon={Network}
                iconTone="primary"
                label="供应商总数"
                value={isLoading ? '…' : kpis.total}
              />
              <StatCard
                icon={CheckCircle2}
                iconTone="success"
                label="已启用"
                value={isLoading ? '…' : kpis.enabled}
                hint={`占 ${kpis.total ? Math.round((kpis.enabled / kpis.total) * 100) : 0}%`}
              />
              <StatCard
                icon={AlertTriangle}
                iconTone="warning"
                label="Key 缺失"
                value={isLoading ? '…' : kpis.missingKey}
                hint={kpis.missingKey > 0 ? '需要补充密钥' : '全部已配置'}
              />
              <StatCard
                icon={Cpu}
                iconTone="secondary"
                label="模型总数"
                value={isLoading ? '…' : kpis.totalModels}
              />
            </div>
          }
        />

        {isLoading ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-72 w-full rounded-xl" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={PowerOff}
            title="尚未配置任何供应商"
            description={
              isAdmin ? (
                <>点击右上角「新增供应商」添加第一个模型供应商。</>
              ) : (
                <>请联系管理员在此添加模型供应商。</>
              )
            }
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {items.map((p) => (
              <ProviderCard
                key={p.id}
                p={p}
                isAdmin={isAdmin}
                onEdit={() => setEditTarget(p)}
                onDelete={() => setDeleteTarget(p)}
                onToggle={(next) => toggleMut.mutate({ id: p.id, enabled: next })}
                toggleBusy={toggleMut.isPending}
              />
            ))}
          </div>
        )}
      </div>

      {createOpen && (
        <ProviderDialog
          mode="create"
          onClose={() => setCreateOpen(false)}
          onDone={() => {
            setCreateOpen(false)
            refresh()
          }}
        />
      )}

      {editTarget && (
        <ProviderDialog
          mode="edit"
          provider={editTarget}
          onClose={() => setEditTarget(null)}
          onDone={() => {
            setEditTarget(null)
            refresh()
          }}
        />
      )}

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除供应商</AlertDialogTitle>
            <AlertDialogDescription>
              确定删除供应商「{deleteTarget?.name}」？删除后其模型不再参与路由，
              正在进行的调用不受影响。此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={async () => {
                if (!deleteTarget) return
                try {
                  await api.deleteProvider(deleteTarget.id)
                  toast.success('已删除供应商')
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

function ProviderDialog(props: {
  mode: 'create' | 'edit'
  provider?: Provider
  onClose: () => void
  onDone: () => void
}) {
  const { mode, provider } = props
  const isEdit = mode === 'edit'

  const [name, setName] = useState(provider?.name || '')
  const [baseUrl, setBaseUrl] = useState(provider?.base_url || '')
  const [apiKey, setApiKey] = useState('')
  const [priority, setPriority] = useState(provider?.priority ?? 0)
  const [enabled, setEnabled] = useState(provider?.enabled ?? true)
  const [models, setModels] = useState<ModelInfo[]>(
    provider?.models?.length
      ? provider.models.map((m) => ({ ...m }))
      : [{ id: '', role: 'general' }],
  )
  const [busy, setBusy] = useState(false)

  const updateModel = (idx: number, patch: Partial<ModelInfo>) => {
    setModels((ms) => ms.map((m, i) => (i === idx ? { ...m, ...patch } : m)))
  }
  const addModel = () => setModels((ms) => [...ms, { id: '', role: 'general' }])
  const removeModel = (idx: number) =>
    setModels((ms) => (ms.length <= 1 ? ms : ms.filter((_, i) => i !== idx)))

  const submit = async () => {
    const cleanModels = models
      .map((m) => ({ id: m.id.trim(), role: m.role || 'general' }))
      .filter((m) => m.id)
    if (!name.trim()) {
      toast.error('请填写供应商名称')
      return
    }
    if (!baseUrl.trim()) {
      toast.error('请填写 base_url')
      return
    }
    if (cleanModels.length === 0) {
      toast.error('至少配置一个模型（模型 ID 不能为空）')
      return
    }
    if (!isEdit && !apiKey.trim()) {
      toast.error('请填写 API Key（新增供应商时必填）')
      return
    }

    setBusy(true)
    try {
      if (isEdit && provider) {
        const patch: Partial<ProviderUpsert> = {
          name: name.trim(),
          base_url: baseUrl.trim(),
          models: cleanModels,
          enabled,
          priority,
        }

        if (apiKey.trim()) patch.api_key = apiKey.trim()
        await api.updateProvider(provider.id, patch)
        toast.success('已保存供应商')
      } else {
        await api.createProvider({
          name: name.trim(),
          base_url: baseUrl.trim(),
          api_key: apiKey.trim(),
          models: cleanModels,
          enabled,
          priority,
        })
        toast.success('供应商已创建')
      }
      props.onDone()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && props.onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? `编辑供应商 · ${provider?.name}` : '新增供应商'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Field label="供应商名称">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如 Kimi / 通义千问 / DeepSeek"
            />
          </Field>
          <Field label="base_url（OpenAI 兼容接口地址）">
            <Input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.moonshot.cn/v1"
            />
          </Field>
          <Field
            label={
              isEdit ? 'API Key（留空表示不修改）' : 'API Key'
            }
          >
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                isEdit
                  ? provider && hasApiKey(provider)
                    ? `当前：${provider.api_key_preview}（留空则不改）`
                    : '未配置，输入以设置'
                  : 'sk-...'
              }
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="优先级（越小越优先）">
              <Input
                type="number"
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value) || 0)}
              />
            </Field>
            <div className="space-y-1.5">
              <Label>启用</Label>
              <div className="flex h-9 items-center">
                <Switch checked={enabled} onCheckedChange={setEnabled} />
              </div>
            </div>
          </div>

          {}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>模型列表</Label>
              <Button size="sm" variant="outline" onClick={addModel}>
                <Plus className="h-3.5 w-3.5" />
                加一个模型
              </Button>
            </div>
            <div className="space-y-2">
              {models.map((m, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <Input
                    className="flex-1"
                    value={m.id}
                    onChange={(e) => updateModel(idx, { id: e.target.value })}
                    placeholder="模型 ID，如 kimi-k2.6"
                  />
                  <Select
                    value={String(m.role)}
                    onValueChange={(v) => updateModel(idx, { role: v })}
                  >
                    <SelectTrigger className="w-28">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ROLE_OPTIONS.map((r) => (
                        <SelectItem key={r} value={r}>
                          {r}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive"
                    disabled={models.length <= 1}
                    onClick={() => removeModel(idx)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              至少一个模型；role 决定路由角色（general 通用 / fast 快 / complex 复杂 / vision 识图）。
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

function Field(props: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{props.label}</Label>
      {props.children}
    </div>
  )
}

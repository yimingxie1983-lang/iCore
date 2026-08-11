

import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  Library,
  MessageSquare,
  Sparkles,
  Wand2,
} from 'lucide-react'

import { api, type Agent, type Persona } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import { Badge } from '@/ui/widgets/ui/badge'
import { Skeleton } from '@/ui/widgets/ui/skeleton'
import { toast } from '@/ui/widgets/ui/sonner'

import PageHeader from '@/ui/widgets/common/PageHeader'
import StatCard from '@/ui/widgets/common/StatCard'
import EmptyState from '@/ui/widgets/common/EmptyState'
import { cn } from '@/shared/foundation/utils'

const MASTER_AGENT_ID = 'claw_master'

function MasterAgentHero({
  master,
  activePersona,
}: {
  master?: Agent
  activePersona?: Persona | null
}) {
  if (!master) {
    return <Skeleton className="h-40 w-full rounded-2xl" />
  }
  return (
    <div className="surface-card relative overflow-hidden rounded-2xl">
      <div
        className="absolute inset-0 opacity-90 pointer-events-none"
        style={{
          background:
            'radial-gradient(circle at 0% 0%, hsl(207 78% 96%) 0%, transparent 45%), radial-gradient(circle at 100% 100%, hsl(185 84% 95%) 0%, transparent 50%)',
        }}
      />
      <div className="relative flex flex-col gap-5 p-6 sm:flex-row sm:items-start sm:p-7">
        <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-card-hover">
          <Bot className="h-8 w-8" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <Badge variant="default" className="font-normal">
              主智能体
            </Badge>
            <code className="font-mono text-[11px] text-muted-foreground">
              {master.id}
            </code>
            <Badge variant="success" className="h-4 px-1.5 text-[10px] font-normal">
              {master.status}
            </Badge>
          </div>
          <h2 className="text-xl font-semibold tracking-tight text-foreground">
            {master.name}
          </h2>
          <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
            {master.description}
          </p>

          <div className="mt-4 grid grid-cols-1 gap-3 text-[12px] sm:grid-cols-2">
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Soul 文件:</span>
              <code className="break-all font-mono text-[11px] text-foreground/80">
                {master.soul_path}
              </code>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">当前人格:</span>
              {activePersona ? (
                <span className="inline-flex items-center gap-1">
                  <span className="text-base leading-none">{activePersona.icon || '🦀'}</span>
                  <span className="font-medium text-foreground">{activePersona.name}</span>
                </span>
              ) : (
                <span className="text-muted-foreground">（默认 / 未切换）</span>
              )}
            </div>
          </div>
        </div>

        <div className="flex shrink-0 flex-col gap-2 sm:items-end">
          <Button asChild>
            <Link to="/chat">
              <MessageSquare />
              进入对话
            </Link>
          </Button>
          <span className="text-[11px] text-muted-foreground">
            人格切换在对话顶部条进行
          </span>
        </div>
      </div>
    </div>
  )
}

function PersonaCard({
  p,
  isActive,
  isDefault,
  switching,
  onActivate,
}: {
  p: Persona
  isActive: boolean
  isDefault: boolean
  switching: boolean
  onActivate: () => void
}) {
  return (
    <div
      className={cn(
        'surface-card surface-card-hover group relative flex flex-col rounded-xl p-5 transition-all',
        isActive ? 'border-secondary/60 bg-secondary/[0.03]' : 'hover:border-secondary/40',
      )}
    >
      {isActive && (
        <span className="absolute right-4 top-4 inline-flex items-center gap-1 rounded-full bg-secondary/15 px-2 py-0.5 text-[10px] font-medium text-secondary">
          <CheckCircle2 className="h-3 w-3" />
          生效中
        </span>
      )}

      <div className="mb-3 flex items-center gap-3">
        <div
          className={cn(
            'flex h-12 w-12 items-center justify-center rounded-xl text-2xl',
            isActive ? 'bg-secondary/[0.12]' : 'bg-muted',
          )}
        >
          {p.icon || '🦀'}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-[15px] font-semibold tracking-tight">{p.name}</h3>
          {isDefault && (
            <Badge variant="muted" className="mt-1 h-4 px-1.5 text-[10px] font-normal">
              系统默认
            </Badge>
          )}
        </div>
      </div>

      <p className="mb-4 line-clamp-3 min-h-[3lh] text-[12.5px] leading-relaxed text-muted-foreground">
        {p.description}
      </p>

      <div className="mb-4 flex flex-wrap gap-1">
        {p.suggested_tools.slice(0, 5).map((t) => (
          <Badge key={t} variant="outline" className="h-5 px-1.5 text-[10.5px] font-normal">
            {t}
          </Badge>
        ))}
        {p.suggested_tools.length > 5 && (
          <Badge variant="muted" className="h-5 px-1.5 text-[10.5px] font-normal">
            +{p.suggested_tools.length - 5}
          </Badge>
        )}
      </div>

      <div className="mt-auto flex items-center justify-between border-t border-border pt-3">
        <span className="font-mono text-[10.5px] text-muted-foreground">{p.id}</span>
        <Button
          variant={isActive ? 'ghost' : 'outline'}
          size="sm"
          disabled={isActive || switching}
          onClick={onActivate}
          className={cn(isActive && 'pointer-events-none text-secondary')}
        >
          {isActive ? '当前人格' : switching ? '切换中…' : '设为当前'}
          {!isActive && <ArrowRight className="h-3.5 w-3.5" />}
        </Button>
      </div>
    </div>
  )
}

export default function Agents() {
  const qc = useQueryClient()

  const { data: agentsData, isLoading: loadingAgents } = useQuery({
    queryKey: ['agents'],
    queryFn: () => api.listAgents(),
  })
  const { data: personas, isLoading: loadingPersonas } = useQuery({
    queryKey: ['personas'],
    queryFn: () => api.listPersonas(),
    staleTime: 5 * 60_000,
  })
  const { data: activeData } = useQuery({
    queryKey: ['agent-persona', MASTER_AGENT_ID],
    queryFn: () => api.getAgentPersona(MASTER_AGENT_ID),
    refetchInterval: 60_000,
  })

  const switchMut = useMutation({
    mutationFn: (personaId: string) =>
      api.switchAgentPersona(MASTER_AGENT_ID, personaId),
    onSuccess: (r) => {
      toast.success(`已切换到「${r.name}」`)
      qc.invalidateQueries({ queryKey: ['agent-persona', MASTER_AGENT_ID] })
    },
    onError: (e: Error) => toast.error('切换失败', { description: e.message }),
  })

  const master = agentsData?.items.find((a) => a.id === MASTER_AGENT_ID)
  const others = (agentsData?.items || []).filter((a) => a.id !== MASTER_AGENT_ID)
  const activePersona = activeData?.persona
  const defaultId = personas?.default_id

  const currentPersonaName = useMemo(() => {
    if (activePersona) return activePersona.name
    const def = personas?.items.find((p) => p.id === defaultId)
    return def?.name || '默认'
  }, [activePersona, personas, defaultId])

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 p-6 lg:p-8">
        <PageHeader
          icon={Bot}
          title="智能体 & 人格库"
          description="单智能体内核 + 可热插拔的人格库；在对话工作台顶部切换 persona，对话历史保留。"
          stats={
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <StatCard
                icon={Bot}
                iconTone="primary"
                label="注册智能体"
                value={loadingAgents ? '…' : agentsData?.total ?? 0}
                hint="系统 + 用户创建"
              />
              <StatCard
                icon={Library}
                iconTone="secondary"
                label="可用人格"
                value={loadingPersonas ? '…' : personas?.total ?? 0}
                hint={`目录: ${personas?.personas_dir || '...'}`}
              />
              <StatCard
                icon={Wand2}
                iconTone="accent"
                label="当前人格"
                value={currentPersonaName}
                hint={`for ${MASTER_AGENT_ID}`}
              />
            </div>
          }
        />

        {}
        <MasterAgentHero master={master} activePersona={activePersona} />

        {}
        <div>
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-base font-semibold tracking-tight text-foreground">
              人格库（Persona）
            </h2>
            <span className="text-[11px] text-muted-foreground">
              点击「设为当前」即可热切换，对话历史不会丢失
            </span>
          </div>

          {loadingPersonas ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-56 w-full rounded-xl" />
              ))}
            </div>
          ) : (personas?.items || []).length === 0 ? (
            <EmptyState
              icon={Library}
              title="人格库为空"
              description={
                <>
                  请在仓库的 <code className="font-mono">cancer_claw/resources/persona_profiles/</code> 下添加
                  Markdown 人格文件，重启后端即可。
                </>
              }
            />
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {personas?.items.map((p) => {
                const isActive = (activePersona?.id || defaultId) === p.id
                return (
                  <PersonaCard
                    key={p.id}
                    p={p}
                    isActive={isActive}
                    isDefault={p.id === defaultId}
                    switching={switchMut.isPending}
                    onActivate={() => switchMut.mutate(p.id)}
                  />
                )
              })}
            </div>
          )}
        </div>

        {}
        {others.length > 0 && (
          <div>
            <h2 className="mb-3 text-base font-semibold tracking-tight text-foreground">
              其它智能体
            </h2>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
              {others.map((a) => (
                <div
                  key={a.id}
                  className="surface-card surface-card-hover rounded-xl p-4"
                >
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-secondary" />
                    <span className="font-semibold">{a.name}</span>
                    <code className="ml-auto font-mono text-[10.5px] text-muted-foreground">
                      {a.id}
                    </code>
                  </div>
                  <p className="mt-2 line-clamp-2 text-[12.5px] text-muted-foreground">
                    {a.description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

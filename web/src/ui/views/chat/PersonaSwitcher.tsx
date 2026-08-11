

import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeftRight, Loader2 } from 'lucide-react'

import { api } from '@/client/services/client'
import { Badge } from '@/ui/widgets/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/ui/widgets/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/ui/widgets/ui/tooltip'
import { toast } from '@/ui/widgets/ui/sonner'
import { cn } from '@/shared/foundation/utils'

const DEFAULT_AGENT_ICON = '🦀'

interface Props {
  agentId: string
}

export default function PersonaSwitcher({ agentId }: Props) {
  const qc = useQueryClient()

  const { data: listData } = useQuery({
    queryKey: ['personas'],
    queryFn: () => api.listPersonas(),
    staleTime: 5 * 60_000,
  })

  const { data: activeData, isLoading: loadingActive } = useQuery({
    queryKey: ['agent-persona', agentId],
    queryFn: () => api.getAgentPersona(agentId),
    enabled: !!agentId,
    refetchInterval: 30_000,
  })

  const switchMut = useMutation({
    mutationFn: (personaId: string) => api.switchAgentPersona(agentId, personaId),
    onSuccess: (r) => {
      toast.success(`已切换到「${r.name}」`)
      qc.invalidateQueries({ queryKey: ['agent-persona', agentId] })
    },
    onError: (e: Error) => toast.error('切换失败', { description: e.message }),
  })

  const items = listData?.items || []
  const defaultId = listData?.default_id || 'master'
  const active = activeData?.persona

  const current = useMemo(() => {
    if (loadingActive) return { icon: '…', name: '加载中', desc: '' }
    if (active) {
      return {
        icon: active.icon || DEFAULT_AGENT_ICON,
        name: active.name || active.id,
        desc: active.description || '',
      }
    }
    const def = items.find((p) => p.id === defaultId)
    return {
      icon: def?.icon || DEFAULT_AGENT_ICON,
      name: def?.name || '主智能体',
      desc: def?.description || '默认人格',
    }
  }, [loadingActive, active, items, defaultId])

  if (!agentId) return null

  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="inline-flex h-7 items-center gap-1.5 rounded-full border border-secondary/30 bg-secondary/[0.06] px-2.5 text-xs font-medium text-secondary transition-colors hover:bg-secondary/[0.12] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {switchMut.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <ArrowLeftRight className="h-3.5 w-3.5" />
              )}
              <span className="text-sm">{current.icon}</span>
              <span>{current.name}</span>
            </button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent>{current.desc || '点击切换人格'}</TooltipContent>
      </Tooltip>

      <DropdownMenuContent
        align="start"
        className="flex max-h-[min(70vh,520px)] w-[300px] flex-col overflow-hidden"
      >
        <DropdownMenuLabel className="shrink-0 font-normal">
          切换主智能体的"工作视角"，对话历史保留
        </DropdownMenuLabel>
        <DropdownMenuSeparator className="shrink-0" />

        {
}
        <div className="min-h-0 flex-1 overflow-y-auto">
        {items.length === 0 && (
          <DropdownMenuItem disabled>（未发现可用 persona）</DropdownMenuItem>
        )}

        {items.map((p) => {
          const isActive = (active?.id || defaultId) === p.id
          return (
            <DropdownMenuItem
              key={p.id}
              onSelect={() => {
                if (!isActive) switchMut.mutate(p.id)
              }}
              className={cn(
                'items-start gap-2 py-2',
                isActive && 'bg-muted/60',
              )}
            >
              <span className="mt-0.5 text-base leading-none">
                {p.icon || DEFAULT_AGENT_ICON}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span
                    className={cn(
                      'text-sm',
                      isActive ? 'font-bold' : 'font-medium',
                    )}
                  >
                    {p.name}
                  </span>
                  {isActive && (
                    <Badge variant="success" className="h-4 px-1.5 text-[10px]">
                      生效中
                    </Badge>
                  )}
                </div>
                <p className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-muted-foreground">
                  {p.description}
                </p>
              </div>
            </DropdownMenuItem>
          )
        })}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

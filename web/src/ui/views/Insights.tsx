import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Newspaper,
  ExternalLink,
  Search,
  RefreshCw,
  CalendarDays,
  Flame,
  LayoutGrid,
  Bell,
  Plus,
  X,
  Send,
} from 'lucide-react'

import { api, type InsightItem, type InsightStats } from '@/client/services/client'
import { useAuthStore } from '@/application/state/authStore'
import { Badge } from '@/ui/widgets/ui/badge'
import { Button } from '@/ui/widgets/ui/button'
import { Input } from '@/ui/widgets/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/ui/widgets/ui/dialog'
import { toast } from '@/ui/widgets/ui/sonner'
import { cn } from '@/shared/foundation/utils'

const CATEGORY_META: Record<
  string,
  { label: string; badge: string; dot: string }
> = {
  policy: {
    label: '政策监管',
    badge: 'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300',
    dot: 'bg-sky-500',
  },
  research: {
    label: '文献前沿',
    badge: 'border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300',
    dot: 'bg-violet-500',
  },
  industry: {
    label: '产业动态',
    badge: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
    dot: 'bg-emerald-500',
  },
  funding: {
    label: '融资上市',
    badge: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
    dot: 'bg-amber-500',
  },
  conference: {
    label: '会议活动',
    badge: 'border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300',
    dot: 'bg-rose-500',
  },
}

const CATEGORY_ORDER = ['policy', 'research', 'industry', 'funding', 'conference']

function relTime(iso: string): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
  const m = Math.floor(diff / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  return `${d} 天前`
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function HighlightedTitle({ title, keywords }: { title: string; keywords: string[] }) {
  const kws = keywords.filter((k) => k.trim().length > 0)
  if (kws.length === 0) return <>{title}</>
  const re = new RegExp(`(${kws.map(escapeRegExp).join('|')})`, 'gi')
  const parts = title.split(re)
  return (
    <>
      {parts.map((p, i) =>
        re.test(p) ? (
          <mark key={i} className="rounded bg-amber-300/60 px-0.5 text-foreground dark:bg-amber-500/40">
            {p}
          </mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  )
}

function InsightCard({
  item,
  keywords,
  onAsk,
}: {
  item: InsightItem
  keywords: string[]
  onAsk: (item: InsightItem) => void
}) {
  const meta = CATEGORY_META[item.category] || CATEGORY_META.industry
  return (
    <article className="group flex flex-col rounded-xl border border-border bg-card p-4 transition-colors hover:border-primary/40">
      <div className="mb-2 flex items-center justify-between gap-2">
        <Badge variant="outline" className={cn('text-[11px]', meta.badge)}>
          <span className={cn('mr-1 h-1.5 w-1.5 rounded-full', meta.dot)} />
          {meta.label}
        </Badge>
        <span className="text-[11px] text-muted-foreground">{relTime(item.published_at)}</span>
      </div>

      <h3 className="line-clamp-2 text-[14px] font-semibold leading-snug text-foreground">
        <HighlightedTitle title={item.title} keywords={keywords} />
      </h3>

      <p className="mt-1.5 line-clamp-3 text-[12.5px] leading-relaxed text-muted-foreground">
        {item.summary}
      </p>

      {item.tags.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {item.tags.map((t) => (
            <span
              key={t}
              className="rounded-full border border-border bg-muted/60 px-2 py-0.5 text-[10.5px] text-muted-foreground"
            >
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="mt-auto flex items-center justify-between gap-2 pt-3">
        <span className="truncate text-[11.5px] text-muted-foreground">{item.source}</span>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => onAsk(item)}
            title="把这条资讯发给 Agent 分析"
            className="inline-flex items-center gap-1 text-[11.5px] font-medium text-secondary hover:underline"
          >
            <Send className="h-3 w-3" />
            问 Agent
          </button>
          {item.url && (
            <a
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-[11.5px] font-medium text-primary hover:underline"
            >
              原文
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      </div>
    </article>
  )
}

function InsightSkeleton() {
  return (
    <div className="animate-pulse overflow-hidden rounded-xl border border-border bg-card">
      <div className="aspect-[16/9] w-full bg-muted" />
      <div className="p-4">
        <div className="h-4 w-4/5 rounded bg-muted" />
        <div className="mt-2 h-3 w-full rounded bg-muted" />
        <div className="mt-1.5 h-3 w-11/12 rounded bg-muted" />
        <div className="mt-1.5 h-3 w-2/3 rounded bg-muted" />
        <div className="mt-4 h-3 w-24 rounded bg-muted" />
      </div>
    </div>
  )
}

function SubscriptionsDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['insights-subs'],
    queryFn: () => api.listInsightSubscriptions(),
    enabled: open,
  })
  const [keyword, setKeyword] = useState('')
  const [busy, setBusy] = useState(false)

  const add = async () => {
    const kw = keyword.trim()
    if (!kw) return
    setBusy(true)
    try {
      await api.createInsightSubscription(kw)
      setKeyword('')
      toast.success('订阅已添加')
      qc.invalidateQueries({ queryKey: ['insights-subs'] })
      qc.invalidateQueries({ queryKey: ['insights-hits'] })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '添加失败')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: number) => {
    try {
      await api.deleteInsightSubscription(id)
      qc.invalidateQueries({ queryKey: ['insights-subs'] })
      qc.invalidateQueries({ queryKey: ['insights-hits'] })
    } catch {
      toast.error('删除失败')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>我的订阅</DialogTitle>
          <DialogDescription>
            订阅关键词后，命中的资讯会高亮显示，侧边栏出现红点提醒（每账号最多 20 个）。
          </DialogDescription>
        </DialogHeader>
        <div className="flex gap-2">
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && add()}
            placeholder="如：食管癌 / 影像组学 / FDA"
            maxLength={40}
            className="h-9 text-[13px]"
          />
          <Button size="sm" onClick={add} disabled={busy || !keyword.trim()} className="gap-1">
            <Plus className="h-3.5 w-3.5" />
            添加
          </Button>
        </div>
        <div className="mt-3 max-h-64 space-y-1.5 overflow-y-auto">
          {isLoading && <p className="px-1 text-[12px] text-muted-foreground">加载中…</p>}
          {!isLoading && (data?.items || []).length === 0 && (
            <p className="px-1 py-4 text-center text-[12px] text-muted-foreground">
              还没有订阅，添加一个关键词试试
            </p>
          )}
          {(data?.items || []).map((s) => (
            <div
              key={s.id}
              className="flex items-center justify-between gap-2 rounded-lg border border-border bg-card px-3 py-2"
            >
              <div className="min-w-0">
                <div className="truncate text-[13px] font-medium text-foreground">{s.keyword}</div>
                <div className="text-[11px] text-muted-foreground">近 7 天命中 {s.hits_week} 条</div>
              </div>
              <button
                type="button"
                onClick={() => remove(s.id)}
                className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-destructive"
                aria-label="删除订阅"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default function Insights() {
  const nav = useNavigate()
  const isAdmin = useAuthStore((s) => s.isAdmin)
  const qc = useQueryClient()
  const [category, setCategory] = useState('')
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [seeding, setSeeding] = useState(false)
  const [subsOpen, setSubsOpen] = useState(false)

  useEffect(() => {
    const id = setTimeout(() => setDebounced(search.trim()), 300)
    return () => clearTimeout(id)
  }, [search])

  const { data, isLoading } = useQuery({
    queryKey: ['insights', category, debounced],
    queryFn: () =>
      api.listInsights({ category: category || undefined, q: debounced || undefined }),
  })
  const { data: stats } = useQuery({
    queryKey: ['insights-stats'],
    queryFn: () => api.insightStats(),
    refetchInterval: 60_000,
  })
  const { data: subs } = useQuery({
    queryKey: ['insights-subs'],
    queryFn: () => api.listInsightSubscriptions(),
  })

  const items = useMemo(() => data?.items || [], [data])
  const keywords = useMemo(
    () => (subs?.items || []).map((s) => s.keyword).filter(Boolean),
    [subs],
  )

  const reseed = async () => {
    setSeeding(true)
    try {
      const r = await api.seedInsights()
      toast.success(`已重置演示数据（${r.inserted} 条）`)
      qc.invalidateQueries({ queryKey: ['insights'] })
      qc.invalidateQueries({ queryKey: ['insights-stats'] })
    } catch {
      toast.error('重置失败，请稍后重试')
    } finally {
      setSeeding(false)
    }
  }

  const askAgent = (it: InsightItem) => {
    const prompt =
      `请分析这条医学 AI 行业资讯的关键事实、对医学科研/临床工作的启示，` +
      `以及我们可以进一步追踪的行动点：\n\n标题：${it.title}\n摘要：${it.summary}\n来源：${it.source}` +
      (it.url ? `\n链接：${it.url}` : '')
    nav(`/chat?ask=${encodeURIComponent(prompt)}`)
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto p-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-foreground">
            <Newspaper className="h-4 w-4 text-secondary" />
            行业资讯
          </h2>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            医学 AI 咨询墙：政策监管 / 文献前沿 / 产业动态 / 融资上市 / 会议活动，滚动保留最近 7 天。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setSubsOpen(true)}
            className="gap-1.5 text-[12px]"
          >
            <Bell className="h-3.5 w-3.5" />
            我的订阅
            {keywords.length > 0 && (
              <span className="rounded-full bg-secondary px-1.5 text-[10px] text-secondary-foreground">
                {keywords.length}
              </span>
            )}
          </Button>
          {isAdmin && (
            <Button
              variant="outline"
              size="sm"
              onClick={reseed}
              disabled={seeding}
              className="gap-1.5 text-[12px]"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', seeding && 'animate-spin')} />
              重置演示数据
            </Button>
          )}
        </div>
      </div>

      <div className="mb-4 grid grid-cols-3 gap-3">
        <div className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
          <Flame className="h-4 w-4 shrink-0 text-orange-500" />
          <div className="min-w-0">
            <div className="font-mono text-lg font-semibold leading-tight text-foreground">
              {stats?.today ?? '—'}
            </div>
            <div className="text-[11px] text-muted-foreground">今日更新</div>
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
          <CalendarDays className="h-4 w-4 shrink-0 text-sky-500" />
          <div className="min-w-0">
            <div className="font-mono text-lg font-semibold leading-tight text-foreground">
              {stats?.week ?? '—'}
            </div>
            <div className="text-[11px] text-muted-foreground">本周条目</div>
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
          <LayoutGrid className="h-4 w-4 shrink-0 text-emerald-500" />
          <div className="min-w-0">
            <div className="font-mono text-lg font-semibold leading-tight text-foreground">
              {stats?.total ?? '—'}
            </div>
            <div className="text-[11px] text-muted-foreground">当前在墙</div>
          </div>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setCategory('')}
          className={cn(
            'rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors',
            category === ''
              ? 'border-primary bg-primary text-primary-foreground'
              : 'border-border bg-card text-foreground hover:bg-muted',
          )}
        >
          全部{stats ? ` · ${stats.total}` : ''}
        </button>
        {CATEGORY_ORDER.map((c) => {
          const meta = CATEGORY_META[c]
          const active = category === c
          return (
            <button
              key={c}
              type="button"
              onClick={() => setCategory(active ? '' : c)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors',
                active
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border bg-card text-foreground hover:bg-muted',
              )}
            >
              <span className={cn('h-1.5 w-1.5 rounded-full', meta.dot)} />
              {meta.label}
              {stats?.by_category?.[c] != null && ` · ${stats.by_category[c]}`}
            </button>
          )
        })}
        <div className="relative ml-auto w-full sm:w-64">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索标题 / 摘要 / 来源"
            className="h-9 pl-8 text-[12.5px]"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <InsightSkeleton key={i} />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-16 text-muted-foreground">
          <Newspaper className="mb-2 h-8 w-8 opacity-40" />
          <p className="text-sm">没有匹配的资讯</p>
          <p className="mt-1 text-[12px]">换个分类或关键词试试</p>
        </div>
      ) : (
        <div className="grid content-start gap-3 pb-2 md:grid-cols-2 xl:grid-cols-3">
          {items.map((it) => (
            <InsightCard key={it.id} item={it} keywords={keywords} onAsk={askAgent} />
          ))}
        </div>
      )}

      <SubscriptionsDialog open={subsOpen} onOpenChange={setSubsOpen} />
    </div>
  )
}

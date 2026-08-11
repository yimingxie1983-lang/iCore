

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Check,
  FlaskConical,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
  X,
} from 'lucide-react'

import { api, type SkillDraftStatus } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import { Badge } from '@/ui/widgets/ui/badge'
import { cn } from '@/shared/foundation/utils'
import { toast } from '@/ui/widgets/ui/sonner'
import { TxPagination } from '@/ui/views/Credits'

const DRAFT_PAGE_SIZE = 20

const STATUS_TABS: { key: SkillDraftStatus | ''; label: string }[] = [
  { key: 'pending', label: '待审批' },
  { key: 'approved', label: '已通过' },
  { key: 'rejected', label: '已拒绝' },
  { key: '', label: '全部' },
]

function statusBadge(status: SkillDraftStatus) {
  switch (status) {
    case 'approved':
      return <Badge variant="success" className="h-5">已通过</Badge>
    case 'rejected':
      return <Badge variant="muted" className="h-5">已拒绝</Badge>
    default:
      return <Badge variant="warning" className="h-5">待审批</Badge>
  }
}

export default function AdminEvolution() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<SkillDraftStatus | ''>('pending')
  const [activeId, setActiveId] = useState<number | null>(null)
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [limit, setLimit] = useState<number>(DRAFT_PAGE_SIZE)
  const [offset, setOffset] = useState(0)

  useEffect(() => {
    const id = setTimeout(() => {
      setSearch(searchInput.trim())
      setOffset(0)
    }, 300)
    return () => clearTimeout(id)
  }, [searchInput])

  const { data, isLoading } = useQuery({
    queryKey: ['skill-drafts', tab, search, limit, offset],
    queryFn: () => api.listSkillDrafts({ status: tab, search, limit, offset }),
  })

  const refresh = () => qc.invalidateQueries({ queryKey: ['skill-drafts'] })

  const items = data?.items || []
  const counts = data?.counts || {}
  const total = data?.total ?? 0

  const changeTab = (key: SkillDraftStatus | '') => {
    setTab(key)
    setActiveId(null)
    setOffset(0)
  }
  const changeLimit = (n: number) => {
    setLimit(n)
    setOffset(0)
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-foreground">
            <Sparkles className="h-4 w-4 text-secondary" />
            进化审批
          </h2>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            自进化产出的 SKILL.md 草稿。审核通过才写入技能库，拒绝仅留档。
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh}>
          <RefreshCw className="h-3.5 w-3.5" />
          刷新
        </Button>
      </div>

      {}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex gap-1">
          {STATUS_TABS.map((t) => (
            <button
              key={t.key || 'all'}
              onClick={() => changeTab(t.key)}
              className={cn(
                'rounded-full px-3 py-1 text-[12px] font-medium transition-colors',
                tab === t.key
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/70',
              )}
            >
              {t.label}
              {t.key && counts[t.key] != null && (
                <span className="ml-1 opacity-70">{counts[t.key]}</span>
              )}
            </button>
          ))}
        </div>
        <div className="relative ml-auto w-full sm:w-64">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="搜索名称 / 内容…"
            className="w-full rounded-md border border-border bg-background py-1.5 pl-8 pr-8 text-[12.5px] outline-none focus:ring-2 focus:ring-ring"
          />
          {searchInput && (
            <button
              onClick={() => setSearchInput('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              title="清空"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(280px,340px)_1fr]">
        {}
        <div className="flex min-h-0 flex-col gap-2">
          <div className="min-h-0 flex-1 overflow-y-auto rounded-xl border border-border bg-card">
            {isLoading ? (
              <div className="flex items-center justify-center py-10 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
              </div>
            ) : items.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-12 text-center text-muted-foreground">
                <FlaskConical className="h-8 w-8 opacity-40" />
                <p className="text-[13px]">
                  {search
                    ? '没有匹配的草稿'
                    : `暂无${tab === 'pending' ? '待审批' : ''}草稿`}
                </p>
                <p className="max-w-[220px] text-[11px]">
                  {search
                    ? '换个关键词，或清空搜索看全部。'
                    : '任务完成后进化链会异步提炼可复用经验，值得沉淀的会出现在这里。'}
                </p>
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {items.map((d) => (
                  <li key={d.id}>
                    <button
                      onClick={() => setActiveId(d.id)}
                      className={cn(
                        'flex w-full flex-col gap-1 px-3 py-2.5 text-left transition-colors hover:bg-muted/40',
                        activeId === d.id && 'bg-muted/60',
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-mono text-[12.5px] font-medium">
                          {d.name || `草稿 #${d.id}`}
                        </span>
                        {statusBadge(d.status)}
                      </div>
                      <p className="line-clamp-2 text-[11px] text-muted-foreground">
                        {d.preview}
                      </p>
                      <span className="text-[10.5px] text-muted-foreground/70">
                        #{d.id} · {d.created_at || ''}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <TxPagination
            total={total}
            limit={limit}
            offset={offset}
            onOffset={setOffset}
            onLimit={changeLimit}
          />
        </div>

        {}
        <div className="min-h-0 overflow-hidden rounded-xl border border-border bg-card">
          {activeId == null ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
              <Sparkles className="h-8 w-8 opacity-40" />
              <p className="text-[13px]">从左侧选择一份草稿查看 / 审核</p>
            </div>
          ) : (
            <DraftEditor
              key={activeId}
              draftId={activeId}
              onDone={() => {
                setActiveId(null)
                refresh()
              }}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function DraftEditor(props: { draftId: number; onDone: () => void }) {
  const { draftId } = props
  const qc = useQueryClient()

  const { data: draft, isLoading } = useQuery({
    queryKey: ['skill-draft', draftId],
    queryFn: () => api.getSkillDraft(draftId),
  })

  const [name, setName] = useState<string | null>(null)
  const [content, setContent] = useState<string | null>(null)

  const effName = name ?? draft?.name ?? ''
  const effContent = content ?? draft?.content ?? ''
  const isPending = draft?.status === 'pending'

  const dirty = useMemo(() => {
    if (!draft) return false
    return (name != null && name !== draft.name) ||
      (content != null && content !== draft.content)
  }, [draft, name, content])

  const saveMut = useMutation({
    mutationFn: () =>
      api.updateSkillDraft(draftId, { name: effName, content: effContent }),
    onSuccess: () => {
      toast.success('草稿已保存')
      qc.invalidateQueries({ queryKey: ['skill-draft', draftId] })
      qc.invalidateQueries({ queryKey: ['skill-drafts'] })
    },
    onError: (e: Error) => toast.error('保存失败', { description: e.message }),
  })

  const approveMut = useMutation({
    mutationFn: async () => {
      if (dirty) await api.updateSkillDraft(draftId, { name: effName, content: effContent })
      return api.approveSkillDraft(draftId)
    },
    onSuccess: (r) => {
      toast.success('已通过并固化为 Skill', { description: r.message })
      props.onDone()
    },
    onError: (e: Error) => toast.error('通过失败', { description: e.message }),
  })

  const rejectMut = useMutation({
    mutationFn: () => api.rejectSkillDraft(draftId),
    onSuccess: () => {
      toast.success('已拒绝该草稿')
      props.onDone()
    },
    onError: (e: Error) => toast.error('拒绝失败', { description: e.message }),
  })

  if (isLoading || !draft) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
      </div>
    )
  }

  const busy = saveMut.isPending || approveMut.isPending || rejectMut.isPending

  return (
    <div className="flex h-full flex-col">
      {}
      <div className="shrink-0 border-b border-border px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
            <span>草稿 #{draft.id}</span>
            {statusBadge(draft.status)}
          </div>
          {draft.source_session_id && (
            <span className="truncate text-[11px] text-muted-foreground/70">
              来源会话 {draft.source_session_id.slice(0, 8)} · agent {draft.source_agent_id}
            </span>
          )}
        </div>
      </div>

      {}
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
        <div className="space-y-1.5">
          <label className="text-[12px] font-medium text-muted-foreground">
            Skill 名称（短横线小写英文）
          </label>
          <input
            value={effName}
            disabled={!isPending || busy}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-border bg-background px-3 py-1.5 font-mono text-[13px] outline-none focus:ring-2 focus:ring-ring disabled:opacity-60"
            placeholder="policy-gap-analysis"
          />
        </div>
        <div className="flex min-h-0 flex-1 flex-col space-y-1.5">
          <label className="text-[12px] font-medium text-muted-foreground">
            SKILL.md 内容（含 frontmatter）
          </label>
          <textarea
            value={effContent}
            disabled={!isPending || busy}
            onChange={(e) => setContent(e.target.value)}
            className="min-h-[320px] flex-1 resize-none rounded-md border border-border bg-background px-3 py-2 font-mono text-[12.5px] leading-relaxed outline-none focus:ring-2 focus:ring-ring disabled:opacity-60"
            spellCheck={false}
          />
        </div>
        {!isPending && (
          <p className="text-[11px] text-muted-foreground">
            该草稿已{draft.status === 'approved' ? '通过' : '拒绝'}
            {draft.skill_path ? ` · 已写入 ${draft.skill_path}` : ''}，不可再编辑。
          </p>
        )}
      </div>

      {}
      {isPending && (
        <div className="flex shrink-0 items-center justify-between gap-2 border-t border-border px-4 py-3">
          <Button
            variant="outline"
            size="sm"
            disabled={!dirty || busy}
            onClick={() => saveMut.mutate()}
          >
            保存修改
          </Button>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:text-destructive"
              disabled={busy}
              onClick={() => rejectMut.mutate()}
            >
              <X className="h-3.5 w-3.5" />
              拒绝
            </Button>
            <Button size="sm" disabled={busy} onClick={() => approveMut.mutate()}>
              {approveMut.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Check className="h-3.5 w-3.5" />
              )}
              通过并固化
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

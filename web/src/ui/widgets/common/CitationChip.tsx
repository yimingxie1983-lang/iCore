

import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, ExternalLink, Loader2, TriangleAlert } from 'lucide-react'
import { api, type CitationItem } from '@/client/services/client'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/ui/widgets/ui/popover'
import { cn } from '@/shared/foundation/utils'

type CacheKey = string
const _cache = new Map<CacheKey, Promise<CitationItem | null>>()

function makeKey(kind: ChipKind, id: string): CacheKey {
  return `${kind}:${id}`
}

async function resolveOne(
  kind: ChipKind,
  id: string,
): Promise<CitationItem | null> {
  const key = makeKey(kind, id)
  const hit = _cache.get(key)
  if (hit) return hit
  const p = (async () => {
    try {

      if (kind === 'gov') {
        const resp = await api.verifyPolicyUrls([id])
        const items = resp.items || []
        return items.find((it) => it.url === id || it.id === id) ?? items[0] ?? null
      }
      const resp = await api.resolveCitations([id], { fetchAbstract: true })
      const item = (resp.items || []).find(
        (it) => it.type === kind && it.id === id,
      )
      return item ?? null
    } catch (err) {
      console.warn('[CitationChip] resolve failed', { kind, id, err })
      return null
    }
  })()
  _cache.set(key, p)
  return p
}

function govDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

export type ChipKind = 'pmid' | 'doi' | 'placeholder' | 'gov'

interface Props {
  kind: ChipKind

  id: string

  raw?: string
}

function PlaceholderChip({ raw }: { raw?: string }) {
  return (
    <span
      className="not-prose mx-[1px] inline-flex items-center gap-1 rounded border border-dashed border-amber-400/60 bg-amber-50 px-1.5 py-[1px] align-baseline font-mono text-[10.5px] text-amber-700"
      title="占位引用未填，作者需补充真实 PMID / DOI"
    >
      <TriangleAlert className="h-2.5 w-2.5" />
      待填{raw ? `(${raw})` : ''}
    </span>
  )
}

function makeUrl(kind: ChipKind, id: string): string {
  if (kind === 'pmid') return `https://pubmed.ncbi.nlm.nih.gov/${id}/`
  if (kind === 'doi') return `https://doi.org/${id}`
  if (kind === 'gov') return id
  return ''
}

function makeLabel(kind: ChipKind, id: string): string {
  if (kind === 'pmid') return `PMID:${id}`
  if (kind === 'doi') return `DOI:${id}`
  return `政策·${govDomain(id)}`
}

export default function CitationChip({ kind, id, raw }: Props) {
  if (kind === 'placeholder') {
    return <PlaceholderChip raw={raw} />
  }

  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [item, setItem] = useState<CitationItem | null>(null)
  const [errored, setErrored] = useState(false)
  const requestedRef = useRef(false)

  useEffect(() => {
    if (!open || requestedRef.current) return
    requestedRef.current = true
    setLoading(true)
    resolveOne(kind, id)
      .then((it) => {
        setItem(it)
        if (!it) setErrored(true)
      })
      .catch(() => setErrored(true))
      .finally(() => setLoading(false))
  }, [open, kind, id])

  const externalUrl = useMemo(() => makeUrl(kind, id), [kind, id])
  const label = makeLabel(kind, id)

  const chipTone = errored
    ? 'border-destructive/40 bg-destructive/[0.05] text-destructive hover:bg-destructive/[0.08]'
    : item
      ? 'border-secondary/40 bg-secondary/[0.08] text-secondary hover:bg-secondary/[0.12]'
      : 'border-border bg-card-muted text-muted-foreground hover:bg-muted/60 hover:text-foreground'

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'not-prose mx-[1px] inline-flex max-w-[260px] cursor-pointer items-center gap-1',
            'rounded border px-1.5 py-[1px] align-baseline font-mono text-[10.5px] leading-tight',
            'transition-colors',
            chipTone,
          )}
          title={`点击核验 ${label}`}
        >
          {loading ? (
            <Loader2 className="h-2.5 w-2.5 animate-spin" />
          ) : errored ? (
            <TriangleAlert className="h-2.5 w-2.5" />
          ) : item ? (
            <CheckCircle2 className="h-2.5 w-2.5" />
          ) : null}
          <span className="truncate">{label}</span>
        </button>
      </PopoverTrigger>

      <PopoverContent
        align="start"
        sideOffset={6}
        className="w-[360px] max-w-[92vw] p-0 text-[13px]"
      >
        <CitationCard
          kind={kind}
          id={id}
          loading={loading}
          item={item}
          errored={errored}
          fallbackUrl={externalUrl}
          raw={raw}
        />
      </PopoverContent>
    </Popover>
  )
}

function CitationCard({
  kind,
  id,
  loading,
  item,
  errored,
  fallbackUrl,
  raw,
}: {
  kind: ChipKind
  id: string
  loading: boolean
  item: CitationItem | null
  errored: boolean
  fallbackUrl: string
  raw?: string
}) {
  const label = makeLabel(kind, id)

  if (loading && !item) {
    return (
      <div className="space-y-2 p-4">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          <span className="text-[12px]">正在核验 {label} …</span>
        </div>
      </div>
    )
  }

  if (errored || !item || !item.ok) {
    const reason =
      item?.error ||
      (kind === 'gov'
        ? '无法核验该政策链接（可能已失效或被反爬拦截）'
        : '未在 PubMed / Crossref 找到该条目')
    const openLabel =
      kind === 'pmid' ? '仍在 PubMed 打开' : kind === 'doi' ? '仍在 doi.org 打开' : '仍打开该链接'
    return (
      <div className="space-y-2 p-4">
        <div className="flex items-center gap-2 text-destructive">
          <TriangleAlert className="h-3.5 w-3.5" />
          <span className="text-[12px] font-medium">未能核验 {label}</span>
        </div>
        <p className="text-[12px] text-muted-foreground">
          {reason}
          {raw && raw !== label && (
            <> · 原文：<code className="font-mono text-[11.5px]">{raw}</code></>
          )}
        </p>
        <a
          href={fallbackUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[12px] text-secondary underline underline-offset-2"
        >
          <ExternalLink className="h-3 w-3" />
          {openLabel}
        </a>
      </div>
    )
  }

  if (kind === 'gov') {
    return (
      <div className="space-y-2 p-4">
        <div className="flex items-center gap-1.5 text-[10.5px] font-medium uppercase tracking-wider text-secondary">
          <CheckCircle2 className="h-3 w-3" />
          政策原文
          <span className="text-muted-foreground/70">· {govDomain(item.url || id)}</span>
          {item.is_authority && (
            <span className="rounded bg-secondary/15 px-1 py-[1px] text-[9.5px] normal-case text-secondary">
              权威源
            </span>
          )}
        </div>

        {item.title && (
          <h4 className="text-[13.5px] font-semibold leading-snug text-foreground">
            {item.title}
          </h4>
        )}

        {item.abstract && (
          <p className="rounded border border-border/60 bg-muted/40 p-2 text-[11.5px] leading-relaxed text-foreground/80">
            {item.abstract}
          </p>
        )}

        <a
          href={item.url || fallbackUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[12px] text-secondary underline underline-offset-2"
        >
          <ExternalLink className="h-3 w-3" />
          打开政策原文
        </a>
      </div>
    )
  }

  const authors = item.authors || []
  const authorLine =
    authors.length === 0
      ? '(无作者)'
      : authors.length <= 3
        ? authors.join(', ')
        : `${authors.slice(0, 3).join(', ')}, et al`

  const journalBits: string[] = []
  if (item.journal) journalBits.push(item.journal)
  if (item.year) journalBits.push(item.year)
  if (item.volume) {
    let cite = item.volume
    if (item.issue) cite += `(${item.issue})`
    if (item.pages) cite += `:${item.pages}`
    journalBits.push(cite)
  }

  return (
    <div className="space-y-2 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5 text-[10.5px] font-medium uppercase tracking-wider text-secondary">
          <CheckCircle2 className="h-3 w-3" />
          {label}
          <span className="text-muted-foreground/70">· {item.source}</span>
        </div>
      </div>

      {item.title && (
        <h4 className="text-[13.5px] font-semibold leading-snug text-foreground">
          {item.title}
        </h4>
      )}

      <div className="text-[11.5px] text-muted-foreground">
        <div>{authorLine}</div>
        {journalBits.length > 0 && (
          <div className="mt-0.5 italic">{journalBits.join('; ')}</div>
        )}
        {item.doi && kind !== 'doi' && (
          <div className="mt-0.5 font-mono text-[10.5px] text-muted-foreground/80">
            DOI: {item.doi}
          </div>
        )}
        {item.pmid && kind !== 'pmid' && (
          <div className="mt-0.5 font-mono text-[10.5px] text-muted-foreground/80">
            PMID: {item.pmid}
          </div>
        )}
      </div>

      {item.abstract && (
        <p className="rounded border border-border/60 bg-muted/40 p-2 text-[11.5px] leading-relaxed text-foreground/80">
          {item.abstract}
        </p>
      )}

      <a
        href={item.url || fallbackUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-[12px] text-secondary underline underline-offset-2"
      >
        <ExternalLink className="h-3 w-3" />
        在 {item.source === 'pubmed' ? 'PubMed' : 'doi.org'} 打开全文
      </a>
    </div>
  )
}

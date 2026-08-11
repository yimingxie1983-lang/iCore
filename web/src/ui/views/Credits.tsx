

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Coins,
  TrendingDown,
  Wallet,
  Receipt,
  Info,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'

import { api, type CreditTx, type CreditTxType } from '@/client/services/client'
import { Badge } from '@/ui/widgets/ui/badge'
import { Separator } from '@/ui/widgets/ui/separator'
import { parseBackendTime } from '@/shared/foundation/utils'

export const TX_PAGE_SIZE = 10

export const TX_PAGE_SIZE_OPTIONS = [10, 20, 50] as const

function fmtTxTime(raw: unknown): string {
  const ms = parseBackendTime(raw as string | number | null | undefined)
  if (ms == null) return '—'
  return new Date(ms).toLocaleString('zh-CN', { hour12: false })
}

export function TxPagination({
  total,
  limit,
  offset,
  onOffset,
  onLimit,
}: {
  total: number
  limit: number
  offset: number
  onOffset: (next: number) => void
  onLimit?: (next: number) => void
}) {
  if (total <= 0) return null
  const from = offset + 1
  const to = Math.min(offset + limit, total)
  const canPrev = offset > 0
  const canNext = offset + limit < total
  const page = Math.floor(offset / limit) + 1
  const pages = Math.max(1, Math.ceil(total / limit))
  const btn =
    'flex items-center gap-0.5 rounded-md border border-border px-2 py-1 text-[12px] ' +
    'transition-colors disabled:cursor-not-allowed disabled:opacity-40 ' +
    'enabled:hover:bg-muted'
  return (
    <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[12px] text-muted-foreground">
      <div className="flex items-center gap-2">
        <span>
          共 {total} 条 · 第 {from}-{to} 条 · {page}/{pages} 页
        </span>
        {onLimit && (
          <label className="flex items-center gap-1">
            每页
            <select
              value={limit}
              onChange={(e) => onLimit(Number(e.target.value))}
              className="rounded-md border border-border bg-background px-1.5 py-1 text-[12px] text-foreground outline-none"
            >
              {TX_PAGE_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            条
          </label>
        )}
      </div>
      <div className="flex gap-1.5">
        <button
          className={btn}
          disabled={!canPrev}
          onClick={() => onOffset(Math.max(0, offset - limit))}
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          上一页
        </button>
        <button
          className={btn}
          disabled={!canNext}
          onClick={() => onOffset(offset + limit)}
        >
          下一页
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

export function formatCredits(n: number): string {
  return Math.round(n).toLocaleString('zh-CN')
}

export function formatCNY(cny: number): string {
  if (cny === 0) return '¥0'
  if (Math.abs(cny) < 0.01) return `¥${(cny * 100).toFixed(3)}分`
  return `¥${cny.toFixed(3)}`
}

const TX_LABEL: Record<CreditTxType, string> = {
  grant: '注册赠送',
  recharge: '充值',
  consume: '消费',
  adjust: '调整',
}

export function txLabel(t: CreditTxType): string {
  return TX_LABEL[t] || t
}

function StatBox({
  icon: Icon,
  label,
  value,
  hint,
  accent,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
  hint?: string
  accent?: boolean
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div
        className={
          'mt-1.5 font-mono text-2xl font-bold ' +
          (accent ? 'text-primary' : 'text-foreground')
        }
      >
        {value}
      </div>
      {hint && <div className="mt-0.5 text-[11px] text-muted-foreground">{hint}</div>}
    </div>
  )
}

function TxAmount({ tx }: { tx: CreditTx }) {
  const positive = tx.amount >= 0
  return (
    <span
      className={
        'font-mono font-semibold ' +
        (positive ? 'text-emerald-600' : 'text-destructive')
      }
    >
      {positive ? '+' : ''}
      {formatCredits(tx.amount)}
    </span>
  )
}

export function TransactionsTable({
  items,
  showTokens = true,
}: {
  items: CreditTx[]
  showTokens?: boolean
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-[12px] text-muted-foreground">
          <tr>
            <th className="px-4 py-2.5 text-left font-medium">时间</th>
            <th className="px-4 py-2.5 text-left font-medium">类型</th>
            <th className="px-4 py-2.5 text-right font-medium">积分变动</th>
            <th className="px-4 py-2.5 text-right font-medium">变动后余额</th>
            {showTokens && (
              <th className="px-4 py-2.5 text-left font-medium">明细</th>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((t) => (
            <tr key={t.id} className="hover:bg-muted/30">
              <td className="whitespace-nowrap px-4 py-2.5 text-[12px] text-muted-foreground">
                {fmtTxTime(t.created_at)}
              </td>
              <td className="px-4 py-2.5">
                <Badge
                  variant={t.type === 'consume' ? 'outline' : 'secondary'}
                  className="text-[11px]"
                >
                  {txLabel(t.type)}
                </Badge>
              </td>
              <td className="px-4 py-2.5 text-right">
                <TxAmount tx={t} />
              </td>
              <td className="px-4 py-2.5 text-right font-mono text-[13px] text-foreground">
                {formatCredits(t.balance_after)}
              </td>
              {showTokens && (
                <td className="px-4 py-2.5 text-[11px] text-muted-foreground">
                  {t.type === 'consume' ? (
                    <span>
                      {t.model || '模型'} · 入{t.input_tokens}
                      {t.cached_input_tokens > 0 ? `(缓存${t.cached_input_tokens})` : ''} / 出
                      {t.output_tokens} · 成本 {formatCNY(t.cost_cny)}
                    </span>
                  ) : (
                    <span>{t.reason || '—'}</span>
                  )}
                </td>
              )}
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td
                colSpan={showTokens ? 5 : 4}
                className="px-4 py-8 text-center text-muted-foreground"
              >
                暂无记录
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default function Credits() {
  const [txType, setTxType] = useState<CreditTxType | ''>('')
  const [offset, setOffset] = useState(0)
  const [limit, setLimit] = useState<number>(TX_PAGE_SIZE)

  const changeType = (tp: CreditTxType | '') => {
    setTxType(tp)
    setOffset(0)
  }

  const changeLimit = (n: number) => {
    setLimit(n)
    setOffset(0)
  }

  const { data: bal } = useQuery({
    queryKey: ['my-credits'],
    queryFn: () => api.myCredits(),
    refetchInterval: 15_000,
  })

  const { data: txs, isLoading } = useQuery({
    queryKey: ['my-credit-tx', txType, offset, limit],
    queryFn: () =>
      api.myCreditTransactions({
        limit,
        offset,
        type: txType || undefined,
      }),
  })

  const { data: pricing } = useQuery({
    queryKey: ['pricing'],
    queryFn: () => api.getPricing(),
  })

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto p-6">
      <div className="mb-4">
        <h2 className="text-base font-semibold text-foreground">我的额度</h2>
        <p className="mt-0.5 text-[12px] text-muted-foreground">
          积分余额、消费明细与当前计费费率。按 token 消耗实时扣减积分。
        </p>
      </div>

      {}
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatBox
          icon={Wallet}
          label="当前余额"
          value={formatCredits(bal?.balance ?? 0)}
          hint="积分"
          accent
        />
        <StatBox
          icon={Coins}
          label="累计获得"
          value={formatCredits(bal?.total_recharged ?? 0)}
          hint="充值 + 赠送"
        />
        <StatBox
          icon={TrendingDown}
          label="累计消费"
          value={formatCredits(bal?.total_consumed ?? 0)}
          hint={`${bal?.consume_count ?? 0} 次对话调用`}
        />
        <StatBox
          icon={Receipt}
          label="累计成本"
          value={formatCNY(bal?.total_cost_cny ?? 0)}
          hint="真实模型成本"
        />
      </div>

      {}
      {bal != null && bal.balance <= 0 && (
        <div className="mb-5 flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/[0.06] px-4 py-3 text-[13px] text-destructive">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <span>积分余额已用尽，无法发起新对话。请联系管理员为你充值。</span>
        </div>
      )}

      {}
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">积分流水</h3>
        <div className="flex gap-1">
          {(['', 'consume', 'recharge', 'grant', 'adjust'] as const).map((tp) => (
            <button
              key={tp || 'all'}
              onClick={() => changeType(tp)}
              className={
                'rounded-md px-2.5 py-1 text-[12px] transition-colors ' +
                (txType === tp
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted')
              }
            >
              {tp === '' ? '全部' : txLabel(tp)}
            </button>
          ))}
        </div>
      </div>
      {isLoading ? (
        <div className="rounded-xl border border-border bg-card px-4 py-8 text-center text-muted-foreground">
          加载中…
        </div>
      ) : (
        <>
          <TransactionsTable items={txs?.items ?? []} />
          <TxPagination
            total={txs?.total ?? 0}
            limit={limit}
            offset={offset}
            onOffset={setOffset}
            onLimit={changeLimit}
          />
        </>
      )}

      {}
      {pricing && (
        <>
          <Separator className="my-5" />
          <h3 className="mb-2 text-sm font-semibold text-foreground">
            当前费率
            {pricing.markup !== 1 && (
              <span className="ml-2 text-[12px] font-normal text-muted-foreground">
                （已应用 {pricing.markup}× 价格系数）
              </span>
            )}
          </h3>

          {pricing.mode === 'flat' ? (

            <>
              <div className="rounded-xl border border-border bg-card px-5 py-4">
                <div className="text-[13px] text-muted-foreground">统一计费单价</div>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="font-mono text-2xl font-semibold text-foreground">
                    {formatCredits(
                      Math.round(pricing.flat_credits_per_1m * pricing.markup),
                    )}
                  </span>
                  <span className="text-[13px] text-muted-foreground">积分 / 百万 tokens</span>
                </div>
                <p className="mt-2 text-[12px] text-muted-foreground">
                  不分输入 / 输出，所有 token 按同一单价计费，简单透明。
                </p>
              </div>
              <p className="mt-2 text-[11px] text-muted-foreground">
                1M = 100 万 tokens。实际扣费以模型返回的真实用量为准。
              </p>
            </>
          ) : pricing.mode === 'split' ? (

            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-border bg-card px-5 py-4">
                  <div className="text-[13px] text-muted-foreground">输入单价</div>
                  <div className="mt-1 flex items-baseline gap-2">
                    <span className="font-mono text-2xl font-semibold text-foreground">
                      {formatCredits(
                        Math.round(pricing.flat_credits_per_1m * pricing.markup),
                      )}
                    </span>
                    <span className="text-[13px] text-muted-foreground">积分 / 百万 tokens</span>
                  </div>
                  <p className="mt-2 text-[12px] text-muted-foreground">
                    输入不分缓存，统一按此单价计费。
                  </p>
                </div>
                <div className="rounded-xl border border-border bg-card px-5 py-4">
                  <div className="text-[13px] text-muted-foreground">输出单价</div>
                  <div className="mt-1 flex items-baseline gap-2">
                    <span className="font-mono text-2xl font-semibold text-foreground">
                      {formatCredits(
                        Math.round(pricing.flat_output_credits_per_1m * pricing.markup),
                      )}
                    </span>
                    <span className="text-[13px] text-muted-foreground">积分 / 百万 tokens</span>
                  </div>
                  <p className="mt-2 text-[12px] text-muted-foreground">
                    输出按模型返回的真实用量单独计费。
                  </p>
                </div>
              </div>
              <p className="mt-2 text-[11px] text-muted-foreground">
                1M = 100 万 tokens。实际扣费以模型返回的真实用量为准。
              </p>
            </>
          ) : (
            <>
              <div className="overflow-hidden rounded-xl border border-border bg-card">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-[12px] text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2.5 text-left font-medium">模型</th>
                      <th className="px-4 py-2.5 text-right font-medium">输入（积分/1M）</th>
                      <th className="px-4 py-2.5 text-right font-medium">缓存命中（积分/1M）</th>
                      <th className="px-4 py-2.5 text-right font-medium">输出（积分/1M）</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {pricing.items
                      .filter((p) => p.model !== 'default')
                      .map((p) => (
                        <tr key={p.model} className="hover:bg-muted/30">
                          <td className="px-4 py-2.5 font-medium text-foreground">
                            {p.label || p.model}
                            <span className="ml-1.5 text-[11px] text-muted-foreground">
                              {p.model}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono">
                            {formatCredits(p.credits_per_1m_input)}
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono text-emerald-600">
                            {formatCredits(p.credits_per_1m_cached_input)}
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono">
                            {formatCredits(p.credits_per_1m_output)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-[11px] text-muted-foreground">
                1M = 100 万 tokens。命中上下文缓存的输入按更低费率计费。
              </p>
            </>
          )}
        </>
      )}
    </div>
  )
}

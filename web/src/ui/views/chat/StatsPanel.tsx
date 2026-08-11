

import { useEffect, useState } from 'react'

import { Progress } from '@/ui/widgets/ui/progress'
import { Separator } from '@/ui/widgets/ui/separator'
import { cn } from '@/shared/foundation/utils'
import type { TurnStats } from '@/application/state/chatStore'

interface Props {
  stats: TurnStats
  streaming: boolean
}

function formatNum(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

function formatUSD(n: number): string {
  if (n < 0.001) return `$${(n * 1000).toFixed(3)}m`
  if (n < 1) return `$${n.toFixed(4)}`
  return `$${n.toFixed(3)}`
}

function formatCNY(usd: number): string {
  const cny = usd * 7.2
  if (cny < 0.01) return `¥${(cny * 100).toFixed(3)}分`
  return `¥${cny.toFixed(3)}`
}

function ElapsedClock({
  startedAt,
  finishedAt,
}: {
  startedAt: number | null
  finishedAt: number | null
}) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!startedAt || finishedAt) return
    const t = setInterval(() => setNow(Date.now()), 100)
    return () => clearInterval(t)
  }, [startedAt, finishedAt])

  if (!startedAt) return <span>—</span>
  const end = finishedAt || now
  const ms = end - startedAt
  if (ms < 1000) return <span>{ms}ms</span>
  return <span>{(ms / 1000).toFixed(2)}s</span>
}

function Row({
  label,
  value,
  hint,
  accent,
}: {
  label: string
  value: React.ReactNode
  hint?: string
  accent?: boolean
}) {
  return (
    <div className="flex items-baseline py-0.5">
      <span className="flex-1 text-[11px] text-muted-foreground">{label}</span>
      <span
        className={cn(
          'font-mono',
          accent
            ? 'text-base font-bold text-primary'
            : 'text-sm font-medium text-foreground',
        )}
      >
        {value}
      </span>
      {hint && (
        <span className="ml-1 text-[11px] text-muted-foreground">{hint}</span>
      )}
    </div>
  )
}

export default function StatsPanel({ stats, streaming }: Props) {
  const inputPct =
    stats.inputTokens > 0
      ? Math.round((stats.cachedInputTokens / stats.inputTokens) * 100)
      : 0

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-sm font-semibold text-foreground">本轮统计</h2>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          每次发送消息后重置；流式期间实时刷新
        </p>
      </div>

      <div>
        <Row
          label="耗时"
          value={
            <ElapsedClock
              startedAt={stats.startedAt}
              finishedAt={stats.finishedAt}
            />
          }
        />
        <Row label="事件总数" value={formatNum(stats.totalEvents)} />
        <Row label="模型调用" value={formatNum(stats.modelCalls)} />
        <Row label="工具调用" value={formatNum(stats.toolCalls)} />
      </div>

      <Separator />

      <div>
        <h3 className="mb-1 text-sm font-semibold text-foreground">Token 计费</h3>
        <Row
          label="总 token"
          value={formatNum(stats.totalTokens)}
          accent
          hint="in+out"
        />
        <Row label="输入" value={formatNum(stats.inputTokens)} />
        <Row
          label="└ 缓存命中"
          value={formatNum(stats.cachedInputTokens)}
          hint={`${inputPct}%`}
        />
        <Row label="输出" value={formatNum(stats.outputTokens)} />

        {stats.inputTokens > 0 && (
          <div className="mt-2">
            <div className="mb-1 text-[11px] text-muted-foreground">缓存命中率</div>
            <Progress
              value={inputPct}
              indicatorClassName="bg-emerald-600"
              className="h-1.5"
            />
          </div>
        )}
      </div>

      {stats.creditsBalance != null && (
        <>
          <Separator />
          <div>
            <h3 className="mb-1 text-sm font-semibold text-foreground">积分计费</h3>
            <Row
              label="本轮实扣"
              value={Math.round(stats.creditsCharged).toLocaleString('zh-CN')}
              accent
              hint="积分"
            />
            <Row
              label="当前余额"
              value={Math.round(stats.creditsBalance).toLocaleString('zh-CN')}
              hint="积分"
            />
            <p className="mt-1 text-[11px] text-muted-foreground">
              按 token 用量实时扣减；余额以「我的额度」页为准。
            </p>
          </div>
        </>
      )}

      <Separator />

      <div>
        <h3 className="mb-1 text-sm font-semibold text-foreground">估算费用</h3>
        <Row label="美元" value={formatUSD(stats.estCostUSD)} accent />
        <Row label="人民币" value={formatCNY(stats.estCostUSD)} />
        <p className="mt-1 text-[11px] text-muted-foreground">
          按公开 GA 价目表估算，仅供参考；以供应商账单为准。
        </p>
      </div>

      {streaming && (
        <div>
          <Progress value={undefined} className="h-1 animate-pulse" />
          <p className="mt-1 text-[11px] text-secondary">流式接收中…</p>
        </div>
      )}
    </div>
  )
}

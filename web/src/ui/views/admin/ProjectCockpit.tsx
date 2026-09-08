import { useId, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import type {
  AdminProjectStats,
  AdminProjectTokenDay,
  AdminProjectTokenHour,
  AdminProjectTokenModel,
  CockpitProject,
} from '@/client/services/client'
import { Skeleton } from '@/ui/widgets/ui/skeleton'
import { cn } from '@/shared/foundation/utils'

const STATUS = {
  active: { label: '正常', color: '#10b981' },
  paused: { label: '已暂停', color: '#f59e0b' },
  frozen: { label: '已冻结', color: '#94a3b8' },
} as const

const TOKEN_TONE = {
  cached: { label: '缓存命中', color: 'hsl(var(--secondary))' },
  fresh: { label: '新输入', color: 'hsl(var(--primary))' },
  output: { label: '输出', color: 'hsl(var(--accent))' },
} as const

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1000).toFixed(1)}k`
  return String(Math.round(n))
}

function fmtCny(micro: number): string {
  const n = (micro || 0) / 1_000_000
  if (n === 0) return '¥0.00'
  if (Math.abs(n) < 0.01) return `¥${n.toFixed(4)}`
  return `¥${n.toFixed(2)}`
}

function useSvgUid() {
  return useId().replace(/:/g, '')
}

function clamp01(n: number) {
  if (Number.isNaN(n) || n < 0) return 0
  if (n > 1) return 1
  return n
}

function ChartFrame({
  title,
  hint,
  children,
  className,
}: {
  title: string
  hint?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('cockpit-panel surface-card relative overflow-hidden rounded-xl p-4', className)}>
      <div className="relative z-[1] mb-3 flex items-baseline justify-between gap-2">
        <div className="text-[13px] font-semibold tracking-tight text-foreground">{title}</div>
        {hint ? <div className="text-[11px] text-muted-foreground">{hint}</div> : null}
      </div>
      <div className="relative z-[1]">{children}</div>
    </div>
  )
}

function HudMetric({
  label,
  value,
  hint,
}: {
  label: string
  value: React.ReactNode
  hint?: React.ReactNode
}) {
  return (
    <div className="cockpit-panel surface-card relative overflow-hidden rounded-xl px-4 py-3">
      <div className="relative z-[1]">
        <div className="text-[10px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
          {label}
        </div>
        <div className="mt-1 font-mono text-[1.65rem] font-semibold leading-none tracking-tight text-foreground">
          {value}
        </div>
        {hint ? <div className="mt-1.5 text-[11px] text-muted-foreground">{hint}</div> : null}
      </div>
    </div>
  )
}

function GlowDefs({ id }: { id: string }) {
  return (
    <defs>
      <filter id={`${id}-glow`} x="-40%" y="-40%" width="180%" height="180%">
        <feGaussianBlur stdDeviation="2.4" result="b" />
        <feMerge>
          <feMergeNode in="b" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
      <filter id={`${id}-soft`} x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="1.2" result="b" />
        <feMerge>
          <feMergeNode in="b" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>
  )
}

function StatusDonut({
  active,
  paused,
  frozen,
  running,
  total,
}: {
  active: number
  paused: number
  frozen: number
  running: number
  total: number
}) {
  const uid = useSvgUid()
  const size = 240
  const cx = size / 2
  const cy = size / 2
  const thickness = 20
  const r = 78
  const C = 2 * Math.PI * r
  const slices = [
    { key: 'active', ...STATUS.active, value: active },
    { key: 'paused', ...STATUS.paused, value: paused },
    { key: 'frozen', ...STATUS.frozen, value: frozen },
  ]
  const sum = slices.reduce((s, it) => s + it.value, 0)
  let offset = 0
  const runPct = clamp01(running / Math.max(1, total))
  const innerR = 52
  const innerC = 2 * Math.PI * innerR

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center sm:justify-center sm:gap-8">
      <svg viewBox={`0 0 ${size} ${size}`} className="cockpit-draw h-[220px] w-[220px] shrink-0">
        <GlowDefs id={uid} />
        {Array.from({ length: 48 }, (_, i) => {
          const a = ((i / 48) * 360 - 90) * (Math.PI / 180)
          const long = i % 4 === 0
          const r1 = 102
          const r2 = long ? 112 : 107
          return (
            <line
              key={i}
              x1={cx + Math.cos(a) * r1}
              y1={cy + Math.sin(a) * r1}
              x2={cx + Math.cos(a) * r2}
              y2={cy + Math.sin(a) * r2}
              stroke="hsl(var(--secondary))"
              strokeOpacity={long ? 0.45 : 0.18}
              strokeWidth={long ? 1.6 : 1}
            />
          )
        })}
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke="hsl(var(--muted))"
          strokeWidth={thickness}
        />
        {sum > 0
          ? slices.map((slice) => {
              if (slice.value <= 0) return null
              const gap = slices.filter((s) => s.value > 0).length > 1 ? 5 : 0
              const len = Math.max(0, (slice.value / sum) * C - gap)
              const el = (
                <circle
                  key={slice.key}
                  cx={cx}
                  cy={cy}
                  r={r}
                  fill="none"
                  stroke={slice.color}
                  strokeWidth={thickness}
                  strokeDasharray={`${len} ${C - len}`}
                  strokeDashoffset={-offset}
                  strokeLinecap="butt"
                  transform={`rotate(-90 ${cx} ${cy})`}
                  filter={`url(#${uid}-glow)`}
                />
              )
              offset += len + gap
              return el
            })
          : null}
        <circle
          cx={cx}
          cy={cy}
          r={innerR}
          fill="none"
          stroke="hsl(var(--border))"
          strokeWidth={8}
        />
        {runPct > 0 ? (
          <circle
            cx={cx}
            cy={cy}
            r={innerR}
            fill="none"
            stroke="hsl(var(--secondary))"
            strokeWidth={8}
            strokeDasharray={`${runPct * innerC} ${innerC}`}
            strokeLinecap="round"
            transform={`rotate(-90 ${cx} ${cy})`}
            filter={`url(#${uid}-glow)`}
          />
        ) : null}
        <text
          x={cx}
          y={cy - 4}
          textAnchor="middle"
          className="fill-foreground"
          style={{ fontSize: 28, fontFamily: 'ui-monospace, monospace', fontWeight: 650 }}
        >
          {total}
        </text>
        <text
          x={cx}
          y={cy + 16}
          textAnchor="middle"
          className="fill-muted-foreground"
          style={{ fontSize: 10, letterSpacing: '0.18em' }}
        >
          项目
        </text>
      </svg>
      <div className="w-full min-w-[140px] space-y-3 sm:w-auto">
        {slices.map((s) => (
          <div key={s.key} className="flex items-center justify-between gap-6 text-[12px]">
            <span className="flex items-center gap-2 text-muted-foreground">
              <span className="h-2 w-2 rounded-full" style={{ background: s.color, boxShadow: `0 0 8px ${s.color}` }} />
              {s.label}
            </span>
            <span className="font-mono tabular-nums text-foreground">{s.value}</span>
          </div>
        ))}
        <div className="flex items-center justify-between gap-6 border-t border-border/70 pt-2 text-[12px]">
          <span className="flex items-center gap-2 text-muted-foreground">
            <span className="h-2 w-2 rounded-full bg-secondary shadow-[0_0_8px_hsl(var(--secondary))]" />
            运行中
          </span>
          <span className="font-mono tabular-nums text-foreground">
            {running}
            <span className="ml-1 text-muted-foreground">{Math.round(runPct * 100)}%</span>
          </span>
        </div>
      </div>
    </div>
  )
}

function RadarChart({ axes }: { axes: { label: string; value: number }[] }) {
  const uid = useSvgUid()
  const size = 280
  const cx = 140
  const cy = 132
  const r = 86
  const n = axes.length || 1
  const angle = (i: number) => -Math.PI / 2 + (i / n) * 2 * Math.PI
  const pt = (i: number, ratio: number) => {
    const a = angle(i)
    return [cx + r * ratio * Math.cos(a), cy + r * ratio * Math.sin(a)] as const
  }
  const poly = axes
    .map((ax, i) => pt(i, clamp01(ax.value / 100)).join(','))
    .join(' ')

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="cockpit-draw mx-auto h-[240px] w-full max-w-[320px]">
      <GlowDefs id={uid} />
      {[0.25, 0.5, 0.75, 1].map((lv) => (
        <polygon
          key={lv}
          fill="none"
          stroke="hsl(var(--secondary))"
          strokeOpacity={lv === 1 ? 0.28 : 0.12}
          strokeWidth={lv === 1 ? 1.2 : 1}
          points={axes.map((_, i) => pt(i, lv).join(',')).join(' ')}
        />
      ))}
      {axes.map((_, i) => {
        const [x, y] = pt(i, 1)
        return (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={x}
            y2={y}
            stroke="hsl(var(--secondary))"
            strokeOpacity="0.16"
          />
        )
      })}
      <polygon
        points={poly}
        fill="hsl(var(--secondary) / 0.22)"
        stroke="hsl(var(--secondary))"
        strokeWidth="1.8"
        filter={`url(#${uid}-glow)`}
      />
      {axes.map((ax, i) => {
        const [x, y] = pt(i, clamp01(ax.value / 100))
        return <circle key={`d-${ax.label}`} cx={x} cy={y} r="3.2" fill="hsl(var(--secondary))" />
      })}
      {axes.map((ax, i) => {
        const [x, y] = pt(i, 1.22)
        return (
          <text
            key={`l-${ax.label}`}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
            className="fill-muted-foreground"
            style={{ fontSize: 10 }}
          >
            {ax.label}
          </text>
        )
      })}
    </svg>
  )
}

function AreaTrend({
  days,
  created7,
  created30,
  active24h,
}: {
  days: { date: string; count: number }[]
  created7: number
  created30: number
  active24h: number
}) {
  const uid = useSvgUid()
  const [hover, setHover] = useState<number | null>(null)
  const W = 720
  const H = 220
  const pad = { t: 18, r: 16, b: 32, l: 36 }
  const max = Math.max(1, ...days.map((d) => d.count))
  const innerW = W - pad.l - pad.r
  const innerH = H - pad.t - pad.b
  const pts = days.map((d, i) => {
    const x = pad.l + (days.length <= 1 ? innerW / 2 : (i / (days.length - 1)) * innerW)
    const y = pad.t + innerH - (d.count / max) * innerH
    return { ...d, x, y }
  })
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const area =
    pts.length === 0
      ? ''
      : `${line} L${pts[pts.length - 1].x.toFixed(1)},${pad.t + innerH} L${pts[0].x.toFixed(1)},${pad.t + innerH} Z`
  const hi = hover == null ? null : pts[hover]

  return (
    <ChartFrame
      title="近 14 天新建"
      hint={
        <span>
          7 天 {created7} · 30 天 {created30} · 24h 活跃 {active24h}
        </span>
      }
    >
      <div
        className="relative"
        onMouseLeave={() => setHover(null)}
      >
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="cockpit-draw h-[220px] w-full"
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect()
            const x = ((e.clientX - rect.left) / rect.width) * W
            let best = 0
            let dist = Infinity
            pts.forEach((p, i) => {
              const d = Math.abs(p.x - x)
              if (d < dist) {
                dist = d
                best = i
              }
            })
            setHover(best)
          }}
        >
          <GlowDefs id={uid} />
          <linearGradient id={`${uid}-fill`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(var(--secondary))" stopOpacity="0.42" />
            <stop offset="100%" stopColor="hsl(var(--secondary))" stopOpacity="0.02" />
          </linearGradient>
          {[0, 0.5, 1].map((lv) => {
            const y = pad.t + innerH * (1 - lv)
            return (
              <g key={lv}>
                <line
                  x1={pad.l}
                  x2={W - pad.r}
                  y1={y}
                  y2={y}
                  stroke="hsl(var(--secondary))"
                  strokeOpacity="0.12"
                />
                <text
                  x={pad.l - 8}
                  y={y + 3}
                  textAnchor="end"
                  className="fill-muted-foreground"
                  style={{ fontSize: 10, fontFamily: 'ui-monospace, monospace' }}
                >
                  {Math.round(max * lv)}
                </text>
              </g>
            )
          })}
          {area ? <path d={area} fill={`url(#${uid}-fill)`} /> : null}
          {line ? (
            <path
              d={line}
              fill="none"
              stroke="hsl(var(--secondary))"
              strokeWidth="2.4"
              filter={`url(#${uid}-glow)`}
            />
          ) : null}
          {pts.map((p, i) => (
            <circle
              key={p.date}
              cx={p.x}
              cy={p.y}
              r={hover === i ? 5 : p.count > 0 ? 3.2 : 2}
              fill={p.count > 0 ? 'hsl(var(--secondary))' : 'hsl(var(--muted-foreground) / 0.35)'}
            />
          ))}
          {pts.map((p, i) =>
            i % 2 === 0 ? (
              <text
                key={`t-${p.date}`}
                x={p.x}
                y={H - 10}
                textAnchor="middle"
                className="fill-muted-foreground"
                style={{ fontSize: 10 }}
              >
                {p.date.slice(5).replace('-', '/')}
              </text>
            ) : null,
          )}
          {hi ? (
            <line
              x1={hi.x}
              x2={hi.x}
              y1={pad.t}
              y2={pad.t + innerH}
              stroke="hsl(var(--accent))"
              strokeOpacity="0.55"
              strokeDasharray="3 4"
            />
          ) : null}
        </svg>
        {hi ? (
          <div className="pointer-events-none absolute right-2 top-0 rounded-md border border-border bg-popover/95 px-2.5 py-1.5 text-[11px] shadow-md backdrop-blur-sm">
            <div className="text-muted-foreground">{hi.date}</div>
            <div className="font-mono text-foreground">新建 {hi.count}</div>
          </div>
        ) : null}
      </div>
    </ChartFrame>
  )
}

function stackedArea(
  pts: { x: number; top: number; base: number }[],
): string {
  if (pts.length === 0) return ''
  const top = pts.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.top.toFixed(1)}`).join(' ')
  const back = [...pts]
    .reverse()
    .map((p) => `L${p.x.toFixed(1)},${p.base.toFixed(1)}`)
    .join(' ')
  return `${top} ${back} Z`
}

function TokenTrend({
  days,
  last7,
  last24h,
  last7Cost,
}: {
  days: AdminProjectTokenDay[]
  last7: number
  last24h: number
  last7Cost: number
}) {
  const uid = useSvgUid()
  const [hover, setHover] = useState<number | null>(null)
  const W = 720
  const H = 220
  const pad = { t: 18, r: 52, b: 32, l: 44 }
  const series = days.map((d) => {
    const cached = d.cached_input_tokens
    const fresh = Math.max(0, d.input_tokens - d.cached_input_tokens)
    const output = d.output_tokens
    return {
      ...d,
      cached,
      fresh,
      output,
      total: cached + fresh + output,
      cost: d.cost_micro_cny || 0,
      credits: d.credits || 0,
    }
  })
  const max = Math.max(1, ...series.map((d) => d.total))
  const maxCost = Math.max(1, ...series.map((d) => d.cost))
  const innerW = W - pad.l - pad.r
  const innerH = H - pad.t - pad.b
  const yOf = (v: number) => pad.t + innerH - (v / max) * innerH
  const yCost = (v: number) => pad.t + innerH - (v / maxCost) * innerH
  const pts = series.map((d, i) => {
    const x = pad.l + (series.length <= 1 ? innerW / 2 : (i / (series.length - 1)) * innerW)
    const y0 = pad.t + innerH
    const yC = yOf(d.cached)
    const yF = yOf(d.cached + d.fresh)
    const yO = yOf(d.total)
    return { ...d, x, y0, yC, yF, yO, yFee: yCost(d.cost) }
  })
  const hi = hover == null ? null : pts[hover]
  const feeLine = pts.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.yFee.toFixed(1)}`).join(' ')

  return (
    <ChartFrame
      title="近 14 天 Token / 费用"
      hint={
        <span>
          7 天 {fmtTokens(last7)} · 费用 {fmtCny(last7Cost)} · 24h {fmtTokens(last24h)}
        </span>
      }
    >
      <div className="relative" onMouseLeave={() => setHover(null)}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="cockpit-draw h-[220px] w-full"
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect()
            const x = ((e.clientX - rect.left) / rect.width) * W
            let best = 0
            let dist = Infinity
            pts.forEach((p, i) => {
              const d = Math.abs(p.x - x)
              if (d < dist) {
                dist = d
                best = i
              }
            })
            setHover(best)
          }}
        >
          <GlowDefs id={uid} />
          <linearGradient id={`${uid}-out`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(var(--accent))" stopOpacity="0.55" />
            <stop offset="100%" stopColor="hsl(var(--accent))" stopOpacity="0.06" />
          </linearGradient>
          <linearGradient id={`${uid}-fresh`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity="0.45" />
            <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity="0.06" />
          </linearGradient>
          <linearGradient id={`${uid}-cached`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(var(--secondary))" stopOpacity="0.5" />
            <stop offset="100%" stopColor="hsl(var(--secondary))" stopOpacity="0.06" />
          </linearGradient>
          {[0, 0.5, 1].map((lv) => {
            const y = pad.t + innerH * (1 - lv)
            return (
              <g key={lv}>
                <line
                  x1={pad.l}
                  x2={W - pad.r}
                  y1={y}
                  y2={y}
                  stroke="hsl(var(--secondary))"
                  strokeOpacity="0.12"
                />
                <text
                  x={pad.l - 8}
                  y={y + 3}
                  textAnchor="end"
                  className="fill-muted-foreground"
                  style={{ fontSize: 10, fontFamily: 'ui-monospace, monospace' }}
                >
                  {fmtTokens(max * lv)}
                </text>
                <text
                  x={W - pad.r + 8}
                  y={y + 3}
                  className="fill-muted-foreground"
                  style={{ fontSize: 10, fontFamily: 'ui-monospace, monospace' }}
                >
                  {fmtCny(maxCost * lv)}
                </text>
              </g>
            )
          })}
          <path
            d={stackedArea(pts.map((p) => ({ x: p.x, top: p.yC, base: p.y0 })))}
            fill={`url(#${uid}-cached)`}
          />
          <path
            d={stackedArea(pts.map((p) => ({ x: p.x, top: p.yF, base: p.yC })))}
            fill={`url(#${uid}-fresh)`}
          />
          <path
            d={stackedArea(pts.map((p) => ({ x: p.x, top: p.yO, base: p.yF })))}
            fill={`url(#${uid}-out)`}
          />
          <path
            d={feeLine}
            fill="none"
            stroke="hsl(var(--accent))"
            strokeWidth="2.2"
            filter={`url(#${uid}-glow)`}
          />
          {pts.map((p) => (
            <circle key={`fee-${p.date}`} cx={p.x} cy={p.yFee} r="2.4" fill="hsl(var(--accent))" />
          ))}
          {pts.map((p, i) =>
            i % 2 === 0 ? (
              <text
                key={`t-${p.date}`}
                x={p.x}
                y={H - 10}
                textAnchor="middle"
                className="fill-muted-foreground"
                style={{ fontSize: 10 }}
              >
                {p.date.slice(5).replace('-', '/')}
              </text>
            ) : null,
          )}
          {hi ? (
            <line
              x1={hi.x}
              x2={hi.x}
              y1={pad.t}
              y2={pad.t + innerH}
              stroke="hsl(var(--accent))"
              strokeOpacity="0.55"
              strokeDasharray="3 4"
            />
          ) : null}
        </svg>
        {hi ? (
          <div className="pointer-events-none absolute right-2 top-0 rounded-md border border-border bg-popover/95 px-2.5 py-1.5 text-[11px] shadow-md backdrop-blur-sm">
            <div className="text-muted-foreground">{hi.date}</div>
            <div className="font-mono text-foreground">合计 {fmtTokens(hi.total)}</div>
            <div className="font-mono text-foreground">
              {fmtCny(hi.cost)} · 积分 {hi.credits}
            </div>
            <div className="font-mono text-muted-foreground">
              新输入 {fmtTokens(hi.fresh)} · 缓存 {fmtTokens(hi.cached)} · 输出 {fmtTokens(hi.output)}
            </div>
          </div>
        ) : null}
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full" style={{ background: TOKEN_TONE.cached.color }} />
          {TOKEN_TONE.cached.label}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full" style={{ background: TOKEN_TONE.fresh.color }} />
          {TOKEN_TONE.fresh.label}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full" style={{ background: TOKEN_TONE.output.color }} />
          {TOKEN_TONE.output.label}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-3 rounded-full bg-accent" />
          费用
        </span>
      </div>
    </ChartFrame>
  )
}

function CostTimeline({
  hours,
  last24h,
  last24hCost,
}: {
  hours: AdminProjectTokenHour[]
  last24h: number
  last24hCost: number
}) {
  const uid = useSvgUid()
  const [hover, setHover] = useState<number | null>(null)
  const W = 720
  const H = 200
  const pad = { t: 16, r: 52, b: 28, l: 44 }
  const innerW = W - pad.l - pad.r
  const innerH = H - pad.t - pad.b
  const series = hours.map((h) => ({
    ...h,
    total: h.input_tokens + h.output_tokens,
    cost: h.cost_micro_cny || 0,
    credits: h.credits || 0,
  }))
  const max = Math.max(1, ...series.map((d) => d.total))
  const maxCost = Math.max(1, ...series.map((d) => d.cost))
  const barW = series.length ? (innerW / series.length) * 0.62 : 8
  const pts = series.map((d, i) => {
    const x =
      pad.l +
      (series.length <= 1 ? innerW / 2 : (i / Math.max(1, series.length - 1)) * innerW)
    const barH = (d.total / max) * innerH
    return {
      ...d,
      x,
      y0: pad.t + innerH,
      barY: pad.t + innerH - barH,
      barH,
      yFee: pad.t + innerH - (d.cost / maxCost) * innerH,
    }
  })
  const hi = hover == null ? null : pts[hover]
  const feeLine = pts.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.yFee.toFixed(1)}`).join(' ')

  return (
    <ChartFrame
      title="近 24 小时时序"
      hint={
        <span>
          Token {fmtTokens(last24h)} · 费用 {fmtCny(last24hCost)}
        </span>
      }
      className="lg:col-span-2"
    >
      <div className="relative" onMouseLeave={() => setHover(null)}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="cockpit-draw h-[200px] w-full"
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect()
            const x = ((e.clientX - rect.left) / rect.width) * W
            let best = 0
            let dist = Infinity
            pts.forEach((p, i) => {
              const d = Math.abs(p.x - x)
              if (d < dist) {
                dist = d
                best = i
              }
            })
            setHover(best)
          }}
        >
          <GlowDefs id={uid} />
          {[0, 0.5, 1].map((lv) => {
            const y = pad.t + innerH * (1 - lv)
            return (
              <g key={lv}>
                <line
                  x1={pad.l}
                  x2={W - pad.r}
                  y1={y}
                  y2={y}
                  stroke="hsl(var(--secondary))"
                  strokeOpacity="0.12"
                />
                <text
                  x={pad.l - 8}
                  y={y + 3}
                  textAnchor="end"
                  className="fill-muted-foreground"
                  style={{ fontSize: 10, fontFamily: 'ui-monospace, monospace' }}
                >
                  {fmtTokens(max * lv)}
                </text>
                <text
                  x={W - pad.r + 8}
                  y={y + 3}
                  className="fill-muted-foreground"
                  style={{ fontSize: 10, fontFamily: 'ui-monospace, monospace' }}
                >
                  {fmtCny(maxCost * lv)}
                </text>
              </g>
            )
          })}
          {pts.map((p, i) => (
            <rect
              key={p.hour}
              x={p.x - barW / 2}
              y={p.barY}
              width={barW}
              height={Math.max(p.barH, p.total > 0 ? 2 : 0)}
              rx={2}
              fill="hsl(var(--secondary))"
              fillOpacity={hover === i ? 0.95 : 0.45}
            />
          ))}
          <path
            d={feeLine}
            fill="none"
            stroke="hsl(var(--accent))"
            strokeWidth="2.2"
            filter={`url(#${uid}-glow)`}
          />
          {pts.map((p) => (
            <circle key={`c-${p.hour}`} cx={p.x} cy={p.yFee} r="2.2" fill="hsl(var(--accent))" />
          ))}
          {pts.map((p, i) =>
            i % 3 === 0 ? (
              <text
                key={`l-${p.hour}`}
                x={p.x}
                y={H - 8}
                textAnchor="middle"
                className="fill-muted-foreground"
                style={{ fontSize: 10 }}
              >
                {p.hour.slice(11, 13)}:00
              </text>
            ) : null,
          )}
          {hi ? (
            <line
              x1={hi.x}
              x2={hi.x}
              y1={pad.t}
              y2={pad.t + innerH}
              stroke="hsl(var(--accent))"
              strokeOpacity="0.45"
              strokeDasharray="3 4"
            />
          ) : null}
        </svg>
        {hi ? (
          <div className="pointer-events-none absolute right-2 top-0 rounded-md border border-border bg-popover/95 px-2.5 py-1.5 text-[11px] shadow-md backdrop-blur-sm">
            <div className="text-muted-foreground">{hi.hour.replace('T', ' ').replace('Z', ' UTC')}</div>
            <div className="font-mono text-foreground">
              {fmtTokens(hi.total)} · {fmtCny(hi.cost)} · 积分 {hi.credits}
            </div>
          </div>
        ) : null}
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm bg-secondary/70" />
          Token
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-3 rounded-full bg-accent" />
          费用
        </span>
      </div>
    </ChartFrame>
  )
}

function TokenMix({
  fresh,
  cached,
  output,
  calls,
}: {
  fresh: number
  cached: number
  output: number
  calls: number
}) {
  const uid = useSvgUid()
  const slices = [
    { key: 'fresh', ...TOKEN_TONE.fresh, value: fresh },
    { key: 'cached', ...TOKEN_TONE.cached, value: cached },
    { key: 'output', ...TOKEN_TONE.output, value: output },
  ]
  const total = slices.reduce((s, it) => s + it.value, 0)
  const size = 200
  const cx = 100
  const cy = 100
  const r = 68
  const C = 2 * Math.PI * r
  let offset = 0

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-center sm:gap-8">
      <svg viewBox={`0 0 ${size} ${size}`} className="cockpit-draw h-[180px] w-[180px] shrink-0">
        <GlowDefs id={uid} />
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="hsl(var(--muted))" strokeWidth={18} />
        {total > 0
          ? slices.map((slice) => {
              if (slice.value <= 0) return null
              const gap = slices.filter((s) => s.value > 0).length > 1 ? 4 : 0
              const len = Math.max(0, (slice.value / total) * C - gap)
              const el = (
                <circle
                  key={slice.key}
                  cx={cx}
                  cy={cy}
                  r={r}
                  fill="none"
                  stroke={slice.color}
                  strokeWidth={18}
                  strokeDasharray={`${len} ${C - len}`}
                  strokeDashoffset={-offset}
                  transform={`rotate(-90 ${cx} ${cy})`}
                  filter={`url(#${uid}-glow)`}
                />
              )
              offset += len + gap
              return el
            })
          : null}
        <text
          x={cx}
          y={cy - 2}
          textAnchor="middle"
          fill="hsl(var(--foreground))"
          style={{ fontSize: 22, fontFamily: 'ui-monospace, monospace', fontWeight: 650 }}
        >
          {fmtTokens(total)}
        </text>
        <text
          x={cx}
          y={cy + 16}
          textAnchor="middle"
          fill="hsl(var(--muted-foreground))"
          style={{ fontSize: 10, letterSpacing: '0.12em' }}
        >
          TOKEN
        </text>
      </svg>
      <div className="w-full min-w-[150px] space-y-2.5 sm:w-auto">
        {slices.map((s) => (
          <div key={s.key} className="flex items-center justify-between gap-6 text-[12px]">
            <span className="flex items-center gap-2 text-muted-foreground">
              <span className="h-2 w-2 rounded-full" style={{ background: s.color, boxShadow: `0 0 8px ${s.color}` }} />
              {s.label}
            </span>
            <span className="font-mono tabular-nums text-foreground">{fmtTokens(s.value)}</span>
          </div>
        ))}
        <div className="flex items-center justify-between gap-6 border-t border-border/70 pt-2 text-[12px] text-muted-foreground">
          <span>计费轮次</span>
          <span className="font-mono tabular-nums text-foreground">{calls}</span>
        </div>
      </div>
    </div>
  )
}

function ModelBars({ items }: { items: AdminProjectTokenModel[] }) {
  const max = Math.max(1, ...items.map((m) => m.input_tokens + m.output_tokens))
  if (items.length === 0) {
    return <div className="py-10 text-center text-[12px] text-muted-foreground">还没有 Token 消耗记录</div>
  }
  return (
    <div className="space-y-3">
      {items.map((m) => {
        const total = m.input_tokens + m.output_tokens
        const pct = (total / max) * 100
        const label = m.model.length > 28 ? `${m.model.slice(0, 26)}…` : m.model
        return (
          <div key={m.model}>
            <div className="mb-1 flex items-center justify-between gap-2 text-[12px]">
              <span className="truncate text-foreground" title={m.model}>
                {label}
              </span>
              <span className="shrink-0 font-mono tabular-nums text-muted-foreground">
                {fmtTokens(total)} · {fmtCny(m.cost_micro_cny || 0)}
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-gradient-to-r from-primary via-secondary to-accent"
                style={{ width: `${Math.max(pct, total > 0 ? 4 : 0)}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function PolarOwners({
  owners,
}: {
  owners: { owner_id: string; username: string; display_name: string; projects: number }[]
}) {
  const uid = useSvgUid()
  const size = 340
  const cx = 170
  const cy = 170
  const inner = 36
  const maxLen = 78
  const maxV = Math.max(1, ...owners.map((o) => o.projects))
  const tones = ['hsl(var(--secondary))', 'hsl(var(--primary))', 'hsl(var(--accent))']

  if (owners.length === 0) {
    return <div className="py-10 text-center text-[12px] text-muted-foreground">暂无创建者数据</div>
  }

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="cockpit-draw mx-auto h-[260px] w-full max-w-[360px]">
      <GlowDefs id={uid} />
      {[0.33, 0.66, 1].map((lv) => (
        <circle
          key={lv}
          cx={cx}
          cy={cy}
          r={inner + maxLen * lv}
          fill="none"
          stroke="hsl(var(--secondary))"
          strokeOpacity={lv === 1 ? 0.22 : 0.1}
        />
      ))}
      {owners.map((o, i) => {
        const a = -Math.PI / 2 + (i / owners.length) * 2 * Math.PI
        const len = inner + (o.projects / maxV) * maxLen
        const x1 = cx + Math.cos(a) * inner
        const y1 = cy + Math.sin(a) * inner
        const x2 = cx + Math.cos(a) * len
        const y2 = cy + Math.sin(a) * len
        const lx = cx + Math.cos(a) * (inner + maxLen + 28)
        const ly = cy + Math.sin(a) * (inner + maxLen + 28)
        const raw = o.display_name || o.username || o.owner_id || '未归属'
        const name = raw.length > 6 ? `${raw.slice(0, 6)}…` : raw
        const anchor = Math.cos(a) > 0.2 ? 'start' : Math.cos(a) < -0.2 ? 'end' : 'middle'
        return (
          <g key={o.owner_id || raw}>
            <line
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={tones[i % tones.length]}
              strokeWidth="12"
              strokeLinecap="round"
              filter={`url(#${uid}-soft)`}
            />
            <text
              x={lx}
              y={ly}
              textAnchor={anchor}
              dominantBaseline="middle"
              fill="hsl(var(--foreground))"
              style={{ fontSize: 11 }}
            >
              {name} {o.projects}
            </text>
          </g>
        )
      })}
      <circle cx={cx} cy={cy} r="24" fill="hsl(var(--card))" stroke="hsl(var(--secondary))" strokeOpacity="0.35" />
      <text
        x={cx}
        y={cy + 4}
        textAnchor="middle"
        fill="hsl(var(--foreground))"
        style={{ fontSize: 14, fontFamily: 'ui-monospace, monospace', fontWeight: 650 }}
      >
        {owners.length}
      </text>
    </svg>
  )
}

function VisibilitySplit({ privateCount, marketCount }: { privateCount: number; marketCount: number }) {
  const uid = useSvgUid()
  const total = Math.max(1, privateCount + marketCount)
  const privPct = privateCount / total
  const r = 54
  const C = Math.PI * r
  const W = 220
  const H = 120
  const cx = 110
  const cy = 92

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="cockpit-draw mx-auto h-[120px] w-full max-w-[260px]">
      <GlowDefs id={uid} />
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none"
        stroke="hsl(var(--muted))"
        strokeWidth="14"
        strokeLinecap="round"
      />
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none"
        stroke="hsl(var(--primary))"
        strokeWidth="14"
        strokeDasharray={`${privPct * C} ${C}`}
        strokeLinecap="butt"
        filter={`url(#${uid}-glow)`}
      />
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none"
        stroke="hsl(var(--accent))"
        strokeWidth="14"
        strokeDasharray={`${(1 - privPct) * C} ${C}`}
        strokeDashoffset={-privPct * C}
        strokeLinecap="butt"
      />
      <text
        x={cx}
        y={cy - 10}
        textAnchor="middle"
        className="fill-foreground"
        style={{ fontSize: 20, fontFamily: 'ui-monospace, monospace', fontWeight: 650 }}
      >
        {Math.round(privPct * 100)}%
      </text>
      <text
        x={cx}
        y={cy + 8}
        textAnchor="middle"
        className="fill-muted-foreground"
        style={{ fontSize: 10 }}
      >
        私有占比
      </text>
    </svg>
  )
}

function ActivityField({ projects }: { projects: CockpitProject[] }) {
  const uid = useSvgUid()
  const nav = useNavigate()
  const [tip, setTip] = useState<{
    name: string
    x: number
    y: number
    sessions: number
    messages: number
    tokens: number
    cost: number
    running: boolean
  } | null>(null)

  const W = 420
  const H = 260
  const pad = { t: 18, r: 18, b: 36, l: 42 }
  const innerW = W - pad.l - pad.r
  const innerH = H - pad.t - pad.b
  const maxS = Math.max(0, ...projects.map((p) => p.session_count))
  const maxM = Math.max(0, ...projects.map((p) => p.message_count))
  const useLogS = maxS > 8
  const useLogM = maxM > 8

  const norm = (v: number, max: number, log: boolean) => {
    if (max <= 0) return 0
    return log ? Math.log1p(v) / Math.log1p(max) : v / max
  }

  const emptyLoad = maxS <= 0 && maxM <= 0
  const dots = projects.map((p, i) => {
    let h = 0
    for (const c of p.id) h = (h * 31 + c.charCodeAt(0)) >>> 0
    const jitterX = ((h % 7) - 3) * 1.2
    const jitterY = (((h >> 3) % 7) - 3) * 1.2
    let x: number
    let y: number
    if (emptyLoad) {
      const a = -Math.PI / 2 + (i / Math.max(1, projects.length)) * 2 * Math.PI
      const rr = Math.min(innerW, innerH) * 0.32
      x = pad.l + innerW / 2 + Math.cos(a) * rr
      y = pad.t + innerH / 2 + Math.sin(a) * rr
    } else {
      x = pad.l + norm(p.session_count, maxS, useLogS) * innerW + jitterX
      y = pad.t + innerH - norm(p.message_count, maxM, useLogM) * innerH + jitterY
    }
    const color = p.running
      ? 'hsl(var(--secondary))'
      : p.status === 'paused'
        ? STATUS.paused.color
        : p.status === 'frozen'
          ? STATUS.frozen.color
          : STATUS.active.color
    const tok = (p.input_tokens || 0) + (p.output_tokens || 0)
    return { p, x, y, color, r: (p.running ? 6 : 4) + Math.min(8, Math.sqrt(tok) / 40), tokens: tok }
  })

  if (projects.length === 0) {
    return <div className="py-10 text-center text-[12px] text-muted-foreground">当前实例还没有网页项目</div>
  }

  return (
    <div className="relative" onMouseLeave={() => setTip(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} className="cockpit-draw h-[240px] w-full">
        <GlowDefs id={uid} />
        <line
          x1={pad.l}
          y1={pad.t + innerH}
          x2={W - pad.r}
          y2={pad.t + innerH}
          stroke="hsl(var(--secondary))"
          strokeOpacity="0.25"
        />
        <line
          x1={pad.l}
          y1={pad.t}
          x2={pad.l}
          y2={pad.t + innerH}
          stroke="hsl(var(--secondary))"
          strokeOpacity="0.25"
        />
        <text
          x={W / 2}
          y={H - 8}
          textAnchor="middle"
          className="fill-muted-foreground"
          style={{ fontSize: 10 }}
        >
          {emptyLoad ? '尚无会话，按项目排布' : `会话数${useLogS ? '（对数）' : ''}`}
        </text>
        {emptyLoad ? null : (
          <text
            x={14}
            y={H / 2}
            textAnchor="middle"
            className="fill-muted-foreground"
            style={{ fontSize: 10 }}
            transform={`rotate(-90 14 ${H / 2})`}
          >
            消息数{useLogM ? '（对数）' : ''}
          </text>
        )}
        {dots.map((d) => (
          <g key={d.p.id}>
            <circle
              cx={d.x}
              cy={d.y}
              r={14}
              fill="transparent"
              className="cursor-pointer"
              onMouseEnter={() =>
                setTip({
                  name: d.p.name,
                  x: d.x,
                  y: d.y,
                  sessions: d.p.session_count,
                  messages: d.p.message_count,
                  tokens: d.tokens,
                  cost: d.p.cost_micro_cny || 0,
                  running: d.p.running,
                })
              }
              onClick={() => nav(`/chat/${d.p.id}`)}
            />
            <circle
              cx={d.x}
              cy={d.y}
              r={d.r}
              fill={d.color}
              fillOpacity="0.9"
              filter={d.p.running ? `url(#${uid}-glow)` : undefined}
              pointerEvents="none"
            />
          </g>
        ))}
      </svg>
      {tip ? (
        <div
          className="pointer-events-none absolute z-10 max-w-[200px] rounded-md border border-border bg-popover/95 px-2.5 py-1.5 text-[11px] shadow-md backdrop-blur-sm"
          style={{
            left: `${(tip.x / W) * 100}%`,
            top: `${(tip.y / H) * 100}%`,
            transform: 'translate(10px, -120%)',
          }}
        >
          <div className="truncate font-medium text-foreground">{tip.name}</div>
          <div className="mt-0.5 font-mono text-muted-foreground">
            会话 {tip.sessions} · 消息 {tip.messages} · Token {fmtTokens(tip.tokens)} · {fmtCny(tip.cost)}
            {tip.running ? ' · 运行中' : ''}
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default function ProjectCockpit({
  data,
  isLoading,
}: {
  data?: AdminProjectStats
  isLoading: boolean
}) {
  const t = data?.totals

  const radarAxes = useMemo(() => {
    if (!t) return []
    const p = Math.max(1, t.projects)
    return [
      { label: '健康度', value: (t.active / p) * 100 },
      { label: '在跑率', value: (t.running_projects / p) * 100 },
      { label: '新增动能', value: Math.min(100, (t.created_7d / p) * 400) },
      { label: '会话密度', value: Math.min(100, (t.sessions / p) * 12.5) },
      { label: '24h 活跃', value: (t.active_24h / p) * 100 },
    ]
  }, [t])

  if (isLoading && !data) {
    return (
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-36 w-full rounded-xl" />
        ))}
      </div>
    )
  }

  if (!data || !t) return null

  const tok = data.tokens

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
        <HudMetric label="项目总数" value={t.projects} hint="不含 CLI 本地工作区" />
        <HudMetric
          label="运行中"
          value={t.running_projects}
          hint={`${t.running_sessions} 条会话在推理`}
        />
        <HudMetric label="会话 / 消息" value={`${t.sessions} / ${t.messages}`} hint="全实例累计" />
        <HudMetric
          label="Token 消耗"
          value={fmtTokens(tok?.total_tokens ?? 0)}
          hint={`in ${fmtTokens(tok?.input_tokens ?? 0)} / out ${fmtTokens(tok?.output_tokens ?? 0)}`}
        />
        <HudMetric
          label="对应费用"
          value={fmtCny(tok?.cost_micro_cny ?? 0)}
          hint={`积分 ${tok?.credits ?? 0} · 24h ${fmtCny(tok?.last_24h_cost_micro_cny ?? 0)}`}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <ChartFrame title="状态环" hint="外环状态 · 内环运行占比">
          <StatusDonut
            active={t.active}
            paused={t.paused}
            frozen={t.frozen}
            running={t.running_projects}
            total={t.projects}
          />
          <div className="mt-4 border-t border-border/70 pt-3">
            <div className="mb-1 flex items-center justify-between text-[11px] text-muted-foreground">
              <span>可见性</span>
              <span>
                私有 {data.by_visibility.private ?? 0} · 市场 {data.by_visibility.market ?? 0}
              </span>
            </div>
            <VisibilitySplit
              privateCount={data.by_visibility.private ?? 0}
              marketCount={data.by_visibility.market ?? 0}
            />
          </div>
        </ChartFrame>
        <ChartFrame title="态势雷达" hint="相对全集群归一化">
          <RadarChart axes={radarAxes} />
        </ChartFrame>
        <AreaTrend
          days={data.created_last_14d}
          created7={t.created_7d}
          created30={t.created_30d}
          active24h={t.active_24h}
        />
        <TokenTrend
          days={tok?.last_14d ?? []}
          last7={tok?.last_7d ?? 0}
          last24h={tok?.last_24h ?? 0}
          last7Cost={tok?.last_7d_cost_micro_cny ?? 0}
        />
        <CostTimeline
          hours={tok?.last_24h_hourly ?? []}
          last24h={tok?.last_24h ?? 0}
          last24hCost={tok?.last_24h_cost_micro_cny ?? 0}
        />
        <ChartFrame title="Token 构成" hint="新输入不含缓存命中">
          <TokenMix
            fresh={tok?.fresh_input_tokens ?? 0}
            cached={tok?.cached_input_tokens ?? 0}
            output={tok?.output_tokens ?? 0}
            calls={tok?.calls ?? 0}
          />
        </ChartFrame>
        <ChartFrame title="模型消耗" hint="按 Token 合计 · 含对应费用">
          <ModelBars items={tok?.by_model ?? []} />
        </ChartFrame>
        <ChartFrame title="创建者星图" hint={`共 ${t.owners} 人`}>
          <PolarOwners owners={data.by_owner} />
        </ChartFrame>
        <ChartFrame title="会话载荷场" hint="点越大 Token 越多 · 点击进入对话">
          <ActivityField projects={data.projects} />
        </ChartFrame>
      </div>
    </div>
  )
}

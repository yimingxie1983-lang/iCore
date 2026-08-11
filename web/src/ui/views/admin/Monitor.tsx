

import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  Cpu,
  Database,
  Gauge,
  HardDrive,
  MemoryStick,
  Network,
  RefreshCw,
  Server,
  Users,
} from 'lucide-react'

import { api, type SystemMetrics } from '@/client/services/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/ui/widgets/ui/card'
import { Progress } from '@/ui/widgets/ui/progress'
import { Badge } from '@/ui/widgets/ui/badge'
import { cn } from '@/shared/foundation/utils'

const POLL_MS = 2000
const HISTORY_LEN = 45

function fmtBytes(n?: number | null): string {
  if (n == null) return '—'
  if (n <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)))
  return `${(n / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function fmtRate(n?: number | null): string {
  if (n == null) return '—'
  return `${fmtBytes(n)}/s`
}

function fmtUptime(sec?: number | null): string {
  if (sec == null) return '—'
  const s = Math.floor(sec)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (d > 0) return `${d}天 ${h}小时`
  if (h > 0) return `${h}小时 ${m}分`
  if (m > 0) return `${m}分 ${s % 60}秒`
  return `${s}秒`
}

function usageTone(pct: number): string {
  if (pct >= 90) return 'text-destructive'
  if (pct >= 70) return 'text-amber-600'
  return 'text-emerald-600'
}

function barTone(pct: number): string {
  if (pct >= 90) return 'bg-destructive'
  if (pct >= 70) return 'bg-amber-500'
  return 'bg-emerald-500'
}

function Sparkline({ data, tone }: { data: number[]; tone: string }) {
  return (
    <div className="flex h-12 items-end gap-[2px]">
      {Array.from({ length: HISTORY_LEN }).map((_, i) => {
        const v = data[data.length - HISTORY_LEN + i]
        const h = v == null ? 0 : Math.max(2, Math.min(100, v))
        return (
          <div
            key={i}
            className={cn('flex-1 rounded-sm transition-all', v == null ? 'bg-muted' : tone)}
            style={{ height: `${h}%`, opacity: v == null ? 0.3 : 1 }}
          />
        )
      })}
    </div>
  )
}

function StatCard({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  children: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2 space-y-0 pb-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <CardTitle className="text-[13px] font-semibold">{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

function BigMetric({ value, unit, tone }: { value: string; unit?: string; tone?: string }) {
  return (
    <div className="flex items-baseline gap-1">
      <span className={cn('font-mono text-3xl font-semibold tabular-nums', tone)}>{value}</span>
      {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
    </div>
  )
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between text-[12px]">
      <span className="text-muted-foreground">{k}</span>
      <span className="font-mono text-foreground">{v}</span>
    </div>
  )
}

function ServiceBadge({ name, state }: { name: string; state?: string }) {
  const ok = state === 'ok'
  return (
    <div className="flex items-center justify-between rounded-md border border-border bg-muted/30 px-3 py-2">
      <span className="text-[12px] font-medium text-foreground">{name}</span>
      <span
        className={cn(
          'inline-flex items-center gap-1.5 text-[11px] font-medium',
          ok ? 'text-emerald-600' : 'text-destructive',
        )}
        title={state}
      >
        <span className={cn('h-1.5 w-1.5 rounded-full', ok ? 'bg-emerald-500' : 'bg-destructive')} />
        {ok ? '正常' : '异常'}
      </span>
    </div>
  )
}

export default function AdminMonitor() {
  const { data, isError, error, isLoading, dataUpdatedAt } = useQuery<SystemMetrics>({
    queryKey: ['system-metrics'],
    queryFn: () => api.systemMetrics(),
    refetchInterval: POLL_MS,
    retry: 0,
  })

  const [cpuHist, setCpuHist] = useState<number[]>([])
  const [memHist, setMemHist] = useState<number[]>([])
  const lastTs = useRef(0)

  useEffect(() => {
    if (!data || data.timestamp === lastTs.current) return
    lastTs.current = data.timestamp
    const cpu = data.system.cpu?.percent
    const mem = data.system.memory?.percent
    if (cpu != null) setCpuHist((h) => [...h, cpu].slice(-HISTORY_LEN))
    if (mem != null) setMemHist((h) => [...h, mem].slice(-HISTORY_LEN))
  }, [data])

  const sys = data?.system
  const cpuPct = sys?.cpu?.percent ?? 0
  const memPct = sys?.memory?.percent ?? 0
  const diskPct = sys?.disk?.percent ?? 0
  const rate = data?.app.request_rate

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl space-y-4 p-6">
        {}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Gauge className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold text-foreground">系统监控</h2>
          </div>
          <div className="flex-1" />
          {data && (
            <>
              <Badge variant="outline" className="gap-1.5 font-normal">
                <Server className="h-3 w-3" />
                {data.services.backend === 'postgres' ? 'PostgreSQL' : 'SQLite'}
                {data.services.multi_worker ? ' · 多 worker' : ' · 单进程'}
              </Badge>
              <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <RefreshCw className={cn('h-3 w-3', !isError && 'animate-spin [animation-duration:2s]')} />
                {new Date(dataUpdatedAt).toLocaleTimeString('zh-CN')} · 每 {POLL_MS / 1000}s 刷新
              </span>
            </>
          )}
        </div>

        {isError && (
          <Card className="border-destructive/30 bg-destructive/[0.04]">
            <CardContent className="py-4 text-[13px] text-destructive">
              指标获取失败：{(error as Error)?.message || '请稍后重试'}
            </CardContent>
          </Card>
        )}

        {isLoading && !data && (
          <Card>
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              正在采集资源指标…
            </CardContent>
          </Card>
        )}

        {sys && sys.available === false && (
          <Card className="border-amber-500/30 bg-amber-500/[0.05]">
            <CardContent className="py-4 text-[13px] text-amber-700">
              后端未安装 psutil，主机资源指标不可用（服务健康 / 会话 / 请求速率仍正常）。
            </CardContent>
          </Card>
        )}

        {data && (
          <>
            {}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              {}
              <StatCard icon={Cpu} title="CPU">
                <BigMetric value={cpuPct.toFixed(1)} unit="%" tone={usageTone(cpuPct)} />
                <Progress value={cpuPct} className="my-2 h-1.5" />
                <Sparkline data={cpuHist} tone={barTone(cpuPct)} />
                <div className="mt-2 space-y-1">
                  <KV k="核心数" v={sys?.cpu?.cores ?? '—'} />
                  {sys?.cpu?.load_avg?.[0] != null && (
                    <KV
                      k="负载 (1/5/15m)"
                      v={sys.cpu.load_avg
                        .map((x) => (x == null ? '—' : x.toFixed(2)))
                        .join(' / ')}
                    />
                  )}
                </div>
                {sys?.cpu?.per_core && sys.cpu.per_core.length > 1 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {sys.cpu.per_core.map((c, i) => (
                      <span
                        key={i}
                        title={`核 ${i}: ${c}%`}
                        className={cn(
                          'h-4 w-4 rounded-sm text-[8px] leading-4 text-center text-white',
                          barTone(c),
                        )}
                        style={{ opacity: 0.35 + (c / 100) * 0.65 }}
                      />
                    ))}
                  </div>
                )}
              </StatCard>

              {}
              <StatCard icon={MemoryStick} title="内存">
                <BigMetric value={memPct.toFixed(1)} unit="%" tone={usageTone(memPct)} />
                <Progress value={memPct} className="my-2 h-1.5" />
                <Sparkline data={memHist} tone={barTone(memPct)} />
                <div className="mt-2 space-y-1">
                  <KV k="已用" v={fmtBytes(sys?.memory?.used)} />
                  <KV k="可用" v={fmtBytes(sys?.memory?.available)} />
                  <KV k="总量" v={fmtBytes(sys?.memory?.total)} />
                </div>
              </StatCard>

              {}
              <StatCard icon={HardDrive} title="磁盘（数据盘）">
                <BigMetric value={diskPct.toFixed(1)} unit="%" tone={usageTone(diskPct)} />
                <Progress value={diskPct} className="my-2 h-1.5" />
                <div className="mt-2 space-y-1">
                  <KV k="已用" v={fmtBytes(sys?.disk?.used)} />
                  <KV k="剩余" v={fmtBytes(sys?.disk?.free)} />
                  <KV k="总量" v={fmtBytes(sys?.disk?.total)} />
                </div>
                <p className="mt-2 truncate text-[10px] text-muted-foreground" title={sys?.disk?.path}>
                  {sys?.disk?.path}
                </p>
              </StatCard>

              {}
              <StatCard icon={Network} title="网络">
                <div className="space-y-2">
                  <div>
                    <div className="text-[11px] text-muted-foreground">↑ 上行速率</div>
                    <div className="font-mono text-lg font-semibold text-sky-600">
                      {fmtRate(sys?.network?.sent_rate)}
                    </div>
                  </div>
                  <div>
                    <div className="text-[11px] text-muted-foreground">↓ 下行速率</div>
                    <div className="font-mono text-lg font-semibold text-violet-600">
                      {fmtRate(sys?.network?.recv_rate)}
                    </div>
                  </div>
                </div>
                <div className="mt-2 space-y-1 border-t border-border pt-2">
                  <KV k="累计发送" v={fmtBytes(sys?.network?.bytes_sent)} />
                  <KV k="累计接收" v={fmtBytes(sys?.network?.bytes_recv)} />
                </div>
              </StatCard>
            </div>

            {}
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              {}
              <StatCard icon={Database} title="服务健康">
                <div className="mb-3 flex items-center gap-2">
                  <span
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium',
                      data.services.status === 'healthy'
                        ? 'border-emerald-500/30 bg-emerald-500/[0.08] text-emerald-700'
                        : 'border-amber-500/30 bg-amber-500/[0.08] text-amber-700',
                    )}
                  >
                    {data.services.status === 'healthy' ? '全部正常' : '存在降级'}
                  </span>
                </div>
                <div className="space-y-2">
                  <ServiceBadge name="PostgreSQL / DB" state={data.services.components.database} />
                  {'redis' in data.services.components && (
                    <ServiceBadge name="Redis" state={data.services.components.redis} />
                  )}
                </div>
              </StatCard>

              {}
              <StatCard icon={Activity} title="请求速率">
                <BigMetric
                  value={rate ? rate.per_sec_avg.toFixed(1) : '—'}
                  unit={rate ? 'req/s 均值' : ''}
                />
                <div className="mt-2 space-y-1">
                  <KV k="上一秒" v={rate ? `${rate.last_sec} req` : '—'} />
                  <KV k={`${rate?.window ?? 60}s 峰值`} v={rate ? `${rate.peak_sec} req/s` : '—'} />
                </div>
                {!rate && (
                  <p className="mt-2 text-[10px] text-muted-foreground">
                    未配置 Redis，跨 worker 请求速率不可用。
                  </p>
                )}
              </StatCard>

              {}
              <StatCard icon={Users} title="应用运行态">
                <div className="flex items-baseline gap-2">
                  <BigMetric value={String(data.app.active_sessions ?? '—')} unit="活跃会话" />
                </div>
                <div className="mt-2 space-y-1">
                  <KV k="版本" v={data.app.version} />
                  <KV k="Worker 进程" v={`PID ${data.app.worker_pid}`} />
                  {data.app.configured_workers != null && (
                    <KV k="Worker 数" v={data.app.configured_workers} />
                  )}
                  {sys?.process?.threads != null && (
                    <KV k="本进程线程" v={sys.process.threads} />
                  )}
                  {sys?.process?.rss != null && (
                    <KV k="本进程内存" v={fmtBytes(sys.process.rss)} />
                  )}
                  <KV k="Worker 运行" v={fmtUptime(data.app.worker_uptime_seconds)} />
                </div>
              </StatCard>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

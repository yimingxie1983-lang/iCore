import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  CalendarClock,
  FlaskConical,
  FolderOpen,
  Microscope,
  Newspaper,
  Stethoscope,
} from 'lucide-react'

import { api, type Project } from '@/client/services/client'
import { useAuthStore } from '@/application/state/authStore'
import { cn } from '@/shared/foundation/utils'

const SCENARIOS = [
  {
    key: 'clinical-trial',
    title: '临床试验',
    desc: '方案设计 / 入排筛选 / 数据管理',
    icon: CalendarClock,
    accent: 'bg-sky-500/10 text-sky-600 dark:text-sky-400',
  },
  {
    key: 'basic-research',
    title: '基础研究',
    desc: '文献综述 / 实验设计 / 数据分析',
    icon: FlaskConical,
    accent: 'bg-violet-500/10 text-violet-600 dark:text-violet-400',
  },
  {
    key: 'clinical-care',
    title: '临床诊疗',
    desc: '辅助诊断 / 病历质控 / 随访管理',
    icon: Stethoscope,
    accent: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  },
]

function relTime(iso: string): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
  const m = Math.floor(diff / 60000)
  if (m < 60) return `${Math.max(m, 1)} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  return `${Math.floor(h / 24)} 天前`
}

export default function Dashboard() {
  const nav = useNavigate()
  const user = useAuthStore((s) => s.user)

  const { data: projectData } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.listProjects(),
    staleTime: 15_000,
  })
  const { data: insights } = useQuery({
    queryKey: ['insights', '', ''],
    queryFn: () => api.listInsights({ limit: 3 }),
    staleTime: 60_000,
  })

  const projects = (projectData?.items || [])
    .filter((p: Project) => Boolean(user?.id) && p.owner_id === user?.id)
    .slice()
    .sort((a: Project, b: Project) =>
      String(b.updated_at || '').localeCompare(String(a.updated_at || '')),
    )
    .slice(0, 4)

  const hour = new Date().getHours()
  const greeting = hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好'
  const today = new Date().toLocaleDateString('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  })

  return (
    <div className="h-full min-h-0 overflow-y-auto p-6">
      <div className="mb-6">
        <h1 className="text-lg font-semibold tracking-tight text-foreground">
          {greeting}，{user?.display_name || user?.username || '医生'}
        </h1>
        <p className="mt-1 text-[12.5px] text-muted-foreground">
          {today} · 今天想推进哪类工作？
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        {SCENARIOS.map((s) => {
          const Icon = s.icon
          return (
            <button
              key={s.key}
              type="button"
              onClick={() => nav('/projects/new')}
              className="group surface-card surface-card-hover flex items-start gap-3 rounded-xl p-4 text-left transition-all hover:border-secondary/40"
            >
              <div
                className={cn(
                  'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
                  s.accent,
                )}
              >
                <Icon className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-foreground">{s.title}</div>
                <div className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
                  {s.desc}
                </div>
              </div>
              <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-secondary" />
            </button>
          )
        })}
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-3">
        <section className="xl:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <FolderOpen className="h-4 w-4 text-secondary" />
              最近项目
            </h2>
            <button
              type="button"
              onClick={() => nav('/projects')}
              className="text-[12px] text-muted-foreground transition-colors hover:text-foreground"
            >
              全部项目 →
            </button>
          </div>
          {projects.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-10 text-muted-foreground">
              <Microscope className="mb-2 h-7 w-7 opacity-40" />
              <p className="text-[13px]">还没有项目</p>
              <button
                type="button"
                onClick={() => nav('/projects/new')}
                className="mt-2 text-[12.5px] font-medium text-primary hover:underline"
              >
                新建第一个科研项目 →
              </button>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {projects.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => nav(`/chat/${p.id}`)}
                  className="group surface-card surface-card-hover rounded-xl p-4 text-left transition-all hover:border-secondary/40"
                >
                  <div className="truncate text-sm font-semibold text-foreground">{p.name}</div>
                  <div className="mt-1 line-clamp-2 text-[12px] text-muted-foreground">
                    {p.description || '—'}
                  </div>
                  <div className="mt-2 text-[11px] text-muted-foreground">
                    {p.updated_at ? `更新于 ${relTime(p.updated_at)}` : ''}
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>

        <section>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Newspaper className="h-4 w-4 text-secondary" />
              行业资讯精选
            </h2>
            <button
              type="button"
              onClick={() => nav('/insights')}
              className="text-[12px] text-muted-foreground transition-colors hover:text-foreground"
            >
              查看全部 →
            </button>
          </div>
          <div className="space-y-3">
            {(insights?.items || []).map((it) => (
              <button
                key={it.id}
                type="button"
                onClick={() => nav('/insights')}
                className="surface-card surface-card-hover w-full rounded-xl p-3 text-left transition-all hover:border-secondary/40"
              >
                <div className="line-clamp-2 text-[13px] font-semibold leading-snug text-foreground">
                  {it.title}
                </div>
                <div className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-muted-foreground">
                  {it.summary}
                </div>
                <div className="mt-1.5 truncate text-[11px] text-muted-foreground">
                  {it.source} · {relTime(it.published_at)}
                </div>
              </button>
            ))}
            {(insights?.items || []).length === 0 && (
              <div className="rounded-xl border border-dashed border-border py-8 text-center text-[12px] text-muted-foreground">
                暂无资讯
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}

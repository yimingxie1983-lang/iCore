

import {
  BookOpen,
  BrainCircuit,
  Clock3,
  Cpu,
  Database,
  FileCode,
  FileText,
  FolderTree,
  History,
  Layers,
  NotebookPen,
  Sparkles,
  User,
} from 'lucide-react'

import { Badge } from '@/ui/widgets/ui/badge'
import { Separator } from '@/ui/widgets/ui/separator'

import PageHeader from '@/ui/widgets/common/PageHeader'
import StatCard from '@/ui/widgets/common/StatCard'
import { cn } from '@/shared/foundation/utils'

interface MemFile {
  name: string
  tag: string
  note: string
  source: 'human' | 'auto'
}
interface MemLayer {
  icon: React.ComponentType<{ className?: string }>
  title: string
  path: string
  desc: string
  tone: 'primary' | 'secondary' | 'accent' | 'success'
  files: MemFile[]
}

const LAYERS: MemLayer[] = [
  {
    icon: FolderTree,
    title: '项目记忆',
    path: 'projects/{project_id}/memory/',
    desc: '本项目特有的「决策 / 事实 / 待办」，跨任务复用',
    tone: 'primary',
    files: [
      { name: 'MEMORY.md', tag: '核心', source: 'human', note: '人手写，每次对话都会注入到上下文' },
      { name: 'digests/', tag: '摘要', source: 'auto', note: '进化链自动生成的每日任务摘要' },
    ],
  },
  {
    icon: NotebookPen,
    title: '智能体经验簿',
    path: 'agents/{agent_id}/memory/',
    desc: '智能体跨项目积累的第一人称经验（"我学到了什么"）',
    tone: 'secondary',
    files: [
      { name: 'digests/', tag: '经验', source: 'auto', note: '每次任务结束后追加第一人称记录' },
    ],
  },
  {
    icon: Layers,
    title: '工作区文档',
    path: 'projects/{project_id}/workspace/',
    desc: '智能体产出的代码 / 报告 / PLAN.md 等业务交付物',
    tone: 'success',
    files: [
      { name: 'PLAN.md', tag: '计划', source: 'auto', note: 'Plan Mode 产出，任务级真相源' },
      { name: 'docs/plans/', tag: '归档', source: 'auto', note: '任务完成时按日期归档' },
    ],
  },
  {
    icon: BookOpen,
    title: 'Craft 方法论库',
    path: 'cancer_claw/resources/knowledge/playbooks/',
    desc: 'AI 方法论 / 领域知识包；按需 activate 才注入上下文，节省 token',
    tone: 'accent',
    files: [
      { name: 'craft_hpo_downloader.md', tag: '医学', source: 'human', note: 'HPO 表型本体下载与查询' },
      { name: 'craft_omics_data_sources.md', tag: '医学', source: 'human', note: '组学公开数据源目录' },
    ],
  },
]

const TONE_BG: Record<MemLayer['tone'], string> = {
  primary: 'bg-primary/[0.08] text-primary',
  secondary: 'bg-secondary/[0.12] text-secondary',
  accent: 'bg-accent/[0.14] text-accent',
  success: 'bg-emerald-500/[0.12] text-emerald-700',
}

const TONE_RING: Record<MemLayer['tone'], string> = {
  primary: 'ring-primary/15',
  secondary: 'ring-secondary/20',
  accent: 'ring-accent/20',
  success: 'ring-emerald-500/20',
}

function LayerCard({ layer }: { layer: MemLayer }) {
  const Icon = layer.icon
  return (
    <div className="surface-card surface-card-hover flex flex-col rounded-xl">
      <div className="flex items-start gap-3 p-5">
        <div
          className={cn(
            'flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ring-1',
            TONE_BG[layer.tone],
            TONE_RING[layer.tone],
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-[15px] font-semibold tracking-tight">{layer.title}</h3>
          <div className="mt-0.5 break-all font-mono text-[11px] text-muted-foreground">
            {layer.path}
          </div>
          <p className="mt-2 text-[12.5px] leading-relaxed text-muted-foreground">
            {layer.desc}
          </p>
        </div>
      </div>
      <Separator />
      <div className="space-y-1.5 p-4">
        {layer.files.map((f) => (
          <div
            key={f.name}
            className="flex flex-wrap items-center gap-2 rounded-md bg-muted/40 px-2.5 py-1.5"
          >
            {f.name.endsWith('/') ? (
              <FolderTree className="h-3.5 w-3.5 text-muted-foreground" />
            ) : (
              <FileText className="h-3.5 w-3.5 text-muted-foreground" />
            )}
            <code className="min-w-[160px] font-mono text-[11.5px]">{f.name}</code>
            <Badge variant="outline" className="h-4 px-1.5 text-[10px] font-normal">
              {f.tag}
            </Badge>
            <Badge
              variant={f.source === 'human' ? 'muted' : 'success'}
              className="h-4 px-1.5 text-[10px] font-normal"
            >
              {f.source === 'human' ? (
                <>
                  <User className="mr-0.5 h-2.5 w-2.5" />
                  人写
                </>
              ) : (
                <>
                  <Sparkles className="mr-0.5 h-2.5 w-2.5" />
                  自动
                </>
              )}
            </Badge>
            <span className="ml-auto text-[11px] text-muted-foreground">{f.note}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function MemoryFlow() {
  return (
    <div className="surface-card relative overflow-hidden rounded-2xl">
      <div className="grid grid-cols-1 gap-0 lg:grid-cols-[1fr_2fr_1fr]">
        {}
        <div className="border-b border-border bg-card-muted p-5 lg:border-b-0 lg:border-r">
          <div className="mb-3 flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/[0.12] text-emerald-700">
              <NotebookPen className="h-4 w-4" />
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                写入
              </div>
              <div className="text-[14px] font-semibold">任务结束后</div>
            </div>
          </div>
          <ul className="space-y-1.5 text-[12px] text-muted-foreground">
            <li className="flex gap-1.5">
              <span className="text-emerald-700">·</span>
              进化链分析对话历史
            </li>
            <li className="flex gap-1.5">
              <span className="text-emerald-700">·</span>
              提炼项目级事实 / 决策
            </li>
            <li className="flex gap-1.5">
              <span className="text-emerald-700">·</span>
              追加智能体第一人称经验
            </li>
            <li className="flex gap-1.5">
              <span className="text-emerald-700">·</span>
              归档 PLAN / 报告到 docs
            </li>
          </ul>
        </div>

        {}
        <div className="p-5">
          <div className="mb-3 flex items-center gap-2">
            <Database className="h-4 w-4 text-primary" />
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
              四层分级存储
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {LAYERS.map((l) => {
              const Icon = l.icon
              return (
                <div
                  key={l.title}
                  className="flex items-center gap-2 rounded-md bg-card px-2.5 py-2 ring-1 ring-border"
                >
                  <div
                    className={cn(
                      'flex h-6 w-6 shrink-0 items-center justify-center rounded',
                      TONE_BG[l.tone],
                    )}
                  >
                    <Icon className="h-3 w-3" />
                  </div>
                  <span className="truncate text-[12px] font-medium">{l.title}</span>
                </div>
              )
            })}
          </div>
        </div>

        {}
        <div className="border-t border-border bg-card-muted p-5 lg:border-l lg:border-t-0">
          <div className="mb-3 flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/[0.10] text-primary">
              <Cpu className="h-4 w-4" />
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                读取
              </div>
              <div className="text-[14px] font-semibold">每次对话开始</div>
            </div>
          </div>
          <ul className="space-y-1.5 text-[12px] text-muted-foreground">
            <li className="flex gap-1.5">
              <span className="text-primary">·</span>
              注入项目 MEMORY.md
            </li>
            <li className="flex gap-1.5">
              <span className="text-primary">·</span>
              智能体最近 N 条经验
            </li>
            <li className="flex gap-1.5">
              <span className="text-primary">·</span>
              按需激活 craft（节省 token）
            </li>
            <li className="flex gap-1.5">
              <span className="text-primary">·</span>
              cache-safe compaction
            </li>
          </ul>
        </div>
      </div>
    </div>
  )
}

function RecentDigestsPlaceholder() {
  return (
    <div className="surface-card rounded-xl">
      <div className="flex items-center justify-between border-b border-border p-4">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-secondary" />
          <h3 className="text-sm font-semibold">最近沉淀</h3>
          <Badge variant="muted" className="h-4 px-1.5 text-[10px] font-normal">
            v0.2 接入
          </Badge>
        </div>
        <span className="text-[11px] text-muted-foreground">
          自动从进化链拉取最新摘要
        </span>
      </div>
      <div className="divide-y divide-border">
        {[
          {
            scope: '项目记忆',
            tone: 'primary' as const,
            text: '已识别队列中有 12 例缺失"随访月份"字段；建议在统计前补齐或剔除。',
            time: '— 等待真实数据',
          },
          {
            scope: '智能体经验',
            tone: 'secondary' as const,
            text: '使用 pandas.read_csv 时遇到混合编码，最终用 chardet 自动检测解决。',
            time: '— 等待真实数据',
          },
          {
            scope: '任务计划',
            tone: 'success' as const,
            text: 'PLAN.md 已归档到 docs/plans/2026-05-19_cohort-analysis.md',
            time: '— 等待真实数据',
          },
        ].map((item, i) => (
          <div key={i} className="flex items-start gap-3 px-4 py-3 opacity-70">
            <FileCode
              className={cn(
                'mt-0.5 h-3.5 w-3.5 shrink-0',
                item.tone === 'primary' && 'text-primary',
                item.tone === 'secondary' && 'text-secondary',
                item.tone === 'success' && 'text-emerald-600',
              )}
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <Badge
                  variant={item.tone === 'success' ? 'success' : 'outline'}
                  className="h-4 px-1.5 text-[10px] font-normal"
                >
                  {item.scope}
                </Badge>
                <Clock3 className="h-3 w-3 text-muted-foreground" />
                <span className="text-[11px] text-muted-foreground">{item.time}</span>
              </div>
              <div className="mt-1 text-[12.5px] text-muted-foreground">{item.text}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Memory() {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 p-6 lg:p-8">
        <PageHeader
          icon={BrainCircuit}
          title="记忆库"
          description={
            <>
              iCore 的「长期记忆」按层级保存在文件系统里，可直接用 IDE / 编辑器查看。
              每次任务结束后，进化链会自动追加新的记忆片段。
            </>
          }
          stats={
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <StatCard
                icon={Layers}
                iconTone="primary"
                label="记忆分层"
                value={LAYERS.length}
                hint="项目 / 智能体 / 工作区 / Craft"
              />
              <StatCard
                icon={Sparkles}
                iconTone="secondary"
                label="自动沉淀"
                value="已开启"
                hint="任务结束后异步执行"
              />
              <StatCard
                icon={Database}
                iconTone="accent"
                label="数据位置"
                value="文件系统"
                hint="可直接 IDE 编辑"
              />
            </div>
          }
        />

        {}
        <MemoryFlow />

        {}
        <div>
          <h2 className="mb-3 text-base font-semibold tracking-tight">记忆层级详解</h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {LAYERS.map((layer) => (
              <LayerCard key={layer.title} layer={layer} />
            ))}
          </div>
        </div>

        {}
        <RecentDigestsPlaceholder />
      </div>
    </div>
  )
}

import type { ToolStep, TurnStep } from '@/application/state/chatStore'
import { describeThinkingBrief } from '@/shared/foundation/reasoningNarrator'

export interface EpisodeRow {
  id: string
  label: string
  status: 'running' | 'success' | 'failed' | 'pending'
}

interface Episode {
  id: string
  thinking: string
  tools: ToolStep[]
  notices: string[]
  status: 'running' | 'success' | 'failed'
}

function parseArgs(raw: string): Record<string, unknown> {
  if (!raw?.trim()) return {}
  try {
    const v = JSON.parse(raw)
    if (v && typeof v === 'object' && !Array.isArray(v)) return v as Record<string, unknown>
  } catch {
    /* ignore */
  }
  return {}
}

function basename(path: string): string {
  const p = path.replace(/\\/g, '/').trim()
  const parts = p.split('/').filter(Boolean)
  return parts[parts.length - 1] || p
}

function truncate(s: string, max: number): string {
  const t = s.replace(/\s+/g, ' ').trim()
  if (t.length <= max) return t
  return `${t.slice(0, max)}…`
}

function hostOf(url: unknown): string {
  if (typeof url !== 'string' || !url) return ''
  try {
    return new URL(url).hostname || url
  } catch {
    return url.slice(0, 40)
  }
}

/** 把连续工具调用收成若干「活动片段」，每段一句完整人话（做了什么 + 为什么） */
export function narrateStepEpisodes(steps: TurnStep[]): EpisodeRow[] {
  const episodes: Episode[] = []
  let pendingThinking = ''
  let current: Episode | null = null

  const flush = () => {
    if (!current) return
    if (current.tools.length === 0 && current.notices.length === 0 && !current.thinking) {
      current = null
      return
    }
    episodes.push(current)
    current = null
  }

  const ensureEpisode = (seedId: string) => {
    if (!current) {
      current = {
        id: seedId,
        thinking: pendingThinking,
        tools: [],
        notices: [],
        status: 'success',
      }
      pendingThinking = ''
    }
    return current
  }

  for (const step of steps) {
    if (step.kind === 'thinking') {
      // 思考作为下一段活动的「为什么」
      pendingThinking = step.content || pendingThinking
      if (step.streaming) {
        const ep = ensureEpisode(step.id)
        ep.thinking = step.content || ep.thinking
        ep.status = 'running'
        ep.id = step.id
      }
      continue
    }

    if (step.kind === 'ask_user' || step.kind === 'pretext' || step.kind === 'message') {
      continue
    }

    if (step.kind === 'notice') {
      const text = (step.content || '').trim()
      if (text.length < 4) continue
      // 阶段推进：结束当前片段，单独成段
      flush()
      const label = text
        .replace(
          /^阶段\s*\d+「[^」]*」完成，自动继续阶段\s*\d+「([^」]*)」.*$/u,
          '上一阶段做完了，接着开始「$1」',
        )
        .replace(/^\[框架自动推进\]\s*/u, '')
      episodes.push({
        id: step.id,
        thinking: '',
        tools: [],
        notices: [label],
        status: 'success',
      })
      continue
    }

    if (
      step.kind === 'delegate' ||
      step.kind === 'subagent' ||
      step.kind === 'pipeline' ||
      step.kind === 'squad' ||
      step.kind === 'council'
    ) {
      flush()
      episodes.push({
        id: step.id,
        thinking: pendingThinking,
        tools: [],
        notices: [narrateSpecial(step)],
        status:
          'status' in step && step.status === 'running'
            ? 'running'
            : 'status' in step && (step.status === 'failed' || step.status === 'escalated')
              ? 'failed'
              : 'success',
      })
      pendingThinking = ''
      continue
    }

    if (step.kind === 'error') {
      const ep = ensureEpisode(step.id)
      ep.notices.push(step.content ? `遇到问题：${step.content}` : '执行过程中遇到问题')
      ep.status = 'failed'
      ep.id = step.id
      continue
    }

    if (step.kind === 'tool') {
      // 主题切换时切开片段，避免整段任务糊成一句
      // 说明：current 仅在闭包内赋值，外层流分析会把它当 null，这里取局部别名恢复联合类型
      const active = current as Episode | null
      if (active && shouldSplitEpisode(active.tools, step)) {
        flush()
      }
      const ep = ensureEpisode(step.id)
      ep.tools.push(step)
      if (step.status === 'running') ep.status = 'running'
      else if (step.status === 'failed' && ep.status !== 'running') ep.status = 'failed'
      ep.id = step.id
      continue
    }
  }

  // 末尾若只有思考（还在想），也展示
  if (pendingThinking && !current) {
    ensureEpisode('thinking-live').thinking = pendingThinking
  }
  flush()

  return episodes
    .map((ep) => ({
      id: ep.id,
      label: composeEpisodeLabel(ep),
      status: ep.status === 'running' ? ('running' as const) : ep.status === 'failed' ? ('failed' as const) : ('success' as const),
    }))
    .filter((r) => r.label.trim().length > 0)
}

function narrateSpecial(step: TurnStep): string {
  if (step.kind === 'delegate') {
    const persona = step.persona || '同事'
    return step.task
      ? `请「${persona}」帮忙：${truncate(step.task, 48)}`
      : `请「${persona}」接手处理一段工作`
  }
  if (step.kind === 'subagent') {
    return step.question
      ? `安排子任务：${truncate(step.question, 48)}`
      : '安排子任务去处理'
  }
  if (step.kind === 'pipeline') {
    return step.title ? `按流程推进：${step.title}` : '按预定流程往下做'
  }
  if (step.kind === 'squad') {
    return step.title ? `几件事并行推进：${step.title}` : '把工作拆成几路并行推进'
  }
  if (step.kind === 'council') {
    return step.question
      ? `多方讨论：${truncate(step.question, 48)}`
      : '组织多方讨论后再决定'
  }
  return ''
}

/** 主题明显切换时拆段：例如从「搜代码」切到「装依赖跑解密」仍可同段；从完全无关的 http 批量切到 git 再拆 */
function shouldSplitEpisode(prev: ToolStep[], next: ToolStep): boolean {
  if (prev.length === 0) return false
  const prevTheme = episodeTheme(prev)
  const nextTheme = episodeTheme([next])
  if (!prevTheme || !nextTheme) return false
  // 同属调查/解密/取数，不拆
  if (prevTheme === nextTheme) return false
  // 调查 → 执行（装库/跑脚本）视为同一故事的后半段，不拆
  if (prevTheme === 'investigate' && nextTheme === 'execute') return false
  if (prevTheme === 'web' && (nextTheme === 'investigate' || nextTheme === 'execute')) return false
  // 其它主题切换才拆
  return prevTheme !== nextTheme && prev.length >= 2
}

function episodeTheme(tools: ToolStep[]): string {
  const blob = tools
    .map((t) => `${t.tool} ${t.args} ${t.output || ''}`)
    .join('\n')
    .toLowerCase()
  if (/decrypt|privatekey|gmssl|sm2|cipher|加密|解密|密钥/.test(blob)) return 'investigate'
  if (/select-string|regex|app\.js|studyinfo|grep |\brg /.test(blob)) return 'investigate'
  if (/http_fetch|invoke-webrequest|curl |wget /.test(blob)) return 'web'
  if (/pip install|npm install|pytest|python -c|python \w+\.py/.test(blob)) return 'execute'
  if (/file_ops/.test(blob) && /write|str_replace/.test(blob)) return 'execute'
  if (/git /.test(blob)) return 'git'
  return 'general'
}

function composeEpisodeLabel(ep: Episode): string {
  if (ep.tools.length === 0 && ep.notices.length > 0) {
    return ep.notices.join('；')
  }

  const why = ep.thinking ? describeThinkingBrief(ep.thinking, false) : ''
  const what = narrateToolsAsStory(ep.tools)
  const extra = ep.notices.length ? ep.notices.join('；') : ''

  const parts: string[] = []
  if (why) parts.push(why.endsWith('。') ? why.slice(0, -1) : why)
  if (what) parts.push(what)
  if (extra) parts.push(extra)

  if (parts.length === 0) {
    return ep.status === 'running' ? '正在推进这项工作…' : ''
  }
  if (parts.length === 1) return ensurePeriod(parts[0])
  // 「为什么」+「做了什么」
  if (why && what) {
    const reason = parts[0].replace(/[。！？]$/u, '')
    return ensurePeriod(`${reason}。为此，${what}`)
  }
  return ensurePeriod(parts.join('。'))
}

function ensurePeriod(s: string): string {
  const t = s.trim().replace(/[；，]+$/u, '')
  if (!t) return t
  if (/[。！？…]$/u.test(t)) return t
  return `${t}。`
}

function narrateToolsAsStory(tools: ToolStep[]): string {
  if (tools.length === 0) return ''
  if (tools.every((t) => t.status === 'running') && tools.length === 1) {
    return narrateSingleRunning(tools[0])
  }

  const fetches = tools.filter((t) => t.tool === 'http_fetch' || t.tool === 'http_post')
  const shells = tools.filter((t) => t.tool === 'shell_exec')
  const files = tools.filter((t) => t.tool === 'file_ops')
  const codes = tools.filter((t) => t.tool === 'code_exec')
  const presents = tools.filter((t) => t.tool === 'present_file')
  const crafts = tools.filter((t) => t.tool === 'craft_search' || t.tool === 'memory_recall')
  const charters = tools.filter((t) => t.tool === 'task_charter')
  const trains = tools.filter((t) => t.tool === 'train_run')
  const others = tools.filter(
    (t) =>
      ![
        'http_fetch',
        'http_post',
        'shell_exec',
        'file_ops',
        'code_exec',
        'present_file',
        'craft_search',
        'memory_recall',
        'task_charter',
        'train_run',
      ].includes(t.tool),
  )

  const bits: string[] = []
  const running = tools.some((t) => t.status === 'running')

  // —— 上网查阅 ——
  if (fetches.length > 0) {
    const hosts = unique(
      fetches.map((t) => hostOf(parseArgs(t.args).url)).filter(Boolean),
    )
    const failN = fetches.filter((t) => t.status === 'failed').length
    const hostText =
      hosts.length === 0
        ? '相关网站'
        : hosts.length === 1
          ? `「${hosts[0]}」`
          : `「${hosts.slice(0, 2).join('」「')}」${hosts.length > 2 ? '等' : ''}`
    if (failN === fetches.length) {
      bits.push(`去${hostText}查资料，但请求都没有成功`)
    } else if (failN > 0) {
      bits.push(`去${hostText}查资料，其中有 ${failN} 次没能打开`)
    } else {
      bits.push(running ? `正在查阅${hostText}上的资料` : `查阅了${hostText}上的资料`)
    }
  }

  // —— 终端：识别「在某文件里反复搜索」vs 装依赖 vs 跑脚本 ——
  if (shells.length > 0) {
    bits.push(...narrateShellCluster(shells, running))
  }

  // —— 读文件 ——
  if (files.length > 0) {
    bits.push(...narrateFileCluster(files, running))
  }

  // —— Python ——
  if (codes.length > 0) {
    const intents = codes.map((t) => inferCodeIntent(String(parseArgs(t.args).code || '')))
    const uniq = unique(intents)
    if (uniq.length === 1) {
      bits.push(running ? `正在用 Python ${uniq[0]}` : `用 Python ${uniq[0]}`)
    } else {
      bits.push(
        running
          ? `正在用 Python 做：${uniq.slice(0, 2).join('、')}`
          : `用 Python 做了：${uniq.slice(0, 2).join('、')}`,
      )
    }
  }

  if (crafts.length > 0) {
    bits.push(running ? '正在查方法论和历史经验' : '查阅了方法论和历史经验')
  }

  if (charters.length > 0) {
    const adv = charters.some((t) => String(parseArgs(t.args).action) === 'advance_stage')
    const init = charters.some((t) => String(parseArgs(t.args).action) === 'init')
    if (adv) bits.push('推进了任务阶段')
    else if (init) bits.push('把长任务拆成了几个阶段')
    else bits.push('更新了任务安排')
  }

  if (trains.length > 0) {
    const actions = unique(trains.map((t) => String(parseArgs(t.args).action || '')))
    if (actions.includes('confirm')) bits.push(running ? '正在启动本机训练' : '启动了本机训练')
    else if (actions.includes('design')) bits.push(running ? '正在生成训练方案' : '生成了训练方案')
    else bits.push(running ? '正在查看训练进度' : '查看了训练进度')
  }

  if (presents.length > 0) {
    const names = unique(
      presents.map((t) => basename(String(parseArgs(t.args).path || ''))).filter(Boolean),
    )
    bits.push(
      names.length
        ? `把「${names.slice(0, 3).join('」「')}」展示给你看`
        : '把产出文件展示给你看',
    )
  }

  if (others.length > 0 && bits.length === 0) {
    bits.push(running ? '正在继续处理这项工作' : '完成了这一步相关操作')
  }

  if (bits.length === 0) return running ? '正在处理' : ''
  if (bits.length === 1) return bits[0]
  if (bits.length === 2) return `${bits[0]}，然后${bits[1]}`
  return `${bits[0]}，接着${bits.slice(1, -1).join('，')}，最后${bits[bits.length - 1]}`
}

function narrateShellCluster(shells: ToolStep[], running: boolean): string[] {
  const cmds = shells.map((t) => String(parseArgs(t.args).command || parseArgs(t.args).cmd || ''))
  const blob = cmds.join('\n')

  const searchFiles = unique(
    [...blob.matchAll(/(?:Select-String|Get-Content|type|cat|rg |grep ).*?([A-Za-z0-9_.-]+\.(?:js|ts|py|tsx|jsx|json|md|txt))/gi)]
      .map((m) => m[1]),
  )
  const isSearchHeavy =
    cmds.filter((c) => /Select-String|regex::|\bgrep\b|\brg\b|Get-Content.*-TotalCount/i.test(c))
      .length >= 2

  const out: string[] = []

  if (isSearchHeavy) {
    const targets = searchFiles.length ? searchFiles : ['相关代码']
    const themes: string[] = []
    if (/decrypt|解密/i.test(blob)) themes.push('解密')
    if (/privateKey|私钥|gmssl|sm2/i.test(blob)) themes.push('密钥')
    if (/studyInfo|study/i.test(blob)) themes.push('检查/影像信息')
    if (/https?:\/\//i.test(blob)) themes.push('接口地址')
    const themeText = themes.length ? themes.join('、') : '关键逻辑'
    const targetText =
      targets.length === 1 ? `「${targets[0]}」` : `「${targets.slice(0, 2).join('」「')}」等文件`
    out.push(
      running
        ? `正在${targetText}里查找与${themeText}有关的代码`
        : `在${targetText}里查找了与${themeText}有关的代码`,
    )
  }

  const installs = cmds.filter((c) => /pip\s+install|npm\s+i(nstall)?|yarn\s+add/i.test(c))
  if (installs.length) {
    const pkg =
      installs[0].match(/pip\s+install\s+(\S+)/i)?.[1]?.replace(/-q$/, '') ||
      installs[0].match(/npm\s+i(?:nstall)?\s+(\S+)/i)?.[1] ||
      '所需依赖'
    out.push(running ? `正在安装「${pkg}」` : `安装了「${pkg}」`)
  }

  const scripts = cmds.filter(
    (c) =>
      /python(\.exe)?\s+\S+\.py|py\s+\S+\.py|node\s+\S+\.js/i.test(c) ||
      /Invoke-WebRequest|curl |wget /i.test(c),
  )
  if (scripts.length) {
    if (/Invoke-WebRequest|curl |wget /i.test(scripts.join('\n'))) {
      const host = scripts.join('\n').match(/https?:\/\/([^/\s"']+)/i)?.[1]
      out.push(
        host
          ? running
            ? `正在请求「${host}」拉取数据`
            : `请求「${host}」拉取了数据`
          : running
            ? '正在请求网络接口拉取数据'
            : '请求网络接口拉取了数据',
      )
    } else {
      const script =
        scripts[0].match(/(?:python(?:\.exe)?|py|node)\s+(\S+)/i)?.[1] || '脚本'
      out.push(running ? `正在运行「${basename(script)}」` : `运行了「${basename(script)}」`)
    }
  }

  // 其它零散命令：不逐条展开，只给一句概括
  const covered = new Set(
    [...installs, ...scripts].map((c) => c),
  )
  const rest = cmds.filter(
    (c) =>
      c &&
      !covered.has(c) &&
      !(isSearchHeavy && /Select-String|regex::|\bgrep\b|\brg\b/i.test(c)),
  )
  if (rest.length && out.length === 0) {
    out.push(
      running
        ? `正在终端完成 ${rest.length} 项操作`
        : `在终端完成了 ${rest.length} 项操作`,
    )
  } else if (rest.length >= 3 && !isSearchHeavy) {
    out.push(running ? '并在终端继续做配套操作' : '并在终端做了配套操作')
  }

  return out
}

function narrateFileCluster(files: ToolStep[], running: boolean): string[] {
  const reads: string[] = []
  const writes: string[] = []
  const others: string[] = []
  for (const t of files) {
    const a = parseArgs(t.args)
    const action = String(a.action || 'read')
    const name = basename(String(a.path || a.file || ''))
    if (!name || name.startsWith('.') && name.includes('tool_cache')) {
      // 工具缓存文件对用户无意义，跳过
      continue
    }
    if (action === 'read' || action === 'list') reads.push(name)
    else if (action === 'write' || action === 'append' || action === 'str_replace' || action === 'replace')
      writes.push(name)
    else others.push(name)
  }
  const out: string[] = []
  const r = unique(reads)
  const w = unique(writes)
  const o = unique(others)
  if (r.length === 1) out.push(running ? `正在查看「${r[0]}」` : `查看了「${r[0]}」`)
  else if (r.length > 1)
    out.push(
      running
        ? `正在查看「${r[0]}」等 ${r.length} 个文件`
        : `查看了「${r[0]}」等 ${r.length} 个文件`,
    )
  if (w.length === 1) out.push(running ? `正在写「${w[0]}」` : `写好了「${w[0]}」`)
  else if (w.length > 1)
    out.push(running ? `正在更新 ${w.length} 个文件` : `更新了「${w[0]}」等文件`)
  if (o.length && out.length === 0) {
    out.push(running ? `正在处理「${o[0]}」` : `处理了「${o[0]}」`)
  }
  return out
}

function inferCodeIntent(code: string): string {
  const joined = code.split(/\r?\n/).slice(0, 20).join(' ')
  if (/gmssl|sm2|decrypt|encrypt|私钥|解密/.test(joined)) return '做加解密相关计算'
  if (/read_csv|pandas|DataFrame/.test(joined)) return '处理表格数据'
  if (/matplotlib|seaborn|plotly|\.plot\(/.test(joined)) return '画图分析'
  if (/sklearn|fit\(|predict\(/.test(joined)) return '做模型训练或预测'
  if (/requests\.|urllib|httpx|Invoke-WebRequest/.test(joined)) return '请求网络数据'
  if (/open\(.*['\"]w|to_csv|to_excel|json\.dump/.test(joined)) return '生成结果文件'
  return '做一段计算'
}

function narrateSingleRunning(t: ToolStep): string {
  const a = parseArgs(t.args)
  if (t.tool === 'http_fetch') {
    const h = hostOf(a.url)
    return h ? `正在查阅「${h}」上的资料` : '正在上网查资料'
  }
  if (t.tool === 'shell_exec') {
    const cmd = String(a.command || '')
    if (/Select-String|grep |\brg /i.test(cmd)) return '正在代码里查找关键线索'
    if (/pip install/i.test(cmd)) return '正在安装依赖'
    return '正在终端执行操作'
  }
  if (t.tool === 'file_ops') {
    const name = basename(String(a.path || ''))
    return name ? `正在查看「${name}」` : '正在查看文件'
  }
  if (t.tool === 'code_exec') return `正在用 Python ${inferCodeIntent(String(a.code || ''))}`
  if (t.tool === 'train_run') {
    const action = String(a.action || '')
    if (action === 'design') return '正在生成训练方案'
    if (action === 'confirm') return '正在启动本机训练'
    if (action === 'log' || action === 'status') return '正在查看训练进度'
    return '正在处理本机训练'
  }
  return '正在处理'
}

function unique(items: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const x of items) {
    const k = x.trim()
    if (!k || seen.has(k)) continue
    seen.add(k)
    out.push(k)
  }
  return out
}

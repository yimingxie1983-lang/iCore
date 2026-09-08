

import type { SSEEvent } from '@/client/services/sse'
import type { ChatEvent } from '@/application/state/chatStore'
import { personaIcon, personaName } from '@/shared/foundation/personas'

export type NarrationKind =
  | 'narration'
  | 'action'
  | 'activity'
  | 'subagent'
  | 'group'
  | 'group_child'
  | 'verdict'
  | 'ask'
  | 'warning'
  | 'final'
  | 'error'

export interface ResultSummary {

  headline: string

  highlights?: string[]

  excerpt?: string

  fullLength?: number
  success: boolean
}

export interface NarrationBlock {

  id: string
  kind: NarrationKind

  icon: string

  text: string
  status?: 'running' | 'success' | 'failed'

  ts: number

  tool?: string

  args?: Record<string, unknown>

  resultSummary?: ResultSummary

  durationMs?: number

  children?: NarrationBlock[]

  causedBy?: string

  rawEventIds: string[]

  toolCount?: number

  failedCount?: number

  totalDurationMs?: number

  toolLabels?: string[]
}

type ToolTemplate = (args: Record<string, unknown>) => { icon: string; text: string }

function extractHost(url: unknown): string {
  if (typeof url !== 'string' || !url) return '某个网站'
  try {
    const u = new URL(url)
    return u.hostname || url
  } catch {

    return url.length > 60 ? url.slice(0, 60) + '…' : url
  }
}

function truncate(s: unknown, max = 60): string {
  const str = String(s ?? '')
  if (str.length <= max) return str
  return str.slice(0, max - 1) + '…'
}

const TOOL_NARRATIVE_TEMPLATES: Record<string, ToolTemplate> = {
  http_fetch: (args) => ({
    icon: '🌐',
    text: `好，我去查一下 \`${extractHost(args.url)}\` 这个网站……`,
  }),
  http_post: () => ({ icon: '📤', text: '我去提交个请求……' }),

  file_ops: (args) => {
    const action = String(args.action || 'read')
    const path = String(args.path || '')
    if (action === 'read') return { icon: '📄', text: `我看看 \`${path}\` 里写了什么……` }
    if (action === 'write') return { icon: '✍️', text: `我把整理好的内容写到 \`${path}\`……` }
    if (action === 'list') return { icon: '📁', text: `看看 \`${path}\` 目录下有什么文件……` }
    if (action === 'delete') return { icon: '🗑️', text: `删除 \`${path}\`……` }
    return { icon: '📄', text: `操作文件 \`${path}\`（${action}）……` }
  },

  code_exec: () => ({ icon: '🐍', text: '我跑段 Python 算一下……' }),
  shell_exec: (args) => ({
    icon: '⌨️',
    text: `执行命令 \`${truncate(args.command, 40)}\`……`,
  }),

  craft_search: (args) => {
    const action = String(args.action || 'search')
    if (action === 'view') {
      return {
        icon: '📚',
        text: `我去读一下方法论 \`${args.craft_id || '?'}\` 的完整正文……`,
      }
    }
    return { icon: '📚', text: '我去方法论库里找找有没有现成套路……' }
  },

  memory_recall: () => ({ icon: '🧠', text: '我回忆一下之前的同类项目……' }),

  switch_persona: (args) => {
    const pid = args.persona_id || args.persona
    const reason = String(args.reason || '换个角度看')
    return {
      icon: '🎭',
      text: `切换到 **${personaName(pid as string | undefined)}** 视角（${reason}）……`,
    }
  },

  as_persona: (args) => {
    const pid = args.persona_id || args.persona
    return {
      icon: '🎭',
      text: `临时借用 **${personaName(pid as string | undefined)}** 的视角处理一段……`,
    }
  },

  ask_user: (args) => ({
    icon: '❓',
    text: `我先问你一下：${truncate(args.question, 60)}`,
  }),

  dispatch_squad: () => ({ icon: '👥', text: '这事情我拆成几个子任务并行做……' }),
  convene_council: () => ({ icon: '⚖️', text: '这事争议比较大，召开议会讨论……' }),

  enter_plan_mode: () => ({ icon: '📝', text: '这事比较复杂，我先写个计划……' }),
  exit_plan_mode: () => ({ icon: '✅', text: '计划已对齐，退出规划模式开始执行……' }),

  task_charter: (args) => {
    const action = String(args.action || '')
    if (action === 'init') return { icon: '📋', text: '这是个长任务，先立个契约写明阶段……' }
    if (action === 'advance_stage') return { icon: '➡️', text: '当前阶段完成，自动推进到下一阶段……' }
    if (action === 'log_event') return { icon: '📌', text: '随手记一笔关键进展……' }
    if (action === 'finalize') return { icon: '🏁', text: '全任务完成，归档契约……' }
    return { icon: '📋', text: `更新任务契约（${action}）……` }
  },

  self_inspect: () => ({ icon: '🔍', text: '我看看自己手上有什么工具可用……' }),
  tool_activator: () => ({ icon: '🔌', text: '激活一个按需工具……' }),
  activate_craft: (args) => ({
    icon: '⚡',
    text: `挂载方法论 \`${args.craft_id || '?'}\` 到当前会话……`,
  }),

  present_file: (args) => ({
    icon: '📎',
    text: `把文件 \`${args.path || '?'}\` 呈现给你……`,
  }),

  attempt_completion: () => ({ icon: '🎯', text: '整理一下，准备给你最终答复……' }),

  train_run: (args) => {
    const action = String(args.action || '')
    if (action === 'runtime') return { icon: '⚡', text: '探测本机训练环境和 CUDA……' }
    if (action === 'design') return { icon: '⚡', text: '按你的描述生成训练方案……' }
    if (action === 'confirm') return { icon: '⚡', text: '在沙箱里启动本机训练……' }
    if (action === 'cancel') return { icon: '⚡', text: '取消当前训练任务……' }
    if (action === 'log') return { icon: '⚡', text: '读取训练日志……' }
    if (action === 'list') return { icon: '⚡', text: '查看最近的训练任务……' }
    return { icon: '⚡', text: '查看本机训练进度……' }
  },

  default: (args) => ({
    icon: '🔧',
    text: `调用工具 \`${args._tool || '...'}\`……`,
  }),
}

function templateOf(tool: string, args: Record<string, unknown>): { icon: string; text: string } {
  const tpl = TOOL_NARRATIVE_TEMPLATES[tool]
  if (tpl) return tpl(args)
  return TOOL_NARRATIVE_TEMPLATES.default({ ...args, _tool: tool })
}

type BriefTemplate = (args: Record<string, unknown>) => string

const TOOL_BRIEF_TEMPLATES: Record<string, BriefTemplate> = {
  http_fetch: (args) => {
    const host = extractHost(args.url)
    let path = ''
    if (typeof args.url === 'string') {
      try {
        path = new URL(args.url).pathname || ''
      } catch {
        /* ignore */
      }
    }
    const shortPath =
      path && path !== '/' ? truncate(path.replace(/\/+$/, ''), 36) : ''
    return shortPath ? `查阅 ${host}${shortPath}` : `查阅 ${host}`
  },
  http_post: (args) => {
    const host = extractHost(args.url)
    return host && host !== '某个网站' ? `提交到 ${host}` : '提交请求'
  },

  file_ops: (args) => {
    const action = String(args.action || 'read')
    const rawPath = String(args.path || args.file || '')
    const path = truncate(rawPath, 48)
    const base = rawPath.split(/[/\\]/).filter(Boolean).pop() || path
    if (action === 'read') return path ? `读取 ${base}` : '读取文件'
    if (action === 'write') return path ? `写入 ${base}` : '写入文件'
    if (action === 'list') return path ? `列出 ${path}` : '列出目录'
    if (action === 'delete') return path ? `删除 ${base}` : '删除文件'
    if (action === 'append') return path ? `追加 ${base}` : '追加文件'
    if (action === 'str_replace' || action === 'replace') {
      return path ? `修改 ${base}` : '修改文件'
    }
    return path ? `${action} ${base}` : action
  },

  code_exec: (args) => {
    const code = String(args.code || args.script || '')
    const first = code
      .split(/\r?\n/)
      .map((l) => l.trim())
      .find((l) => l && !l.startsWith('#') && !l.startsWith('"""') && !l.startsWith("'''"))
    if (first) return `运行 Python · ${truncate(first, 42)}`
    return '运行 Python'
  },
  shell_exec: (args) => {
    const cmd = String(args.command || args.cmd || '').trim()
    if (!cmd) return '执行命令'
    const head = cmd.split(/\r?\n/)[0].trim()
    return `运行 \`${truncate(head, 52)}\``
  },

  craft_search: (args) => {
    const action = String(args.action || 'search')
    const q = String(args.query || args.craft_id || '')
    if (action === 'view') {
      return q ? `读方法论 ${truncate(q, 36)}` : '读方法论正文'
    }
    return q ? `查方法论「${truncate(q, 28)}」` : '查方法论库'
  },

  memory_recall: (args) => {
    const q = String(args.query || args.keyword || '')
    return q ? `回忆「${truncate(q, 28)}」` : '查项目回忆'
  },

  switch_persona: (args) => `切到 ${personaName(args.persona_id as string | undefined) || '?'} 视角`,
  as_persona: (args) => `借用 ${personaName(args.persona_id as string | undefined) || '?'} 视角`,

  ask_user: () => '准备提问',
  enter_plan_mode: () => '编写计划',
  exit_plan_mode: () => '计划完成，开始执行',

  task_charter: (args) => {
    const action = String(args.action || '')
    if (action === 'init') return '建立任务契约'
    if (action === 'advance_stage') {
      const summary = String(args.result_summary || '')
      return summary
        ? `完成阶段 · ${truncate(summary, 36)}`
        : '推进到下一阶段'
    }
    if (action === 'log_event') {
      const text = String(args.text || '')
      return text ? `记录：${truncate(text, 36)}` : '记录进展'
    }
    if (action === 'finalize') return '归档任务契约'
    return `更新契约（${action || '…'}）`
  },

  self_inspect: () => '检查可用能力',
  tool_activator: () => '激活按需工具',
  activate_craft: (args) => {
    const id = String(args.craft_id || '')
    return id ? `挂载方法论 ${truncate(id, 28)}` : '挂载方法论'
  },
  present_file: (args) => {
    const path = String(args.path || '')
    const base = path.split(/[/\\]/).filter(Boolean).pop() || path
    return base ? `展示 ${truncate(base, 36)}` : '展示文件'
  },
  attempt_completion: () => '整理最终答复',

  dispatch_squad: (args) => {
    const title = String(args.title || args.goal || '')
    return title ? `并行小队 · ${truncate(title, 32)}` : '派发并行小队'
  },
  convene_council: (args) => {
    const q = String(args.question || '')
    return q ? `召开议会 · ${truncate(q, 32)}` : '召开议会'
  },

  train_run: (args) => {
    const action = String(args.action || '')
    if (action === 'runtime') return '探测训练环境'
    if (action === 'design') return '生成训练方案'
    if (action === 'confirm') return '启动本机训练'
    if (action === 'cancel') return '取消训练'
    if (action === 'log') return '读取训练日志'
    if (action === 'list') return '查看训练任务'
    return '查看训练进度'
  },

  default: (args) => String(args._tool || '调用工具'),
}

function briefToolLabel(tool: string, args: Record<string, unknown>): string {
  const tpl = TOOL_BRIEF_TEMPLATES[tool]
  if (tpl) return tpl(args)
  return TOOL_BRIEF_TEMPLATES.default({ ...args, _tool: tool })
}

export function describeToolBrief(
  tool: string,
  args: Record<string, unknown> | string | undefined,
  result?: { output?: string; error?: string; success?: boolean },
): string {
  let parsed: Record<string, unknown> = {}
  if (typeof args === 'string' && args.trim()) {
    try {
      const v = JSON.parse(args)
      if (v && typeof v === 'object' && !Array.isArray(v)) parsed = v as Record<string, unknown>
    } catch {
      /* ignore */
    }
  } else if (args && typeof args === 'object') {
    parsed = args
  }
  const base = briefToolLabel(tool, parsed)
  if (!result) return base

  if (result.success === false || result.error) {
    const err = firstLine(String(result.error || ''), 40)
    return err ? `${base} · 失败：${err}` : `${base} · 失败`
  }

  const output = typeof result.output === 'string' ? result.output.trim() : ''
  if (!output) return base

  if (tool === 'shell_exec') {
    const exitMatch = output.match(/exit[_\s]*code[:=\s]+(\d+)/i)
    const code = exitMatch?.[1]
    if (code && code !== '0') return `${base} · exit ${code}`
    const last = output
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean)
      .slice(-1)[0]
    if (last && last.length < 60 && !/^exit/i.test(last)) {
      return `${base} · ${truncate(last, 40)}`
    }
    return base
  }

  if (tool === 'code_exec') {
    const last = output
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean)
      .slice(-1)[0]
    if (last) return `${base} · ${truncate(last, 36)}`
    return base
  }

  if (tool === 'http_fetch') {
    const titleMatch = output.match(/<title[^>]*>([^<]+)<\/title>/i)
    if (titleMatch?.[1]) return `${base} · ${truncate(titleMatch[1].trim(), 28)}`
    const count = output.match(COUNT_RE)
    if (count?.[1] || count?.[2]) return `${base} · ${count[1] || count[2]} 条`
    return base
  }

  if (tool === 'file_ops') {
    const action = String(parsed.action || 'read')
    if (action === 'list') {
      const n = output.split(/\r?\n/).filter((l) => l.trim()).length
      return n > 0 ? `${base} · ${n} 项` : base
    }
    if (action === 'read') {
      const lines = output.split(/\r?\n/).length
      return lines > 1 ? `${base} · ${lines} 行` : base
    }
  }

  if (tool === 'craft_search') {
    const m = output.match(COUNT_RE)
    if (m?.[1] || m?.[2]) return `${base} · ${m[1] || m[2]} 个`
  }

  return base
}

/** 从思考正文提炼一行意图（Codex 风格），空则返回空串 */
export function describeThinkingBrief(content: string, streaming?: boolean): string {
  const text = clean(content || '')
  if (!text) return streaming ? '正在想下一步怎么做…' : ''
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.replace(/^[\s>*#\-\d.、]+/, '').trim())
    .filter((l) => l.length >= 4)
  const first = lines[0] || text.slice(0, 80)
  const sentence = first.split(/[。！？\n]/)[0]?.trim() || first
  const body = truncate(sentence.replace(/\s+/g, ' '), 64)
  return streaming ? `${body}…` : body
}

function parseArgsLoose(
  args: Record<string, unknown> | string | undefined,
): Record<string, unknown> {
  if (typeof args === 'string' && args.trim()) {
    try {
      const v = JSON.parse(args)
      if (v && typeof v === 'object' && !Array.isArray(v)) return v as Record<string, unknown>
    } catch {
      /* ignore */
    }
    return {}
  }
  if (args && typeof args === 'object') return args
  return {}
}

function fileDisplayName(path: string): string {
  const p = path.replace(/\\/g, '/').trim()
  if (!p) return '文件'
  const parts = p.split('/').filter(Boolean)
  if (parts.length >= 2) return truncate(parts.slice(-2).join('/'), 48)
  return truncate(parts[parts.length - 1] || p, 48)
}

function narrateShellCommand(cmd: string, running: boolean): string {
  const head = cmd.split(/\r?\n/)[0].trim()
  const lower = head.toLowerCase()
  const verb = running ? '正在' : '已经'
  if (/\bpytest\b|\bunittest\b|\bnpm test\b|\bvitest\b/.test(lower)) {
    return `${verb}跑测试：${truncate(head, 56)}`
  }
  if (/\bpip\s+install\b|\bnpm\s+i(nstall)?\b|\byarn\s+add\b/.test(lower)) {
    return `${verb}安装依赖：${truncate(head, 56)}`
  }
  if (/\bpython(\.exe)?\b|\bpy\b/.test(lower)) {
    return `${verb}运行脚本：${truncate(head, 56)}`
  }
  if (/\bgit\s+status\b/.test(lower)) return `${verb}查看代码仓库状态`
  if (/\bgit\s+diff\b/.test(lower)) return `${verb}查看代码改动`
  if (/\bgit\s+log\b/.test(lower)) return `${verb}查看提交历史`
  if (/\bgit\s+clone\b/.test(lower)) return `${verb}克隆代码仓库`
  if (/^(dir|ls|Get-ChildItem)\b/i.test(head)) {
    return `${verb}查看目录内容：${truncate(head, 48)}`
  }
  if (/^(type|cat|Get-Content)\b/i.test(head)) {
    return `${verb}查看文件内容：${truncate(head, 48)}`
  }
  if (/\bcurl\b|\bwget\b|\binvoke-webrequest\b/i.test(lower)) {
    return `${verb}下载或请求网络资源：${truncate(head, 48)}`
  }
  return `${verb}在终端执行：${truncate(head, 60)}`
}

function narrateCodeIntent(code: string, running: boolean): string {
  const verb = running ? '正在用 Python' : '用 Python'
  const lines = code
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#') && !l.startsWith('"""') && !l.startsWith("'''"))
  const joined = lines.slice(0, 8).join(' ')
  if (/read_csv|pandas|DataFrame/.test(joined)) {
    return `${verb}处理表格数据`
  }
  if (/matplotlib|seaborn|plotly|\.plot\(/.test(joined)) {
    return `${verb}画图分析`
  }
  if (/sklearn|fit\(|predict\(/.test(joined)) {
    return `${verb}做模型训练或预测`
  }
  if (/open\(.*['\"]w|to_csv|to_excel|json\.dump/.test(joined)) {
    return `${verb}生成结果文件`
  }
  if (/requests\.|urllib|httpx/.test(joined)) {
    return `${verb}请求网络数据`
  }
  const first = lines[0]
  if (first) return `${verb}计算：${truncate(first, 48)}`
  return `${verb}跑一段计算`
}

/**
 * 主界面步骤：用通俗自然语言描述「具体在做什么」，
 * 而不是工具名 / 合并计数。
 */
export function narrateToolStep(
  tool: string,
  args: Record<string, unknown> | string | undefined,
  opts?: {
    output?: string
    error?: string
    success?: boolean
    running?: boolean
  },
): string {
  const a = parseArgsLoose(args)
  const running = Boolean(opts?.running)
  const failed = opts?.success === false || Boolean(opts?.error)
  const output = typeof opts?.output === 'string' ? opts.output.trim() : ''

  let text = ''

  if (tool === 'file_ops') {
    const action = String(a.action || 'read')
    const path = fileDisplayName(String(a.path || a.file || ''))
    if (action === 'read') {
      text = running ? `正在打开查看「${path}」` : `查看了「${path}」里的内容`
    } else if (action === 'write') {
      text = running ? `正在把内容写进「${path}」` : `把结果写进了「${path}」`
    } else if (action === 'list') {
      text = running ? `正在查看「${path}」目录有哪些文件` : `查看了「${path}」目录下的文件`
    } else if (action === 'delete') {
      text = running ? `正在删除「${path}」` : `删除了「${path}」`
    } else if (action === 'append') {
      text = running ? `正在往「${path}」追加内容` : `往「${path}」追加了内容`
    } else if (action === 'str_replace' || action === 'replace') {
      text = running ? `正在修改「${path}」里的内容` : `修改了「${path}」里的内容`
    } else {
      text = running ? `正在处理文件「${path}」` : `处理了文件「${path}」`
    }
    if (!running && !failed && action === 'list' && output) {
      const n = output.split(/\r?\n/).filter((l) => l.trim()).length
      if (n > 0) text += `，共 ${n} 项`
    }
  } else if (tool === 'shell_exec') {
    const cmd = String(a.command || a.cmd || '').trim()
    text = cmd
      ? narrateShellCommand(cmd, running)
      : running
        ? '正在终端执行操作'
        : '在终端执行了操作'
    if (!running && !failed && output) {
      const exitMatch = output.match(/exit[_\s]*code[:=\s]+(\d+)/i)
      if (exitMatch?.[1] && exitMatch[1] !== '0') {
        text += `（未成功，退出码 ${exitMatch[1]}）`
      }
    }
  } else if (tool === 'code_exec') {
    text = narrateCodeIntent(String(a.code || a.script || ''), running)
    if (!running && !failed && output) {
      const last = output
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter(Boolean)
        .slice(-1)[0]
      if (last && last.length <= 48) text += `，得到：${truncate(last, 40)}`
    }
  } else if (tool === 'http_fetch') {
    const host = extractHost(a.url)
    text = running
      ? `正在上网查阅「${host}」的资料`
      : `查阅了「${host}」上的资料`
    if (!running && !failed && output) {
      const titleMatch = output.match(/<title[^>]*>([^<]+)<\/title>/i)
      if (titleMatch?.[1]) text += `（${truncate(titleMatch[1].trim(), 28)}）`
    }
  } else if (tool === 'http_post') {
    const host = extractHost(a.url)
    text =
      host && host !== '某个网站'
        ? running
          ? `正在向「${host}」提交数据`
          : `已向「${host}」提交数据`
        : running
          ? '正在提交网络请求'
          : '已提交网络请求'
  } else if (tool === 'craft_search') {
    const action = String(a.action || 'search')
    const q = String(a.query || a.craft_id || '')
    if (action === 'view') {
      text = running
        ? `正在阅读方法论「${truncate(q || '相关条目', 32)}」`
        : `阅读了方法论「${truncate(q || '相关条目', 32)}」`
    } else {
      text = q
        ? running
          ? `正在方法论库里查找「${truncate(q, 28)}」`
          : `在方法论库里查找了「${truncate(q, 28)}」`
        : running
          ? '正在方法论库里找现成做法'
          : '在方法论库里找了现成做法'
    }
  } else if (tool === 'memory_recall') {
    const q = String(a.query || a.keyword || '')
    text = q
      ? running
        ? `正在回忆以前和「${truncate(q, 28)}」有关的经验`
        : `回忆了以前和「${truncate(q, 28)}」有关的经验`
      : running
        ? '正在回忆以前做过的类似项目'
        : '回忆了以前做过的类似项目'
  } else if (tool === 'task_charter') {
    const action = String(a.action || '')
    if (action === 'init') {
      text = running ? '正在把长任务拆成几个阶段' : '把长任务拆成了几个阶段'
    } else if (action === 'advance_stage') {
      const summary = String(a.result_summary || '').trim()
      text = summary
        ? `完成了当前阶段：${truncate(summary, 48)}`
        : '当前阶段做完了，进入下一阶段'
    } else if (action === 'log_event') {
      const t = String(a.text || '').trim()
      text = t ? `记下进展：${truncate(t, 48)}` : '记下了当前进展'
    } else if (action === 'finalize') {
      text = '整个任务收尾并归档'
    } else {
      text = '更新了任务安排'
    }
  } else if (tool === 'present_file') {
    const path = fileDisplayName(String(a.path || ''))
    text = running ? `正在把「${path}」展示给你` : `把「${path}」展示给你看`
  } else if (tool === 'attempt_completion') {
    text = running ? '正在整理最终答复' : '整理好了最终答复'
  } else if (tool === 'enter_plan_mode') {
    text = running ? '正在写执行计划' : '先写好了执行计划'
  } else if (tool === 'exit_plan_mode') {
    text = '计划对齐后，开始动手做'
  } else if (tool === 'switch_persona' || tool === 'as_persona') {
    const name = personaName((a.persona_id || a.persona) as string | undefined) || '专业视角'
    text =
      tool === 'switch_persona'
        ? running
          ? `正在切换到「${name}」视角`
          : `切换到「${name}」视角继续处理`
        : running
          ? `正在临时借用「${name}」的视角`
          : `临时借用了「${name}」的视角`
  } else if (tool === 'dispatch_squad') {
    const title = String(a.title || a.goal || '').trim()
    text = title
      ? running
        ? `正在把任务拆开并行做：${truncate(title, 36)}`
        : `把任务拆开并行处理了：${truncate(title, 36)}`
      : running
        ? '正在把任务拆成几个子任务并行做'
        : '把任务拆成几个子任务并行做了'
  } else if (tool === 'convene_council') {
    const q = String(a.question || '').trim()
    text = q
      ? running
        ? `正在组织讨论：${truncate(q, 40)}`
        : `组织讨论了：${truncate(q, 40)}`
      : running
        ? '正在组织多视角讨论'
        : '组织了多视角讨论'
  } else if (tool === 'self_inspect') {
    text = running ? '正在检查自己当前能用哪些能力' : '检查了自己当前能用的能力'
  } else if (tool === 'activate_craft') {
    const id = String(a.craft_id || '')
    text = id
      ? running
        ? `正在启用方法论「${truncate(id, 28)}」`
        : `启用了方法论「${truncate(id, 28)}」`
      : running
        ? '正在启用相关方法论'
        : '启用了相关方法论'
  } else {
    const fallback = briefToolLabel(tool, { ...a, _tool: tool })
    text = running ? `正在${fallback}` : `完成了：${fallback}`
  }

  if (failed) {
    const err = firstLine(String(opts?.error || ''), 36)
    return err ? `${text}，但没有成功：${err}` : `${text}，但没有成功`
  }
  return text
}

function clean(s: string): string {
  return s.replace(/\r\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim()
}

const COUNT_RE = /(?:找到|matched|匹配到|共)\s*(\d+)|(\d+)\s*(?:results?|条|篇|个|项)/i

const STATUS_RE = /\b([2-5]\d{2})\b/

const URL_RE = /https?:\/\/[^\s)"'<>，。、）]+/g

/** 取首行（带最大长度截断） */
function firstLine(s: string, max = 100): string {
  const line = s.split(/\r?\n/, 1)[0] || ''
  return truncate(line, max)
}

/** 取 body 前 N 字作为 excerpt */
function makeExcerpt(s: string, max = 200): string {
  const c = clean(s)
  if (!c) return ''
  return truncate(c, max)
}

/** 字节数 / 字符数友好化展示（"48 KB" / "32 字符"） */
function humanSize(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return ''
  if (n < 1024) return `${n} 字符`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

/**
 * 智能摘要：按工具名分发不同的提取策略。
 *
 * 入参 ev 必须是 tool_result 事件；返回的 ResultSummary 会挂到关联的 action block 上。
 */
function extractResultSummary(tool: string, ev: SSEEvent): ResultSummary {
  // 后端字段口径：tool_result 主要看 ev.result.{success,output,error,data}
  const result = ev.result || {}
  const success = result.success !== false && !result.error
  const output = typeof result.output === 'string' ? result.output : ''
  const error = typeof result.error === 'string' ? result.error : ''
  const fullLength = output.length || undefined

  // 失败统一格式：headline="失败：..."
  if (!success) {
    const status = error.match(STATUS_RE)?.[1]
    const headline = status
      ? `失败：${status}${/forbidden|denied/i.test(error) ? ' 拒绝访问' : ''}`
      : `失败：${firstLine(error, 60) || '未知错误'}`
    return {
      headline,
      highlights: error ? [firstLine(error, 100)] : undefined,
      success: false,
    }
  }

  // ── http_fetch：解析 status code / size / URL ──
  if (tool === 'http_fetch') {
    const status = output.match(STATUS_RE)?.[1] || '200'
    const size = humanSize(output.length)
    const headline = `返回 ${status}${size ? `，${size}` : ''}`
    const urls = (output.match(URL_RE) || []).slice(0, 2)
    const titleMatch = output.match(/<title[^>]*>([^<]+)<\/title>/i)
    const highlights: string[] = []
    if (titleMatch?.[1]) highlights.push(`📰 ${truncate(titleMatch[1].trim(), 100)}`)
    for (const url of urls) highlights.push(`🔗 ${truncate(url, 80)}`)
    return {
      headline,
      highlights: highlights.length > 0 ? highlights : undefined,
      excerpt: makeExcerpt(output, 240),
      fullLength,
      success: true,
    }
  }

  // ── file_ops ──
  if (tool === 'file_ops') {
    const args = parseToolArgs(ev.arguments)
    const action = String(args.action || 'read')
    if (action === 'write') {
      return {
        headline: `写入完成${output.length > 0 ? `（${humanSize(output.length)}）` : ''}`,
        success: true,
      }
    }
    if (action === 'list') {
      // list 输出常是路径换行列表；取前 5 条作 highlights
      const lines = output.split(/\r?\n/).filter((l) => l.trim()).slice(0, 5)
      return {
        headline: `列出 ${output.split(/\r?\n/).filter((l) => l.trim()).length} 项`,
        highlights: lines.length > 0 ? lines.map((l) => `· ${truncate(l, 80)}`) : undefined,
        success: true,
      }
    }
    // read（默认）
    const lineCount = output.split(/\r?\n/).length
    return {
      headline: `读到 ${lineCount} 行${output.length > 0 ? `（${humanSize(output.length)}）` : ''}`,
      excerpt: makeExcerpt(output, 240),
      fullLength,
      success: true,
    }
  }

  // ── code_exec：python 沙箱 ──
  if (tool === 'code_exec') {
    const lines = output.split(/\r?\n/).filter((l) => l).length
    const lastLine = output.split(/\r?\n/).filter((l) => l.trim()).slice(-1)[0] || ''
    return {
      headline: `✓ 执行完成（${lines} 行输出）`,
      highlights: lastLine ? [`📤 ${truncate(lastLine, 120)}`] : undefined,
      excerpt: makeExcerpt(output, 240),
      fullLength,
      success: true,
    }
  }

  // ── shell_exec ──
  if (tool === 'shell_exec') {
    const exitMatch = output.match(/exit[_\s]*code[:=\s]+(\d+)/i)
    const code = exitMatch?.[1] || '0'
    return {
      headline: `exit=${code}`,
      excerpt: makeExcerpt(output, 240),
      fullLength,
      success: true,
    }
  }

  // ── craft_search ──
  if (tool === 'craft_search') {
    const m = output.match(COUNT_RE)
    const count = m?.[1] || m?.[2] || '?'
    // craft 行常长这样："- craft_id: xxx   title: xxx"
    const craftLines = output
      .split(/\r?\n/)
      .filter((l) => /^[-*•]\s*\S/.test(l) || /craft_id|title/.test(l))
      .slice(0, 3)
    return {
      headline: `找到 ${count} 个 craft`,
      highlights: craftLines.length > 0 ? craftLines.map((l) => truncate(l.trim(), 100)) : undefined,
      success: true,
    }
  }

  // ── memory_recall ──
  if (tool === 'memory_recall') {
    const m = output.match(COUNT_RE)
    const count = m?.[1] || m?.[2] || (output.trim() ? '若干' : '0')
    return {
      headline: `找到 ${count} 条记忆`,
      highlights: output.trim() ? [firstLine(output, 120)] : undefined,
      success: true,
    }
  }

  // ── dispatch_squad（仅 tool_result 阶段，启动 + 收尾会有独立 squad_* 事件）──
  if (tool === 'dispatch_squad') {
    return {
      headline: `派发完成${output ? `：${firstLine(output, 60)}` : ''}`,
      success: true,
    }
  }

  // ── convene_council ──
  if (tool === 'convene_council') {
    return {
      headline: `议会完成${output ? `：${firstLine(output, 60)}` : ''}`,
      success: true,
    }
  }

  // ── 默认：返回字符数 + 首行 100 字 ──
  return {
    headline: output ? `返回 ${humanSize(output.length)}` : '✓ 完成',
    highlights: output ? [firstLine(output, 100)] : undefined,
    excerpt: output ? makeExcerpt(output, 240) : undefined,
    fullLength,
    success: true,
  }
}

// ────────────────────────────────────────────────────────────────
// Pass 1：基础翻译（单事件 → 单 base block）
// ────────────────────────────────────────────────────────────────

/** "第 N 轮推理…"等模型自言自语，过滤掉避免干扰用户阅读 */
const INTERNAL_THINKING_RE = /^(第\s*\d+\s*轮推理|round\s*\d+|step\s*\d+)/i

/** 安全解析 tool_call.arguments：可能是 string 也可能是 object */
function parseToolArgs(raw: unknown): Record<string, unknown> {
  if (raw == null) return {}
  if (typeof raw === 'object') return raw as Record<string, unknown>
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object') return parsed as Record<string, unknown>
    } catch {
      /* 不是合法 JSON，原样丢回 */
    }
    return { _raw: raw }
  }
  return {}
}

/**
 * 单事件 → 单 base block。
 *
 * - 返回 null：表示这个事件不直接产生 block（如 message_delta / usage / session_started）
 * - tool_result 在这里也返回 null：由 Pass 2 merge 到对应 tool_call 的 block 上
 */
function narrateBaseEvent(ev: SSEEvent, evId: string, ts: number): NarrationBlock | null {
  const type = String(ev.type || '')

  // ── thinking 系列：直显（过滤"第 N 轮推理"开头） ──
  if (type === 'thinking' || type === 'squad_task_thinking' || type === 'council_role_thinking' || type === 'council_role_rebut_thinking' || type === 'council_arbiter_thinking') {
    const content = String(ev.content || '').trim()
    if (!content) return null
    if (INTERNAL_THINKING_RE.test(content)) return null
    return {
      id: evId,
      kind: 'narration',
      icon: '💭',
      text: content,
      ts,
      rawEventIds: [evId],
    }
  }

  // ── tool_call：走模板表 ──
  if (type === 'tool_call' || type === 'squad_task_tool_call' || type === 'council_role_tool_call' || type === 'council_role_rebut_tool_call' || type === 'council_arbiter_tool_call') {
    const tool = String(ev.tool || ev.tool_name || 'tool')
    const args = parseToolArgs(ev.arguments)
    const { icon, text } = templateOf(tool, args)
    return {
      id: evId,
      kind: 'action',
      icon,
      text,
      status: 'running',
      tool,
      args,
      ts,
      rawEventIds: [evId],
    }
  }

  // ── tool_result：留给 Pass 2 配对 ──
  if (type === 'tool_result' || type === 'squad_task_tool_result' || type === 'council_role_tool_result' || type === 'council_role_rebut_tool_result' || type === 'council_arbiter_tool_result') {
    return null
  }

  // ── message / message_delta：主气泡已展示，这里不再渲染 ──
  if (type === 'message' || type === 'message_delta') return null

  // ── usage / session_started：不渲染 ──
  if (type === 'usage' || type === 'session_started') return null

  // ── delegate（单 sub 委派） ──
  if (type === 'delegate_start') {
    const persona = String(ev.persona || ev.agent_id || '')
    return {
      id: evId,
      kind: 'subagent',
      icon: '🎯',
      text: `把这个子任务派给 **${personaName(persona) || persona || '某个分身'}** 来做……`,
      status: 'running',
      ts,
      rawEventIds: [evId],
    }
  }
  if (type === 'delegate_result') {
    // 不单独成块，merge 阶段把它 attach 到上一个 running 的 delegate block
    return null
  }

  // ── subagent_request / subagent_reply（双向问答型） ──
  if (type === 'subagent_request' || type === 'subagent_ask') {
    const to = String(ev.to_agent || ev.target || ev.agent_id || '')
    const q = truncate(String(ev.question || ev.content || ''), 80)
    return {
      id: evId,
      kind: 'subagent',
      icon: '💬',
      text: `请教 **${personaName(to) || to}**：${q}`,
      status: 'running',
      ts,
      rawEventIds: [evId],
    }
  }
  if (type === 'subagent_reply' || type === 'subagent_answer') {
    const from = String(ev.from_agent || ev.agent_id || '')
    const a = truncate(String(ev.answer || ev.content || ev.result || ''), 80)
    return {
      id: evId,
      kind: 'subagent',
      icon: '💬',
      text: `**${personaName(from) || from}** 回我了：${a}`,
      status: 'success',
      ts,
      rawEventIds: [evId],
    }
  }

  // ── pipeline 系列 ──
  if (type === 'pipeline_start') {
    const title = String(ev.title || ev.name || ev.content || '某个流水线')
    return {
      id: evId,
      kind: 'action',
      icon: '🛠️',
      text: `启动 **${title}** 流水线……`,
      status: 'running',
      ts,
      rawEventIds: [evId],
    }
  }
  if (type === 'pipeline_result' || type === 'pipeline_done') {
    return null // merge 到对应 pipeline_start
  }

  // ── squad 系列 ──
  if (type === 'squad_started') {
    const total = Number(ev.tasks_total ?? 0)
    const title = String(ev.title || '并行小队')
    return {
      id: evId,
      kind: 'group',
      icon: '👥',
      text: `**${title}** · 召集了 ${total} 个并行子任务`,
      status: 'running',
      ts,
      rawEventIds: [evId],
      children: [],
    }
  }
  if (type === 'squad_task_started') {
    const ptag = ev.persona_id
      ? `${personaIcon(String(ev.persona_id))} **${personaName(String(ev.persona_id))}**`
      : ''
    return {
      id: evId,
      kind: 'group_child',
      icon: '·',
      text: `${ptag ? ptag + ' 接手' : '开始'}：${String(ev.task_title || ev.task_id || '')}`,
      status: 'running',
      ts,
      rawEventIds: [evId],
    }
  }
  if (type === 'squad_task_done') {
    // 这事件本身在 Pass 1 不直接成块，由嵌套 pass 把成功/失败 merge 到对应子任务
    // 不过为了让用户在 timeline 末尾看到"x 完成"信息，仍保留为 group_child 形式
    const ok = ev.success !== false
    const summary = truncate(String(ev.summary || ev.error || ''), 80)
    return {
      id: evId,
      kind: 'group_child',
      icon: ok ? '✓' : '✗',
      text: `${ok ? '完成' : '失败'}${summary ? `：${summary}` : ''}`,
      status: ok ? 'success' : 'failed',
      ts,
      rawEventIds: [evId],
    }
  }
  if (type === 'squad_concluded') {
    return null // 收口信息合并到对应父 group block 的 status
  }

  // ── council 系列 ──
  if (type === 'council_convened') {
    const roleCount = Array.isArray(ev.roles) ? ev.roles.length : 0
    const arbiter = personaName(String(ev.arbiter_persona || 'critical_reviewer'))
    return {
      id: evId,
      kind: 'group',
      icon: '⚖️',
      text: `**召开议会**：${roleCount} 位专家 + ${arbiter} 仲裁`,
      status: 'running',
      ts,
      rawEventIds: [evId],
      children: [],
    }
  }
  if (type === 'council_role_started' || type === 'council_role_rebut_started') {
    const pid = String(ev.persona_id || '')
    const isRebut = type === 'council_role_rebut_started'
    return {
      id: evId,
      kind: 'group_child',
      icon: personaIcon(pid),
      text: `**${personaName(pid)}** ${isRebut ? '准备反驳……' : '准备发言……'}`,
      status: 'running',
      ts,
      rawEventIds: [evId],
    }
  }
  if (type === 'council_role_stance') {
    const stance = truncate(String(ev.stance_text || ev.text || ''), 120)
    return {
      id: evId,
      kind: 'group_child',
      icon: '💬',
      text: `立场：${stance}`,
      status: ev.success === false ? 'failed' : 'success',
      ts,
      rawEventIds: [evId],
    }
  }
  if (type === 'council_role_rebuttal') {
    const reb = truncate(String(ev.rebuttal_text || ev.text || ''), 120)
    return {
      id: evId,
      kind: 'group_child',
      icon: '↩️',
      text: `反驳：${reb}`,
      status: ev.success === false ? 'failed' : 'success',
      ts,
      rawEventIds: [evId],
    }
  }
  if (type === 'council_arbiter_started') {
    const arb = personaName(String(ev.arbiter_persona || ev.persona_id || ''))
    return {
      id: evId,
      kind: 'group_child',
      icon: '⚖️',
      text: `**${arb}** 综合各方意见……`,
      status: 'running',
      ts,
      rawEventIds: [evId],
    }
  }
  if (type === 'council_verdict') {
    const vtype = String(ev.verdict_type || 'consensus')
    const text = truncate(String(ev.text || ev.verdict_text || ''), 200)
    const label = vtype === 'consensus' ? '共识' : vtype === 'arbitrated' ? '仲裁' : vtype === 'escalate' ? '升级' : vtype
    return {
      id: evId,
      kind: 'verdict',
      icon: '🔨',
      text: `**裁决（${label}）**：${text}`,
      status: 'success',
      ts,
      rawEventIds: [evId],
    }
  }
  if (type === 'council_concluded') {
    return null // 收口信息合并到对应父 group block 的 status
  }

  // ── ask_user_pending ──
  if (type === 'ask_user_pending') {
    return {
      id: evId,
      kind: 'ask',
      icon: '❓',
      text: `**我有个问题想问你**：${String(ev.question || '')}`,
      status: 'running',
      ts,
      rawEventIds: [evId],
    }
  }

  // ── evidence_warning ──
  if (type === 'evidence_warning') {
    return {
      id: evId,
      kind: 'warning',
      icon: '⚠️',
      text: `引用预警：\`${ev.ref || ''}\` 命中主观词 \`${ev.hit || ''}\``,
      status: 'failed',
      ts,
      rawEventIds: [evId],
    }
  }

  // ── error ──
  if (type === 'error') {
    return {
      id: evId,
      kind: 'error',
      icon: '❌',
      text: `**出错了**：${String(ev.error || ev.content || '未知错误')}`,
      status: 'failed',
      ts,
      rawEventIds: [evId],
    }
  }

  // ── done ──
  if (type === 'done') {
    return {
      id: evId,
      kind: 'final',
      icon: '✓',
      text: '本轮思考结束',
      status: 'success',
      ts,
      rawEventIds: [evId],
    }
  }

  // ── 其它未覆盖类型：直接忽略（这是预期的，比如 squad_concluded / message_delta） ──
  return null
}

// ────────────────────────────────────────────────────────────────
// Pass 2：tool_call ↔ tool_result 配对 + delegate_start ↔ delegate_result + pipeline_*
// ────────────────────────────────────────────────────────────────

/**
 * tool_result / delegate_result / pipeline_result 不单独成块，
 * 这里扫一遍原事件流，把它们 attach 到上一个匹配的 running block 上。
 *
 * 匹配规则：从后往前找第一个 status=running 且 tool 名匹配的 action block
 *           （tool 名能对就对，对不上 fallback 到任意 running 的 action）。
 */
function mergeToolPairs(blocks: NarrationBlock[], events: ChatEvent[]): NarrationBlock[] {
  // 用 Map<evId, block index> 快速定位
  const idxByEvId = new Map<string, number>()
  blocks.forEach((b, i) => {
    for (const eid of b.rawEventIds) idxByEvId.set(eid, i)
  })

  const out = blocks.map((b) => ({ ...b }))

  for (const chatEv of events) {
    const ev = chatEv.raw
    const type = String(ev.type || '')

    // ── tool_result 配对 ──
    const isToolResult =
      type === 'tool_result' ||
      type === 'squad_task_tool_result' ||
      type === 'council_role_tool_result' ||
      type === 'council_role_rebut_tool_result' ||
      type === 'council_arbiter_tool_result'

    if (isToolResult) {
      const toolName = String(ev.tool || '')
      // 从后往前找匹配的 running action
      for (let i = out.length - 1; i >= 0; i--) {
        const b = out[i]
        if (b.kind !== 'action') continue
        if (b.status !== 'running') continue
        if (toolName && b.tool && b.tool !== toolName) continue
        // 命中
        const summary = extractResultSummary(b.tool || toolName || 'tool', ev)
        out[i] = {
          ...b,
          status: summary.success ? 'success' : 'failed',
          resultSummary: summary,
          durationMs: Number(ev.duration_ms || 0) || b.durationMs,
          rawEventIds: [...b.rawEventIds, chatEv.id],
        }
        break
      }
      continue
    }

    // ── delegate_result 配对 ──
    if (type === 'delegate_result') {
      for (let i = out.length - 1; i >= 0; i--) {
        const b = out[i]
        if (b.kind !== 'subagent') continue
        if (b.status !== 'running') continue
        out[i] = {
          ...b,
          status: 'success',
          text: b.text + `\n\n→ ${truncate(String(ev.result || ev.content || ''), 100)}`,
          rawEventIds: [...b.rawEventIds, chatEv.id],
        }
        break
      }
      continue
    }

    // ── pipeline_result 配对 ──
    if (type === 'pipeline_result' || type === 'pipeline_done') {
      for (let i = out.length - 1; i >= 0; i--) {
        const b = out[i]
        if (b.kind !== 'action') continue
        if (b.status !== 'running') continue
        if (!b.text.includes('流水线')) continue
        const ok = ev.success !== false
        out[i] = {
          ...b,
          status: ok ? 'success' : 'failed',
          durationMs: Number(ev.duration_ms || 0) || b.durationMs,
          rawEventIds: [...b.rawEventIds, chatEv.id],
        }
        break
      }
      continue
    }
  }

  return out
}

// ────────────────────────────────────────────────────────────────
// Pass 3a：squad / council 嵌套（子项归到父 group block.children）
// ────────────────────────────────────────────────────────────────

/**
 * 把 group_child 块（来自 squad_task_* / council_role_* / council_arbiter_*）
 * 折进对应父 group block.children 数组里，不再作为顶层块出现。
 *
 * 父匹配规则：从前往后扫，最后一个 status=running 或 status=success 的同类型 group。
 * 因为同时只有一个 squad / council 在跑，这个简化规则足够鲁棒。
 *
 * 同时把 squad_concluded / council_concluded 事件的 duration / status 应用到父。
 */
function nestGroupChildren(blocks: NarrationBlock[], events: ChatEvent[]): NarrationBlock[] {
  // 找出所有 group block 的位置 + 类型（squad / council）
  // 类型判断：squad 看 text 含"并行小队/召集"；council 看 text 含"召开议会"
  const groupSlots: Array<{ index: number; kind: 'squad' | 'council' }> = []
  blocks.forEach((b, i) => {
    if (b.kind !== 'group') return
    const isCouncil = b.icon === '⚖️' || b.text.includes('议会')
    groupSlots.push({ index: i, kind: isCouncil ? 'council' : 'squad' })
  })
  if (groupSlots.length === 0) return blocks

  // 复制一份可修改
  const out = blocks.map((b) => ({ ...b, children: b.children ? [...b.children] : b.children }))

  // 给每个 group_child 找父；判定标准：原始事件 type
  const childIndexesToRemove = new Set<number>()

  for (let i = 0; i < out.length; i++) {
    const b = out[i]
    if (b.kind !== 'group_child') continue
    // 看它来自哪种事件
    const firstEvId = b.rawEventIds[0]
    const ev = events.find((e) => e.id === firstEvId)?.raw
    if (!ev) continue
    const type = String(ev.type || '')
    const isCouncilChild = type.startsWith('council_')
    const isSquadChild = type.startsWith('squad_task')
    if (!isCouncilChild && !isSquadChild) continue

    // 从后往前找匹配类型的、index < i 的 group
    let parentIdx = -1
    for (let g = groupSlots.length - 1; g >= 0; g--) {
      const slot = groupSlots[g]
      if (slot.index >= i) continue
      if (isCouncilChild && slot.kind !== 'council') continue
      if (isSquadChild && slot.kind !== 'squad') continue
      parentIdx = slot.index
      break
    }
    if (parentIdx < 0) continue

    const parent = out[parentIdx]
    if (!parent.children) parent.children = []
    parent.children.push(b)
    childIndexesToRemove.add(i)
  }

  // 把 verdict block 也归到对应 council group 的 children（保持视觉上议会卡内一体）
  for (let i = 0; i < out.length; i++) {
    const b = out[i]
    if (b.kind !== 'verdict') continue
    // 找前面最近的 council group
    for (let g = groupSlots.length - 1; g >= 0; g--) {
      const slot = groupSlots[g]
      if (slot.index >= i) continue
      if (slot.kind !== 'council') continue
      const parent = out[slot.index]
      if (!parent.children) parent.children = []
      parent.children.push(b)
      childIndexesToRemove.add(i)
      break
    }
  }

  // 把 squad_concluded / council_concluded 事件的状态应用到父
  for (const chatEv of events) {
    const ev = chatEv.raw
    const type = String(ev.type || '')
    if (type !== 'squad_concluded' && type !== 'council_concluded') continue
    const isCouncil = type === 'council_concluded'
    // 找匹配类型且 status=running 的最近 group
    for (let g = groupSlots.length - 1; g >= 0; g--) {
      const slot = groupSlots[g]
      if (isCouncil && slot.kind !== 'council') continue
      if (!isCouncil && slot.kind !== 'squad') continue
      const parent = out[slot.index]
      if (parent.status !== 'running') continue
      // 看孩子里有没有 failed
      const childFailed = (parent.children || []).some((c) => c.status === 'failed')
      out[slot.index] = {
        ...parent,
        status: childFailed ? 'failed' : 'success',
        durationMs: Number(ev.duration_ms || 0) || parent.durationMs,
        rawEventIds: [...parent.rawEventIds, chatEv.id],
        children: parent.children,
      }
      break
    }
  }

  // 移除已经归到 parent.children 里的顶层项
  return out.filter((_, i) => !childIndexesToRemove.has(i))
}

// ────────────────────────────────────────────────────────────────
// Pass 3a-bis：把连续 action 折叠成一个 activity 行
//
// 这是 v2 调整的核心 pass：医生 / 患者 / 投资人不需要看到一长串工具卡片，
// 他们只需要知道"AI 正在做某件事"——所以把同一段思考下连续的 tool_call
// 都收成一个 spinner 行：
//
//   [💭 思考叙述]
//   [⠋ 正在 查阅 nccn.org…]   ← 连调 2 个工具时文字会轮换为最新一个
//   [💭 后续思考]
//
// 完成后 spinner 行变为：
//   [✓ 已完成 3 步操作 · 1.4s]
//
// 聚合规则：
//   - 'action' 系列连续出现 → 合成 1 个 activity
//   - 任意非 action 块（narration / group / verdict / ask / warning / error / final
//     / subagent / group_child）出现 → flush 当前 activity，断开聚合
//   - subagent 不参与聚合（"派给某个分身"是用户能直观理解的大动作，独立显示更清楚）
// ────────────────────────────────────────────────────────────────

function mergeActionsToActivity(blocks: NarrationBlock[]): NarrationBlock[] {
  const out: NarrationBlock[] = []
  let pending: NarrationBlock | null = null

  const flush = () => {
    if (pending) {
      out.push(pending)
      pending = null
    }
  }

  for (const b of blocks) {
    if (b.kind !== 'action') {
      flush()
      out.push(b)
      continue
    }

    // 单条工具调用 → 转成 activity "草稿"
    const brief = briefToolLabel(b.tool || 'tool', b.args || {})

    if (!pending) {
      pending = {
        id: b.id,
        kind: 'activity',
        // icon 字段保留作 fallback；实际视觉由 ActivityRow 的 Loader2 spinner 渲染
        icon: '⏳',
        text: brief,
        status: b.status || 'running',
        ts: b.ts,
        tool: b.tool,
        toolCount: 1,
        failedCount: b.status === 'failed' ? 1 : 0,
        totalDurationMs: b.durationMs || 0,
        toolLabels: [brief],
        rawEventIds: [...b.rawEventIds],
      }
      continue
    }

    // 累积进 pending
    pending.toolCount = (pending.toolCount || 0) + 1
    if (b.status === 'failed') {
      pending.failedCount = (pending.failedCount || 0) + 1
    }
    pending.tool = b.tool
    pending.text = brief
    pending.totalDurationMs = (pending.totalDurationMs || 0) + (b.durationMs || 0)
    pending.toolLabels = [...(pending.toolLabels || []), brief]
    pending.rawEventIds = [...pending.rawEventIds, ...b.rawEventIds]

    // 状态收敛规则：
    //   - 任一 running → 整体 running
    //   - 全部 success → success
    //   - 有 failed 但全部已结束 → 整体 failed（让用户能看到"有过失败"）
    if (b.status === 'running') {
      pending.status = 'running'
    } else if (pending.status !== 'running') {
      pending.status = (pending.failedCount || 0) > 0 ? 'failed' : 'success'
    }
  }

  flush()
  return out
}

// ────────────────────────────────────────────────────────────────
// Pass 3b：因果绑定（thinking 紧跟在已完成 action / activity 之后 → causedBy）
// ────────────────────────────────────────────────────────────────

/**
 * 严格规则（设计 4.6 + v2 扩展）：
 *   curr 是 narration，prev 是 activity/action/verdict/group，且 prev.status !== 'running'
 *   → curr.causedBy = prev.id
 *
 * v2：把 'activity' 也加进合法 prev kind ——
 *   单条 action 已经被 mergeActionsToActivity 折叠成 activity，
 *   但保留 'action' 兼容（理论上不会再出现，留作防御性）。
 */
function bindCausality(blocks: NarrationBlock[]): NarrationBlock[] {
  const out = blocks.map((b) => ({ ...b }))
  const CAUSAL_PREV_KINDS: NarrationKind[] = ['activity', 'action', 'verdict', 'group']
  for (let i = 1; i < out.length; i++) {
    const curr = out[i]
    const prev = out[i - 1]
    if (curr.kind !== 'narration') continue
    if (!CAUSAL_PREV_KINDS.includes(prev.kind)) continue
    if (prev.status === 'running') continue
    out[i] = { ...curr, causedBy: prev.id }
  }
  return out
}

// ────────────────────────────────────────────────────────────────
// Pass 3c：相邻 thinking 合并（无中间事件的两个 thinking 合成一个）
// ────────────────────────────────────────────────────────────────

function mergeConsecutiveThinking(blocks: NarrationBlock[]): NarrationBlock[] {
  if (blocks.length < 2) return blocks
  const out: NarrationBlock[] = []
  for (const b of blocks) {
    const last = out[out.length - 1]
    if (
      last &&
      last.kind === 'narration' &&
      b.kind === 'narration' &&
      !b.causedBy // 后者不是因果绑定块（被 prev=action 中断）就允许合并
    ) {
      // merge：text 串接，rawEventIds 累加，id / ts / icon 保留前者
      out[out.length - 1] = {
        ...last,
        text: `${last.text}\n\n${b.text}`,
        rawEventIds: [...last.rawEventIds, ...b.rawEventIds],
      }
      continue
    }
    out.push(b)
  }
  return out
}

// ────────────────────────────────────────────────────────────────
// 主入口
// ────────────────────────────────────────────────────────────────

/**
 * 把整段事件流翻译成叙述块列表。
 *
 * 注意：输入是 ChatEvent[]（已经 chatStore 包过 id + ts），不是裸 SSEEvent[]，
 *      因为我们要用 ChatEvent.id 当作叙述块的稳定 key。
 */
export function narrateEvents(events: ChatEvent[]): NarrationBlock[] {
  if (!events || events.length === 0) return []

  // Pass 1：基础翻译
  const base: NarrationBlock[] = []
  for (const chatEv of events) {
    const block = narrateBaseEvent(chatEv.raw, chatEv.id, chatEv.ts)
    if (block) base.push(block)
  }

  // Pass 2：tool_call ↔ tool_result 配对
  const merged = mergeToolPairs(base, events)

  // Pass 3a：squad / council 嵌套（先于 activity 折叠，避免子任务的 action
  // 被顶层 activity 错误吞掉；group_child 当前不属于 'action'，不参与折叠）
  const nested = nestGroupChildren(merged, events)

  // Pass 3a-bis（v2 新增）：连续 action 折叠成 1 个 activity 行
  // 这是裁话给医生看的核心步骤——把"调了什么 API"折叠成"在干嘛"
  const folded = mergeActionsToActivity(nested)

  // Pass 3b：因果绑定（thinking 紧跟 activity 完成 → causedBy）
  const causality = bindCausality(folded)

  // Pass 3c：连续 thinking 合并（放在 bindCausality 之后，
  // 这样被中断的两个 thinking 因 causedBy 标记就不会被错合到一起）
  const finalBlocks = mergeConsecutiveThinking(causality)

  return finalBlocks
}

// ────────────────────────────────────────────────────────────────
// dev-only 自检：覆盖 SSEEventType 联合里所有 type；缺失模板提示补
// ────────────────────────────────────────────────────────────────

if (import.meta.env?.DEV) {
  // 所有应当在 narrateBaseEvent 里覆盖的事件类型（与 sse.ts 联合保持同步）
  const COVERED_EVENT_TYPES = [
    'thinking',
    'tool_call',
    'tool_result',
    'message',
    'message_delta',
    'delegate_start',
    'delegate_result',
    'subagent_request',
    'subagent_ask',
    'subagent_reply',
    'subagent_answer',
    'pipeline_start',
    'pipeline_result',
    'pipeline_done',
    'ask_user_pending',
    'usage',
    'session_started',
    'error',
    'done',
    'squad_started',
    'squad_task_started',
    'squad_task_thinking',
    'squad_task_tool_call',
    'squad_task_tool_result',
    'squad_task_done',
    'squad_concluded',
    'council_convened',
    'council_role_started',
    'council_role_thinking',
    'council_role_tool_call',
    'council_role_tool_result',
    'council_role_stance',
    'council_role_rebut_started',
    'council_role_rebut_thinking',
    'council_role_rebut_tool_call',
    'council_role_rebut_tool_result',
    'council_role_rebuttal',
    'council_arbiter_started',
    'council_arbiter_thinking',
    'council_arbiter_tool_call',
    'council_arbiter_tool_result',
    'council_verdict',
    'council_concluded',
    'evidence_warning',
  ] as const

  // 跑一遍空事件，确保各 type 不抛异常即可（业务覆盖到否由开发自检）
  for (const t of COVERED_EVENT_TYPES) {
    try {
      narrateBaseEvent({ type: t } as SSEEvent, 'dev-check', 0)
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn(`[reasoningNarrator] dev 自检：事件 type=${t} 翻译时抛异常：`, err)
    }
  }

  // 工具模板覆盖自检：列一份常用工具白名单，缺失的提示补
  const COMMON_TOOLS = [
    'http_fetch',
    'http_post',
    'file_ops',
    'code_exec',
    'shell_exec',
    'craft_search',
    'memory_recall',
    'switch_persona',
    'as_persona',
    'ask_user',
    'dispatch_squad',
    'convene_council',
    'enter_plan_mode',
    'exit_plan_mode',
    'task_charter',
    'self_inspect',
    'tool_activator',
    'activate_craft',
    'present_file',
    'attempt_completion',
    'train_run',
  ]
  const missing = COMMON_TOOLS.filter((t) => !TOOL_NARRATIVE_TEMPLATES[t])
  if (missing.length > 0) {
    // eslint-disable-next-line no-console
    console.warn(
      '[reasoningNarrator] 以下工具缺翻译模板（会走 default 兜底，文案略生硬）：',
      missing,
    )
  }
}

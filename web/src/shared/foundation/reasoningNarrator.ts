

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
    if (action === 'advance_stage') return { icon: '➡️', text: '当前阶段完成，推进到下一阶段……' }
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
  http_fetch: (args) => `查阅 ${extractHost(args.url)}`,
  http_post: () => '提交请求',

  file_ops: (args) => {
    const action = String(args.action || 'read')
    const path = truncate(String(args.path || ''), 40)
    if (action === 'read') return `读取 ${path}`
    if (action === 'write') return `保存 ${path}`
    if (action === 'list') return `列出 ${path}`
    if (action === 'delete') return `删除 ${path}`
    return `${action} ${path}`
  },

  code_exec: () => '运行计算',
  shell_exec: () => '执行命令',

  craft_search: (args) =>
    String(args.action || 'search') === 'view' ? '读方法论正文' : '查方法论库',

  memory_recall: () => '查回忆',

  switch_persona: (args) => `切到 ${personaName(args.persona_id as string | undefined) || '?'} 视角`,
  as_persona: (args) => `借用 ${personaName(args.persona_id as string | undefined) || '?'} 视角`,

  ask_user: () => '准备提问',
  enter_plan_mode: () => '写计划',
  exit_plan_mode: () => '完成计划',

  task_charter: (args) => {
    const action = String(args.action || '')
    if (action === 'init') return '建立任务契约'
    if (action === 'advance_stage') return '推进阶段'
    if (action === 'log_event') return '记录进展'
    if (action === 'finalize') return '归档契约'
    return `更新契约`
  },

  self_inspect: () => '自检能力',
  tool_activator: () => '激活工具',
  activate_craft: () => '挂载方法论',
  present_file: (args) => `展示 ${truncate(String(args.path || '?'), 30)}`,
  attempt_completion: () => '准备最终回复',

  dispatch_squad: () => '派发并行小队',
  convene_council: () => '召开议会',

  default: (args) => String(args._tool || '调用工具'),
}

function briefToolLabel(tool: string, args: Record<string, unknown>): string {
  const tpl = TOOL_BRIEF_TEMPLATES[tool]
  if (tpl) return tpl(args)
  return TOOL_BRIEF_TEMPLATES.default({ ...args, _tool: tool })
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

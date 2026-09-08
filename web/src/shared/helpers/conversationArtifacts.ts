import type { ChatMessage, TurnStep } from '@/application/state/chatStore'
import type { FilePresentation, FileRenderKind, PresentedFile } from '@/client/services/client'

export type ArtifactSource = 'submission' | 'artifact'

export interface ConversationArtifact {
  id: string
  source: ArtifactSource
  name: string
  path: string
  size: number
  createdAt: number
  messageId: string
  groupTitle?: string
  groupDescription?: string
  presented?: PresentedFile
}

const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'])
const MARKDOWN_EXTS = new Set(['md', 'markdown'])
const JSON_EXTS = new Set(['json'])
const CSV_EXTS = new Set(['csv', 'tsv'])
const PDF_EXTS = new Set(['pdf'])
const DOCX_EXTS = new Set(['docx', 'docm'])
const XLSX_EXTS = new Set(['xlsx', 'xlsm'])
const PPTX_EXTS = new Set(['pptx', 'pptm'])
const CODE_EXTS = new Set([
  'py',
  'r',
  'sh',
  'bash',
  'js',
  'ts',
  'tsx',
  'jsx',
  'sql',
  'yaml',
  'yml',
  'toml',
  'ini',
  'cfg',
  'txt',
  'log',
  'vcf',
])

export function inferRenderKind(name: string, kind?: string): FileRenderKind {
  if (kind === 'image') return 'image'
  const ext = (name.split('.').pop() || '').toLowerCase()
  if (IMAGE_EXTS.has(ext)) return 'image'
  if (MARKDOWN_EXTS.has(ext)) return 'markdown'
  if (JSON_EXTS.has(ext)) return 'json'
  if (CSV_EXTS.has(ext)) return 'csv'
  if (PDF_EXTS.has(ext)) return 'pdf'
  if (DOCX_EXTS.has(ext)) return 'docx'
  if (XLSX_EXTS.has(ext)) return 'xlsx'
  if (PPTX_EXTS.has(ext)) return 'pptx'
  if (CODE_EXTS.has(ext)) return 'code'
  if (kind && kind !== 'download') return kind as FileRenderKind
  return 'download'
}

const OUTPUT_ARTIFACT_KINDS = new Set<FileRenderKind>([
  'markdown',
  'code',
  'json',
  'image',
  'csv',
  'pdf',
  'docx',
  'xlsx',
  'pptx',
])
const OUTPUT_ARTIFACT_DENY_EXTS = new Set([
  'log',
  'vcf',
  'joblib',
  'npz',
  'npy',
])

function isCharterPath(path: string): boolean {
  const p = path.replace(/\\/g, '/').toLowerCase()
  if (/(^|\/)charters(\/|$)/.test(p)) return true
  const name = p.split('/').pop() || ''
  return name === 'charter.md'
}

export function isOutputArtifactFile(name: string, kind?: string, path?: string): boolean {
  const loc = path || name
  if (isCharterPath(loc) || isCharterPath(name)) return false
  if (/_probe/i.test(name) || /_probe/i.test(loc)) return false
  const ext = (name.split('.').pop() || '').toLowerCase()
  if (OUTPUT_ARTIFACT_DENY_EXTS.has(ext)) return false
  return OUTPUT_ARTIFACT_KINDS.has(inferRenderKind(name, kind))
}

export function extractPresentation(data: unknown): FilePresentation | null {
  if (!data || typeof data !== 'object') return null
  const p = (data as { presentation?: unknown }).presentation
  if (!p || typeof p !== 'object') return null
  const cast = p as Partial<FilePresentation>
  if (cast.kind !== 'files') return null
  if (!Array.isArray(cast.files) || cast.files.length === 0) return null
  return cast as FilePresentation
}

function normalizePresentation(group: FilePresentation): FilePresentation {
  return {
    ...group,
    files: (group.files || []).map((file) => ({
      ...file,
      path: normalizeArtifactPath(file.path) || file.path,
      render_kind: inferRenderKind(file.name || file.path, file.render_kind),
    })),
  }
}

export function collectPresentations(message: ChatMessage): FilePresentation[] {
  return presentationsForMessage(message)
}

function makeGroupPusher(seen: Set<string>) {
  return (group: FilePresentation | null | undefined, into: FilePresentation[]) => {
    if (!group) return
    const normalized = normalizePresentation(group)
    const files = normalized.files.filter((file) => {
      const key = file.path || file.name
      if (!key || seen.has(key)) return false
      if (!isOutputArtifactFile(file.name || file.path, file.render_kind, file.path)) return false
      seen.add(key)
      return true
    })
    if (!files.length) return
    into.push({ ...normalized, files })
  }
}

function presentationsFromStep(step: TurnStep): FilePresentation[] {
  const seen = new Set<string>()
  const groups: FilePresentation[] = []
  const pushGroup = makeGroupPusher(seen)
  if (step.kind === 'tool') {
    pushGroup(extractPresentation(step.data), groups)
    if (step.tool === 'present_file') {
      const args = parseStepArgs(step.args)
      const files = coercePresentPaths(args.paths ?? args.path)
        .map((raw) => {
          const path = normalizeArtifactPath(raw)
          if (!path) return null
          const name = fileNameFromPath(path)
          return {
            name,
            path,
            size: 0,
            mime: '',
            render_kind: inferRenderKind(name),
          } satisfies PresentedFile
        })
        .filter((file): file is PresentedFile => !!file)
      if (files.length) {
        pushGroup(
          {
            kind: 'files',
            title: typeof args.title === 'string' ? args.title : undefined,
            description:
              typeof args.description === 'string' ? args.description : undefined,
            files,
          },
          groups,
        )
      }
    }
  }
  if (step.kind === 'squad') {
    const squadFiles: PresentedFile[] = []
    for (const task of step.tasks || []) {
      for (const raw of task.artifacts || []) {
        const path = normalizeArtifactPath(String(raw || '').trim())
        if (!path) continue
        const name = fileNameFromPath(path)
        squadFiles.push({
          name,
          path,
          size: 0,
          mime: '',
          render_kind: inferRenderKind(name),
        })
      }
    }
    if (squadFiles.length) {
      pushGroup({ kind: 'files', title: step.title, files: squadFiles }, groups)
    }
  }
  return groups
}

export function presentationsForMessage(message: ChatMessage): FilePresentation[] {
  const seen = new Set<string>()
  const groups: FilePresentation[] = []
  const pushGroup = makeGroupPusher(seen)
  for (const step of message.steps || []) {
    for (const group of presentationsFromStep(step)) pushGroup(group, groups)
  }
  for (const group of message.presentedFiles || []) pushGroup(group, groups)
  return groups
}

function fileNameFromPath(path: string): string {
  const cleaned = path.replace(/\\/g, '/').replace(/\/+$/, '')
  const parts = cleaned.split('/')
  return parts[parts.length - 1] || path
}

export function coercePresentPaths(raw: unknown): string[] {
  if (raw == null) return []
  if (Array.isArray(raw)) {
    return raw.flatMap((item) => coercePresentPaths(item)).filter(Boolean)
  }
  if (typeof raw !== 'string') {
    const text = String(raw).trim()
    return text ? [text] : []
  }
  const text = raw.trim()
  if (!text) return []
  if (
    (text.startsWith('[') && text.endsWith(']')) ||
    (text.startsWith('{') && text.endsWith('}'))
  ) {
    try {
      return coercePresentPaths(JSON.parse(text))
    } catch {
      // 继续按普通字符串处理
    }
  }
  if (text.length >= 2 && text.startsWith('"') && text.endsWith('"')) {
    try {
      return coercePresentPaths(JSON.parse(text))
    } catch {
      // 继续按普通字符串处理
    }
  }
  if (text.includes(',')) {
    const parts = text
      .split(',')
      .map((p) => p.trim().replace(/^['"]+|['"]+$/g, ''))
      .filter(Boolean)
    if (parts.length > 1) return parts
  }
  return [text.replace(/^['"]+|['"]+$/g, '')]
}

export function normalizeArtifactPath(raw: string): string {
  let p = raw.trim().replace(/\\/g, '/')
  p = p.replace(/^[['"\s]+|[\]'"\s]+$/g, '')
  if (!p) return ''
  const marker = '/workspace/'
  const idx = p.toLowerCase().indexOf(marker)
  if (idx >= 0) return p.slice(idx + 1)
  const name = p.split('/').filter(Boolean).pop() || ''
  if (/^[a-zA-Z]:\//.test(p) || p.startsWith('/')) {
    return name ? `workspace/${name}` : ''
  }
  if (p.startsWith('workspace/')) return p
  return `workspace/${p}`
}

export function artifactPathCandidates(path: string): string[] {
  const p = path.replace(/\\/g, '/').replace(/^\/+/, '')
  if (!p) return []
  const out = [p]
  if (p.startsWith('workspace/')) out.push(p.slice('workspace/'.length))
  else out.push(`workspace/${p}`)
  return [...new Set(out.filter(Boolean))]
}

function parseStepArgs(raw: string): Record<string, unknown> {
  const text = (raw || '').trim()
  if (!text) return {}
  try {
    const parsed = JSON.parse(text)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    return {}
  }
  return {}
}

export function toPresentedFile(item: ConversationArtifact): PresentedFile {
  if (item.presented) {
    return {
      ...item.presented,
      path: normalizeArtifactPath(item.presented.path || item.path) || item.path,
      name: item.presented.name || item.name,
      render_kind: inferRenderKind(
        item.presented.name || item.name || item.path,
        item.presented.render_kind,
      ),
    }
  }
  return {
    name: item.name,
    path: item.path,
    size: item.size,
    mime: '',
    render_kind: inferRenderKind(item.name),
  }
}

export function artifactsToPresentations(
  items: ConversationArtifact[],
): FilePresentation[] {
  const groups: FilePresentation[] = []
  const indexByKey = new Map<string, number>()
  const seen = new Set<string>()
  for (const item of items) {
    const file = toPresentedFile(item)
    const fileKey = file.path || file.name
    if (!fileKey || seen.has(fileKey)) continue
    seen.add(fileKey)
    const key = item.groupTitle || ''
    let idx = indexByKey.get(key)
    if (idx == null) {
      idx = groups.length
      indexByKey.set(key, idx)
      groups.push({
        kind: 'files',
        title: item.groupTitle,
        description: item.groupDescription,
        files: [],
      })
    }
    groups[idx].files.push(file)
  }
  return groups.filter((group) => group.files.length > 0)
}

function pushUnique(
  map: Map<string, ConversationArtifact>,
  item: ConversationArtifact,
) {
  const key = item.path || `${item.source}:${item.name}:${item.messageId}`
  const existing = map.get(key)
  if (!existing || item.createdAt >= existing.createdAt) {
    map.set(key, item)
  }
}

export function collectConversationArtifacts(messages: ChatMessage[]): {
  submissions: ConversationArtifact[]
  artifacts: ConversationArtifact[]
} {
  const submissions = new Map<string, ConversationArtifact>()
  const artifacts = new Map<string, ConversationArtifact>()

  for (const message of messages) {
    if (message.role === 'user') {
      for (const att of message.attachments || []) {
        if (!att.path && !att.name) continue
        pushUnique(submissions, {
          id: `sub:${message.id}:${att.path || att.name}`,
          source: 'submission',
          name: att.name || fileNameFromPath(att.path),
          path: att.path,
          size: att.size || 0,
          createdAt: message.createdAt,
          messageId: message.id,
          presented: {
            name: att.name || fileNameFromPath(att.path),
            path: att.path,
            size: att.size || 0,
            mime: '',
            render_kind: inferRenderKind(att.name, att.kind),
          },
        })
      }
      continue
    }

    const presentations = presentationsForMessage(message)
    for (const group of presentations) {
      for (const file of group.files || []) {
        if (!file.path && !file.name) continue
        const path = normalizeArtifactPath(file.path) || file.path
        pushUnique(artifacts, {
          id: `art:${message.id}:${path || file.name}`,
          source: 'artifact',
          name: file.name || fileNameFromPath(path),
          path,
          size: file.size || 0,
          createdAt: message.createdAt,
          messageId: message.id,
          groupTitle: group.title,
          groupDescription: group.description,
          presented: file,
        })
      }
    }
  }

  const byTimeDesc = (a: ConversationArtifact, b: ConversationArtifact) =>
    b.createdAt - a.createdAt

  return {
    submissions: [...submissions.values()].sort(byTimeDesc),
    artifacts: [...artifacts.values()].sort(byTimeDesc),
  }
}

export interface DiskDeliverable {
  path: string
  name: string
  size: number
  mtime: number
  group: string
}

export interface StageOutputSegment {
  afterStepId: string
  title?: string
  presentations: FilePresentation[]
}

const CN_STAGE_NUM: Record<string, string> = {
  一: '1',
  二: '2',
  三: '3',
  四: '4',
  五: '5',
  六: '6',
  七: '7',
  八: '8',
  九: '9',
}

export function stageKeyFromText(text: string): string | null {
  const raw = (text || '').replace(/\\/g, '/')
  const lower = raw.toLowerCase()
  if (/[\\/]charters[\\/]/.test(lower) || /章程/.test(raw)) return 'charter'
  if (/[\\/]manuscript[\\/]/.test(lower) || /文稿|sci_manuscript/.test(lower)) {
    return 'manuscript'
  }
  const habitatLevel = lower.match(/(?:^|[\\/\s_-])l([123])(?:[_\s.-]|$)/)
  if (habitatLevel || /habitat/.test(lower)) {
    if (habitatLevel) return `habitat:l${habitatLevel[1]}`
    if (/habitat/.test(lower)) return 'habitat'
  }
  const stage = raw.match(/阶段\s*([1-9一二三四五六七八九])/) || lower.match(/stage\s*([1-9])/)
  if (stage) {
    const n = CN_STAGE_NUM[stage[1]] || stage[1]
    return `stage:${n}`
  }
  if (
    /总交付|deliver_summary|deliver_stage|最终产出|研究方案/.test(raw) ||
    /\.docx$/i.test(lower)
  ) {
    return 'final'
  }
  return null
}

export function stageKeyFromPath(path: string): string {
  return stageKeyFromText(path) || 'other'
}

function keysCompatible(fileKey: string, messageKeys: Set<string>): boolean {
  if (messageKeys.has(fileKey)) return true
  if (fileKey === 'habitat' && [...messageKeys].some((k) => k.startsWith('habitat'))) {
    return true
  }
  if (fileKey.startsWith('habitat:') && messageKeys.has('habitat')) return true
  if (fileKey === 'other') return false
  return false
}

function charterAdvance(
  step: TurnStep,
): { name: string; index: number } | null {
  if (step.kind !== 'tool' || step.tool !== 'task_charter' || step.status === 'failed') {
    return null
  }
  const args = parseStepArgs(step.args)
  const action = String(args.action || '')
  if (action && action !== 'advance_stage') return null
  const data =
    step.data && typeof step.data === 'object'
      ? (step.data as Record<string, unknown>)
      : {}
  const index = Number(data.stage_done_index || 0)
  const name = String(data.stage_done || '')
  if (action === 'advance_stage' || index > 0 || name) {
    return { name, index }
  }
  return null
}

export function inferMessageStageKeys(message: ChatMessage): Set<string> {
  const keys = new Set<string>()
  const add = (value: string | null | undefined) => {
    if (value) keys.add(value)
  }
  add(stageKeyFromText(message.text || ''))
  for (const group of presentationsForMessage(message)) {
    add(stageKeyFromText(group.title || ''))
    for (const file of group.files || []) {
      add(stageKeyFromPath(file.path || file.name))
    }
  }
  for (const step of message.steps || []) {
    const done = charterAdvance(step)
    if (done) {
      add(done.index > 0 ? `stage:${done.index}` : null)
      add(stageKeyFromText(done.name))
    }
    if (step.kind === 'tool') {
      add(stageKeyFromText(step.args || ''))
      add(stageKeyFromText(step.output || ''))
    }
  }
  keys.delete('other')
  return keys
}

function diskToPresentation(item: DiskDeliverable, title?: string): FilePresentation {
  const path = normalizeArtifactPath(item.path) || item.path
  return {
    kind: 'files',
    title: title || item.group,
    files: [
      {
        name: item.name,
        path,
        size: item.size,
        mime: '',
        render_kind: inferRenderKind(item.name),
      },
    ],
  }
}

function mergePresentationLists(
  seen: Set<string>,
  into: FilePresentation[],
  groups: FilePresentation[],
) {
  const pushGroup = makeGroupPusher(seen)
  for (const group of groups) pushGroup(group, into)
}

export function partitionTurnOutputs(
  message: ChatMessage,
  extras: DiskDeliverable[] = [],
): { stageSegments: StageOutputSegment[]; final: FilePresentation[] } {
  const seen = new Set<string>()
  const stageSegments: StageOutputSegment[] = []
  let buffer: FilePresentation[] = []
  let remaining = [...extras]

  const takeExtras = (stageKey: string | null, title?: string) => {
    if (!remaining.length) return [] as FilePresentation[]
    const keep: DiskDeliverable[] = []
    const taken: FilePresentation[] = []
    for (const item of remaining) {
      const key = stageKeyFromPath(item.path)
      const match = Boolean(stageKey) && key === stageKey
      if (match) {
        taken.push(diskToPresentation(item, title || item.group))
      } else {
        keep.push(item)
      }
    }
    remaining = keep
    return taken
  }

  const flush = (afterStepId: string, title?: string, stageKey?: string | null) => {
    const groups: FilePresentation[] = []
    mergePresentationLists(seen, groups, buffer)
    buffer = []
    if (stageKey) mergePresentationLists(seen, groups, takeExtras(stageKey, title))
    if (!groups.length) return
    stageSegments.push({ afterStepId, title, presentations: groups })
  }

  for (const step of message.steps || []) {
    const groups = presentationsFromStep(step)
    if (groups.length) buffer.push(...groups)
    const done = charterAdvance(step)
    if (done) {
      const key =
        (done.index > 0 ? `stage:${done.index}` : null) ||
        stageKeyFromText(done.name) ||
        'stage'
      const title = done.name
        ? done.index > 0
          ? `阶段 ${done.index} · ${done.name}`
          : done.name
        : `阶段 ${done.index || ''}`.trim()
      flush(step.id, title, key)
    }
  }

  const final: FilePresentation[] = []
  if (!message.streaming) {
    mergePresentationLists(seen, final, buffer)
    for (const group of message.presentedFiles || []) {
      mergePresentationLists(seen, final, [group])
    }
    mergePresentationLists(seen, final, remaining.map((item) => diskToPresentation(item)))
  }
  return { stageSegments, final }
}

export function assignDiskFilesToMessages(
  messages: ChatMessage[],
  disk: DiskDeliverable[],
): Map<string, DiskDeliverable[]> {
  const assigned = new Map<string, DiskDeliverable[]>()
  const assistants = messages.filter((m) => m.role === 'assistant')
  if (!assistants.length || !disk.length) return assigned

  const presented = new Set<string>()
  const keysById = new Map<string, Set<string>>()
  for (const message of assistants) {
    keysById.set(message.id, inferMessageStageKeys(message))
    for (const group of presentationsForMessage(message)) {
      for (const file of group.files || []) {
        const path = normalizeArtifactPath(file.path) || file.path
        if (path) presented.add(path)
      }
    }
  }
  const lastId = assistants[assistants.length - 1]?.id

  const push = (messageId: string, item: DiskDeliverable) => {
    const list = assigned.get(messageId) || []
    list.push(item)
    assigned.set(messageId, list)
  }

  for (const item of disk) {
    const path = normalizeArtifactPath(item.path) || item.path
    if (!path || presented.has(path)) continue
    if (!isOutputArtifactFile(item.name || path, undefined, path)) continue
    const fileKey = stageKeyFromPath(path)
    if (fileKey === 'final' || fileKey === 'other') continue
    const matches = assistants.filter((m) =>
      keysCompatible(fileKey, keysById.get(m.id) || new Set()),
    )
    const withoutLast =
      lastId && matches.length > 1
        ? matches.filter((m) => m.id !== lastId)
        : matches
    const pool = withoutLast.length ? withoutLast : matches
    if (pool.length === 1) {
      push(pool[0].id, item)
      continue
    }
    if (pool.length > 1) {
      const mtime = item.mtime * 1000
      let best = pool[0]
      let bestDelta = Number.POSITIVE_INFINITY
      for (const candidate of pool) {
        const end = candidate.finishedAt || candidate.createdAt
        const delta = Math.abs(end - mtime)
        if (delta < bestDelta) {
          best = candidate
          bestDelta = delta
        }
      }
      push(best.id, item)
    }
  }
  return assigned
}

export function latestFinalArtifacts(
  messages: ChatMessage[],
  disk: DiskDeliverable[] = [],
): ConversationArtifact[] {
  let last: ChatMessage | undefined
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'assistant') {
      last = messages[i]
      break
    }
  }
  if (!last) return []
  const extras = assignDiskFilesToMessages(messages, disk).get(last.id) || []
  const { stageSegments, final } = partitionTurnOutputs(last, extras)
  const groups = final.length
    ? final
    : stageSegments[stageSegments.length - 1]?.presentations || []
  const out: ConversationArtifact[] = []
  for (const group of groups) {
    for (const file of group.files || []) {
      const path = normalizeArtifactPath(file.path) || file.path
      if (!path && !file.name) continue
      out.push({
        id: `final:${last.id}:${path || file.name}`,
        source: 'artifact',
        name: file.name || fileNameFromPath(path),
        path,
        size: file.size || 0,
        createdAt: last.createdAt,
        messageId: last.id,
        groupTitle: group.title,
        groupDescription: group.description,
        presented: file,
      })
    }
  }
  return out
}

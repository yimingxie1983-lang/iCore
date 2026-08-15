import type { ChatMessage } from '@/application/state/chatStore'
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
  if (CODE_EXTS.has(ext)) return 'code'
  return 'download'
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

export function collectPresentations(message: ChatMessage): FilePresentation[] {
  const fromSteps: FilePresentation[] = []
  for (const step of message.steps || []) {
    if (step.kind !== 'tool') continue
    if (step.tool !== 'present_file') continue
    if (step.status !== 'success') continue
    const p = extractPresentation(step.data)
    if (p) fromSteps.push(p)
  }
  if (fromSteps.length > 0) return fromSteps
  return message.presentedFiles || []
}

function fileNameFromPath(path: string): string {
  const cleaned = path.replace(/\\/g, '/').replace(/\/+$/, '')
  const parts = cleaned.split('/')
  return parts[parts.length - 1] || path
}

export function toPresentedFile(item: ConversationArtifact): PresentedFile {
  if (item.presented) return item.presented
  return {
    name: item.name,
    path: item.path,
    size: item.size,
    mime: '',
    render_kind: inferRenderKind(item.name),
  }
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

    const presentations = collectPresentations(message)
    for (const group of presentations) {
      for (const file of group.files || []) {
        if (!file.path && !file.name) continue
        pushUnique(artifacts, {
          id: `art:${message.id}:${file.path || file.name}`,
          source: 'artifact',
          name: file.name || fileNameFromPath(file.path),
          path: file.path,
          size: file.size || 0,
          createdAt: message.createdAt,
          messageId: message.id,
          groupTitle: group.title,
          groupDescription: group.description,
          presented: file,
        })
      }
    }

    for (const step of message.steps || []) {
      if (step.kind !== 'squad') continue
      for (const task of step.tasks || []) {
        for (const raw of task.artifacts || []) {
          const path = String(raw || '').trim()
          if (!path) continue
          const name = fileNameFromPath(path)
          pushUnique(artifacts, {
            id: `squad:${message.id}:${path}`,
            source: 'artifact',
            name,
            path,
            size: 0,
            createdAt: message.createdAt,
            messageId: message.id,
            groupTitle: task.title || step.title,
          })
        }
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

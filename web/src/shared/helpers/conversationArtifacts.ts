import type { ChatMessage } from '@/application/state/chatStore'
import type { FilePresentation } from '@/client/services/client'

export type ArtifactSource = 'submission' | 'artifact'

export interface ConversationArtifact {
  id: string
  source: ArtifactSource
  name: string
  path: string
}

function fileNameFromPath(path: string): string {
  const cleaned = path.replace(/\\/g, '/').replace(/\/+$/, '')
  const parts = cleaned.split('/')
  return parts[parts.length - 1] || path
}

function extractPresentation(data: unknown): FilePresentation | null {
  if (!data || typeof data !== 'object') return null
  const p = (data as { presentation?: unknown }).presentation
  if (!p || typeof p !== 'object') return null
  const cast = p as Partial<FilePresentation>
  if (cast.kind !== 'files') return null
  if (!Array.isArray(cast.files) || cast.files.length === 0) return null
  return cast as FilePresentation
}

function collectPresentations(message: ChatMessage): FilePresentation[] {
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

function pushUnique(
  map: Map<string, ConversationArtifact>,
  item: ConversationArtifact,
) {
  const key = item.path || `${item.source}:${item.name}`
  if (!map.has(key)) map.set(key, item)
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
        })
      }
      continue
    }

    for (const group of collectPresentations(message)) {
      for (const file of group.files || []) {
        if (!file.path && !file.name) continue
        pushUnique(artifacts, {
          id: `art:${message.id}:${file.path || file.name}`,
          source: 'artifact',
          name: file.name || fileNameFromPath(file.path),
          path: file.path,
        })
      }
    }

    for (const step of message.steps || []) {
      if (step.kind !== 'squad') continue
      for (const task of step.tasks || []) {
        for (const raw of task.artifacts || []) {
          const path = String(raw || '').trim()
          if (!path) continue
          pushUnique(artifacts, {
            id: `squad:${message.id}:${path}`,
            source: 'artifact',
            name: fileNameFromPath(path),
            path,
          })
        }
      }
    }
  }

  return {
    submissions: [...submissions.values()],
    artifacts: [...artifacts.values()],
  }
}

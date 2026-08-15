import { useMemo } from 'react'
import { Package, Upload } from 'lucide-react'

import type { ChatMessage } from '@/application/state/chatStore'
import {
  collectConversationArtifacts,
  type ConversationArtifact,
} from '@/shared/helpers/conversationArtifacts'

function FileList({ items, empty }: { items: ConversationArtifact[]; empty: string }) {
  if (items.length === 0) {
    return <div className="px-0.5 py-2 text-[12px] text-muted-foreground">{empty}</div>
  }
  return (
    <ul className="flex flex-col">
      {items.map((item) => (
        <li
          key={item.id}
          className="truncate rounded px-1 py-1 text-[13px] text-foreground"
          title={item.name}
        >
          {item.name}
        </li>
      ))}
    </ul>
  )
}

export default function ArtifactsPane({ messages }: { messages: ChatMessage[] }) {
  const { submissions, artifacts } = useMemo(
    () => collectConversationArtifacts(messages),
    [messages],
  )

  return (
    <div className="flex h-full min-h-0 flex-col">
      <section className="flex min-h-0 flex-1 flex-col border-b border-border pb-3">
        <div className="mb-1 flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground">
          <Upload className="h-3.5 w-3.5" />
          提交物
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <FileList items={submissions} empty="本会话还没有提交文件" />
        </div>
      </section>
      <section className="flex min-h-0 flex-1 flex-col pt-3">
        <div className="mb-1 flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground">
          <Package className="h-3.5 w-3.5" />
          产出物
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <FileList items={artifacts} empty="本会话还没有产出文件" />
        </div>
      </section>
    </div>
  )
}

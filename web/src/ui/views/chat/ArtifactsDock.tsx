import { useMemo } from 'react'
import { X } from 'lucide-react'

import type { ChatMessage } from '@/application/state/chatStore'
import {
  collectConversationArtifacts,
  type ConversationArtifact,
} from '@/shared/helpers/conversationArtifacts'
import { cn } from '@/shared/foundation/utils'

function FileList({ items }: { items: ConversationArtifact[] }) {
  if (items.length === 0) {
    return <div className="px-1.5 text-[11px] text-muted-foreground/70">无</div>
  }
  return (
    <div className="flex flex-col">
      {items.map((item) => (
        <div
          key={item.id}
          className="truncate px-1.5 py-0.5 text-[12px] leading-tight text-foreground"
          title={item.name}
        >
          {item.name}
        </div>
      ))}
    </div>
  )
}

interface Props {
  projectId: string
  messages: ChatMessage[]
  open: boolean
  onOpenChange: (open: boolean) => void
}

export default function ArtifactsDock({
  messages,
  open,
  onOpenChange,
}: Props) {
  const { submissions, artifacts } = useMemo(
    () => collectConversationArtifacts(messages),
    [messages],
  )

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => onOpenChange(true)}
        className="absolute right-3 top-3 z-20 rounded-full border border-border bg-card px-2 py-1 text-[11px] text-muted-foreground shadow-card hover:text-foreground"
      >
        产物
      </button>
    )
  }

  return (
    <aside
      className={cn(
        'absolute right-3 top-3 z-20 flex w-[110px] max-w-[calc(100%-1.5rem)]',
        'h-[min(40vh,320px)] flex-col overflow-hidden rounded-lg border border-border bg-card shadow-card',
      )}
      aria-label="产物"
    >
      <div className="flex h-7 shrink-0 items-center border-b border-border px-1.5">
        <span className="min-w-0 flex-1 truncate text-[11px] font-medium">产物</span>
        <button
          type="button"
          className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground"
          title="收起"
          onClick={() => onOpenChange(false)}
        >
          <X className="h-3 w-3" />
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        <section className="flex min-h-0 flex-1 flex-col border-b border-border">
          <div className="shrink-0 px-1.5 py-1 text-[10.5px] text-muted-foreground">提交物</div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <FileList items={submissions} />
          </div>
        </section>
        <section className="flex min-h-0 flex-1 flex-col">
          <div className="shrink-0 px-1.5 py-1 text-[10.5px] text-muted-foreground">产出物</div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <FileList items={artifacts} />
          </div>
        </section>
      </div>
    </aside>
  )
}

export function readArtifactsDockOpen(): boolean {
  return true
}



import { Activity, X } from 'lucide-react'

import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/ui/widgets/ui/sheet'
import EventTimeline from '@/ui/views/chat/EventTimeline'
import { personaIcon, personaName } from '@/shared/foundation/personas'
import { cn } from '@/shared/foundation/utils'
import type { ChatEvent } from '@/application/state/chatStore'

export interface TraceDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void

  personaId?: string

  title?: string

  statusLabel?: string

  traceEvents?: ChatEvent[]

  emptyHint?: string
}

export function TraceDrawer({
  open,
  onOpenChange,
  personaId,
  title,
  statusLabel,
  traceEvents,
  emptyHint,
}: TraceDrawerProps) {
  const events = traceEvents || []

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"

        className="flex w-full flex-col gap-0 p-0 sm:max-w-[480px] md:max-w-[640px] lg:max-w-[720px]"
        hideClose
      >
        {}
        <SheetHeader
          className={cn(
            'sticky top-0 z-10 flex flex-row items-center gap-2 border-b border-border bg-background/95 px-4 py-3 backdrop-blur',
          )}
        >
          <span className="text-[16px] leading-none" aria-hidden>
            {personaIcon(personaId)}
          </span>
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <SheetTitle className="flex items-center gap-1.5 truncate text-[13px]">
              <span className="truncate" title={personaId}>
                {personaName(personaId) || '默认人格'}
              </span>
              {statusLabel && (
                <span className="shrink-0 rounded bg-muted/60 px-1.5 py-0.5 text-[10.5px] font-normal text-muted-foreground">
                  {statusLabel}
                </span>
              )}
            </SheetTitle>
            {title && (
              <SheetDescription className="line-clamp-1 text-[11px]">
                {title}
              </SheetDescription>
            )}
          </div>
          <SheetClose asChild>
            <button
              type="button"
              className="rounded p-1 text-muted-foreground hover:bg-muted/60 hover:text-foreground"
              aria-label="关闭"
            >
              <X className="h-4 w-4" />
            </button>
          </SheetClose>
        </SheetHeader>

        {}
        <div className="min-h-0 flex-1 overflow-auto px-3 py-3">
          {events.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-[12px] text-muted-foreground">
              <Activity className="h-5 w-5 opacity-60" />
              <p>{emptyHint || '本子智能体还没产生事件，等等再来。'}</p>
            </div>
          ) : (
            <EventTimeline events={events} />
          )}
        </div>

        {}
        <div className="shrink-0 border-t border-border bg-card-muted/40 px-4 py-2 text-[10.5px] text-muted-foreground">
          共 {events.length} 条事件 · ESC 或点击外部关闭
        </div>
      </SheetContent>
    </Sheet>
  )
}

export default TraceDrawer

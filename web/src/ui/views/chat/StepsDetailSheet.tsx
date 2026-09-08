import { ListOrdered } from 'lucide-react'

import type { ChatMessage } from '@/application/state/chatStore'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/ui/widgets/ui/sheet'
import TurnSteps from './TurnSteps'

export default function StepsDetailSheet({
  open,
  onOpenChange,
  message,
  streaming,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  message: ChatMessage | null
  streaming?: boolean
}) {
  const steps = message?.steps || []
  const live = Boolean(streaming && message?.streaming)

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col p-0 sm:max-w-lg">
        <SheetHeader className="border-b border-border px-5 pb-3 pt-5">
          <SheetTitle className="flex items-center gap-2">
            <ListOrdered className="h-4 w-4 text-secondary" />
            执行步骤
          </SheetTitle>
          <SheetDescription>
            {live
              ? '当前任务正在执行，以下为完整步骤与工具详情'
              : steps.length > 0
                ? `本轮共 ${steps.length} 条步骤记录`
                : '发送任务后，这里会显示完整执行细节'}
          </SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {steps.length > 0 || live ? (
            <TurnSteps steps={steps} streaming={live} />
          ) : (
            <div className="flex h-full min-h-[200px] items-center justify-center px-4 text-center">
              <div className="max-w-xs space-y-2">
                <p className="text-sm font-medium text-foreground">暂无执行步骤</p>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  主界面只显示精简摘要；完整思考、工具参数与输出会集中在这里。
                </p>
              </div>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

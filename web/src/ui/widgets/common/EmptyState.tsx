

import { cn } from '@/shared/foundation/utils'

interface EmptyStateProps {
  icon?: React.ComponentType<{ className?: string }>
  title: string
  description?: React.ReactNode

  action?: React.ReactNode

  secondaryAction?: React.ReactNode
  className?: string

  compact?: boolean
}

export default function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  secondaryAction,
  className,
  compact = false,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card-muted text-center',
        compact ? 'px-6 py-10' : 'px-8 py-16',
        className,
      )}
    >
      {Icon && (
        <div
          className={cn(
            'mb-4 flex items-center justify-center rounded-2xl bg-primary/[0.06] text-primary',
            compact ? 'h-10 w-10' : 'h-14 w-14',
          )}
        >
          <Icon className={compact ? 'h-5 w-5' : 'h-7 w-7'} />
        </div>
      )}
      <h3
        className={cn(
          'font-semibold tracking-tight text-foreground',
          compact ? 'text-sm' : 'text-base',
        )}
      >
        {title}
      </h3>
      {description && (
        <p className="mt-1.5 max-w-md text-[13px] leading-relaxed text-muted-foreground">
          {description}
        </p>
      )}
      {(action || secondaryAction) && (
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
          {action}
          {secondaryAction}
        </div>
      )}
    </div>
  )
}

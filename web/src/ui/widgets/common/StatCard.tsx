

import { cn } from '@/shared/foundation/utils'

interface StatCardProps {
  label: string
  value: React.ReactNode
  hint?: React.ReactNode

  icon?: React.ComponentType<{ className?: string }>
  iconTone?: 'primary' | 'secondary' | 'accent' | 'success' | 'warning' | 'destructive'
  className?: string
}

const TONE_CLASS: Record<NonNullable<StatCardProps['iconTone']>, string> = {
  primary: 'bg-primary/[0.08] text-primary',
  secondary: 'bg-secondary/[0.12] text-secondary',
  accent: 'bg-accent/[0.14] text-accent',
  success: 'bg-emerald-500/[0.12] text-emerald-600',
  warning: 'bg-amber-500/[0.14] text-amber-600',
  destructive: 'bg-destructive/[0.10] text-destructive',
}

export default function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  iconTone = 'primary',
  className,
}: StatCardProps) {
  return (
    <div
      className={cn(
        'surface-card surface-card-hover flex items-start gap-3 rounded-xl p-4',
        className,
      )}
    >
      {Icon && (
        <div
          className={cn(
            'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
            TONE_CLASS[iconTone],
          )}
        >
          <Icon className="h-4 w-4" />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
        <div className="mt-1 text-2xl font-semibold tracking-tight num-display text-foreground">
          {value}
        </div>
        {hint && <div className="mt-0.5 text-[11px] text-muted-foreground">{hint}</div>}
      </div>
    </div>
  )
}

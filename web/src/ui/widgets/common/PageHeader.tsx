

import { cn } from '@/shared/foundation/utils'

interface PageHeaderProps {
  title: string
  description?: React.ReactNode
  icon?: React.ComponentType<{ className?: string }>

  actions?: React.ReactNode

  stats?: React.ReactNode
  className?: string
}

export default function PageHeader({
  title,
  description,
  icon: Icon,
  actions,
  stats,
  className,
}: PageHeaderProps) {
  return (
    <div className={cn('hero-surface rounded-2xl px-6 py-5 lg:px-8 lg:py-6', className)}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0">
          {Icon && (
            <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/[0.08] text-primary">
              <Icon className="h-5 w-5" />
            </div>
          )}
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-foreground lg:text-2xl">
              {title}
            </h1>
            {description && (
              <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
                {description}
              </p>
            )}
          </div>
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>

      {stats && <div className="mt-5">{stats}</div>}
    </div>
  )
}

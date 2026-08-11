

import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/shared/foundation/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
  {
    variants: {
      variant: {
        default:
          'border-transparent bg-primary text-primary-foreground hover:bg-primary/85',
        secondary:
          'border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80',
        accent:
          'border-transparent bg-accent text-accent-foreground hover:bg-accent/85',
        destructive:
          'border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/85',
        outline: 'text-foreground border-border',
        success:
          'border-transparent bg-emerald-600 text-white hover:bg-emerald-600/85',
        warning:
          'border-transparent bg-amber-500 text-white hover:bg-amber-500/85',
        muted:
          'border-transparent bg-muted text-muted-foreground',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }

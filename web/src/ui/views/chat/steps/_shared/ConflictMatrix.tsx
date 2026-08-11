

import { cn } from '@/shared/foundation/utils'
import { personaIcon, personaName } from '@/shared/foundation/personas'
import type { CouncilRoleState, CouncilVerdictState } from '@/application/state/chatStore'

export interface ConflictMatrixProps {
  conflictMatrix: NonNullable<CouncilVerdictState['conflictMatrix']>
  roles: CouncilRoleState[]
}

type PositionType = 'support' | 'against' | 'unknown' | 'neutral'

function classifyPosition(value: string): PositionType {
  const lower = value.toLowerCase().trim()

  if (
    lower.includes('中立') ||
    lower.includes('中性') ||
    lower.includes('观望') ||
    lower.includes('待定') ||
    lower.includes('neutral') ||
    lower.includes('abstain')
  ) {
    return 'neutral'
  }
  if (
    lower.includes('反对') ||
    lower.includes('against') ||
    lower.includes('否决') ||
    lower.includes('不支持') ||
    lower.includes('不推荐') ||
    lower.includes('反驳')
  ) {
    return 'against'
  }
  if (
    lower.includes('支持') ||
    lower.includes('support') ||
    lower.includes('赞同') ||
    lower.includes('推荐') ||
    lower.includes('同意') ||
    lower.includes('赞成')
  ) {
    return 'support'
  }
  return 'unknown'
}

const POSITION_LABEL_CN: Record<PositionType, string> = {
  support: '支持',
  against: '反对',
  neutral: '中立',
  unknown: '不确定',
}

const POSITION_ICON: Record<PositionType, string> = {
  support: '✓',
  against: '✕',
  neutral: '—',
  unknown: '?',
}

function PositionCell({ value, posType }: { value: string; posType: PositionType }) {

  const label = POSITION_LABEL_CN[posType]
  const icon = POSITION_ICON[posType]
  return (
    <td
      className={cn(
        'border border-border/50 px-1.5 py-1 text-center text-[11px]',
        posType === 'support' &&
          'bg-emerald-500/[0.06] text-emerald-700 dark:text-emerald-400',
        posType === 'against' &&
          'bg-red-500/[0.06] text-red-700 dark:text-red-400',
        posType === 'neutral' &&
          'bg-amber-500/[0.06] text-amber-700 dark:text-amber-400',
        posType === 'unknown' && 'text-muted-foreground',
      )}
      title={value }
    >
      <span className="inline-flex items-center gap-1 font-medium">
        <span className="text-[10.5px]" aria-hidden>
          {icon}
        </span>
        <span>{label}</span>
      </span>
    </td>
  )
}

export default function ConflictMatrix({ conflictMatrix, roles }: ConflictMatrixProps) {
  if (!conflictMatrix || conflictMatrix.length === 0) return null

  const allRoleKeys = new Set<string>()
  for (const row of conflictMatrix) {
    for (const key of Object.keys(row.positions)) {
      allRoleKeys.add(key)
    }
  }
  const roleKeys = Array.from(allRoleKeys)

  const roleDisplayMap: Record<string, { label: string; icon: string }> = {}
  for (const key of roleKeys) {
    const matched = roles.find(
      (r) => r.roleId === key || r.personaId === key,
    )
    if (matched) {

      roleDisplayMap[key] = {
        label: personaName(matched.personaId),
        icon: personaIcon(matched.personaId),
      }
    } else {

      roleDisplayMap[key] = { label: key, icon: '🧑' }
    }
  }

  return (
    <div className="overflow-x-auto rounded border border-border/50">
      <table className="w-full border-collapse text-[10.5px]">
        <thead>
          <tr className="bg-muted/30">
            <th className="border border-border/50 px-2 py-1 text-left font-medium text-muted-foreground">
              争议轴
            </th>
            {roleKeys.map((key) => {
              const display = roleDisplayMap[key]
              return (
                <th
                  key={key}
                  className="border border-border/50 px-1.5 py-1 text-center font-medium text-muted-foreground"
                  title={`${display.icon} ${display.label}（${key}）`}
                >
                  <span className="inline-flex items-center gap-1 text-[10px]">
                    <span aria-hidden>{display.icon}</span>
                    <span>
                      {display.label.length > 8
                        ? display.label.slice(0, 7) + '…'
                        : display.label}
                    </span>
                  </span>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {conflictMatrix.map((row, i) => (
            <tr key={`${row.axis}-${i}`}>
              <td className="border border-border/50 px-2 py-1 text-[10.5px] font-medium text-foreground/80">
                {row.axis}
              </td>
              {roleKeys.map((key) => {
                const value = row.positions[key] || '—'
                const posType = value === '—' ? 'unknown' : classifyPosition(value)
                return (
                  <PositionCell
                    key={`${row.axis}-${key}`}
                    value={value}
                    posType={posType}
                  />
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

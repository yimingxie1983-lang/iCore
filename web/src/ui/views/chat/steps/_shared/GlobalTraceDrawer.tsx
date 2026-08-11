

import { useMemo } from 'react'

import {
  useChatStore,
  type CouncilRoleState,
  type CouncilStep,
  type SquadStep,
  type SquadTaskState,
} from '@/application/state/chatStore'
import { TraceDrawer } from './TraceDrawer'

function squadStatusLabel(s: SquadTaskState['status']): string {
  if (s === 'pending') return '排队'
  if (s === 'running') return '进行中'
  if (s === 'success') return '完成'
  return '失败'
}
function councilStatusLabel(s: CouncilRoleState['status']): string {
  if (s === 'pending') return '排队'
  if (s === 'running') return '进行中'
  if (s === 'done') return '完成'
  return '失败'
}

export default function GlobalTraceDrawer() {
  const drawer = useChatStore((s) => s.traceDrawer)
  const closeDrawer = useChatStore((s) => s.closeTraceDrawer)
  const messages = useChatStore((s) => s.messages)

  const target = useMemo(() => {
    if (!drawer) return null
    for (const m of messages) {
      if (m.role !== 'assistant') continue
      for (const step of m.steps || []) {
        if (step.id !== drawer.stepId) continue
        if (drawer.kind === 'squad' && step.kind === 'squad') {
          const sq = step as SquadStep
          const t = sq.tasks.find((x) => x.taskId === drawer.laneId)
          if (t) return { kind: 'squad' as const, step: sq, task: t }
        }
        if (drawer.kind === 'council' && step.kind === 'council') {
          const co = step as CouncilStep
          const r = co.roles.find((x) => x.roleId === drawer.laneId)
          if (r) return { kind: 'council' as const, step: co, role: r }
        }
      }
    }
    return null
  }, [drawer, messages])

  if (!drawer) {

    return null
  }

  if (!target) {
    return (
      <TraceDrawer
        open={true}
        onOpenChange={(o) => {
          if (!o) closeDrawer()
        }}
        emptyHint="找不到对应子任务的事件流（消息可能已被清理）"
      />
    )
  }

  if (target.kind === 'squad') {
    const t = target.task
    return (
      <TraceDrawer
        open={true}
        onOpenChange={(o) => {
          if (!o) closeDrawer()
        }}
        personaId={t.personaId}
        title={t.title}
        statusLabel={squadStatusLabel(t.status)}
        traceEvents={t.traceEvents}
        emptyHint={
          t.status === 'pending'
            ? '子任务还没启动，等等再来。'
            : '该子任务还没产生事件流，可能是后端事件未冒泡。'
        }
      />
    )
  }

  const r = target.role
  return (
    <TraceDrawer
      open={true}
      onOpenChange={(o) => {
        if (!o) closeDrawer()
      }}
      personaId={r.personaId}
      title={`${r.roleId}（议会角色）`}
      statusLabel={councilStatusLabel(r.status)}
      traceEvents={r.traceEvents}
      emptyHint={
        r.status === 'pending'
          ? '该角色还没启动，等等再来。'
          : '该角色还没产生事件流，可能是后端事件未冒泡。'
      }
    />
  )
}

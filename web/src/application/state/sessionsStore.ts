

import { create } from 'zustand'
import { api, type SessionMeta, type SessionMessageRecord } from '@/client/services/client'
import { streamSessionLive } from '@/client/services/sse'
import { useChatStore } from './chatStore'

const PAGE_LIMIT = 20
const MESSAGE_LOAD_LIMIT = 50

const liveSubs = new Map<string, AbortController>()

const userStoppedSids = new Set<string>()

function abortAllLiveSubs() {
  for (const ctrl of liveSubs.values()) {
    try { ctrl.abort() } catch {  }
  }
  liveSubs.clear()
}

export function abortLiveSubForSession(
  sessionId: string | null | undefined,
  userStop = false,
): void {
  if (!sessionId) return
  if (userStop) userStoppedSids.add(sessionId)
  const sub = liveSubs.get(sessionId)
  if (!sub) return
  try { sub.abort() } catch {  }
  liveSubs.delete(sessionId)
}

async function attachLiveStream(
  projectId: string,
  sid: string,
  fromSeq: number,
  assistantId: string,
): Promise<void> {
  if (liveSubs.has(sid)) return
  const ctrl = new AbortController()
  liveSubs.set(sid, ctrl)

  const chat = useChatStore.getState()
  let finalState: 'done' | 'cancelled' | 'error' = 'done'
  let finalErr: string | undefined
  try {
    for await (const ev of streamSessionLive({
      projectId,
      sessionId: sid,
      fromSeq,
      signal: ctrl.signal,
    })) {
      if (ev.type === 'session_started') continue
      chat.ingestEvent(assistantId, ev)
      if (ev.type === 'error') {
        const errMsg = String(
          (ev as Record<string, unknown>).error ||
          (ev as Record<string, unknown>).content ||
          '推理失败',
        )
        if (errMsg.includes('取消')) {
          finalState = 'cancelled'
          finalErr = errMsg
        } else {
          finalState = 'error'
          finalErr = errMsg
        }
        break
      }
      if (ev.type === 'done') break
    }
  } catch (e: unknown) {
    if ((e as { name?: string })?.name === 'AbortError') {
      finalState = 'cancelled'
      finalErr = userStoppedSids.has(sid)
        ? '用户中断了流'
        : '已断开续看（后台推理继续）'
      userStoppedSids.delete(sid)
    } else {
      finalState = 'error'
      finalErr = e instanceof Error ? e.message : String(e)
    }
  } finally {
    liveSubs.delete(sid)
    useChatStore.getState().finishAssistantTurn(assistantId, finalState, finalErr)

    if (finalState === 'done') {
      const st = useSessionsStore.getState()
      if (st.projectId === projectId) void st.refreshSessionList()
    }
  }
}

interface SessionsState {

  projectId: string | null

  sessionId: string | null

  list: SessionMeta[]
  listTotal: number
  listOffset: number
  listLoading: boolean

  listLoadingMore: boolean

  hasMoreOlder: boolean
  loadingOlder: boolean

  loadedOffsetTop: number
  loadedTotal: number

  liveSids: string[]

  setProjectId: (pid: string | null) => Promise<void>
  refreshSessionList: () => Promise<void>

  loadMoreSessions: () => Promise<void>

  refreshLiveSids: () => Promise<void>
  loadSession: (sid: string) => Promise<void>
  loadMoreOlder: () => Promise<void>
  startNewSession: () => void
  renameSession: (sid: string, title: string) => Promise<void>
  deleteSession: (sid: string) => Promise<void>

  acceptSessionStarted: (sid: string, title?: string) => void
}

const initialState: Pick<
  SessionsState,
  | 'projectId'
  | 'sessionId'
  | 'list'
  | 'listTotal'
  | 'listOffset'
  | 'listLoading'
  | 'listLoadingMore'
  | 'hasMoreOlder'
  | 'loadingOlder'
  | 'loadedOffsetTop'
  | 'loadedTotal'
  | 'liveSids'
> = {
  projectId: null,
  sessionId: null,
  list: [],
  listTotal: 0,
  listOffset: 0,
  listLoading: false,
  listLoadingMore: false,
  hasMoreOlder: false,
  loadingOlder: false,
  loadedOffsetTop: 0,
  loadedTotal: 0,
  liveSids: [],
}

export const useSessionsStore = create<SessionsState>((set, get) => ({
  ...initialState,

  setProjectId: async (pid: string | null) => {

    abortAllLiveSubs()
    set({
      ...initialState,
      projectId: pid,
    })
    useChatStore.getState().clearAll()
    if (!pid) return
    await get().refreshSessionList()
  },

  refreshSessionList: async () => {
    const { projectId } = get()
    if (!projectId) return
    set({ listLoading: true })
    try {
      const [resp, live] = await Promise.all([
        api.listSessions(projectId, {
          limit: PAGE_LIMIT,
          offset: 0,
        }),

        api.getLiveSessions(projectId).catch(() => ({ running: [] as string[] })),
      ])

      if (get().projectId !== projectId) return
      set({
        list: resp.items,
        listTotal: resp.total,
        listOffset: resp.items.length,
        liveSids: live.running || [],
      })
    } finally {
      if (get().projectId === projectId) set({ listLoading: false })
    }
  },

  loadMoreSessions: async () => {
    const { projectId, list, listTotal, listLoading, listLoadingMore } = get()
    if (!projectId) return

    if (listLoading || listLoadingMore) return
    if (list.length >= listTotal) return
    set({ listLoadingMore: true })
    try {

      const resp = await api.listSessions(projectId, {
        limit: PAGE_LIMIT,
        offset: list.length,
      })
      if (get().projectId !== projectId) return
      set((s) => {
        const seen = new Set(s.list.map((it) => it.session_id))
        const merged = s.list.slice()
        for (const it of resp.items) {
          if (!seen.has(it.session_id)) merged.push(it)
        }
        return {
          list: merged,
          listTotal: resp.total,
          listOffset: merged.length,
        }
      })
    } finally {
      if (get().projectId === projectId) set({ listLoadingMore: false })
    }
  },

  refreshLiveSids: async () => {
    const { projectId } = get()
    if (!projectId) return
    try {
      const live = await api.getLiveSessions(projectId)
      if (get().projectId !== projectId) return
      set({ liveSids: live.running || [] })
    } catch {

    }
  },

  loadSession: async (sid: string) => {
    const { projectId } = get()
    if (!projectId) return

    const chatState = useChatStore.getState()

    if (chatState.activeSessionId === sid && chatState.streaming) {
      if (get().sessionId !== sid) set({ sessionId: sid })
      return
    }

    chatState.switchToSession(sid)
    set({ sessionId: sid })

    const targetSlot = useChatStore.getState().getSlot(sid)
    if (targetSlot.streaming || liveSubs.has(sid)) {
      return
    }

    const stale = () =>
      get().projectId !== projectId ||
      get().sessionId !== sid ||
      useChatStore.getState().activeSessionId !== sid

    let running = false
    try {
      const st = await api.getSessionLiveStatus(projectId, sid)
      running = !!st.running
    } catch {

    }
    if (stale()) return

    const head = await api.getSessionMessages(projectId, sid, {
      offset: 0,
      limit: 1,
    })
    if (stale()) return

    const total = head.total
    const offset = Math.max(0, total - MESSAGE_LOAD_LIMIT)
    let messages: SessionMessageRecord[] = []
    if (total > 0) {
      const page = await api.getSessionMessages(projectId, sid, {
        offset,
        limit: MESSAGE_LOAD_LIMIT,
      })
      if (stale()) return
      messages = page.messages
    }

    set({
      loadedOffsetTop: offset,
      loadedTotal: total,
      hasMoreOlder: offset > 0,
      loadingOlder: false,
    })
    useChatStore.getState().hydrateFromSessionRecords(messages, { prepend: false })

    try {
      const eventsResp = await api.getSessionEvents(projectId, sid, {

        limit: 5000,
      })
      if (stale()) return
      if (running) {
        const assistantId = useChatStore.getState().beginAssistantTurn()
        useChatStore.getState().replayEvents(eventsResp.events, { live: true })
        const evs = eventsResp.events
        const lastSeq = evs.length > 0 ? Number(evs[evs.length - 1].seq || 0) : 0
        void attachLiveStream(projectId, sid, lastSeq, assistantId)
      } else {
        useChatStore.getState().replayEvents(eventsResp.events)
      }
    } catch (e) {

      console.warn('[sessions] 拉 events 失败（议会/squad 卡片不会重建）', e)
      if (running && !stale()) {

        const assistantId = useChatStore.getState().beginAssistantTurn()
        void attachLiveStream(projectId, sid, 0, assistantId)
      }
    }
  },

  loadMoreOlder: async () => {
    const { projectId, sessionId, loadedOffsetTop, hasMoreOlder, loadingOlder } = get()
    if (!projectId || !sessionId) return
    if (!hasMoreOlder || loadingOlder) return
    if (loadedOffsetTop <= 0) {
      set({ hasMoreOlder: false })
      return
    }

    set({ loadingOlder: true })
    try {
      const newOffset = Math.max(0, loadedOffsetTop - MESSAGE_LOAD_LIMIT)
      const wantLimit = loadedOffsetTop - newOffset
      const page = await api.getSessionMessages(projectId, sessionId, {
        offset: newOffset,
        limit: wantLimit,
      })
      if (get().projectId !== projectId || get().sessionId !== sessionId) return
      useChatStore.getState().hydrateFromSessionRecords(page.messages, {
        prepend: true,
      })
      set({
        loadedOffsetTop: newOffset,
        hasMoreOlder: newOffset > 0,
      })
    } finally {
      if (get().projectId === projectId && get().sessionId === sessionId) {
        set({ loadingOlder: false })
      }
    }
  },

  startNewSession: () => {
    set({
      sessionId: null,
      loadedOffsetTop: 0,
      loadedTotal: 0,
      hasMoreOlder: false,
      loadingOlder: false,
    })

    useChatStore.getState().switchToSession(null)
  },

  renameSession: async (sid: string, title: string) => {
    const { projectId } = get()
    if (!projectId) return
    const updated = await api.patchSession(projectId, sid, { title })
    set((s) => ({
      list: s.list.map((it) => (it.session_id === sid ? updated : it)),
    }))
  },

  deleteSession: async (sid: string) => {
    const { projectId, sessionId } = get()
    if (!projectId) return

    const sub = liveSubs.get(sid)
    if (sub) {
      try { sub.abort() } catch {  }
      liveSubs.delete(sid)
    }

    try {
      await api.deleteSession(projectId, sid)
    } catch (e: unknown) {

      const status = (e as { status?: number })?.status
      if (status !== 404) {

        throw e
      }

      console.warn(
        `[sessions] deleteSession(${sid}) 后端返 404，按"幽灵会话"处理直接从 list 移除`,
      )
    }
    set((s) => ({
      list: s.list.filter((it) => it.session_id !== sid),
      listTotal: Math.max(0, s.listTotal - 1),
    }))
    if (sessionId === sid) {

      get().startNewSession()
    }
  },

  acceptSessionStarted: (sid: string, title?: string) => {

    useChatStore.getState().bindActiveSession(sid)

    set((s) => {
      const existed = s.list.some((it) => it.session_id === sid)

      const nextSessionId = sid

      let nextList = s.list
      if (!existed) {
        nextList = [
          {
            session_id: sid,
            project_id: s.projectId || '',
            agent_id: 'claw_master',

            title: title || '新对话',
            preview: '',
            message_count: 0,
            tool_calls: 0,
            status: 'active',
            jsonl_path: '',
            created_at: null,
            updated_at: null,
            ended_at: null,
          },
          ...s.list,
        ]
      } else if (title) {
        nextList = s.list.map((it) =>
          it.session_id === sid ? { ...it, title } : it,
        )
      }
      return { sessionId: nextSessionId, list: nextList }
    })
  },
}))

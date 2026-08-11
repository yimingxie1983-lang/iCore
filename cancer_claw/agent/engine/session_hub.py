

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
import uuid
from typing import Any, AsyncGenerator, Awaitable, Callable

import structlog

from cancer_claw.services.platform.redis_client import get_redis, redis_enabled, rkey

logger = structlog.get_logger()

_DONE = object()

_EVENT_TYPE_DENY_LIST: set[str] = set()

_WORKER_ID = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"

_LOCK_TTL = 30
_HEARTBEAT = 10
_STREAM_MAXLEN = 5000
_META_TTL = 86400
_DONE_TTL = 3600
_BLOCK_MS = 2000

async def persist_agent_event(
    session_id: str,
    project_id: str | None,
    agent_id: str,
    seq: int,
    event: dict,
) -> None:

    ev_type = str(event.get("type") or "")
    if not ev_type or ev_type in _EVENT_TYPE_DENY_LIST:
        return
    from cancer_claw.db import get_db

    try:
        payload_json = json.dumps(event, ensure_ascii=False, default=str)
        db = await get_db()
        await db.execute(
            "INSERT INTO agent_events "
            "(session_id, project_id, agent_id, seq, type, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, project_id, agent_id, seq, ev_type, payload_json, time.time()),
        )
        await db.commit()
    except Exception as e:
        logger.warning(
            "agent_event_persist_failed",
            session_id=session_id, seq=seq, type=ev_type, error=str(e),
        )

async def load_max_seq(session_id: str) -> int:

    from cancer_claw.db import get_db

    try:
        db = await get_db()
        cur = await db.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM agent_events WHERE session_id = ?",
            (session_id,),
        )
        row = await cur.fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0

class Emitter:


    def __init__(self, emit_fn: Callable[[dict], Awaitable[None]]) -> None:
        self._emit_fn = emit_fn

    async def emit(self, event: dict) -> None:
        await self._emit_fn(event)

class SessionRun:


    def __init__(
        self, session_id: str, *, project_id: str | None, agent_id: str
    ) -> None:
        self.session_id = session_id
        self.project_id = project_id
        self.agent_id = agent_id
        self.buffer: list[dict[str, Any]] = []
        self.subscribers: set[asyncio.Queue] = set()
        self.lock = asyncio.Lock()
        self.status: str = "running"
        self.error: str | None = None
        self.seq_counter: int = 0
        self.task: asyncio.Task | None = None
        self.started_at: float = time.time()
        self.finished_at: float | None = None

    @property
    def last_seq(self) -> int:
        return self.seq_counter

    async def _emit(self, event: dict) -> None:
        async with self.lock:
            self.seq_counter += 1
            seq = self.seq_counter
            item = {"seq": seq, "event": event}
            self.buffer.append(item)
            for q in list(self.subscribers):
                q.put_nowait(item)
        asyncio.create_task(
            persist_agent_event(self.session_id, self.project_id, self.agent_id, seq, event)
        )

    async def _finish(self, status: str, error: str | None = None) -> None:
        async with self.lock:
            self.status = status
            self.error = error
            self.finished_at = time.time()
            for q in list(self.subscribers):
                q.put_nowait(_DONE)

    async def subscribe(self, from_seq: int) -> AsyncGenerator[dict, None]:
        async with self.lock:
            backlog = [it for it in self.buffer if it["seq"] > from_seq]
            live_q: asyncio.Queue | None = None
            if self.status == "running":
                live_q = asyncio.Queue()
                self.subscribers.add(live_q)
        for it in backlog:
            yield it
        if live_q is None:
            return
        try:
            while True:
                it = await live_q.get()
                if it is _DONE:
                    break
                yield it
        finally:
            async with self.lock:
                self.subscribers.discard(live_q)

class InMemorySessionHub:


    def __init__(self) -> None:
        self._runs: dict[str, SessionRun] = {}

    def get_run(self, session_id: str) -> SessionRun | None:
        return self._runs.get(session_id)

    async def is_running(self, session_id: str) -> bool:
        run = self._runs.get(session_id)
        return bool(run and run.status == "running")

    async def running_session_ids(self, project_id: str | None = None) -> list[str]:
        out: list[str] = []
        for sid, run in self._runs.items():
            if run.status != "running":
                continue
            if project_id is not None and run.project_id != project_id:
                continue
            out.append(sid)
        return out

    async def get_status(self, session_id: str) -> dict[str, Any] | None:
        run = self._runs.get(session_id)
        if run is None:
            return None
        return {
            "running": run.status == "running",
            "status": run.status,
            "last_seq": run.last_seq,
            "error": run.error,
            "project_id": run.project_id,
        }

    async def start(
        self, session_id: str, *, project_id: str | None, agent_id: str,
        runner: Callable[[Emitter], Awaitable[None]],
    ) -> SessionRun:
        existing = self._runs.get(session_id)
        if existing is not None and existing.status == "running":
            logger.info("session_run_already_running", session_id=session_id)
            return existing

        run = SessionRun(session_id, project_id=project_id, agent_id=agent_id)
        self._runs[session_id] = run
        run.seq_counter = await load_max_seq(session_id)
        emitter = Emitter(run._emit)

        async def _drive() -> None:
            try:
                await runner(emitter)
                await run._finish("done")
            except asyncio.CancelledError:
                with contextlib.suppress(Exception):
                    await run._emit({"type": "error", "error": "推理已被用户取消"})
                await run._finish("error", "cancelled")
                raise
            except Exception as e:
                logger.exception("session_run_failed", session_id=session_id)
                with contextlib.suppress(Exception):
                    await run._emit({"type": "error", "error": str(e) or repr(e)})
                await run._finish("error", str(e) or repr(e))

        run.task = asyncio.create_task(_drive())
        logger.info("session_run_started", session_id=session_id, seq_start=run.seq_counter)
        return run

    async def cancel(self, session_id: str) -> bool:
        run = self._runs.get(session_id)
        if run is None or run.status != "running":
            return False
        task = run.task
        if task is None or task.done():
            return False
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        logger.info("session_run_cancelled", session_id=session_id)
        return True

    async def subscribe(
        self, session_id: str, from_seq: int = 0
    ) -> AsyncGenerator[dict, None]:
        run = self._runs.get(session_id)
        if run is None:
            return
        async for item in run.subscribe(from_seq):
            yield item

class RedisSessionHub:


    def __init__(self) -> None:

        self._local_tasks: dict[str, asyncio.Task] = {}


    @staticmethod
    def _meta(sid: str) -> str:
        return rkey("run", sid, "meta")

    @staticmethod
    def _stream(sid: str) -> str:
        return rkey("run", sid, "events")

    @staticmethod
    def _lock(sid: str) -> str:
        return rkey("run", sid, "lock")

    @staticmethod
    def _control(sid: str) -> str:
        return rkey("run", sid, "control")

    @staticmethod
    def _running_set(project_id: str | None) -> str:
        return rkey("running", project_id) if project_id else rkey("running", "__all__")


    async def is_running(self, session_id: str) -> bool:
        r = await get_redis()
        return (await r.hget(self._meta(session_id), "status")) == "running"

    async def running_session_ids(self, project_id: str | None = None) -> list[str]:
        r = await get_redis()
        sids = await r.smembers(self._running_set(project_id))
        out: list[str] = []
        for sid in sids:
            if (await r.hget(self._meta(sid), "status")) == "running":
                out.append(sid)
            else:

                await r.srem(self._running_set(project_id), sid)
        return out

    async def get_status(self, session_id: str) -> dict[str, Any] | None:
        r = await get_redis()
        meta = await r.hgetall(self._meta(session_id))
        if not meta:
            return None
        return {
            "running": meta.get("status") == "running",
            "status": meta.get("status") or "idle",
            "last_seq": int(meta.get("last_seq") or 0),
            "error": meta.get("error") or None,
            "project_id": meta.get("project_id") or None,
        }


    async def _emit(
        self, sid: str, project_id: str | None, agent_id: str, event: dict
    ) -> None:
        r = await get_redis()
        meta_key = self._meta(sid)
        seq = await r.hincrby(meta_key, "last_seq", 1)
        await r.xadd(
            self._stream(sid),
            {"seq": str(seq), "data": json.dumps(event, ensure_ascii=False, default=str)},
            maxlen=_STREAM_MAXLEN,
            approximate=True,
        )

        asyncio.create_task(persist_agent_event(sid, project_id, agent_id, seq, event))

    async def _finish(
        self, sid: str, project_id: str | None, status: str, error: str | None = None
    ) -> None:
        r = await get_redis()
        meta_key = self._meta(sid)
        await r.hset(meta_key, mapping={
            "status": status, "error": error or "", "finished_at": str(time.time()),
        })

        await r.xadd(self._stream(sid), {"seq": "-1", "done": "1"},
                     maxlen=_STREAM_MAXLEN, approximate=True)
        with contextlib.suppress(Exception):
            await r.srem(self._running_set(project_id), sid)
            await r.srem(self._running_set(None), sid)
            await r.delete(self._lock(sid))

            await r.expire(meta_key, _DONE_TTL)
            await r.expire(self._stream(sid), _DONE_TTL)

    async def _heartbeat(self, sid: str) -> None:

        r = await get_redis()
        try:
            while True:
                await asyncio.sleep(_HEARTBEAT)
                with contextlib.suppress(Exception):
                    await r.expire(self._lock(sid), _LOCK_TTL)
                    await r.expire(self._meta(sid), _META_TTL)
        except asyncio.CancelledError:
            return

    async def _control_listener(self, sid: str) -> None:

        r = await get_redis()
        pubsub = r.pubsub()
        try:
            await pubsub.subscribe(self._control(sid))
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                if str(msg.get("data")) == "cancel":
                    t = self._local_tasks.get(sid)
                    if t and not t.done():
                        t.cancel()
                    return
        except asyncio.CancelledError:
            return
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(self._control(sid))
                await pubsub.aclose()


    async def start(
        self, session_id: str, *, project_id: str | None, agent_id: str,
        runner: Callable[[Emitter], Awaitable[None]],
    ) -> "_RedisRunHandle":
        r = await get_redis()

        got = await r.set(self._lock(session_id), _WORKER_ID, nx=True, ex=_LOCK_TTL)
        if not got:
            logger.info("session_run_already_running", session_id=session_id)
            return _RedisRunHandle(session_id, project_id)

        meta_key = self._meta(session_id)
        stream_key = self._stream(session_id)












        with contextlib.suppress(Exception):
            await r.delete(stream_key)
        max_seq = await load_max_seq(session_id)
        await r.hset(meta_key, mapping={
            "status": "running", "last_seq": str(max_seq), "error": "",
            "finished_at": "",
            "project_id": project_id or "", "agent_id": agent_id,
            "owner": _WORKER_ID, "started_at": str(time.time()),
        })
        await r.expire(meta_key, _META_TTL)
        if project_id:
            await r.sadd(self._running_set(project_id), session_id)
        await r.sadd(self._running_set(None), session_id)

        async def _emit_fn(ev: dict) -> None:
            await self._emit(session_id, project_id, agent_id, ev)

        emitter = Emitter(_emit_fn)

        async def _drive() -> None:
            hb = asyncio.create_task(self._heartbeat(session_id))
            ctrl = asyncio.create_task(self._control_listener(session_id))
            try:
                await runner(emitter)
                await self._finish(session_id, project_id, "done")
            except asyncio.CancelledError:
                with contextlib.suppress(Exception):
                    await self._emit(session_id, project_id, agent_id,
                                     {"type": "error", "error": "推理已被用户取消"})
                await self._finish(session_id, project_id, "error", "cancelled")
                raise
            except Exception as e:
                logger.exception("session_run_failed", session_id=session_id)
                with contextlib.suppress(Exception):
                    await self._emit(session_id, project_id, agent_id,
                                     {"type": "error", "error": str(e) or repr(e)})
                await self._finish(session_id, project_id, "error", str(e) or repr(e))
            finally:
                hb.cancel()
                ctrl.cancel()
                self._local_tasks.pop(session_id, None)

        task = asyncio.create_task(_drive())
        self._local_tasks[session_id] = task
        logger.info("session_run_started", session_id=session_id,
                    seq_start=max_seq, worker=_WORKER_ID)
        return _RedisRunHandle(session_id, project_id)

    async def cancel(self, session_id: str) -> bool:
        r = await get_redis()
        if (await r.hget(self._meta(session_id), "status")) != "running":
            return False

        await r.publish(self._control(session_id), "cancel")

        t = self._local_tasks.get(session_id)
        if t and not t.done():
            t.cancel()
        logger.info("session_run_cancelled", session_id=session_id)
        return True

    async def subscribe(
        self, session_id: str, from_seq: int = 0
    ) -> AsyncGenerator[dict, None]:
        r = await get_redis()
        stream_key = self._stream(session_id)
        meta_key = self._meta(session_id)





        if not await r.exists(stream_key) and not await r.exists(meta_key):
            return
        last_id = "0"
        while True:
            resp = await r.xread({stream_key: last_id}, block=_BLOCK_MS, count=200)
            if not resp:

                status = await r.hget(meta_key, "status")
                if status != "running":
                    return

                if not await r.exists(self._lock(session_id)):
                    return
                continue
            for _stream_name, entries in resp:
                for entry_id, fields in entries:
                    last_id = entry_id
                    if fields.get("done"):
                        return
                    seq = int(fields.get("seq") or 0)
                    if seq > from_seq:
                        yield {"seq": seq, "event": json.loads(fields["data"])}

class _RedisRunHandle:


    def __init__(self, session_id: str, project_id: str | None) -> None:
        self.session_id = session_id
        self.project_id = project_id
        self.status = "running"

_hub: "InMemorySessionHub | RedisSessionHub | None" = None

def get_session_hub() -> "InMemorySessionHub | RedisSessionHub":

    global _hub
    if _hub is None:
        if redis_enabled():
            _hub = RedisSessionHub()
            logger.info("session_hub_backend", backend="redis")
        else:
            _hub = InMemorySessionHub()
            logger.info("session_hub_backend", backend="memory")
    return _hub

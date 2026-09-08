"""进程内本地宿主：无 HTTP，CLI 与桌面 GUI 共用 Agent 运行时。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from pathlib import Path
from typing import Any, AsyncGenerator

from cancer_claw.client.project import ensure_local_project, normalize_local_root
from cancer_claw.client.session import run_turn
from cancer_claw.runtime import bootstrap, shutdown
from cancer_claw.services.identity.deps import LOCAL_SUPERUSER


def configure_client_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level)
    try:
        import structlog

        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(level),
        )
    except Exception:
        pass


async def make_local_agent(project_id: str, root: Path):
    from cancer_claw.agent.engine.agent_factory import get_or_create_agent
    from cancer_claw.agent.engine.system_agents import MASTER_AGENT_ID

    agent = await get_or_create_agent(MASTER_AGENT_ID, project_id=None)
    await agent.bind_local_workspace(project_id, root)
    agent._current_user = dict(LOCAL_SUPERUSER)
    return agent


class LocalHost:
    """当前目录即工作区。桌面 GUI 与 CLI 共用。"""

    def __init__(self, *, verbose: bool = False) -> None:
        self.verbose = verbose
        self.root: Path | None = None
        self.project_id: str | None = None
        self.agent: Any = None
        self.session_id: str | None = None
        self.force_new = True
        self._started = False
        self._turn_task: asyncio.Task[Any] | None = None

    @property
    def busy(self) -> bool:
        task = self._turn_task
        return task is not None and not task.done()

    def new_session(self) -> None:
        self.session_id = None
        self.force_new = True

    async def start(
        self,
        workdir: Path | str | None = None,
        *,
        resume: str | None = None,
    ) -> None:
        configure_client_logging(self.verbose)
        root = normalize_local_root(workdir or Path.cwd())
        os.chdir(root)
        await bootstrap(connect_redis=False)
        self._started = True
        await self._bind(root, reset_session=True)
        if resume:
            await self.resume(resume)

    async def shutdown(self) -> None:
        await self.cancel_turn()
        if self._started:
            self._started = False
            await shutdown()

    async def open_folder(self, path: Path | str) -> None:
        if not self._started or self.agent is None:
            raise RuntimeError("运行时未启动")
        await self.cancel_turn()
        root = normalize_local_root(path)
        os.chdir(root)
        await self._bind(root, reset_session=True)

    async def _bind(self, root: Path, *, reset_session: bool) -> None:
        self.project_id, self.root = await ensure_local_project(root)
        if self.agent is None:
            self.agent = await make_local_agent(self.project_id, self.root)
        else:
            await self.agent.bind_local_workspace(self.project_id, self.root)
            self.agent._current_user = dict(LOCAL_SUPERUSER)
        if reset_session:
            self.new_session()

    async def list_sessions(self, limit: int = 40) -> list[dict[str, Any]]:
        if not self.project_id:
            return []
        from cancer_claw.agent.recall.session_repo import list_sessions

        return await list_sessions(self.project_id, limit=limit)

    async def latest_session_id(self) -> str | None:
        rows = await self.list_sessions(limit=1)
        if not rows:
            return None
        return str(rows[0].get("session_id") or "") or None

    async def resume(self, session_id: str) -> str:
        target = (session_id or "").strip() or "LAST"
        if target.upper() == "LAST":
            found = await self.latest_session_id()
            if not found:
                raise FileNotFoundError("没有可恢复的会话。")
            target = found
        self.session_id = target
        self.force_new = False
        return target

    def load_history(self, session_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        if not self.root:
            return []
        from cancer_claw.capabilities.toolkit.session_history import read_session

        return read_session(self.root, session_id, limit=limit) or []

    async def cancel_turn(self) -> None:
        task = self._turn_task
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    async def run_message(self, message: str) -> AsyncGenerator[dict[str, Any], None]:
        if self.busy:
            raise RuntimeError("上一轮尚未结束")
        if self.agent is None or self.root is None:
            raise RuntimeError("运行时未启动")
        self._turn_task = asyncio.current_task()
        try:
            async for ev in run_turn(
                self.agent,
                message,
                session_id=self.session_id,
                force_new=self.force_new,
                verbose=self.verbose,
            ):
                if ev.get("type") == "session_started":
                    self.session_id = str(ev.get("session_id") or self.session_id or "")
                    self.force_new = False
                yield ev
        finally:
            self._turn_task = None

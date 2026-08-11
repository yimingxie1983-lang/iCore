

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

class SandboxError(Exception):
    pass


class SandboxUnavailable(SandboxError):
    pass


@dataclass
class ExecResult:

    returncode: int
    stdout: str
    stderr: str
    duration_ms: int = 0
    timed_out: bool = False
    killed: bool = False

    @property
    def ok(self) -> bool:

        return self.returncode == 0 and not self.timed_out and not self.killed

@dataclass
class BgProcessInfo:

    pid: int
    command: list[str]
    started_at: datetime
    status: str = "running"
    returncode: Optional[int] = None

@dataclass
class SandboxPolicy:

    max_memory_bytes: int = 2 * 1024 * 1024 * 1024
    max_processes: int = 64
    cpu_time_seconds: int = 3600
    low_integrity: bool = True
    kill_on_close: bool = True
    isolate_network: bool = False
    ui_restrictions: bool = True


    redirect_env_dirs: bool = True

class ProjectExecutor(abc.ABC):


    def __init__(self, project_id: str, policy: SandboxPolicy | None = None):
        self.project_id = project_id
        self.policy = policy or SandboxPolicy()
        self._closed = False



    @property
    @abc.abstractmethod
    def kind(self) -> str:
        raise NotImplementedError
    @property
    def is_alive(self) -> bool:

        return not self._closed



    @abc.abstractmethod
    def prepare(self) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def close(self) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def run(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        stdin_data: str | None = None,
    ) -> ExecResult:
        raise NotImplementedError

    @abc.abstractmethod
    async def run_background(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> BgProcessInfo:
        raise NotImplementedError

    @abc.abstractmethod
    async def read_background_output(
        self,
        pid: int,
        *,
        max_bytes: int = 65536,
    ) -> tuple[str, str]:
        raise NotImplementedError

    @abc.abstractmethod
    async def kill_background(self, pid: int) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_background(self) -> list[BgProcessInfo]:
        raise NotImplementedError

    def get_background_log_path(self, pid: int) -> str | None:

        return None

__all__ = [
    "BgProcessInfo",
    "ExecResult",
    "ProjectExecutor",
    "SandboxError",
    "SandboxPolicy",
    "SandboxUnavailable",
]

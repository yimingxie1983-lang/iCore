

from __future__ import annotations

import asyncio
import ctypes
import os
import subprocess
import sys
import threading
import time
from collections import deque
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from cancer_claw.config import settings
from cancer_claw.capabilities.toolkit.executor.base import (
    BgProcessInfo,
    ExecResult,
    ProjectExecutor,
    SandboxError,
    SandboxPolicy,
    SandboxUnavailable,
)
from cancer_claw.capabilities.toolkit.executor.bg_log import BgLogFile

logger = structlog.get_logger()

if sys.platform != "win32":

    raise SandboxUnavailable("win_executor is Windows-only")

CREATE_SUSPENDED = 0x00000004
CREATE_NO_WINDOW = 0x08000000
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

JobObjectExtendedLimitInformation = 9
JobObjectBasicUIRestrictions = 4

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_JOB_TIME = 0x00000004

JOB_OBJECT_UILIMIT_HANDLES = 0x00000001
JOB_OBJECT_UILIMIT_READCLIPBOARD = 0x00000002
JOB_OBJECT_UILIMIT_WRITECLIPBOARD = 0x00000004
JOB_OBJECT_UILIMIT_SYSTEMPARAMETERS = 0x00000008
JOB_OBJECT_UILIMIT_DISPLAYSETTINGS = 0x00000010
JOB_OBJECT_UILIMIT_GLOBALATOMS = 0x00000020
JOB_OBJECT_UILIMIT_DESKTOP = 0x00000040
JOB_OBJECT_UILIMIT_EXITWINDOWS = 0x00000080

INFINITE = 0xFFFFFFFF
WAIT_TIMEOUT = 0x00000102
WAIT_OBJECT_0 = 0x00000000

class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]

class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]

class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]

class JOBOBJECT_BASIC_UI_RESTRICTIONS(ctypes.Structure):
    _fields_ = [("UIRestrictionsClass", wintypes.DWORD)]

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_ntdll = ctypes.WinDLL("ntdll")

_CreateJobObjectW = _kernel32.CreateJobObjectW
_CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
_CreateJobObjectW.restype = wintypes.HANDLE

_SetInformationJobObject = _kernel32.SetInformationJobObject
_SetInformationJobObject.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
_SetInformationJobObject.restype = wintypes.BOOL

_AssignProcessToJobObject = _kernel32.AssignProcessToJobObject
_AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_AssignProcessToJobObject.restype = wintypes.BOOL

_TerminateJobObject = _kernel32.TerminateJobObject
_TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
_TerminateJobObject.restype = wintypes.BOOL

_CloseHandle = _kernel32.CloseHandle
_CloseHandle.argtypes = [wintypes.HANDLE]
_CloseHandle.restype = wintypes.BOOL

_NtResumeProcess = _ntdll.NtResumeProcess
_NtResumeProcess.argtypes = [wintypes.HANDLE]
_NtResumeProcess.restype = ctypes.c_long

class _BgRecord:

    OUTPUT_TAIL_BYTES = 256 * 1024

    def __init__(
        self,
        popen: subprocess.Popen,
        command: list[str],
        log_file: Optional[BgLogFile] = None,
    ):
        self.popen = popen
        self.pid = popen.pid
        self.command = list(command)
        self.started_at = datetime.now(timezone.utc)
        self.status = "running"
        self.returncode: Optional[int] = None
        self._stdout_buf: deque[bytes] = deque()
        self._stderr_buf: deque[bytes] = deque()
        self._stdout_size = 0
        self._stderr_size = 0
        self._lock = threading.Lock()
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None

        self.log_file: Optional[BgLogFile] = log_file

    def start_reader_threads(self) -> None:

        if self.popen.stdout is not None:
            t = threading.Thread(target=self._pump, args=(self.popen.stdout, True), daemon=True)
            t.start()
            self._stdout_thread = t
        if self.popen.stderr is not None:
            t = threading.Thread(target=self._pump, args=(self.popen.stderr, False), daemon=True)
            t.start()
            self._stderr_thread = t

    def _pump(self, stream, is_stdout: bool) -> None:
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break

                if self.log_file is not None:
                    self.log_file.write_chunk(
                        "stdout" if is_stdout else "stderr", chunk
                    )
                with self._lock:
                    if is_stdout:
                        self._stdout_buf.append(chunk)
                        self._stdout_size += len(chunk)

                        while self._stdout_size > self.OUTPUT_TAIL_BYTES and self._stdout_buf:
                            popped = self._stdout_buf.popleft()
                            self._stdout_size -= len(popped)
                    else:
                        self._stderr_buf.append(chunk)
                        self._stderr_size += len(chunk)
                        while self._stderr_size > self.OUTPUT_TAIL_BYTES and self._stderr_buf:
                            popped = self._stderr_buf.popleft()
                            self._stderr_size -= len(popped)
        except Exception:

            pass

    def snapshot_output(self, max_bytes: int) -> tuple[str, str]:
        with self._lock:
            out = b"".join(self._stdout_buf)
            err = b"".join(self._stderr_buf)
        if max_bytes and len(out) > max_bytes:
            out = out[-max_bytes:]
        if max_bytes and len(err) > max_bytes:
            err = err[-max_bytes:]
        return (out.decode("utf-8", errors="replace"),
                err.decode("utf-8", errors="replace"))

    def to_info(self) -> BgProcessInfo:
        return BgProcessInfo(
            pid=self.pid,
            command=list(self.command),
            started_at=self.started_at,
            status=self.status,
            returncode=self.returncode,
        )

    def refresh_status(self) -> None:

        if self.status != "running":
            return
        rc = self.popen.poll()
        if rc is not None:
            self.returncode = rc
            self.status = "exited"

            if self.log_file is not None:
                self.log_file.close(rc, status="exited")

class WinProjectExecutor(ProjectExecutor):


    @property
    def kind(self) -> str:
        return "windows-job"

    def __init__(self, project_id: str, policy: SandboxPolicy | None = None):
        super().__init__(project_id, policy)
        self._job_handle: Optional[int] = None
        self._bg: dict[int, _BgRecord] = {}
        self._bg_lock = threading.Lock()
        self._sandbox_home: Optional[Path] = None
        self._prepared = False



    def prepare(self) -> None:
        if self._prepared:
            return


        try:
            projects_dir = Path(settings.paths.projects_dir).expanduser()
            if not projects_dir.is_absolute():
                projects_dir = (Path.cwd() / projects_dir).resolve()
            sandbox_home = projects_dir / self.project_id / "sandbox_home"
            for sub in ("appdata", "localappdata", "temp", "userprofile"):
                (sandbox_home / sub).mkdir(parents=True, exist_ok=True)
            self._sandbox_home = sandbox_home
        except Exception as e:
            raise SandboxUnavailable(f"failed to create sandbox_home: {e}") from e


        job = _CreateJobObjectW(None, None)
        if not job:
            err = ctypes.get_last_error()
            raise SandboxUnavailable(f"CreateJobObjectW failed, LastError={err}")
        self._job_handle = job


        try:
            self._apply_extended_limits()
            if self.policy.ui_restrictions:
                self._apply_ui_restrictions()
        except Exception as e:

            _CloseHandle(job)
            self._job_handle = None
            raise SandboxUnavailable(f"SetInformationJobObject failed: {e}") from e

        self._prepared = True
        logger.info("win_sandbox_prepared",
                    project_id=self.project_id,
                    sandbox_home=str(self._sandbox_home),
                    max_memory_mb=self.policy.max_memory_bytes // (1024 * 1024),
                    max_processes=self.policy.max_processes)

    def _apply_extended_limits(self) -> None:
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        flags = 0
        if self.policy.kill_on_close:
            flags |= JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        flags |= JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION

        if self.policy.max_memory_bytes > 0:
            flags |= JOB_OBJECT_LIMIT_PROCESS_MEMORY
            info.ProcessMemoryLimit = self.policy.max_memory_bytes
        if self.policy.max_processes > 0:
            flags |= JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            info.BasicLimitInformation.ActiveProcessLimit = self.policy.max_processes
        if self.policy.cpu_time_seconds > 0:
            flags |= JOB_OBJECT_LIMIT_JOB_TIME

            info.BasicLimitInformation.PerJobUserTimeLimit = (
                self.policy.cpu_time_seconds * 10_000_000
            )
        info.BasicLimitInformation.LimitFlags = flags

        ok = _SetInformationJobObject(
            self._job_handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            err = ctypes.get_last_error()
            raise OSError(f"SetInformationJobObject(Extended) LastError={err}")

    def _apply_ui_restrictions(self) -> None:
        ui = JOBOBJECT_BASIC_UI_RESTRICTIONS()
        ui.UIRestrictionsClass = (
            JOB_OBJECT_UILIMIT_HANDLES
            | JOB_OBJECT_UILIMIT_READCLIPBOARD
            | JOB_OBJECT_UILIMIT_WRITECLIPBOARD
            | JOB_OBJECT_UILIMIT_SYSTEMPARAMETERS
            | JOB_OBJECT_UILIMIT_DISPLAYSETTINGS
            | JOB_OBJECT_UILIMIT_GLOBALATOMS
            | JOB_OBJECT_UILIMIT_EXITWINDOWS

        )
        ok = _SetInformationJobObject(
            self._job_handle,
            JobObjectBasicUIRestrictions,
            ctypes.byref(ui),
            ctypes.sizeof(ui),
        )
        if not ok:
            err = ctypes.get_last_error()
            raise OSError(f"SetInformationJobObject(UI) LastError={err}")

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        handle = self._job_handle
        self._job_handle = None
        if handle:

            try:
                _TerminateJobObject(handle, 1)
            except Exception as e:
                logger.warning("terminate_job_failed",
                               project_id=self.project_id, error=str(e))
            try:
                _CloseHandle(handle)
            except Exception:
                pass


        with self._bg_lock:
            for rec in self._bg.values():
                if rec.status == "running":
                    rec.status = "killed"
                    rec.returncode = -1

                if rec.log_file is not None:
                    try:
                        rec.log_file.close(rec.returncode, status=rec.status)
                    except Exception:
                        pass


        logger.info("win_sandbox_closed", project_id=self.project_id)



    def _assert_ready(self) -> None:
        if self._closed:
            raise SandboxError(f"executor closed for project {self.project_id}")
        if not self._prepared or not self._job_handle:
            raise SandboxError("executor not prepared; call prepare() first")

    def _build_env(self, base_env: dict[str, str] | None) -> dict[str, str]:

        env = dict(os.environ) if base_env is None else dict(base_env)
        if self.policy.redirect_env_dirs and self._sandbox_home is not None:
            sh = self._sandbox_home
            env["APPDATA"] = str(sh / "appdata")
            env["LOCALAPPDATA"] = str(sh / "localappdata")
            env["TEMP"] = str(sh / "temp")
            env["TMP"] = str(sh / "temp")
            env["USERPROFILE"] = str(sh / "userprofile")
            env["HOME"] = str(sh / "userprofile")
        return env

    def _spawn_into_job(
        self,
        cmd: list[str],
        cwd: str | None,
        env: dict[str, str] | None,
        capture: bool,
    ) -> subprocess.Popen:

        self._assert_ready()

        creationflags = CREATE_SUSPENDED | CREATE_NO_WINDOW
        stdio = subprocess.PIPE if capture else subprocess.DEVNULL

        popen = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdio,
            stderr=stdio,
            creationflags=creationflags,
            close_fds=True,
        )


        proc_handle = int(popen._handle)
        ok = _AssignProcessToJobObject(self._job_handle, proc_handle)
        if not ok:
            err = ctypes.get_last_error()

            try:
                popen.kill()
                popen.wait(timeout=2)
            except Exception:
                pass
            raise SandboxError(f"AssignProcessToJobObject failed, LastError={err}")


        status = _NtResumeProcess(proc_handle)
        if status != 0:
            try:
                popen.kill()
                popen.wait(timeout=2)
            except Exception:
                pass
            raise SandboxError(f"NtResumeProcess failed, NTSTATUS=0x{status & 0xFFFFFFFF:08x}")

        return popen



    async def run(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        stdin_data: str | None = None,
    ) -> ExecResult:
        loop = asyncio.get_running_loop()
        start = time.monotonic()

        env_full = self._build_env(env)

        def _sync_run() -> ExecResult:
            popen = self._spawn_into_job(cmd, cwd, env_full, capture=True)
            timed_out = False
            killed = False
            try:
                if stdin_data is not None and popen.stdin is not None:
                    try:
                        popen.stdin.write(stdin_data.encode("utf-8", errors="replace"))
                    finally:
                        popen.stdin.close()
                try:
                    stdout_b, stderr_b = popen.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    popen.kill()
                    try:
                        stdout_b, stderr_b = popen.communicate(timeout=2)
                    except Exception:
                        stdout_b, stderr_b = b"", b""
                rc = popen.returncode if popen.returncode is not None else -1
                if timed_out:
                    killed = True
                return ExecResult(
                    returncode=rc,
                    stdout=(stdout_b or b"").decode("utf-8", errors="replace"),
                    stderr=(stderr_b or b"").decode("utf-8", errors="replace"),
                    duration_ms=int((time.monotonic() - start) * 1000),
                    timed_out=timed_out,
                    killed=killed,
                )
            except Exception:
                try:
                    popen.kill()
                except Exception:
                    pass
                raise

        return await loop.run_in_executor(None, _sync_run)



    async def run_background(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> BgProcessInfo:
        loop = asyncio.get_running_loop()
        env_full = self._build_env(env)

        def _sync_spawn() -> _BgRecord:
            popen = self._spawn_into_job(cmd, cwd, env_full, capture=True)



            log_file = None
            try:
                log_root = self._infer_workspace_for_logs()
                if log_root is None and cwd:
                    log_root = Path(cwd)
                if log_root is not None:
                    log_path = log_root / "logs" / f"bg-{popen.pid}.log"
                    log_file = BgLogFile(
                        log_path, pid=popen.pid, command=cmd, cwd=str(log_root)
                    )
                    log_file.start()
            except Exception as e:

                logger.warning(
                    "bg_log_init_failed",
                    project_id=self.project_id,
                    pid=popen.pid,
                    error=str(e),
                )
                log_file = None

            rec = _BgRecord(popen, cmd, log_file=log_file)
            rec.start_reader_threads()
            with self._bg_lock:
                self._bg[rec.pid] = rec
            return rec

        rec = await loop.run_in_executor(None, _sync_spawn)
        logger.info("sandbox_bg_started",
                    project_id=self.project_id, pid=rec.pid, command=cmd,
                    log_path=str(rec.log_file.path) if rec.log_file else None)
        return rec.to_info()

    def _infer_workspace_for_logs(self) -> Path | None:

        try:
            projects_dir = Path(settings.paths.projects_dir).expanduser()
            if not projects_dir.is_absolute():
                projects_dir = (Path.cwd() / projects_dir).resolve()
            ws = projects_dir / self.project_id / "workspace"
            return ws if ws.exists() else None
        except Exception:
            return None

    async def read_background_output(
        self,
        pid: int,
        *,
        max_bytes: int = 65536,
    ) -> tuple[str, str]:
        with self._bg_lock:
            rec = self._bg.get(pid)
        if rec is None:
            raise SandboxError(f"pid {pid} not managed by this executor")
        rec.refresh_status()
        return rec.snapshot_output(max_bytes)

    async def kill_background(self, pid: int) -> bool:
        with self._bg_lock:
            rec = self._bg.get(pid)
        if rec is None:

            logger.warning("sandbox_kill_denied_not_owned",
                           project_id=self.project_id, pid=pid)
            return False

        loop = asyncio.get_running_loop()

        def _sync_kill() -> bool:
            try:
                if rec.popen.poll() is None:
                    rec.popen.kill()
                    try:
                        rec.popen.wait(timeout=3)
                    except Exception:
                        pass
                rec.status = "killed"
                if rec.returncode is None:
                    rec.returncode = rec.popen.returncode if rec.popen.returncode is not None else -1

                if rec.log_file is not None:
                    rec.log_file.close(rec.returncode, status="killed")
                return True
            except Exception as e:
                logger.error("sandbox_kill_failed",
                             project_id=self.project_id, pid=pid, error=str(e))
                return False

        return await loop.run_in_executor(None, _sync_kill)

    async def list_background(self) -> list[BgProcessInfo]:
        with self._bg_lock:
            records = list(self._bg.values())
        for rec in records:
            rec.refresh_status()
        return [rec.to_info() for rec in records]

    def get_background_log_path(self, pid: int) -> str | None:

        with self._bg_lock:
            rec = self._bg.get(pid)
        if rec is None or rec.log_file is None:
            return None
        return str(rec.log_file.path)

__all__ = ["WinProjectExecutor"]



import asyncio
import os
import platform
import re
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.executor.bg_log import BgLogFile
from cancer_claw.capabilities.toolkit.workspace import (
    get_active_executor,
    resolve_cwd_for_shell,
    resolve_tool_path,
)

_IS_WINDOWS = platform.system() == "Windows"

def _extract_ports_from_command(command: str) -> list[int]:

    patterns = [
        r'--port[=\s]+(\d{2,5})',
        r'(?<!\w)-p\s+(\d{2,5})',
        r'\bPORT[=\s]+(\d{2,5})',
        r'port[=:\s]+(\d{2,5})',
        r':(\d{2,5})(?:\s|$|["\'])',
    ]
    ports: set[int] = set()
    for pat in patterns:
        for m in re.finditer(pat, command, re.IGNORECASE):
            try:
                p = int(m.group(1))
                if 1024 <= p <= 65535:
                    ports.add(p)
            except ValueError:
                pass
    return list(ports)

def _fix_windows_command(command: str) -> str:

    import re as _re


    command = _re.sub(r'(?<![.\w])curl(?!\.exe)(?=\s)', 'curl.exe', command)




    command = _re.sub(r'(curl\.exe)\s+-s\b', r'\1', command)


    command = _re.sub(
        r'(https?://)localhost\b',
        r'\g<1>127.0.0.1',
        command,
        flags=_re.IGNORECASE,
    )

    return command

def _check_framework_port(command: str) -> str | None:

    from cancer_claw.config import settings

    framework_port: int = settings.app.port
    detected = _extract_ports_from_command(command)
    for p in detected:
        if p == framework_port:
            return (
                f"端口冲突保护：命令中使用的端口 {p} 与 iCore 框架自身监听端口相同。\n"
                f"框架端口 {framework_port} 是系统保留端口，不能被用户服务占用。\n"
                f"请将你的服务改用其他端口，例如 {framework_port + 1} 或 {framework_port + 2}，\n"
                f"然后重新执行命令。\n"
                f"不要尝试 kill_process 来释放此端口——那会关闭框架本身。"
            )
    return None

_SUICIDE_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (


    (re.compile(r"\bStop-Process\b[^|;]*?-Name\b\s+['\"]?(python|pythonw|node|uvicorn|gunicorn)",
                re.IGNORECASE),
     "Stop-Process -Name <python|pythonw|node|...> 会把 iCore 主进程一起 kill"),



    (re.compile(r"\bGet-Process\b[^|;]*?-Name\b\s+['\"]?(python|pythonw|node|uvicorn|gunicorn)[^|;]*?\|[^|;]*?Stop-Process",
                re.IGNORECASE),
     "Get-Process -Name <python|...> | Stop-Process 等价于按名字批量杀，会误伤框架"),


    (re.compile(r"\btaskkill\b[^|;]*?/IM\s+['\"]?(python|pythonw|node|uvicorn)",
                re.IGNORECASE),
     "taskkill /IM <python|...> 会按镜像名杀掉所有同名进程，包括 iCore 自身"),


    (re.compile(r"\bpkill\b[^|;]*?\b(python|node|uvicorn|gunicorn)\b", re.IGNORECASE),
     "pkill <python|...> 会按名字杀掉所有匹配进程，包括 iCore 自身"),
    (re.compile(r"\bkillall\b[^|;]*?\b(python|node|uvicorn|gunicorn)\b", re.IGNORECASE),
     "killall <python|...> 会按名字杀掉所有匹配进程，包括 iCore 自身"),
)

def _check_suicide_command(command: str) -> str | None:

    if not command:
        return None
    for pattern, reason in _SUICIDE_PATTERNS:
        if pattern.search(command):
            return (
                "自杀保护拦截：检测到会误杀 iCore 主进程的命令模式。\n"
                f"问题：{reason}。\n"
                "原因：你想『只杀用户的 python 服务』，但批量杀同名进程会连框架自己一起干掉，\n"
                "之前已经出过这个事故（Process finished with exit code -1）。\n"
                "正确做法（按 PID 精确杀，不会误伤）：\n"
                "  - 后台进程（由本工具 run_background 启动的）：直接调 ``kill_process`` action 传 pid；\n"
                "  - 外部进程：先 ``Get-NetTCPConnection -LocalPort <你服务的端口>`` 查到 OwningProcess，\n"
                "    再 ``Stop-Process -Id <那个具体 PID> -Force`` 精确杀；\n"
                "  - 真的要批量杀，先 ``Get-Process -Name python | Select Id, Path`` 看清楚名单，\n"
                "    确认 iCore 自身 PID（看 prompts 里的 self_inspect 输出）后再排除，**不要**用 ``$PID``——\n"
                "    PowerShell 里 ``$PID`` 是 PowerShell 自己的 PID，不是父进程 iCore 的 PID。"
            )
    return None

_SHELL_HINT = (
    "当前平台：Windows，使用 PowerShell 执行命令。"
    "请使用 PowerShell 语法：New-Item 建目录、Get-ChildItem 列目录、"
    "Remove-Item 删除、命令链接用 ; 不用 &&。"
    "不支持 mkdir -p / ls -la / rm -rf 等 bash 语法。"
    "启动服务进程（python app.py 等）必须用 run_background，不能用 run_command。"
    "⚠️ Windows 注意：HTTP 健康检查/接口验证必须用 PowerShell 原生方式，"
    "不要用 curl.exe -s（Windows 版 curl.exe 的 -s 会吞掉响应 body，导致输出为空）。"
    "正确做法：(Invoke-WebRequest -Uri 'http://127.0.0.1:8080/health' -UseBasicParsing).Content "
    "或 (Invoke-WebRequest -Uri 'http://127.0.0.1:8080/api/xxx' -UseBasicParsing).Content。"
    "必须用 127.0.0.1 而非 localhost（localhost 可能解析到 IPv6 的 ::1 导致超时）。"
) if _IS_WINDOWS else (
    "当前平台：Linux/macOS，使用 bash 执行命令。"
    "支持标准 bash 语法（mkdir -p、ls -la 等）。"
    "启动服务进程（python app.py 等）必须用 run_background，不能用 run_command。"
)

@dataclass
class _BgProcess:

    proc: subprocess.Popen | None = None
    command: str = ""
    buf: deque = field(default_factory=lambda: deque(maxlen=500))
    sandboxed: bool = False

    log_path: str = ""

    log_file: BgLogFile | None = None

    cwd: str = ""
    ports: list[int] = field(default_factory=list)
    fingerprint: str = ""

_bg_procs: dict[int, _BgProcess] = {}

def _normalize_command_fingerprint(command: str) -> str:

    if not command:
        return ""
    s = command.strip()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("\\\\", "/").replace("\\", "/")
    return s.lower()

def _is_bg_alive(pid: int, entry: _BgProcess) -> bool:

    if not entry.sandboxed and entry.proc is not None:
        return entry.proc.poll() is None
    return True

async def _gather_alive_bg_view() -> list[tuple[int, _BgProcess, bool]]:


    sandbox_alive: set[int] = set()
    executor = get_active_executor()
    if executor is not None:
        try:
            infos = await executor.list_background()
            sandbox_alive = {i.pid for i in infos if getattr(i, "status", "") == "running"}
        except Exception:
            sandbox_alive = set()

    view: list[tuple[int, _BgProcess, bool]] = []
    dead_pids: list[int] = []
    for pid, entry in list(_bg_procs.items()):
        if entry.sandboxed:
            alive = (pid in sandbox_alive) if executor is not None else True
        else:
            alive = _is_bg_alive(pid, entry)
        if alive:
            view.append((pid, entry, True))
        else:
            dead_pids.append(pid)

    for pid in dead_pids:
        _bg_procs.pop(pid, None)
    return view

async def _check_bg_duplicate(command: str, cwd: str | None) -> str | None:

    new_fp = _normalize_command_fingerprint(command)
    new_ports = set(_extract_ports_from_command(command))
    new_cwd = (cwd or "").strip().rstrip("/\\").lower()

    view = await _gather_alive_bg_view()
    if not view:
        return None

    for pid, entry, _alive in view:

        if entry.fingerprint and entry.fingerprint == new_fp:
            entry_cwd_norm = (entry.cwd or "").strip().rstrip("/\\").lower()
            if entry_cwd_norm == new_cwd:
                return (
                    f"后台去重拒绝：相同命令 + 相同 cwd 的后台进程已在跑（pid={pid}）。\n"
                    f"  现有命令: {entry.command}\n"
                    f"  现有 cwd : {entry.cwd or '(默认)'}\n"
                    f"  现有日志: {entry.log_path or '(无)'}\n"
                    "下一步怎么走（按你的真实意图选一条）：\n"
                    f"  - 复用：服务已经在跑了，直接验证它（HTTP 探活 / read_process_output pid={pid}）；\n"
                    f"  - 重启：先 ``kill_process pid={pid}``，再 run_background；\n"
                    "  - 真要并行多份：命令里改一个不同的端口 / 参数，让指纹不同。"
                )


        if new_ports and entry.ports:
            shared = new_ports & set(entry.ports)
            if shared:
                port = next(iter(shared))
                return (
                    f"后台去重拒绝：要起的服务绑端口 {port}，但端口 {port} 已被 pid={pid} 占着。\n"
                    f"  占用进程命令: {entry.command}\n"
                    f"  占用进程 cwd : {entry.cwd or '(默认)'}\n"
                    f"  占用进程日志: {entry.log_path or '(无)'}\n"
                    "下一步怎么走：\n"
                    f"  - 是同一个服务的新版本 → 先 ``kill_process pid={pid}`` 再起；\n"
                    "  - 是不同服务凑巧用了同端口 → 改新服务的端口；\n"
                    f"  - 想直接复用 → 不要再起了，对 pid={pid} 做你的后续操作。"
                )
    return None

def _format_log_hint(log_path: str, workspace_cwd: str | None) -> str:

    if not log_path:
        return "日志: （日志文件初始化失败，可用 read_process_output 读取内存缓冲）"
    p = Path(log_path)
    if workspace_cwd:
        try:
            rel = p.relative_to(Path(workspace_cwd))
            return f"日志: {rel.as_posix()}（相对 workspace；用 file_ops.read_file 读取）"
        except ValueError:
            pass
    return f"日志: {log_path}"

class ShellExecTool(BaseTool):

    @property
    def name(self) -> str:
        return "shell_exec"

    @property
    def description(self) -> str:
        return (
            f"执行 Shell 命令。{_SHELL_HINT} "
            "短命令用 run_command；服务进程用 run_background + read_process_output 轮询判断。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "shell_exec",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "run_command",
                                "run_background",
                                "list_background",
                                "read_process_output",
                                "kill_process",
                                "run_script",
                            ],
                            "description": (
                                "run_command: 阻塞执行短命令（建目录/安装包/跑测试），有超时限制；\n"
                                "run_background: 后台启动服务进程，立即返回 PID + 日志文件路径；"
                                "stdout/stderr 实时落盘到 workspace/logs/bg-<pid>.log，"
                                "框架仅在 ~10s 后自动注入一次启动摘要，之后请用 file_ops.read_file 增量读日志；"
                                "**重启服务前先调 list_background 看现状，否则会被去重逻辑拒绝**；\n"
                                "list_background: 列出当前 session 管理的所有后台进程（pid/命令/cwd/端口/日志），"
                                "**重启服务的第 1 步**，避免重复起一份导致僵尸进程堆积；\n"
                                "read_process_output: 读取后台进程的元数据 + 尾部缓冲（仍可用，但优先 file_ops 读日志）；\n"
                                "kill_process: 停止后台进程（按 PID 精确杀，只能杀本工具登记过的）；\n"
                                "run_script: 执行脚本文件（阻塞）。"
                            ),
                        },
                        "command": {
                            "type": "string",
                            "description": f"要执行的命令（run_command / run_background）。{_SHELL_HINT}",
                        },
                        "pid": {
                            "type": "integer",
                            "description": "后台进程 PID（read_process_output / kill_process 时使用）",
                        },
                        "wait_seconds": {
                            "type": "integer",
                            "description": "read_process_output 时先等待 N 秒再读（上限 30s），默认 0 立即读",
                        },
                        "script_path": {
                            "type": "string",
                            "description": "脚本路径（run_script）",
                        },
                        "cwd": {
                            "type": "string",
                            "description": "工作目录（默认项目 workspace/）",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": (
                                "run_command 超时秒数，默认 60。"
                                "健康检查（curl/wget）请保持默认值或设为 30，不要设得过小；"
                                "网络命令在 Windows 上可能有额外延迟。"
                            ),
                            "default": 60,
                        },
                    },
                    "required": ["action"],
                },
            },
        }





    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")
        cwd    = kwargs.get("cwd")

        if action == "run_command":
            cmd = kwargs.get("command", "")
            if not cmd:
                return ToolResult(success=False, error="command 不能为空")
            err = _check_suicide_command(cmd)
            if err:
                return ToolResult(success=False, error=err)
            err = _check_framework_port(cmd)
            if err:
                return ToolResult(success=False, error=err)
            return await self._run_command(cmd, cwd=cwd, timeout=int(kwargs.get("timeout", 60)))

        if action == "run_background":
            cmd = kwargs.get("command", "")
            if not cmd:
                return ToolResult(success=False, error="command 不能为空")
            err = _check_suicide_command(cmd)
            if err:
                return ToolResult(success=False, error=err)
            err = _check_framework_port(cmd)
            if err:
                return ToolResult(success=False, error=err)

            dup_err = await _check_bg_duplicate(cmd, cwd)
            if dup_err:
                return ToolResult(success=False, error=dup_err)
            return await self._run_background(cmd, cwd=cwd)

        if action == "list_background":
            return await self._list_background()

        if action == "read_process_output":
            pid = kwargs.get("pid")
            if not pid:
                return ToolResult(success=False, error="pid 不能为空")
            wait_seconds = int(kwargs.get("wait_seconds", 0) or 0)
            return await self._read_process_output(int(pid), wait_seconds=wait_seconds)

        if action == "kill_process":
            pid = kwargs.get("pid")
            if not pid:
                return ToolResult(success=False, error="pid 不能为空")
            return await self._kill_process_async(int(pid))

        if action == "run_script":
            sp = kwargs.get("script_path", "")
            if not sp:
                return ToolResult(success=False, error="script_path 不能为空")
            return await self._run_script(sp, cwd=cwd, timeout=int(kwargs.get("timeout", 60)))

        return ToolResult(success=False, error=f"不支持的操作: {action}")





    async def _run_command(self, command: str, cwd=None, timeout: int = 60) -> ToolResult:
        cdir, cerr = resolve_cwd_for_shell(cwd)
        if cerr:
            return ToolResult(success=False, error=cerr)

        if _IS_WINDOWS:
            command = _fix_windows_command(command)

        shell_cmd = (["powershell", "-NoProfile", "-Command", command]
                     if _IS_WINDOWS else ["bash", "-c", command])


        executor = get_active_executor()
        if executor is not None:
            try:
                res = await executor.run(shell_cmd, cwd=cdir, timeout=float(timeout))
            except Exception as e:
                return ToolResult(success=False, error=f"沙箱执行失败: {str(e) or repr(e)}")
            if res.timed_out:
                return ToolResult(success=False, error=f"命令超时（{timeout}s）: {command}")
            out = res.stdout
            parts = []
            if out: parts.append(f"[stdout]\n{out}")
            if res.stderr: parts.append(f"[stderr]\n{res.stderr}")
            parts.append(f"[exit_code] {res.returncode}")
            return ToolResult(
                success=True,
                output="\n".join(parts),
                data={"exit_code": res.returncode, "sandboxed": True},
            )


        def _sync():
            return subprocess.run(shell_cmd, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, cwd=cdir, timeout=timeout)
        try:
            r = await asyncio.to_thread(_sync)
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error=f"命令超时（{timeout}s）: {command}")
        except FileNotFoundError as e:
            return ToolResult(success=False, error=f"找不到 Shell '{shell_cmd[0]}': {repr(e)}")
        except Exception as e:
            return ToolResult(success=False, error=f"命令执行失败: {str(e) or repr(e)}")

        out = self._decode(r.stdout)
        err = self._decode(r.stderr)

        parts = []
        if out: parts.append(f"[stdout]\n{out}")
        if err: parts.append(f"[stderr]\n{err}")
        parts.append(f"[exit_code] {r.returncode}")



        return ToolResult(
            success=True,
            output="\n".join(parts),
            data={"exit_code": r.returncode},
        )





    async def _run_background(self, command: str, cwd=None) -> ToolResult:
        cdir, cerr = resolve_cwd_for_shell(cwd)
        if cerr:
            return ToolResult(success=False, error=cerr)

        if _IS_WINDOWS:
            command = _fix_windows_command(command)

        shell_cmd = (["powershell", "-NoProfile", "-Command", command]
                     if _IS_WINDOWS else ["bash", "-c", command])


        executor = get_active_executor()
        if executor is not None:
            try:
                info = await executor.run_background(shell_cmd, cwd=cdir)
            except Exception as e:
                return ToolResult(success=False, error=f"沙箱后台启动失败: {str(e) or repr(e)}")

            await asyncio.sleep(1)
            infos = await executor.list_background()
            cur = next((i for i in infos if i.pid == info.pid), None)
            if cur is None or cur.status != "running":
                out, err = await executor.read_background_output(info.pid, max_bytes=8192)
                rc = cur.returncode if cur else -1
                return ToolResult(
                    success=False,
                    output=f"[进程立即退出 exit_code={rc}]\n{out}\n{err}",
                    error=f"进程启动后立即退出（exit_code={rc}）",
                )
            log_path = executor.get_background_log_path(info.pid) or ""
            ports = _extract_ports_from_command(command)
            _bg_procs[info.pid] = _BgProcess(
                proc=None,
                command=command,
                sandboxed=True,
                log_path=log_path,
                cwd=cdir or "",
                ports=ports,
                fingerprint=_normalize_command_fingerprint(command),
            )
            log_hint = _format_log_hint(log_path, cdir)
            ports_hint = f" | 端口: {ports}" if ports else ""
            return ToolResult(
                success=True,
                output=(
                    f"进程已后台启动（沙箱），PID={info.pid}{ports_hint}\n"
                    f"命令: {command}\n"
                    f"{log_hint}\n"
                    f"框架会在 ~10s 后自动注入一次启动摘要（含尾部日志）。"
                    f"之后请用 file_ops.read_file 自行按需读日志，"
                    f"支持 offset/limit 增量读，避免反复全量拉取。\n"
                    f"⚠️ 服务是长期运行进程，任务完成后请保持服务运行；"
                    f"项目关闭时沙箱会自动回收所有子进程。\n"
                    f"复用提示：之后要重启此服务，调 ``kill_process pid={info.pid}`` 再 run_background；"
                    f"**直接再 run_background 同一条命令会被去重拒绝**。"
                ),
                data={
                    "pid": info.pid,
                    "sandboxed": True,
                    "log_path": log_path,
                    "ports": ports,
                },
            )

        def _start():
            kw: dict = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            cwd=cdir, text=False)
            if _IS_WINDOWS:
                kw["creationflags"] = subprocess.CREATE_NO_WINDOW
            return subprocess.Popen(shell_cmd, **kw)

        try:
            proc = await asyncio.to_thread(_start)
        except FileNotFoundError as e:
            return ToolResult(success=False, error=f"找不到 Shell '{shell_cmd[0]}': {repr(e)}")
        except Exception as e:
            return ToolResult(success=False, error=f"后台启动失败: {str(e) or repr(e)}")


        await asyncio.sleep(1)
        if proc.poll() is not None:
            crash_out = self._decode(proc.stdout.read())
            return ToolResult(
                success=False,
                output=f"[进程立即退出 exit_code={proc.returncode}]\n{crash_out}",
                error=f"进程启动后立即退出（exit_code={proc.returncode}）",
            )

        pid = proc.pid

        log_file: BgLogFile | None = None
        log_path = ""
        try:
            log_root = Path(cdir) if cdir else None
            if log_root is not None:
                lp = log_root / "logs" / f"bg-{pid}.log"
                log_file = BgLogFile(lp, pid=pid, command=command, cwd=str(log_root))
                log_file.start()
                log_path = str(lp)
        except Exception:
            log_file = None
            log_path = ""

        ports = _extract_ports_from_command(command)
        entry = _BgProcess(
            proc=proc, command=command, log_path=log_path, log_file=log_file,
            cwd=cdir or "", ports=ports,
            fingerprint=_normalize_command_fingerprint(command),
        )
        _bg_procs[pid] = entry


        def _reader():
            try:
                for line in proc.stdout:
                    entry.buf.append(line)
                    if entry.log_file is not None:
                        entry.log_file.write_chunk("stdout", line)
            finally:

                if entry.log_file is not None:
                    rc = proc.poll()
                    entry.log_file.close(
                        rc if rc is not None else -1, status="exited"
                    )

        threading.Thread(target=_reader, daemon=True, name=f"bg-{pid}").start()

        log_hint = _format_log_hint(log_path, cdir)
        ports_hint = f" | 端口: {ports}" if ports else ""
        return ToolResult(
            success=True,
            output=(
                f"进程已后台启动，PID={pid}{ports_hint}\n"
                f"命令: {command}\n"
                f"{log_hint}\n"
                f"框架会在 ~10s 后自动注入一次启动摘要（含尾部日志）。"
                f"之后请用 file_ops.read_file 自行按需读日志，"
                f"支持 offset/limit 增量读，避免反复全量拉取。\n"
                f"⚠️ 注意：服务是长期运行进程，任务完成后请保持服务运行，不要主动 kill_process。\n"
                f"复用提示：之后要重启此服务，调 ``kill_process pid={pid}`` 再 run_background；"
                f"**直接再 run_background 同一条命令会被去重拒绝**。"
            ),
            data={"pid": pid, "sandboxed": False, "log_path": log_path, "ports": ports},
        )





    async def _read_process_output(self, pid: int, wait_seconds: int = 0) -> ToolResult:

        if wait_seconds > 0:
            await asyncio.sleep(min(wait_seconds, 30))

        entry = _bg_procs.get(pid)
        if entry is None:
            return ToolResult(
                success=False,
                error=(
                    f"PID={pid} 不在本 session 的后台进程注册表里。"
                    f"可能原因：PID 错了 / 进程由其他 session 启动 / 进程已被清理。"
                ),
            )

        if entry.sandboxed:
            executor = get_active_executor()
            if executor is None:
                return ToolResult(
                    success=False,
                    error=f"PID={pid} 登记为沙箱进程，但当前沙箱 Executor 已卸载。",
                )
            try:
                infos = await executor.list_background()
                cur = next((i for i in infos if i.pid == pid), None)
                out, err = await executor.read_background_output(pid, max_bytes=16384)
            except Exception as e:
                return ToolResult(success=False, error=f"沙箱查询失败: {str(e) or repr(e)}")

            still_running = cur is not None and cur.status == "running"
            exit_code = cur.returncode if (cur and not still_running) else None
            status = "运行中" if still_running else f"已退出(exit_code={exit_code})"
            parts = [f"[沙箱] PID={pid} 状态: {status}", f"命令: {entry.command}"]
            if entry.log_path:
                parts.append(
                    f"💡 完整日志已落盘: {entry.log_path}\n"
                    f"   建议用 file_ops.read_file(path, offset, limit) 增量读取，"
                    f"避免重复拉取已读过的内容"
                )
            if out:
                parts.append(f"[stdout 尾部]\n{out}")
            if err:
                parts.append(f"[stderr 尾部]\n{err}")
            return ToolResult(
                success=True,
                output="\n".join(parts),
                data={
                    "pid": pid,
                    "running": still_running,
                    "exit_code": exit_code,
                    "sandboxed": True,
                    "log_path": entry.log_path,
                },
            )


        if entry.proc is None:
            return ToolResult(success=False, error=f"PID={pid} 登记异常：既非沙箱又无 proc 句柄。")
        exit_code = entry.proc.poll()
        still_running = exit_code is None
        raw_out = ShellExecTool._decode(b"".join(entry.buf))
        status = "运行中" if still_running else f"已退出(exit_code={exit_code})"
        log_hint = (
            f"💡 完整日志已落盘: {entry.log_path}\n"
            f"   建议用 file_ops.read_file(path, offset, limit) 增量读取\n"
            if entry.log_path
            else ""
        )
        return ToolResult(
            success=True,
            output=(
                f"PID={pid} 状态: {status}\n"
                f"命令: {entry.command}\n"
                f"{log_hint}"
                f"{'─'*40}\n"
                + (raw_out or "（暂无输出）")
            ),
            data={
                "pid": pid,
                "running": still_running,
                "exit_code": exit_code,
                "sandboxed": False,
                "log_path": entry.log_path,
            },
        )





    async def _list_background(self) -> ToolResult:

        view = await _gather_alive_bg_view()
        if not view:
            return ToolResult(
                success=True,
                output="当前 session 没有 alive 的后台进程。",
                data={"count": 0, "processes": []},
            )

        lines = [f"当前 session alive 的后台进程（共 {len(view)} 个）："]
        rows: list[dict] = []
        for pid, entry, _alive in view:
            cmd_short = entry.command if len(entry.command) <= 80 else entry.command[:77] + "..."
            ports_str = ",".join(str(p) for p in entry.ports) if entry.ports else "-"
            cwd_str = entry.cwd or "(默认)"
            sandbox_tag = "[沙箱]" if entry.sandboxed else "[直接]"
            lines.append(
                f"  - pid={pid} {sandbox_tag} | 端口={ports_str} | cwd={cwd_str}\n"
                f"      命令: {cmd_short}\n"
                f"      日志: {entry.log_path or '(无)'}"
            )
            rows.append({
                "pid": pid,
                "command": entry.command,
                "cwd": entry.cwd,
                "ports": list(entry.ports),
                "log_path": entry.log_path,
                "sandboxed": entry.sandboxed,
            })
        lines.append(
            "提示：要重启某个服务，调 ``kill_process pid=<PID>`` 再 ``run_background``；"
            "**不要直接 run_background 同一条命令**，会被去重拒绝。"
        )
        return ToolResult(
            success=True,
            output="\n".join(lines),
            data={"count": len(view), "processes": rows},
        )





    async def _kill_process_async(self, pid: int) -> ToolResult:

        executor = get_active_executor()
        if executor is not None:
            ok = await executor.kill_background(pid)
            if ok:
                _bg_procs.pop(pid, None)
                return ToolResult(success=True, output=f"PID={pid} 已终止（沙箱）")
            infos = await executor.list_background()
            known_pids = [i.pid for i in infos]
            return ToolResult(
                success=False,
                error=(
                    f"❌ 拒绝操作：PID={pid} 不是本 session 通过 run_background 启动的进程，"
                    f"不允许终止。\n"
                    f"当前沙箱管理的 PID：{known_pids if known_pids else '无'}\n"
                    f"如果是端口冲突问题，请修改服务配置换用其他端口，而不是 kill 占用端口的进程。"
                ),
            )


        return await asyncio.to_thread(self._kill_process_legacy, pid)

    def _kill_process_legacy(self, pid: int) -> ToolResult:
        entry = _bg_procs.pop(pid, None)
        proc = entry.proc if entry else None

        if proc is None:



            known_pids = list(_bg_procs.keys())
            hint = f"当前 session 可管理的进程 PID：{known_pids if known_pids else '无'}"
            return ToolResult(
                success=False,
                error=(
                    f"❌ 拒绝操作：PID={pid} 不是本 session 通过 run_background 启动的进程，"
                    f"不允许终止。\n"
                    f"{hint}\n"
                    f"如果是端口冲突问题，请修改服务配置换用其他端口，而不是 kill 占用端口的进程。"
                ),
            )

        try:
            proc.kill()
            proc.wait(timeout=5)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            pass
        except OSError:
            pass

        if entry and entry.log_file is not None:
            try:
                rc = proc.returncode if proc.returncode is not None else -1
                entry.log_file.close(rc, status="killed")
            except Exception:
                pass
        return ToolResult(success=True, output=f"PID={pid} 已终止")





    async def _run_script(self, script_path: str, cwd=None, timeout: int = 60) -> ToolResult:
        path, err = resolve_tool_path(script_path)
        if err:
            return ToolResult(success=False, error=err)
        if not path.exists():
            return ToolResult(success=False, error=f"脚本不存在: {path}")

        ext = path.suffix.lower()
        sp = str(path)
        cmd = {
            ".py":  f'"{sys.executable}" "{sp}"',
            ".sh":  f'bash "{sp}"',
            ".ps1": f'powershell -File "{sp}"',
            ".bat": f'cmd /c "{sp}"',
            ".cmd": f'cmd /c "{sp}"',
        }.get(ext, f'"{sp}"')

        return await self._run_command(cmd, cwd=cwd, timeout=timeout)



    @staticmethod
    def _decode(data: bytes) -> str:
        for enc in ["utf-8", "gbk", "cp936", "latin-1"]:
            try:
                return data.decode(enc)
            except (UnicodeDecodeError, LookupError):
                pass
        return data.decode("utf-8", errors="replace")

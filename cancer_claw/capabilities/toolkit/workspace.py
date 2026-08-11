

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

_current_workspace: ContextVar[ToolWorkspaceContext | None] = ContextVar(
    "cancer_claw_tool_workspace", default=None
)

@dataclass(frozen=True)
class ToolWorkspaceContext:


    project_root: Path
    """项目根目录（含 workspace、memory、plans 等子目录）"""

    default_relative_root: Path
    """相对路径的锚点，默认 project_root/workspace（产出物目录）"""

    extra_allow_roots: tuple[Path, ...] = ()
    """除项目根外允许访问的绝对路径前缀（可选，来自配置）"""

    executor: Any = None
    """
    当前项目绑定的沙箱 Executor（`cancer_claw.capabilities.toolkit.executor.ProjectExecutor` 实例）。

    为 None 表示未启用沙箱（config.yaml sandbox.mode == "off"，或平台不支持）；
    此时 shell_exec / code_exec / process_ops 应回退到原生 subprocess 路径。

    类型标注为 Any 而非具体类型是刻意的：避免 workspace.py 强依赖 executor 模块，
    打破循环导入（executor.factory 本身就要用 settings，而 workspace 也用 settings）。
    """

    project_id: str | None = None
    """项目 ID（与 executor 绑定时保留，便于上层审计）。"""

def get_tool_workspace() -> ToolWorkspaceContext | None:
    return _current_workspace.get()

@contextmanager
def tool_workspace_scope(ctx: ToolWorkspaceContext | None) -> Iterator[None]:

    token: Token = _current_workspace.set(ctx)
    try:
        yield
    finally:
        _current_workspace.reset(token)

def _is_descendant(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False

def normalize_extra_allow_roots(paths: list[str]) -> tuple[Path, ...]:
    out: list[Path] = []
    for p in paths:
        if not p or not str(p).strip():
            continue
        rp = Path(p).expanduser()
        if not rp.is_absolute():
            rp = (Path.cwd() / rp).resolve()
        else:
            rp = rp.resolve()
        out.append(rp)
    return tuple(out)

def build_workspace_for_project(
    project_id: str,
    *,
    executor: Any = None,
) -> ToolWorkspaceContext | None:

    from cancer_claw.config import settings

    projects_dir = Path(settings.paths.projects_dir).expanduser()
    if not projects_dir.is_absolute():
        projects_dir = (Path.cwd() / projects_dir).resolve()
    else:
        projects_dir = projects_dir.resolve()
    project_root = (projects_dir / project_id).resolve()
    workspace_sub = project_root / "workspace"
    workspace_sub.mkdir(parents=True, exist_ok=True)
    extra = normalize_extra_allow_roots(list(settings.paths.tool_path_allow_extra or []))
    return ToolWorkspaceContext(
        project_root=project_root,
        default_relative_root=workspace_sub.resolve(),
        extra_allow_roots=extra,
        executor=executor,
        project_id=project_id,
    )

def get_project_workspace_root(project_id: str) -> Path:

    from cancer_claw.config import settings

    projects_dir = Path(settings.paths.projects_dir).expanduser()
    if not projects_dir.is_absolute():
        projects_dir = (Path.cwd() / projects_dir).resolve()
    else:
        projects_dir = projects_dir.resolve()
    workspace = (projects_dir / project_id / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace

def get_active_executor() -> Any:

    ws = _current_workspace.get()
    if ws is None:
        return None
    return ws.executor

def resolve_tool_path(
    path_str: str,
    *,
    allow_project_root: bool = True,
) -> tuple[Path | None, str | None]:

    ws = get_tool_workspace()
    if ws is None:
        return None, (
            "未绑定项目工作区：文件/目录路径无法解析。"
            "请通过项目的对话接口调用（例如 POST /api/projects/{project_id}/chat），"
            "不要使用无 project 的同步调试接口操作磁盘。"
        )

    raw = (path_str or "").strip()
    if not raw:
        return None, "path 不能为空"

    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate.expanduser().resolve()
    else:




        parts = candidate.parts
        if (parts
                and parts[0].lower() == "workspace"
                and ws.default_relative_root.name.lower() == "workspace"):
            candidate = Path(*parts[1:]) if len(parts) > 1 else Path(".")
        resolved = (ws.default_relative_root / candidate).resolve()








    allowed_here = False
    if allow_project_root and _is_descendant(resolved, ws.project_root):
        allowed_here = True
    else:
        for extra in ws.extra_allow_roots:
            if _is_descendant(resolved, extra):
                allowed_here = True
                break

    if not allowed_here:
        extra_hint = ""
        if ws.extra_allow_roots:
            extra_list = ", ".join(str(p) for p in ws.extra_allow_roots)
            extra_hint = f" 已配置的额外允许路径: [{extra_list}]——如需访问请使用其下的绝对路径。"
        else:
            extra_hint = " 如需访问其他位置，由管理员在配置 paths.tool_path_allow_extra 中声明。"
        return None, (
            f"路径越界: {resolved} 不在当前项目目录内。"
            f"项目根: {ws.project_root}；"
            f"相对路径默认相对于: {ws.default_relative_root}。"
            + extra_hint
        )

    return resolved, None

def resolve_cwd_for_shell(cwd: str | None) -> tuple[str | None, str | None]:

    ws = get_tool_workspace()
    if ws is None:
        return None, (
            "未绑定项目工作区，无法设置命令工作目录。"
            "请通过项目对话接口调用。"
        )
    if cwd is None or (isinstance(cwd, str) and cwd.strip() in (".", "")):
        return str(ws.default_relative_root), None
    p, err = resolve_tool_path(cwd)
    if err:
        return None, err
    if not p.is_dir():
        return None, f"工作目录不是文件夹或不存在: {p}"
    return str(p), None

def resolve_two_paths(
    a: str,
    b: str,
) -> tuple[tuple[Path, Path] | None, str | None]:

    pa, e1 = resolve_tool_path(a)
    if e1:
        return None, e1
    pb, e2 = resolve_tool_path(b)
    if e2:
        return None, e2
    return (pa, pb), None

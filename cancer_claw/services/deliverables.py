"""列出项目 workspace 里的阶段产出（排除探查脚本和过程日志）。"""

from __future__ import annotations

import os
from pathlib import Path

_SKIP_DIRS = {
    "scripts",
    "logs",
    "charters",
    ".tool_cache",
    "pip",
    "microsoft",
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "voxfeat",
    "uploads",
    "sandbox_home",
    ".pytest_cache",
}

_SKIP_EXTS = {
    ".py",
    ".pyc",
    ".pyo",
    ".sh",
    ".bash",
    ".ps1",
    ".bat",
    ".cmd",
    ".log",
    ".exe",
    ".dll",
    ".so",
    ".npz",
    ".npy",
    ".dcm",
}

_ALLOWED_EXTS = {
    ".md",
    ".markdown",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
    ".docx",
    ".docm",
    ".xlsx",
    ".xlsm",
    ".pptx",
    ".pptm",
    ".r",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".sql",
    ".yaml",
    ".yml",
    ".toml",
    ".txt",
    ".csv",
    ".tsv",
    ".pdf",
}

_MAX_FILES = 400


def deliverable_group(rel_posix: str) -> str:
    parts = [p for p in rel_posix.replace("\\", "/").split("/") if p]
    if len(parts) >= 2 and parts[0] == "workspace" and parts[1] == "docs":
        return "阶段文档"
    if len(parts) >= 2 and parts[0] == "workspace" and parts[1] == "habitat":
        return "Habitat"
    if len(parts) >= 2 and parts[0] == "workspace" and parts[1] == "manuscript":
        return "文稿"
    return "产出物"


def list_workspace_deliverables(project_root: Path, *, limit: int = _MAX_FILES) -> list[dict]:
    root = project_root.resolve()
    workspace = (root / "workspace").resolve()
    if not workspace.is_dir():
        return []

    items: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(workspace):
        dirnames[:] = [
            d for d in dirnames if d.lower() not in _SKIP_DIRS and not d.startswith(".")
        ]
        for name in filenames:
            path = Path(dirpath) / name
            if not _is_deliverable_file(path):
                continue
            try:
                rel = path.resolve().relative_to(root).as_posix()
                stat = path.stat()
            except (OSError, ValueError):
                continue
            items.append(
                {
                    "path": rel,
                    "name": path.name,
                    "size": int(stat.st_size),
                    "mtime": int(stat.st_mtime),
                    "group": deliverable_group(rel),
                }
            )
            if len(items) >= limit:
                return _sort_items(items)
    return _sort_items(items)


def _is_deliverable_file(path: Path) -> bool:
    name = path.name
    if name.startswith("."):
        return False
    if name.lower() in {"charter.md"}:
        return False
    lower = name.lower()
    if "_probe" in lower:
        return False
    suffixes = {s.lower() for s in path.suffixes}
    if suffixes & _SKIP_EXTS:
        return False
    if path.suffix.lower() in _SKIP_EXTS:
        return False
    if path.suffix.lower() not in _ALLOWED_EXTS:
        return False
    if not path.is_file():
        return False
    return True


def _sort_items(items: list[dict]) -> list[dict]:
    order = {"阶段文档": 0, "Habitat": 1, "文稿": 2, "产出物": 3}
    return sorted(
        items,
        key=lambda it: (
            order.get(str(it.get("group") or ""), 9),
            str(it.get("path") or "").lower(),
        ),
    )

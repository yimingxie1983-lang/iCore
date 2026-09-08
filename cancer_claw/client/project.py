"""把当前目录映射为 iCore 本地项目（稳定 id，元数据仍落在框架 projects_dir）。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from cancer_claw.config import settings
from cancer_claw.db import get_db
from cancer_claw.services.identity.deps import LOCAL_SUPERUSER
from cancer_claw.services.projects.service import PROJECT_SOURCE_CLI_LOCAL

_OWNER_ID = str(LOCAL_SUPERUSER["id"])


def normalize_local_root(root: Path | str) -> Path:
    return Path(root).expanduser().resolve()


def local_project_id(root: Path | str) -> str:
    """同一目录在 Windows 大小写差异下仍得到相同 id。"""
    key = str(normalize_local_root(root)).replace("\\", "/").casefold()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


async def ensure_local_project(root: Path | str) -> tuple[str, Path]:
    resolved = normalize_local_root(root)
    if not resolved.is_dir():
        raise FileNotFoundError(f"工作目录不存在: {resolved}")

    project_id = local_project_id(resolved)
    name = resolved.name or "workspace"
    now = datetime.now(timezone.utc).isoformat()
    workspace_path = str(resolved)

    meta_root = Path(settings.paths.projects_dir) / project_id
    (meta_root / "memory" / "digests").mkdir(parents=True, exist_ok=True)
    (meta_root / "logs").mkdir(parents=True, exist_ok=True)
    memory_file = meta_root / "memory" / "MEMORY.md"
    if not memory_file.is_file():
        memory_file.write_text(
            f"# {name} — 本地工作区记忆\n\n"
            f"> 绑定目录: `{workspace_path}`\n"
            f"> 创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"## 项目概述\n\n本地 iCore 客户端绑定的工作目录。\n\n"
            f"## 关键决策\n\n"
            f"## 约定与规范\n\n",
            encoding="utf-8",
        )

    db = await get_db()
    cursor = await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    if await cursor.fetchone():
        await db.execute(
            "UPDATE projects SET name = ?, workspace_path = ?, source = ?, updated_at = ? WHERE id = ?",
            (name, workspace_path, PROJECT_SOURCE_CLI_LOCAL, now, project_id),
        )
    else:
        await db.execute(
            """INSERT INTO projects
               (id, name, description, workspace_path, owner_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                name,
                f"本地工作区 {workspace_path}",
                workspace_path,
                _OWNER_ID,
                PROJECT_SOURCE_CLI_LOCAL,
                now,
                now,
            ),
        )
    await db.commit()
    return project_id, resolved

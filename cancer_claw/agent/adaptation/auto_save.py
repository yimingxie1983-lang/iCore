

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import structlog

logger = structlog.get_logger()

# best-effort write
def _append_to_md(path: Path, header: str, body: str) -> bool:

    if not body.strip():
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
        block = f"\n\n## {header} · {ts}\n\n{body.strip()}\n"
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(block)
        return True
    except Exception as e:
        logger.warning("memory_append_failed", path=str(path), error=str(e))
        return False

def save_evolved_memory(
    *,
    project_dir: Path | None,
    agent_dir: Path | None,
    project_memory_md: str = "",
    agent_memory_md: str = "",
    task_digest_json: str = "",
    stage_suffix: str = "",
) -> dict[str, bool]:

    out: dict[str, bool] = {
        "project_memory": False,
        "agent_memory": False,
        "task_digest": False,
    }
    if project_dir is not None and project_memory_md.strip():
        out["project_memory"] = _append_to_md(
            project_dir / "memory" / "MEMORY.md",
            header="进化追加",
            body=project_memory_md,
        )
    if agent_dir is not None and agent_memory_md.strip():
        out["agent_memory"] = _append_to_md(
            agent_dir / "memory" / "EXPERIENCE.md",
            header="经验",
            body=agent_memory_md,
        )
    if project_dir is not None and task_digest_json.strip():
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        suffix_part = f"_{stage_suffix}" if stage_suffix else ""
        out["task_digest"] = _append_to_md(
            project_dir / "memory" / "digests" / f"{date}{suffix_part}.md",
            header="任务摘要",
            body=f"```json\n{task_digest_json.strip()}\n```",
        )
    return out

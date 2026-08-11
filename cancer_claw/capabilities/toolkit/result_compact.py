

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

MAX_CHARS_IN_CHAT: int = 8000
HEAD_CHARS: int = 2000
TAIL_CHARS: int = 2000

def _workspace_root(parent: Any | None) -> Path | None:
    if parent is None:
        return None
    ws = getattr(parent, "_bound_workspace", None)
    if ws is None:
        return None
    root = getattr(ws, "default_relative_root", None)
    if root is None:
        return None
    try:
        return Path(root).resolve()
    except Exception:
        return None

def compact_for_chat_context(
    text: str,
    *,
    tool_name: str,
    tag_suffix: str,
    parent_agent: Any | None,
) -> tuple[str, dict[str, Any]]:

    if not text or len(text) <= MAX_CHARS_IN_CHAT:
        return text, {"overflow": False}

    root = _workspace_root(parent_agent)
    rel_note = ""
    meta: dict[str, Any] = {"overflow": True, "original_chars": len(text)}
    if root is not None and root.exists():
        try:
            cache_dir = (root / ".tool_cache").resolve()
            cache_dir.mkdir(parents=True, exist_ok=True)

            h = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:8]
            safe_tag = "".join(c if c.isalnum() or c in "-_" else "_" for c in tag_suffix)[:32]
            fname = f"{tool_name}_{safe_tag}_{int(time.time() * 1000)}_{h}.txt"
            out_path = (cache_dir / fname).resolve()

            if not str(out_path).startswith(str(cache_dir)):
                raise ValueError("path escape")
            out_path.write_text(text, encoding="utf-8")
            rel = out_path.relative_to(root)
            rel_note = rel.as_posix()
            meta["overflow_cache_path"] = rel_note
        except Exception:
            rel_note = ""

    omitted = len(text) - HEAD_CHARS - TAIL_CHARS
    if omitted < 0:
        omitted = 0

    if rel_note:
        mid = (
            f"\n\n[完整输出共 {len(text)} 字符；已写入 workspace/{rel_note} ，"
            f"请用 file_ops.read_file 指定 path 增量读取。以下为上下文内保留的头尾片段。]\n\n"
        )
    else:
        mid = (
            f"\n\n[完整输出共 {len(text)} 字符；中间省略 {omitted} 字符。"
            f"未绑定 workspace 无法落盘缓存，如需全文请缩小查询范围或改用分段工具。]\n\n"
        )

    head = text[:HEAD_CHARS]
    tail = text[-TAIL_CHARS:] if TAIL_CHARS else ""
    return head + mid + tail, meta

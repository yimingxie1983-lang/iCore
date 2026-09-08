"""斜杠命令解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 零宽 / BOM / 方向控制等，微信输入法偶发夹带
_INVISIBLE_RE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff\u00ad]")


@dataclass
class SlashCommand:
    name: str
    args: str
    raw: str


def _clean(text: str) -> str:
    return _INVISIBLE_RE.sub("", str(text or "")).replace("\r", "").strip()


def parse_slash_command(text: str) -> SlashCommand | None:
    raw = _clean(text)
    # 兼容全角斜杠
    if raw.startswith("／"):
        raw = "/" + raw[1:]
    if not raw.startswith("/"):
        return None
    if raw == "/":
        return None
    body = raw[1:].strip()
    if not body:
        return None
    parts = body.split(None, 1)
    name = _clean(parts[0]).lower().lstrip("/").strip()
    args = _clean(parts[1]) if len(parts) > 1 else ""
    if not name:
        return None
    # 中文别名
    aliases = {
        "绑定": "bind",
        "解绑": "unbind",
        "帮助": "help",
        "状态": "status",
    }
    name = aliases.get(name, name)
    return SlashCommand(name=name, args=args, raw=raw)

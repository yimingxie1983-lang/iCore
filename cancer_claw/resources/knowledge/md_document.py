

from __future__ import annotations

import re

from pathlib import Path

from typing import Any

import yaml

_FRONTMATTER = re.compile(

    r"^---[ \t]*\r?\n(?P<fm>.+?)\r?\n---[ \t]*(?:\r?\n(?P<body>.*))?$",

    re.DOTALL,

)

def parse_frontmatter_md(text: str) -> tuple[dict[str, Any], str]:



    raw = text.lstrip("\ufeff").strip()

    if not raw.startswith("---"):

        raise ValueError("文件必须以 YAML frontmatter（以 --- 开头）开始")

    m = _FRONTMATTER.match(raw)

    if not m:

        raise ValueError("无法解析 frontmatter：需要闭合的第二个 ---")

    fm_text = m.group("fm") or ""

    body = m.group("body") or ""

    data = yaml.safe_load(fm_text) or {}

    if not isinstance(data, dict):

        raise ValueError("frontmatter 必须是 YAML 映射（键值对象）")

    return data, body

def dump_frontmatter_md(fm: dict[str, Any], body: str) -> str:



    dumped = yaml.safe_dump(

        fm,

        allow_unicode=True,

        default_flow_style=False,

        sort_keys=False,

    )

    b = body.strip()

    if b:

        return f"---\n{dumped}---\n\n{b}\n"

    return f"---\n{dumped}---\n"

def read_file(path: Path) -> str:



    return path.read_text(encoding="utf-8")

def write_file(path: Path, content: str) -> None:



    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(content, encoding="utf-8")


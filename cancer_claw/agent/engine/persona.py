

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import structlog

logger = structlog.get_logger()

DEFAULT_PERSONA_ID: str = "master"

@dataclass(frozen=True)
class Persona:


    id: str
    """唯一 id，与 ``personas/{id}.md`` 文件名一一对应。"""

    name: str
    """人类可读名称（如 "临床医师"）。"""

    description: str
    """一句话描述，前端切换器悬浮提示用。"""

    soul_text: str
    """soul.md 正文（去掉 frontmatter 后的内容），会被注入到 ContextManager 的 P0/soul 槽。"""

    icon: str = ""
    """可选 emoji / 图标字符（如 "🩺"）；前端没有就用首字母圆 chip。"""

    suggested_tools: tuple[str, ...] = field(default_factory=tuple)
    """建议为这个 persona 打开的工具白名单（仅作 UI 提示，不强制；
    主体仍持有完整 core tools）。"""

    source_path: Path | None = None
    """加载来源文件路径（仅供调试 / 诊断展示，对运行时无影响）。"""

def personas_dir() -> Path:

    import os

    env = os.environ.get("CANCER_CLAW_PERSONAS_DIR")
    if env:
        return Path(env).resolve()

    try:
        from cancer_claw.config import settings
        configured = getattr(getattr(settings, "paths", None), "personas_dir", None)
        if configured:
            return Path(configured).resolve()
    except Exception:
        pass

    return (
        Path(__file__).resolve().parents[2]
        / "resources"
        / "persona_profiles"
    ).resolve()

_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<meta>.*?)\n---\s*\n(?P<body>.*)\Z",
    re.DOTALL,
)

def _parse_frontmatter(raw: str) -> tuple[dict, str]:

    m = _FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw

    meta_block = m.group("meta")
    body = m.group("body")

    try:
        import yaml
        meta = yaml.safe_load(meta_block) or {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception as e:
        logger.warning("persona_frontmatter_yaml_failed", error=str(e))
        meta = {}

    return meta, body

def _meta_to_persona(file_id: str, meta: dict, body: str, path: Path) -> Persona:

    pid = str(meta.get("id") or file_id).strip()
    name = str(meta.get("name") or pid).strip()
    desc = str(meta.get("description") or "").strip()
    icon = str(meta.get("icon") or "").strip()

    raw_tools = meta.get("suggested_tools") or []
    if isinstance(raw_tools, str):

        tools = tuple(t.strip() for t in raw_tools.split(",") if t.strip())
    elif isinstance(raw_tools, (list, tuple)):
        tools = tuple(str(t).strip() for t in raw_tools if str(t).strip())
    else:
        tools = ()

    return Persona(
        id=pid,
        name=name,
        description=desc,
        soul_text=body.strip(),
        icon=icon,
        suggested_tools=tools,
        source_path=path,
    )

def _load_one(path: Path) -> Persona | None:

    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("persona_read_failed", path=str(path), error=str(e))
        return None

    meta, body = _parse_frontmatter(raw)
    file_id = path.stem
    return _meta_to_persona(file_id, meta, body, path)

def load_persona(persona_id: str) -> Persona:

    path = personas_dir() / f"{persona_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"persona 不存在: {persona_id} (期望路径 {path})")
    persona = _load_one(path)
    if persona is None:
        raise ValueError(f"persona 加载失败: {persona_id}")
    return persona

def list_personas() -> list[Persona]:

    base = personas_dir()
    if not base.exists():
        logger.info("personas_dir_missing", path=str(base))
        return []

    out: list[Persona] = []
    for p in sorted(base.glob("*.md")):
        persona = _load_one(p)
        if persona is not None:
            out.append(persona)
    return out

def persona_exists(persona_id: str) -> bool:

    return (personas_dir() / f"{persona_id}.md").is_file()

def get_default_persona() -> Persona:

    try:
        return load_persona(DEFAULT_PERSONA_ID)
    except FileNotFoundError:
        logger.warning("default_persona_missing", id=DEFAULT_PERSONA_ID)
        return Persona(
            id=DEFAULT_PERSONA_ID,
            name="默认人格",
            description="占位 persona（文件缺失），请补建 personas/master.md",
            soul_text="",
        )

__all__ = [
    "Persona",
    "DEFAULT_PERSONA_ID",
    "personas_dir",
    "load_persona",
    "list_personas",
    "persona_exists",
    "get_default_persona",
]

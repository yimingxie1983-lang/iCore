

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import structlog

from cancer_claw.config import settings

logger = structlog.get_logger()

_LOCK = threading.RLock()

def _pins_file() -> Path:

    return Path(settings.paths.data_dir) / "skill_pins.json"

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def load_pins() -> list[str]:

    p = _pins_file()
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            ids = data.get("ids") if isinstance(data, dict) else None
            if isinstance(ids, list):
                return [str(x) for x in ids if isinstance(x, str)]
        except Exception as e:
            logger.warning("skill_pins_load_failed", path=str(p), error=str(e))

    return list(settings.skills.pinned or [])

def save_pins(ids: list[str]) -> Path:

    with _LOCK:
        ids_clean = []
        seen: set[str] = set()
        for x in ids:
            if not isinstance(x, str):
                continue
            s = x.strip()
            if s and s not in seen:
                seen.add(s)
                ids_clean.append(s)

        p = _pins_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ids": ids_clean, "updated_at": _now_iso()}
        p.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("skill_pins_saved", count=len(ids_clean), path=str(p))
        return p

def add_pin(skill_id: str) -> list[str]:

    cur = load_pins()
    if skill_id not in cur:
        cur.append(skill_id)
        save_pins(cur)
    return cur

def remove_pin(skill_id: str) -> list[str]:

    cur = load_pins()
    new = [x for x in cur if x != skill_id]
    if len(new) != len(cur):
        save_pins(new)
    return new

__all__ = ["load_pins", "save_pins", "add_pin", "remove_pin"]

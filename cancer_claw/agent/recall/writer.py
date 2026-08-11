

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import structlog

logger = structlog.get_logger()

_MARKER_NO_MEMORY = "<!-- NO_MEMORY_WORTHY -->"
_RE_ONELINE = re.compile(r"^oneline:\s*(.+)$", re.MULTILINE)

_RE_INDEX_END = re.compile(r"^---\s*$", re.MULTILINE)

class MemoryWriter:


    @staticmethod
    def parse_snippet(raw: str) -> dict | None:

        if not raw or not raw.strip():
            return None

        text = raw.strip()


        if _MARKER_NO_MEMORY in text:
            logger.debug("memory_snippet_no_worthy", reason=text)
            return None


        m = _RE_ONELINE.search(text)
        if not m:
            logger.warning("memory_snippet_missing_oneline", raw_head=text[:200])
            return None

        oneline = m.group(1).strip()



        after_oneline = text[m.end():]
        sep = _RE_INDEX_END.search(after_oneline)
        if sep:
            body = after_oneline[sep.end():].strip()
        else:

            body = after_oneline.strip()

        if not body:
            logger.warning("memory_snippet_empty_body", oneline=oneline)

            body = ""

        return {"oneline": oneline, "body": body}

    @staticmethod
    async def append_to_daily(
        digest_dir: Path,
        snippet: dict,
        timestamp: str = "",
        filename_suffix: str = "",
    ):

        if not snippet or not snippet.get("oneline"):
            return

        oneline = snippet["oneline"]
        body = snippet.get("body", "")


        if not timestamp:
            timestamp = datetime.now(timezone.utc).strftime("%H:%M")


        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        digest_dir.mkdir(parents=True, exist_ok=True)
        suffix_part = f"_{filename_suffix}" if filename_suffix else ""
        filepath = digest_dir / f"{today}{suffix_part}.md"


        event_block = f"\n---\n\n## {timestamp} - {oneline}\n"
        if body:
            event_block += f"{body}\n"


        index_line = f"- {timestamp} | {oneline}"

        if filepath.exists():

            content = filepath.read_text(encoding="utf-8")


            sep_match = _RE_INDEX_END.search(content)
            if sep_match:

                insert_pos = sep_match.start()
                new_content = (
                    content[:insert_pos].rstrip()
                    + "\n"
                    + index_line
                    + "\n\n"
                    + content[insert_pos:]
                    + event_block
                )
            else:

                new_content = content.rstrip() + "\n" + index_line + "\n" + event_block

            filepath.write_text(new_content, encoding="utf-8")
        else:

            new_content = (
                f"# {today} 事件摘要\n\n"
                f"## 摘要索引\n"
                f"{index_line}\n\n"
                f"---"
                f"{event_block}"
            )
            filepath.write_text(new_content, encoding="utf-8")

        logger.info(
            "memory_digest_appended",
            file=str(filepath),
            oneline=oneline,
            timestamp=timestamp,
        )

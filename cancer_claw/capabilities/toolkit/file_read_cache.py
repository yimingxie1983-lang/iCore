

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger()

_MAX_READS_PER_PATH = 8

_MAX_ENTRIES = 200

@dataclass
class _Entry:


    mtime_ns: int
    size: int
    reads: list[tuple[int | None, int | None, float]] = field(default_factory=list)

    total_reads: int = 0
    last_ts: float = 0.0

class FileReadCache:


    def __init__(self):
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}



    @staticmethod
    def _key(path: Path) -> str:

        try:
            return str(path.resolve()).replace("\\", "/").lower()
        except OSError:
            return str(path).replace("\\", "/").lower()

    @staticmethod
    def _normalize_window(offset: int | None, limit: int | None) -> tuple[int | None, int | None]:



        if offset == 0:
            offset = None

        if limit is not None and limit <= 0:
            limit = None
        return offset, limit

    def _evict_if_full(self) -> None:

        if len(self._entries) <= _MAX_ENTRIES:
            return
        n_evict = max(1, len(self._entries) - _MAX_ENTRIES + len(self._entries) // 10)
        oldest = sorted(self._entries.items(), key=lambda kv: kv[1].last_ts)[:n_evict]
        for k, _ in oldest:
            self._entries.pop(k, None)



    def check_hit(
        self,
        path: Path,
        offset: int | None,
        limit: int | None,
    ) -> dict | None:

        try:
            st = path.stat()
        except OSError:

            return None

        key = self._key(path)
        offset, limit = self._normalize_window(offset, limit)

        with self._lock:
            ent = self._entries.get(key)


            if ent is None:
                return None


            if ent.mtime_ns != st.st_mtime_ns or ent.size != st.st_size:
                self._entries.pop(key, None)
                logger.debug(
                    "file_read_cache_invalidated_by_mtime",
                    path=key,
                    old_mtime_ns=ent.mtime_ns,
                    new_mtime_ns=st.st_mtime_ns,
                )
                return None


            same_window = any(
                (o == offset and lo == limit) for o, lo, _ts in ent.reads
            )
            if not same_window:

                return None


            recent = ent.reads[-3:] if len(ent.reads) >= 1 else []
            windows_text = ", ".join(
                f"(offset={o},limit={lo})" for o, lo, _ts in recent
            )
            age_s = time.time() - ent.last_ts
            note = (
                f"\n\n[file_read_cache] 此文件你本会话已读取 {ent.total_reads + 1} 次"
                f"（mtime 与上次一致，内容未变；最近一次约 {age_s:.0f} 秒前）。"
                f"\n请基于上方真实内容继续工作；"
                f"反复读同一文件不会得到新信息，也会浪费上下文窗口。"
            )
            return {
                "total_reads": ent.total_reads,
                "age_s": age_s,
                "recent_windows": windows_text,
                "note": note,
            }

    def record(
        self,
        path: Path,
        offset: int | None,
        limit: int | None,
    ) -> None:

        try:
            st = path.stat()
        except OSError:
            return

        key = self._key(path)
        offset, limit = self._normalize_window(offset, limit)
        now = time.time()

        with self._lock:
            ent = self._entries.get(key)

            if (
                ent is None
                or ent.mtime_ns != st.st_mtime_ns
                or ent.size != st.st_size
            ):
                ent = _Entry(mtime_ns=st.st_mtime_ns, size=st.st_size)
                self._entries[key] = ent

            ent.reads.append((offset, limit, now))
            if len(ent.reads) > _MAX_READS_PER_PATH:
                ent.reads = ent.reads[-_MAX_READS_PER_PATH:]
            ent.total_reads += 1
            ent.last_ts = now

            self._evict_if_full()

    def invalidate(self, path: Path) -> None:

        key = self._key(path)
        with self._lock:
            if self._entries.pop(key, None) is not None:
                logger.debug("file_read_cache_invalidated_manually", path=key)

    def reset(self) -> None:

        with self._lock:
            n = len(self._entries)
            self._entries.clear()
            if n:
                logger.debug("file_read_cache_reset", cleared=n)



    def stats(self) -> dict[str, int]:

        with self._lock:
            total_files = len(self._entries)
            total_reads = sum(e.total_reads for e in self._entries.values())
            return {"files": total_files, "total_reads": total_reads}

_global = FileReadCache()

def get_file_read_cache() -> FileReadCache:

    return _global

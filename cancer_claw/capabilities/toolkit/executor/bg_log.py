

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()

_HEADER_RESERVED_BYTES = 1024

_METADATA_REFRESH_INTERVAL = 5.0

class BgLogFile:


    def __init__(
        self,
        path: Path,
        *,
        pid: int,
        command: list[str] | str,
        cwd: str | None,
    ) -> None:
        self.path = path
        self.pid = pid
        self.command_str = (
            " ".join(command) if isinstance(command, list) else str(command)
        )
        self.cwd = cwd or ""
        self.started_at = datetime.now(timezone.utc).astimezone()
        self._started_monotonic = time.monotonic()

        self._lock = threading.Lock()
        self._closed = False
        self._final_status: str = "running"
        self._final_returncode: Optional[int] = None
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._tick_callback = None

        self.path.parent.mkdir(parents=True, exist_ok=True)


        with self.path.open("wb") as fh:
            header_bytes = self._render_header(running_for_ms=0)
            fh.write(self._pad_header(header_bytes))





    def start(self, *, tick_callback=None) -> None:

        if self._refresh_thread is not None:
            return
        self._tick_callback = tick_callback
        t = threading.Thread(
            target=self._refresh_loop,
            daemon=True,
            name=f"bg-log-{self.pid}",
        )
        t.start()
        self._refresh_thread = t

    def _refresh_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._tick_callback is not None:
                    self._tick_callback(self)
                if not self._closed:
                    self._update_header_inplace()
            except Exception as e:
                logger.warning("bg_log_refresh_failed", pid=self.pid, error=str(e))
            self._stop_event.wait(_METADATA_REFRESH_INTERVAL)





    def write_chunk(self, stream: str, data: bytes) -> None:

        if not data or self._closed:
            return
        ts = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S")


        prefix = f"[{ts}] [{stream}] ".encode("utf-8")
        try:
            with self._lock:
                if self._closed:
                    return
                with self.path.open("ab") as fh:
                    fh.write(prefix)
                    fh.write(data)
                    if not data.endswith(b"\n"):
                        fh.write(b"\n")
        except Exception as e:

            logger.warning("bg_log_write_failed", pid=self.pid, error=str(e))

    def update_header(
        self,
        *,
        status: str | None = None,
        returncode: int | None = None,
    ) -> None:

        if status is not None:
            self._final_status = status
        if returncode is not None:
            self._final_returncode = returncode
        if self._closed:
            return
        try:
            with self._lock:
                self._update_header_inplace()
        except Exception as e:
            logger.warning("bg_log_update_header_failed", pid=self.pid, error=str(e))

    def _update_header_inplace(self) -> None:

        running_ms = int((time.monotonic() - self._started_monotonic) * 1000)
        header = self._render_header(running_for_ms=running_ms)
        padded = self._pad_header(header)
        with self.path.open("r+b") as fh:
            fh.seek(0)
            fh.write(padded)





    def close(self, returncode: int | None, *, status: str = "exited") -> None:

        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._final_status = status
            self._final_returncode = returncode
            elapsed_ms = int((time.monotonic() - self._started_monotonic) * 1000)


            footer = self._render_footer(returncode=returncode, elapsed_ms=elapsed_ms)
            try:
                with self.path.open("ab") as fh:
                    fh.write(footer.encode("utf-8"))
            except Exception as e:
                logger.warning("bg_log_footer_failed", pid=self.pid, error=str(e))


            try:
                self._update_header_inplace()
            except Exception as e:
                logger.warning(
                    "bg_log_close_header_failed", pid=self.pid, error=str(e)
                )

        self._stop_event.set()






    def _render_header(self, *, running_for_ms: int) -> bytes:
        rc_text = (
            "null" if self._final_returncode is None else str(self._final_returncode)
        )

        lines = [
            "---",
            f"pid: {self.pid}",
            f"command: {self.command_str}",
            f"cwd: {self.cwd}",
            f"started_at: {self.started_at.isoformat(timespec='seconds')}",
            f"status: {self._final_status}",
            f"running_for_ms: {running_for_ms}",
            f"last_exit_code: {rc_text}",
            "---",
            "",
        ]
        return ("\n".join(lines)).encode("utf-8")

    @staticmethod
    def _pad_header(header: bytes) -> bytes:

        if len(header) > _HEADER_RESERVED_BYTES:


            return header[: _HEADER_RESERVED_BYTES - 1] + b"\n"

        pad_len = _HEADER_RESERVED_BYTES - len(header)
        return header + b" " * (pad_len - 1) + b"\n"

    def _render_footer(self, *, returncode: int | None, elapsed_ms: int) -> str:
        rc_text = "null" if returncode is None else str(returncode)
        return (
            "\n---\n"
            f"exit_code: {rc_text}\n"
            f"elapsed_ms: {elapsed_ms}\n"
            f"final_status: {self._final_status}\n"
            "---\n"
        )

__all__ = ["BgLogFile"]

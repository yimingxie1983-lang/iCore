"""把已落库的会话、事件和工作区文件按当前隐私规则回填脱敏。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from cancer_claw.config import settings
from cancer_claw.services.privacy.desensitizer import desensitize_file, desensitize_text

logger = structlog.get_logger()

SKIP_DIR = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    "dist",
    "build",
    ".cache",
    "site-packages",
    "sandbox_home",
}
SKIP_PATH_PARTS = (
    "sandbox_home",
    "site-packages",
    "pip-download",
    "uv/cache",
    "chrome/user data",
)
PROCESS_EXT = {
    ".md",
    ".txt",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".html",
    ".htm",
    ".xml",
    ".yml",
    ".yaml",
    ".log",
    ".rst",
    ".tex",
    ".sql",
    ".r",
    ".py",
    ".ipynb",
    ".docx",
    ".xlsx",
    ".dcm",
    ".dicom",
}


def _merge(dst: dict[str, int], src: dict[str, int]) -> None:
    for k, v in src.items():
        dst[k] = dst.get(k, 0) + v


def _should_skip_dir(dirpath: str) -> bool:
    low = dirpath.replace("\\", "/").lower()
    return any(part in low for part in SKIP_PATH_PARTS)


def backfill_database(conn: sqlite3.Connection, *, dry_run: bool) -> dict[str, Any]:
    hits: dict[str, int] = {}
    conv_changed = 0
    sess_changed = 0
    event_changed = 0

    rows = conn.execute(
        "SELECT id, content, tool_calls_json, name FROM conversation_history"
    ).fetchall()
    for row_id, content, tools, name in rows:
        new_content = content or ""
        new_tools = tools or ""
        new_name = name or ""
        row_hits: dict[str, int] = {}
        if new_content:
            r = desensitize_text(new_content, context="backfill:conv", force=True)
            new_content = r.text
            _merge(row_hits, r.hits)
        if new_tools:
            r = desensitize_text(new_tools, context="backfill:tools", force=True)
            new_tools = r.text
            _merge(row_hits, r.hits)
        if new_name:
            r = desensitize_text(new_name, context="backfill:name", force=True)
            new_name = r.text
            _merge(row_hits, r.hits)
        if not row_hits:
            continue
        _merge(hits, row_hits)
        conv_changed += 1
        if not dry_run:
            conn.execute(
                "UPDATE conversation_history SET content=?, tool_calls_json=?, name=? WHERE id=?",
                (new_content, new_tools or None, new_name or None, row_id),
            )

    for row_id, title, preview in conn.execute(
        "SELECT session_id, title, preview FROM chat_sessions"
    ):
        new_title = title or ""
        new_preview = preview or ""
        row_hits = {}
        if new_title:
            r = desensitize_text(new_title, context="backfill:title", force=True)
            new_title = r.text
            _merge(row_hits, r.hits)
        if new_preview:
            r = desensitize_text(new_preview, context="backfill:preview", force=True)
            new_preview = r.text
            _merge(row_hits, r.hits)
        if not row_hits:
            continue
        _merge(hits, row_hits)
        sess_changed += 1
        if not dry_run:
            conn.execute(
                "UPDATE chat_sessions SET title=?, preview=? WHERE session_id=?",
                (new_title, new_preview, row_id),
            )

    tables = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "agent_events" in tables:
        for row_id, payload in conn.execute(
            "SELECT id, payload_json FROM agent_events"
        ):
            if not payload:
                continue
            r = desensitize_text(payload, context="backfill:event", force=True)
            if not r.changed:
                continue
            _merge(hits, r.hits)
            event_changed += 1
            if not dry_run:
                conn.execute(
                    "UPDATE agent_events SET payload_json=? WHERE id=?",
                    (r.text, row_id),
                )

    if not dry_run:
        conn.commit()
    return {
        "conversation_rows_changed": conv_changed,
        "session_rows_changed": sess_changed,
        "event_rows_changed": event_changed,
        "hits": hits,
    }


def backfill_workspace(root: Path, *, dry_run: bool) -> dict[str, Any]:
    hits: dict[str, int] = {}
    files_changed = 0
    dicom_changed = 0
    scanned = 0
    if not root.exists():
        return {
            "scanned": 0,
            "files_changed": 0,
            "dicom_changed": 0,
            "hits": hits,
        }

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in SKIP_DIR and not d.startswith(".")
        ]
        if _should_skip_dir(dirpath):
            dirnames[:] = []
            continue
        for fn in filenames:
            path = Path(dirpath) / fn
            scanned += 1
            if path.suffix.lower() not in PROCESS_EXT:
                continue
            if dry_run:
                suffix = path.suffix.lower()
                if suffix in {".dcm", ".dicom", ".docx", ".xlsx"}:
                    continue
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if size == 0 or size > 8_000_000:
                    continue
                try:
                    text = path.read_bytes()[:8_000_000].decode("utf-8", errors="ignore")
                except OSError:
                    continue
                r = desensitize_text(text, context="backfill:file", force=True)
                if r.changed:
                    files_changed += 1
                    _merge(hits, r.hits)
                continue
            r = desensitize_file(path, context="backfill:file", force=True)
            if not r.changed:
                continue
            files_changed += 1
            _merge(hits, r.hits)
            if path.suffix.lower() in {".dcm", ".dicom"}:
                dicom_changed += 1

    return {
        "scanned": scanned,
        "files_changed": files_changed,
        "dicom_changed": dicom_changed,
        "hits": hits,
    }


def _backup_sqlite(db_path: Path) -> Path | None:
    if not db_path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = db_path.with_name(f"{db_path.name}.bak-privacy-{stamp}")
    shutil.copy2(db_path, dest)
    for suffix in ("-wal", "-shm"):
        extra = Path(str(db_path) + suffix)
        if extra.exists():
            shutil.copy2(extra, Path(str(dest) + suffix))
    return dest


def run_backfill(*, dry_run: bool = False, backup: bool = True) -> dict[str, Any]:
    db_path = Path(settings.database.path)
    ws_root = Path(settings.paths.projects_dir)
    backup_path = None
    if not dry_run and backup and not settings.database.is_postgres:
        backup_path = _backup_sqlite(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        db_stats = backfill_database(conn, dry_run=dry_run)
    finally:
        conn.close()

    projects: list[tuple[str, str]] = []
    conn = sqlite3.connect(str(db_path))
    try:
        projects = [
            (r[0], r[1])
            for r in conn.execute("SELECT id, workspace_path FROM projects")
        ]
        registered = {p[0] for p in projects}
        if ws_root.exists():
            for d in ws_root.iterdir():
                if d.is_dir() and d.name not in registered:
                    projects.append((d.name, str(d)))
    finally:
        conn.close()

    file_hits: dict[str, int] = {}
    files_changed = 0
    dicom_changed = 0
    scanned = 0
    per_project: list[dict[str, Any]] = []
    seen_roots: set[str] = set()
    for pid, wsp in projects:
        root = Path(wsp) if wsp else ws_root / pid
        key = str(root.resolve()) if root.exists() else str(root)
        if key in seen_roots:
            continue
        seen_roots.add(key)
        st = backfill_workspace(root, dry_run=dry_run)
        scanned += st["scanned"]
        files_changed += st["files_changed"]
        dicom_changed += st["dicom_changed"]
        _merge(file_hits, st["hits"])
        if st["files_changed"] or st["dicom_changed"]:
            per_project.append(
                {
                    "project_id": pid,
                    "files_changed": st["files_changed"],
                    "dicom_changed": st["dicom_changed"],
                    "hits": st["hits"],
                }
            )

    summary = {
        "dry_run": dry_run,
        "backup": str(backup_path) if backup_path else None,
        "database": db_stats,
        "files": {
            "scanned": scanned,
            "files_changed": files_changed,
            "dicom_changed": dicom_changed,
            "hits": file_hits,
            "projects": per_project,
        },
    }
    logger.info("privacy_backfill_done", **{k: v for k, v in summary.items() if k != "files"})
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="回填脱敏 iCore 会话与项目工作区")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写回")
    parser.add_argument("--no-backup", action="store_true", help="不备份 SQLite")
    args = parser.parse_args(argv)
    summary = run_backfill(dry_run=args.dry_run, backup=not args.no_backup)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

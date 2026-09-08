"""Pack a portable iCore tree for installing on another server.

Keeps project DB + workspaces so projects remain listable and openable.
Skips bulky extra disks (D:\\temp, D:\\test_pdyy, D:\\data) and runtime caches.
Strips all LLM providers except Moonshot Kimi.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import stat
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
OUT_ROOT = Path(r"D:\backage")
STAMP = datetime.now().strftime("%Y%m%d_%H%M")
STAGE_NAME = f"icore-portable-{STAMP}"
SKIP_ABS_PREFIXES = (
    Path(r"D:\temp").resolve(),
    Path(r"D:\test_pdyy").resolve(),
    Path(r"D:\data").resolve(),
)

DIR_NAME_SKIP = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".cursor",
    "ppt_work",
    "sandbox_home",
    "huggingface",
    "hub",
}

DIR_PREFIX_SKIP = (".venv",)

FILE_SUFFIX_SKIP = {
    ".pyc",
    ".pyo",
    ".log",
    ".tsbuildinfo",
}

REL_SKIP_PREFIXES = (
    "ops/client/",
    "cancer_claw/var/state/cancer_claw.db.bak",
)

# DM 扩展预测：标准化病历 parquet 仅用于离线分析，不参与项目列表/会话/对话展示。
DM_STD_PARQUET_PROJECT = "743e2dccdce7"

# DM 项目标准化病历 parquet：项目列表/会话/对话均在 SQLite，不依赖这些文件。
DM_STD_PARQUET_MARKERS = ("/743e2dccdce7/", "/output/std/")


def _under_skip_abs(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for root in SKIP_ABS_PREFIXES:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def should_skip(path: Path, *, is_dir: bool) -> bool:
    name = path.name
    if name in DIR_NAME_SKIP:
        return True
    if is_dir and any(name.startswith(p) for p in DIR_PREFIX_SKIP):
        return True
    if not is_dir:
        if path.suffix.lower() in FILE_SUFFIX_SKIP:
            return True
        if name.endswith(("-shm", "-wal", ".pid")):
            return True
        if name == "cancer_claw.db" or name.startswith("cancer_claw.db.bak"):
            return True
    rel = path.relative_to(REPO).as_posix()
    posix = rel.replace("\\", "/")
    if (
        not is_dir
        and path.suffix.lower() == ".parquet"
        and f"/{DM_STD_PARQUET_PROJECT}/" in f"/{posix}/"
        and "/output/std/" in f"/{posix}/"
    ):
        return True
    for pref in REL_SKIP_PREFIXES:
        if rel == pref.rstrip("/") or rel.startswith(pref):
            return True
    if "pip/cache" in rel.replace("\\", "/") or "/pip/cache/" in f"/{rel}/":
        return True
    if _under_skip_abs(path):
        return True
    return False


def copy_tree(src: Path, dst: Path) -> tuple[int, int]:
    files = 0
    skipped = 0
    for root, dirs, filenames in os.walk(src, topdown=True, followlinks=False):
        root_p = Path(root)
        keep_dirs = []
        for d in dirs:
            child = root_p / d
            if should_skip(child, is_dir=True):
                skipped += 1
                continue
            keep_dirs.append(d)
        dirs[:] = keep_dirs
        rel_root = root_p.relative_to(src)
        dest_root = dst / rel_root
        dest_root.mkdir(parents=True, exist_ok=True)
        for fn in filenames:
            src_f = root_p / fn
            if should_skip(src_f, is_dir=False):
                skipped += 1
                continue
            dest_f = dest_root / fn
            try:
                shutil.copy2(src_f, dest_f, follow_symlinks=False)
                files += 1
            except OSError as e:
                print(f"skip copy {src_f}: {e}", flush=True)
                skipped += 1
    return files, skipped


def write_kimi_providers(path: Path) -> None:
    data = {
        "providers": [
            {
                "id": "moonshot",
                "name": "Moonshot Kimi",
                "base_url": "https://api.moonshot.cn/v1",
                "api_key": "",
                "models": [
                    {"id": "kimi-k2.6", "role": "general"},
                    {"id": "kimi-k2.6", "role": "fast"},
                    {"id": "kimi-k2.6", "role": "complex"},
                ],
                "enabled": True,
                "priority": 0,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def sanitize_config(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        r"  tool_path_allow_extra:\n(?:    - [^\n]+\n)+",
        "  tool_path_allow_extra: []\n",
        text,
        count=1,
    )
    text = text.replace("QWEN_API_KEY", "MOONSHOT_API_KEY")
    if "D:\\data" in text or "D:\\demo" in text or "QWEN_API_KEY" in text:
        raise SystemExit(f"failed to sanitize extra paths / other providers in {path}")
    path.write_text(text, encoding="utf-8")


def backup_sqlite(src_db: Path, dest_db: Path) -> None:
    dest_db.parent.mkdir(parents=True, exist_ok=True)
    if dest_db.exists():
        dest_db.unlink()
    src = sqlite3.connect(f"file:{src_db.as_posix()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(dest_db))
        try:
            src.backup(dst)
            dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()


def rebase_workspace_paths(db_path: Path) -> None:
    """Rewrite absolute host paths so projects and agents work on another machine."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE projects SET workspace_path = './cancer_claw/var/workspaces/' || id"
        )
        conn.execute(
            "UPDATE agents SET soul_path = './cancer_claw/var/agent_instances/' || id || '/soul.md' "
            "WHERE IFNULL(soul_path, '') != ''"
        )
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        a = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        print(f"rebased workspace_path for {n} projects, soul_path for {a} agents", flush=True)
    finally:
        conn.close()


def write_install_notes(stage: Path) -> None:
    (stage / "start-on-server.ps1").write_text(
        """param([string]$ProjectRoot = $PSScriptRoot)
$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot
Write-Host "[iCore] 安装/启动（仅后端，已内置 web/dist）"
$py = Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"
if (-not (Test-Path -LiteralPath $py)) {
  python -m venv .venv
  $py = Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"
}
& $py -m pip install -U pip
& $py -m pip install -e .
Write-Host "[iCore] 浏览器访问 http://本机IP:8010/  （详见 安装部署说明书.md）"
& $py (Join-Path $ProjectRoot "run_server.py")
""",
        encoding="utf-8",
    )
    (stage / "start-on-server.sh").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "[iCore] install/start (backend + web/dist)"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -U pip
.venv/bin/pip install -e .
echo "[iCore] open http://SERVER_IP:8010/  (see 安装部署说明书.md)"
exec .venv/bin/python run_server.py
""",
        encoding="utf-8",
        newline="\n",
    )
    guide_src = REPO / "ops" / "安装部署说明书.md"
    guide_text = guide_src.read_text(encoding="utf-8") if guide_src.is_file() else ""
    if guide_text:
        (stage / "安装部署说明书.md").write_text(guide_text, encoding="utf-8")
    (stage / "安装说明.txt").write_text(
        "请阅读同目录《安装部署说明书.md》。\n"
        "Windows: powershell -ExecutionPolicy Bypass -File .\\start-on-server.ps1\n"
        "Linux:   bash ./start-on-server.sh\n"
        "浏览器:  http://服务器IP:8010/\n",
        encoding="utf-8",
    )


def assert_kimi_only(stage: Path) -> None:
    forbidden = ("deepseek", "dashscope", "openai", "qwen", "glm", "zhipu", "ollama")
    for rel in (
        "cancer_claw/var/state/providers.yaml",
        "config.yaml",
        "ops/config/production.yaml",
    ):
        path = stage / rel
        if not path.is_file():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        providers = data.get("providers") or []
        ids = [str(p.get("id", "")).lower() for p in providers if isinstance(p, dict)]
        if ids != ["moonshot"]:
            raise SystemExit(f"{rel} providers must be moonshot only, got {ids}")
        blob = path.read_text(encoding="utf-8").lower()
        for word in forbidden:
            if f"id: {word}" in blob or f"id: {word}_" in blob:
                raise SystemExit(f"{rel} still contains provider token: {word}")


def zip_stage(stage: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(
        zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True
    ) as zf:
        for file in stage.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(stage.parent).as_posix())


def main() -> int:
    src_db = REPO / "cancer_claw" / "var" / "state" / "cancer_claw.db"
    if not src_db.is_file():
        print(f"missing db: {src_db}", file=sys.stderr)
        return 1

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    stage = OUT_ROOT / STAGE_NAME
    if stage.exists():
        shutil.rmtree(stage, onerror=lambda fn, p, _exc: (os.chmod(p, stat.S_IWRITE), fn(p)))
    stage.mkdir(parents=True)

    print(f"copy {REPO} -> {stage}", flush=True)
    files, skipped = copy_tree(REPO, stage)
    print(f"copied files={files} skipped_entries={skipped}", flush=True)
    dm_std = stage / "cancer_claw" / "var" / "workspaces" / DM_STD_PARQUET_PROJECT / "workspace" / "output" / "std"
    leftover = list(dm_std.glob("*.parquet")) if dm_std.is_dir() else []
    if leftover:
        raise SystemExit(f"DM std parquet still packed: {[p.name for p in leftover]}")
    print(
        f"DM std parquet skipped; manifests kept={len(list(dm_std.glob('*.manifest.json'))) if dm_std.is_dir() else 0}",
        flush=True,
    )

    dest_db = stage / "cancer_claw" / "var" / "state" / "cancer_claw.db"
    print("snapshot sqlite ...", flush=True)
    backup_sqlite(src_db, dest_db)
    rebase_workspace_paths(dest_db)

    write_kimi_providers(stage / "cancer_claw" / "var" / "state" / "providers.yaml")
    sanitize_config(stage / "config.yaml")
    write_install_notes(stage)
    assert_kimi_only(stage)

    zip_path = OUT_ROOT / f"{STAGE_NAME}.zip"
    print(f"zip -> {zip_path}", flush=True)
    zip_stage(stage, zip_path)
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"done zip={zip_path} size={size_mb:.1f} MB stage={stage}", flush=True)
    extra_guide = OUT_ROOT / "安装部署说明书.md"
    extra_guide.write_text(
        (stage / "安装部署说明书.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    print(f"guide={extra_guide}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

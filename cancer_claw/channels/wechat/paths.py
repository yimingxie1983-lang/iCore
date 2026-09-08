"""本机微信桥状态目录（对标 ~/.codexbridge）。"""

from __future__ import annotations

import os
from pathlib import Path


def icore_home() -> Path:
    env = (os.environ.get("ICORE_HOME") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / ".icore").resolve()


def wechat_root() -> Path:
    return icore_home() / "wechat"


def accounts_dir() -> Path:
    d = wechat_root() / "accounts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def inbound_dir(account_id: str) -> Path:
    d = wechat_root() / "inbound" / account_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def runtime_dir() -> Path:
    d = wechat_root() / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


def serve_lock_path() -> Path:
    return runtime_dir() / "wechat-serve.lock"

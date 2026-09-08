"""微信账号 / context_token / sync cursor 落盘。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cancer_claw.channels.wechat.paths import accounts_dir


class WechatAccountStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or accounts_dir()
        self.root.mkdir(parents=True, exist_ok=True)

    def list_accounts(self) -> list[str]:
        ids: list[str] = []
        for p in self.root.glob("*.json"):
            name = p.name
            if name.endswith(".context-tokens.json") or name.endswith(".sync.json"):
                continue
            ids.append(p.stem)
        return sorted(ids)

    def account_file(self, account_id: str) -> Path:
        return self.root / f"{account_id}.json"

    def context_tokens_file(self, account_id: str) -> Path:
        return self.root / f"{account_id}.context-tokens.json"

    def sync_file(self, account_id: str) -> Path:
        return self.root / f"{account_id}.sync.json"

    def save_account(
        self,
        *,
        account_id: str,
        token: str,
        base_url: str,
        user_id: str = "",
    ) -> dict[str, Any]:
        payload = {
            "token": token,
            "base_url": base_url,
            "user_id": user_id,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_json(self.account_file(account_id), payload)
        return payload

    def load_account(self, account_id: str) -> dict[str, Any] | None:
        return self._read_json(self.account_file(account_id))

    def load_default_account(self) -> tuple[str, dict[str, Any]] | None:
        ids = self.list_accounts()
        if not ids:
            return None
        data = self.load_account(ids[0])
        if not data:
            return None
        return ids[0], data

    def get_context_token(self, account_id: str, peer_id: str) -> str | None:
        tokens = self._read_json(self.context_tokens_file(account_id)) or {}
        val = tokens.get(peer_id)
        return str(val) if isinstance(val, str) and val else None

    def set_context_token(self, account_id: str, peer_id: str, context_token: str) -> None:
        path = self.context_tokens_file(account_id)
        tokens = self._read_json(path) or {}
        tokens[peer_id] = context_token
        self._write_json(path, tokens)

    def clear_context_tokens(self, account_id: str) -> None:
        path = self.context_tokens_file(account_id)
        if path.exists():
            path.unlink()

    def load_sync_cursor(self, account_id: str) -> str:
        data = self._read_json(self.sync_file(account_id)) or {}
        return str(data.get("get_updates_buf") or "")

    def save_sync_cursor(self, account_id: str, sync_cursor: str) -> None:
        self._write_json(self.sync_file(account_id), {"get_updates_buf": sync_cursor or ""})

    def _read_json(self, path: Path) -> Any | None:
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _write_json(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

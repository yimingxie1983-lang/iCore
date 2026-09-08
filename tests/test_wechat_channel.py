"""微信渠道单元测试（无网络）。"""

from __future__ import annotations

import pytest

from cancer_claw.channels.commands import parse_slash_command
from cancer_claw.channels.narration import EpisodeAccumulator
from cancer_claw.channels.wechat.formatting import (
    format_weixin_text,
    split_weixin_text,
    utf8_byte_length,
)


def test_parse_slash_command():
    assert parse_slash_command("hello") is None
    assert parse_slash_command("/") is None
    cmd = parse_slash_command("/bind ABC123")
    assert cmd is not None
    assert cmd.name == "bind"
    assert cmd.args == "ABC123"
    assert parse_slash_command("/HELP").name == "help"
    assert parse_slash_command("/bind\r ABC").name == "bind"
    assert parse_slash_command("/bind\u200b XYZ").name == "bind"
    assert parse_slash_command("／绑定 CODE1").name == "bind"


def test_format_and_split_weixin_text():
    text = format_weixin_text("# 标题\n\n正文一段")
    assert "【标题】" in text
    long = "测" * 2000
    chunks = split_weixin_text(long)
    assert len(chunks) >= 2
    assert all(utf8_byte_length(c) <= 2048 for c in chunks)


def test_episode_accumulator_progress():
    acc = EpisodeAccumulator()
    assert acc.feed({"type": "thinking", "content": "需要先看一下配置文件再改"}) is None
    assert acc.feed({"type": "tool_call", "tool": "read_file", "arguments": {"path": "a.yaml"}}) is None
    assert acc.feed({"type": "tool_result", "tool": "read_file", "success": True}) is None
    assert acc.feed({"type": "tool_call", "tool": "write_file", "arguments": {"path": "a.yaml"}}) is None
    assert acc.feed({"type": "tool_result", "tool": "write_file", "success": True}) is None
    line = acc.feed({"type": "tool_call", "tool": "run_command", "arguments": {"command": "ls"}})
    # 第三个 tool_call 时尚未 flush；结果回来才可能 flush
    assert line is None
    line = acc.feed({"type": "tool_result", "tool": "run_command", "success": True})
    assert line is not None
    assert "正在" in line


@pytest.mark.asyncio
async def test_bind_code_roundtrip(tmp_path):
    from cancer_claw.config import settings
    from cancer_claw.db import close_db, init_db
    from cancer_claw.channels import binding as binding_svc

    old = settings.database.path
    settings.database.path = str(tmp_path / "wechat-bind.db")
    await close_db()
    await init_db()
    try:
        created = await binding_svc.create_bind_code(
            user_id="u1",
            project_id="p1",
            permissions_mode="ask",
            ttl_seconds=120,
        )
        assert created["code"]
        binding = await binding_svc.consume_bind_code(created["code"], external_scope_id="wx_peer_1")
        assert binding is not None
        assert binding["user_id"] == "u1"
        assert binding["project_id"] == "p1"
        assert binding["external_scope_id"] == "wx_peer_1"
        assert await binding_svc.consume_bind_code(created["code"], external_scope_id="wx_peer_2") is None
        got = await binding_svc.get_binding("wechat", "wx_peer_1")
        assert got and got["project_id"] == "p1"
    finally:
        await close_db()
        settings.database.path = old

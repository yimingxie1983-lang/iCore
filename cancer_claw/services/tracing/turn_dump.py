

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from cancer_claw.agent.context_window.budget import estimate_tokens

logger = structlog.get_logger()

def _fmt_int(n: int) -> str:
    return f"{n:,}"

def _fmt_pct(num: int, total: int) -> str:
    return "0.0%" if total == 0 else f"{num / total * 100:.1f}%"

def _bar(value: int, max_value: int, width: int = 30) -> str:
    if max_value == 0:
        return ""
    filled = int(value / max_value * width)
    return "█" * filled + "░" * (width - filled)

def is_enabled() -> bool:

    if os.environ.get("ONEKEY_DIAGNOSTICS_DUMP", "").lower() in ("1", "true", "yes"):
        return True
    try:
        from cancer_claw.config import settings
        return bool(getattr(settings, "diagnostics", None) and settings.diagnostics.dump_after_chat)
    except Exception:
        return False

def dump_turn_diagnostic(
    agent: Any,
    *,
    user_message: str = "",
    final_content: str = "",
    iterations: int = 0,
    elapsed_seconds: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> Path | None:

    if not is_enabled():
        return None

    try:
        return _do_dump(
            agent,
            user_message=user_message,
            final_content=final_content,
            iterations=iterations,
            elapsed_seconds=elapsed_seconds,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    except Exception as e:
        logger.warning("diagnostics_dump_failed", agent_id=getattr(agent, "id", "?"), error=str(e))
        return None

def _do_dump(
    agent: Any,
    *,
    user_message: str,
    final_content: str,
    iterations: int,
    elapsed_seconds: float,
    input_tokens: int,
    output_tokens: int,
) -> Path | None:


    ws = getattr(agent, "_bound_workspace", None)
    if ws is None:

        out_dir = Path.cwd() / ".diagnostics"
    else:
        root_attr = getattr(ws, "default_relative_root", None) or getattr(ws, "workspace_root", None)
        if root_attr is None:
            return None
        out_dir = Path(root_attr) / ".diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"turn_{ts}.md"


    ctx = getattr(agent, "_context", None)
    if ctx is None:
        return None

    messages: list[dict] = list(getattr(ctx, "_messages", []) or [])
    system_parts: dict[str, str] = dict(getattr(ctx, "_system_parts", {}) or {})
    active_tools: list[dict] = list(getattr(ctx, "_active_tools", []) or [])
    tool_usage = dict(getattr(agent, "_tool_usage_this_turn", {}) or {})
    model_calls = getattr(agent, "_model_calls", 0)
    tool_calls = getattr(agent, "_tool_calls", 0)


    lines: list[str] = []
    _write_header(lines, agent, user_message, final_content, ts)
    _write_summary(lines, iterations, elapsed_seconds, model_calls, tool_calls,
                   input_tokens, output_tokens)
    _write_system_parts(lines, system_parts)
    _write_tools_schema(lines, active_tools)
    _write_messages_breakdown(lines, messages)
    _write_tool_results_analysis(lines, messages)
    _write_diagnosis(lines, messages, system_parts, active_tools)
    _write_tool_usage(lines, tool_usage)

    out_path.write_text("\n".join(lines), encoding="utf-8")


    print(
        f"[diagnostics] 已写入 {out_path}（含 {len(messages)} 条消息分析）",
        flush=True,
    )
    return out_path

def _write_header(lines: list[str], agent: Any, user_message: str,
                   final_content: str, ts: str) -> None:
    lines.append(f"# Turn 诊断报告 — {ts}")
    lines.append("")
    lines.append(f"- **Agent**: `{getattr(agent, 'id', '?')}` ({getattr(agent, 'name', '?')})")
    lines.append(f"- **生成时间**: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## 本轮上下文")
    lines.append("")
    lines.append("**用户输入**：")
    lines.append("```")
    lines.append((user_message or "(空)")[:500])
    if len(user_message) > 500:
        lines.append(f"... [总 {len(user_message)} chars]")
    lines.append("```")
    lines.append("")
    lines.append("**模型最终回复**：")
    lines.append("```")
    lines.append((final_content or "(空)")[:500])
    if len(final_content) > 500:
        lines.append(f"... [总 {len(final_content)} chars]")
    lines.append("```")
    lines.append("")

def _write_summary(lines: list[str], iterations: int, elapsed_seconds: float,
                    model_calls: int, tool_calls: int, input_tokens: int,
                    output_tokens: int) -> None:
    lines.append("## 概览")
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|----|")
    lines.append(f"| 推理迭代 | {iterations} 轮 |")
    lines.append(f"| 耗时 | {elapsed_seconds:.1f} 秒 |")
    lines.append(f"| 模型调用次数 | {model_calls} |")
    lines.append(f"| 工具调用次数 | {tool_calls} |")
    lines.append(f"| 累计 input tokens (API 实测) | {_fmt_int(input_tokens)} |")
    lines.append(f"| 累计 output tokens (API 实测) | {_fmt_int(output_tokens)} |")
    lines.append("")

def _write_system_parts(lines: list[str], system_parts: dict[str, str]) -> None:
    lines.append("## System Prompt 各分区占用")
    lines.append("")
    parts_with_tokens = [
        (name, content, estimate_tokens(content))
        for name, content in system_parts.items()
    ]
    total = sum(t for _, _, t in parts_with_tokens)
    if total == 0:
        lines.append("(系统提示为空)")
        lines.append("")
        return

    max_t = max(t for _, _, t in parts_with_tokens)
    lines.append("| 分区 | tokens (est.) | 占比 | 分布 |")
    lines.append("|------|---------------|------|------|")
    for name, content, t in sorted(parts_with_tokens, key=lambda x: -x[2]):
        if t == 0:
            continue
        lines.append(f"| `{name}` | {_fmt_int(t)} | {_fmt_pct(t, total)} | `{_bar(t, max_t, width=20)}` |")
    lines.append(f"| **TOTAL** | **{_fmt_int(total)}** | **100%** | |")
    lines.append("")
    if total > 10000:
        lines.append(f"> ⚠️ system prompt 估算 {_fmt_int(total)} tokens，每轮都重发，多轮累积成本较高")
        lines.append("")

def _write_tools_schema(lines: list[str], active_tools: list[dict]) -> None:
    lines.append("## 当前激活工具 schema")
    lines.append("")
    if not active_tools:
        lines.append("(无激活工具)")
        lines.append("")
        return
    import json
    total_t = estimate_tokens(json.dumps(active_tools, ensure_ascii=False))
    lines.append(f"- 工具数量: **{len(active_tools)}**")
    lines.append(f"- 全部 schema 估算 tokens: **{_fmt_int(total_t)}**")
    lines.append("- 工具列表（按 description 长度排序）:")
    lines.append("")
    tool_sizes = []
    for t in active_tools:
        fn = (t or {}).get("function", {})
        name = fn.get("name", "?")
        desc = fn.get("description", "") or ""
        params = fn.get("parameters", {}) or {}
        size = estimate_tokens(json.dumps(t, ensure_ascii=False))
        tool_sizes.append((name, len(desc), size))
    lines.append("| 工具 | description chars | schema tokens |")
    lines.append("|------|-------------------|---------------|")
    for name, desc_len, size in sorted(tool_sizes, key=lambda x: -x[2]):
        lines.append(f"| `{name}` | {desc_len} | {_fmt_int(size)} |")
    lines.append("")

def _write_messages_breakdown(lines: list[str], messages: list[dict]) -> None:
    lines.append("## 对话消息列表（按顺序）")
    lines.append("")
    if not messages:
        lines.append("(消息列表为空)")
        lines.append("")
        return

    role_total: dict[str, int] = {}
    role_count: dict[str, int] = {}
    grand_total = 0
    for msg in messages:
        content = msg.get("content") or ""
        if not isinstance(content, str):
            content = str(content)

        tc_str = ""
        if msg.get("tool_calls"):
            import json
            tc_str = json.dumps(msg["tool_calls"], ensure_ascii=False)
        t = estimate_tokens(content) + estimate_tokens(tc_str)
        role = msg.get("role", "?")
        role_total[role] = role_total.get(role, 0) + t
        role_count[role] = role_count.get(role, 0) + 1
        grand_total += t


    lines.append("### 按 role 汇总")
    lines.append("")
    lines.append("| role | 条数 | tokens (est.) | 占比 | 分布 |")
    lines.append("|------|------|---------------|------|------|")
    max_t = max(role_total.values()) if role_total else 0
    for role, t in sorted(role_total.items(), key=lambda x: -x[1]):
        lines.append(
            f"| `{role}` | {role_count[role]} | {_fmt_int(t)} | "
            f"{_fmt_pct(t, grand_total)} | `{_bar(t, max_t, 20)}` |"
        )
    lines.append(f"| **TOTAL** | **{len(messages)}** | **{_fmt_int(grand_total)}** | **100%** | |")
    lines.append("")


    lines.append("### 逐条明细")
    lines.append("")
    lines.append("| # | role | chars | tokens | 内容预览 |")
    lines.append("|---|------|-------|--------|----------|")
    for i, msg in enumerate(messages):
        content = msg.get("content") or ""
        if not isinstance(content, str):
            content = str(content)
        chars = len(content)
        tc_extra = ""
        if msg.get("tool_calls"):
            import json
            tc_str = json.dumps(msg["tool_calls"], ensure_ascii=False)
            chars += len(tc_str)
            names = [tc.get("function", {}).get("name", "?") for tc in msg["tool_calls"]]
            tc_extra = f" + tool_calls: {names}"
        t = estimate_tokens(content)
        if msg.get("tool_calls"):
            import json
            t += estimate_tokens(json.dumps(msg["tool_calls"], ensure_ascii=False))
        preview = content[:80].replace("\n", " ").replace("|", "\\|")
        if len(content) > 80:
            preview += "..."
        flag = ""
        if chars > 8000:
            flag = " ⚠️大"
        if msg.get("role") == "tool" and (".tool_cache" in content or "已写入 workspace/" in content):
            flag += " 🗄️cached"
        lines.append(
            f"| {i} | `{msg.get('role')}` | {_fmt_int(chars)} | {_fmt_int(t)} | "
            f"{preview}{tc_extra}{flag} |"
        )
    lines.append("")

def _write_tool_results_analysis(lines: list[str], messages: list[dict]) -> None:
    lines.append("## 工具结果输出大小分布")
    lines.append("")
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    if not tool_msgs:
        lines.append("(本轮无工具结果消息)")
        lines.append("")
        return

    sizes = sorted([len(m.get("content") or "") for m in tool_msgs], reverse=True)
    bands = [
        (0, 1000, "S(0-1k chars)"),
        (1000, 4000, "M(1-4k)"),
        (4000, 8000, "L(4-8k)"),
        (8000, 20000, "XL(8-20k)"),
        (20000, float("inf"), "XXL(20k+)"),
    ]
    lines.append("| 区间 | 数量 |")
    lines.append("|------|------|")
    for lo, hi, name in bands:
        count = sum(1 for s in sizes if lo <= s < hi)
        if count > 0:
            lines.append(f"| {name} | {count} |")
    lines.append("")

    cached_count = sum(
        1 for m in tool_msgs
        if ".tool_cache" in (m.get("content") or "") or "已写入 workspace/" in (m.get("content") or "")
    )
    lines.append(f"- 走了 result_compact 落盘的: **{cached_count} / {len(tool_msgs)}**")
    if sizes and sizes[0] > 8000 and cached_count == 0:
        lines.append(f"- ⚠️ 最大 tool 输出 {_fmt_int(sizes[0])} chars 但未触发 result_compact，请检查接入")
    lines.append("")

def _write_diagnosis(lines: list[str], messages: list[dict], system_parts: dict[str, str],
                      active_tools: list[dict]) -> None:
    lines.append("## 🩺 诊断结论")
    lines.append("")
    issues: list[str] = []
    suggestions: list[str] = []


    sys_total = sum(estimate_tokens(c) for c in system_parts.values())
    if sys_total > 15000:
        issues.append(f"🔴 system prompt 估算 {_fmt_int(sys_total)} tokens，每轮重发开销大")

        biggest = max(system_parts.items(), key=lambda x: estimate_tokens(x[1]))
        suggestions.append(
            f"看 `{biggest[0]}` 分区（{_fmt_int(estimate_tokens(biggest[1]))} tokens），考虑精简或按需注入"
        )


    long_tools = [
        m for m in messages
        if m.get("role") == "tool" and len(m.get("content") or "") > 8000
        and ".tool_cache" not in (m.get("content") or "")
    ]
    if long_tools:
        issues.append(
            f"🔴 有 {len(long_tools)} 条 tool 消息超过 8000 chars 但未走 result_compact"
        )
        suggestions.append(
            "检查 agent.py 是否所有工具调用都走了 _compact_tool_feedback_for_context"
        )


    if active_tools:
        import json
        tools_t = estimate_tokens(json.dumps(active_tools, ensure_ascii=False))
        if tools_t > 8000:
            issues.append(f"🟡 工具 schema {_fmt_int(tools_t)} tokens，考虑减少同时激活的工具数")


    grand_total = sys_total + sum(
        estimate_tokens(m.get("content") or "") for m in messages
    )
    lines.append(f"**估算总上下文** (system + messages): **{_fmt_int(grand_total)} tokens**")
    lines.append("")
    if grand_total > 60000:
        issues.append(f"🔴 总上下文已达 {_fmt_int(grand_total)} tokens，接近常见模型窗口")
    elif grand_total > 30000:
        issues.append(f"🟡 总上下文 {_fmt_int(grand_total)} tokens，多轮后会快速膨胀")

    if not issues:
        lines.append("✅ **未发现明显问题**，上下文管理状态健康。")
    else:
        lines.append("### 发现的问题")
        lines.append("")
        for issue in issues:
            lines.append(f"- {issue}")
        lines.append("")
        if suggestions:
            lines.append("### 建议")
            lines.append("")
            for s in suggestions:
                lines.append(f"- {s}")
    lines.append("")

def _write_tool_usage(lines: list[str], tool_usage: dict[str, int]) -> None:
    if not tool_usage:
        return
    lines.append("## 本轮工具调用统计")
    lines.append("")
    lines.append("| 工具 | 调用次数 |")
    lines.append("|------|----------|")
    for name, cnt in sorted(tool_usage.items(), key=lambda x: -x[1]):
        lines.append(f"| `{name}` | {cnt} |")
    lines.append("")

"""微信出站文本格式化与 UTF-8 字节分片（硬限 2048）。"""

from __future__ import annotations

import re

WEIXIN_DELIVERY_LIMIT_BYTES = 2048
_FENCE_RE = re.compile(r"^```")


def utf8_byte_length(text: str) -> int:
    return len(str(text or "").encode("utf-8"))


def format_weixin_text(content: object) -> str:
    normalized = str(content or "").replace("\r\n", "\n").strip()
    if not normalized:
        return ""
    # 轻量净化：去掉 HTML 标签痕迹，保留 markdown 主体
    filtered = re.sub(r"<[^>]+>", "", normalized).strip()
    if not filtered:
        return ""
    lines = _rewrite_headings_preserving_fences(filtered)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def split_weixin_text(content: object, max_length: int = 4000) -> list[str]:
    normalized = str(content or "").strip()
    if not normalized:
        return []
    delivery_limit = min(int(max_length) or 4000, WEIXIN_DELIVERY_LIMIT_BYTES)
    units: list[str] = []
    for unit in _split_delivery_units(normalized):
        if utf8_byte_length(unit) <= delivery_limit:
            units.append(unit)
        else:
            units.extend(_pack_markdown_blocks(unit, delivery_limit))
    aggregated = _aggregate_units(units, delivery_limit)
    return aggregated or [normalized]


def _rewrite_heading(line: str) -> str:
    if re.match(r"^#\s+", line):
        return f"【{re.sub(r'^#\s+', '', line).strip()}】"
    if re.match(r"^##+\s+", line):
        return f"**{re.sub(r'^##+\s+', '', line).strip()}**"
    return line


def _rewrite_headings_preserving_fences(content: str) -> list[str]:
    rewritten: list[str] = []
    in_fence = False
    for line in content.split("\n"):
        trimmed = line.strip()
        if _FENCE_RE.match(trimmed):
            rewritten.append(line)
            in_fence = not in_fence
            continue
        rewritten.append(line if in_fence else _rewrite_heading(line))
    return rewritten


def _split_markdown_blocks(content: str) -> list[str]:
    lines = str(content or "").split("\n")
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in lines:
        trimmed = line.strip()
        if _FENCE_RE.match(trimmed):
            current.append(line)
            in_fence = not in_fence
            continue
        if not in_fence and not trimmed:
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [b for b in blocks if b]


def _split_delivery_units(content: str) -> list[str]:
    units: list[str] = []
    for block in _split_markdown_blocks(content):
        first = (block.split("\n")[0] or "").strip()
        if _FENCE_RE.match(first):
            units.append(block)
            continue
        current: list[str] = []
        for raw_line in block.split("\n"):
            line = raw_line.rstrip()
            if not line.strip():
                if current:
                    units.append("\n".join(current).strip())
                    current = []
                continue
            is_cont = bool(current) and bool(re.match(r"^[ \t]", raw_line))
            if is_cont:
                current.append(line)
                continue
            if current:
                units.append("\n".join(current).strip())
            current = [line]
        if current:
            units.append("\n".join(current).strip())
    return [u for u in units if u]


def _aggregate_units(units: list[str], max_length: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for unit in units:
        normalized = str(unit or "").strip()
        if not normalized:
            continue
        separator = "\n" if current else ""
        candidate = f"{current}{separator}{normalized}"
        if current and utf8_byte_length(candidate) > max_length:
            chunks.append(current)
            current = normalized
            continue
        if not current and utf8_byte_length(normalized) > max_length:
            chunks.append(normalized)
            continue
        current = candidate
    if current:
        chunks.append(current)
    return chunks


def _pack_markdown_blocks(content: str, max_length: int) -> list[str]:
    if utf8_byte_length(content) <= max_length:
        return [content]
    packed: list[str] = []
    current = ""
    for block in _split_markdown_blocks(content):
        candidate = f"{current}\n\n{block}" if current else block
        if utf8_byte_length(candidate) <= max_length:
            current = candidate
            continue
        if current:
            packed.append(current)
            current = ""
        if utf8_byte_length(block) <= max_length:
            current = block
            continue
        packed.extend(_truncate_message(block, max_length))
    if current:
        packed.append(current)
    return packed


def _truncate_message(content: str, max_length: int) -> list[str]:
    if utf8_byte_length(content) <= max_length:
        return [content]
    chunks: list[str] = []
    remaining = content
    while utf8_byte_length(remaining) > max_length:
        split_at = _find_truncation_boundary(remaining, max_length)
        if split_at <= 0:
            split_at = len(_slice_by_utf8_bytes(remaining, max_length))
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining.strip())
    return [c for c in chunks if c]


def _find_truncation_boundary(text: str, max_bytes: int) -> int:
    best_boundary = -1
    best_sentence = -1
    bytes_n = 0
    for index, ch in enumerate(text):
        bytes_n += utf8_byte_length(ch)
        if bytes_n > max_bytes:
            break
        if ch == "\n":
            best_boundary = index
        if ch in "。！？.!?；;":
            best_sentence = index + 1
    if best_boundary > 0:
        return best_boundary
    return best_sentence


def _slice_by_utf8_bytes(text: str, max_bytes: int) -> str:
    bytes_n = 0
    index = 0
    while index < len(text):
        next_n = utf8_byte_length(text[index])
        if bytes_n + next_n > max_bytes:
            break
        bytes_n += next_n
        index += 1
    return text[:index]

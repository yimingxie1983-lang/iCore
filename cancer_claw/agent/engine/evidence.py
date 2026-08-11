

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

class FactKind(str, Enum):


    CASE_FIELD = "case_field"
    PMID = "pmid"
    DOI = "doi"
    SCORE_RESULT = "score_result"
    LAB_VALUE = "lab_value"
    IMAGING = "imaging"
    UPLOAD = "upload"
    USER_ASSERTION = "user_assertion"

_SUBJECTIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in (

        r"我觉得", r"我认为", r"我建议", r"我倾向", r"我推断", r"我推测",
        r"建议你", r"建议患者", r"建议先",

        r"倾向于", r"应当", r"应该",
        r"也许", r"或许",
        r"似乎", r"看起来", r"看上去",
        r"个人意见", r"个人观点", r"主观判断",

        r"\bI think\b", r"\bI believe\b", r"\bI suggest\b",
        r"\bin my opinion\b", r"\bIMO\b", r"\bIIRC\b",
    )
]

def _looks_subjective(text: str) -> str | None:

    for pat in _SUBJECTIVE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0)
    return None

@dataclass(frozen=True)
class Fact:


    kind: FactKind
    ref: str
    content: str
    source: str = ""

    def __post_init__(self) -> None:

        if not isinstance(self.kind, FactKind):
            object.__setattr__(self, "kind", FactKind(self.kind))
        if not isinstance(self.ref, str) or not self.ref.strip():
            raise ValueError("Fact.ref 必须是非空字符串")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("Fact.content 必须是非空字符串")

    def looks_subjective(self) -> str | None:

        return _looks_subjective(self.content)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "kind": self.kind.value,
            "ref": self.ref,
            "content": self.content,
        }
        if self.source:
            d["source"] = self.source
        return d

@dataclass(frozen=True)
class EvidenceSnapshot:


    id: str
    created_at: float
    facts: tuple[Fact, ...]


    @classmethod
    def from_facts(cls, facts: Iterable[Fact]) -> "EvidenceSnapshot":

        seen: set[tuple[str, str, str]] = set()
        deduped: list[Fact] = []
        for f in facts:
            key = (f.kind.value, f.ref, f.content)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(f)
        deduped.sort(key=lambda x: (x.kind.value, x.ref, x.content))
        payload = json.dumps(
            [f.to_dict() for f in deduped],
            ensure_ascii=False,
            sort_keys=True,
        )
        sid = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
        return cls(id=sid, created_at=time.time(), facts=tuple(deduped))

    @classmethod
    def empty(cls) -> "EvidenceSnapshot":

        return cls.from_facts([])


    def __len__(self) -> int:
        return len(self.facts)

    def __iter__(self):
        return iter(self.facts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "facts": [f.to_dict() for f in self.facts],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


    def subjective_warnings(self) -> list[tuple[Fact, str]]:

        out: list[tuple[Fact, str]] = []
        for f in self.facts:
            hit = f.looks_subjective()
            if hit is not None:
                out.append((f, hit))
        return out


    def as_prompt_section(self) -> str:

        header = f"# 共享事实卷宗（snapshot {self.id}）"
        if not self.facts:
            return f"{header}\n\n_（无事实）_\n"

        groups: dict[FactKind, list[Fact]] = {}
        for f in self.facts:
            groups.setdefault(f.kind, []).append(f)

        lines: list[str] = [
            header,
            "",
            f"> 共 {len(self.facts)} 条事实，已通过客观性校验冻结。",
            "> 你只能基于本卷宗内事实推理。卷宗外信息不得作为论据。",
            "",
        ]
        for kind in FactKind:
            items = groups.get(kind)
            if not items:
                continue
            lines.append(f"## {kind.value}（{len(items)}）")
            for f in items:
                if kind is FactKind.PMID:
                    pmid = f.ref.split(":", 1)[-1]
                    lines.append(f"- [PMID:{pmid}] {f.content}")
                elif kind is FactKind.DOI:
                    doi = f.ref.split(":", 1)[-1]
                    lines.append(f"- [DOI:{doi}] {f.content}")
                else:
                    lines.append(f"- `{f.ref}` — {f.content}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

_PMID_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\[REF[\s:]*PMID[\s:]*(\d{1,9})\]", re.IGNORECASE),
    re.compile(r"\[PMID[\s:]*(\d{1,9})\]", re.IGNORECASE),
]
_DOI_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\[REF[\s:]*DOI[\s:]*(10\.\d{4,9}/[\w\-.()/:;]+?)\]", re.IGNORECASE),
    re.compile(r"\[DOI[\s:]*(10\.\d{4,9}/[\w\-.()/:;]+?)\]", re.IGNORECASE),
]

def _extract_message_text(msg: Any) -> str:

    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for blk in content:
            if isinstance(blk, dict):
                t = blk.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "\n".join(parts)
    return ""

def _scan_citations(text: str, source_tag: str) -> list[Fact]:

    out: list[Fact] = []
    for pat in _PMID_PATTERNS:
        for m in pat.finditer(text):
            pmid = m.group(1).strip()
            out.append(
                Fact(
                    kind=FactKind.PMID,
                    ref=f"PMID:{pmid}",
                    content=f"主对话引用文献 PMID:{pmid}",
                    source=source_tag,
                )
            )
    for pat in _DOI_PATTERNS:
        for m in pat.finditer(text):
            doi = m.group(1).strip()
            out.append(
                Fact(
                    kind=FactKind.DOI,
                    ref=f"DOI:{doi}",
                    content=f"主对话引用文献 DOI:{doi}",
                    source=source_tag,
                )
            )
    return out

def _scan_uploads(workspace_root: Path) -> list[Fact]:

    uploads = workspace_root / "uploads"
    if not uploads.exists() or not uploads.is_dir():
        return []
    out: list[Fact] = []
    for p in sorted(uploads.iterdir()):
        if not p.is_file():
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        out.append(
            Fact(
                kind=FactKind.UPLOAD,
                ref=f"upload:{p.name}",
                content=f"用户上传文件 {p.name}（{size} 字节）",
                source="workspace/uploads",
            )
        )
    return out

def build_from_master(
    master_agent: Any,
    *,
    recent_message_limit: int = 40,
) -> EvidenceSnapshot:

    facts: list[Fact] = []

    ctx = getattr(master_agent, "_context", None)
    msgs = getattr(ctx, "_messages", None) if ctx is not None else None
    if isinstance(msgs, list) and msgs:

        start_idx = max(0, len(msgs) - recent_message_limit)
        for offset, msg in enumerate(msgs[start_idx:]):
            idx = start_idx + offset
            role = msg.get("role") if isinstance(msg, dict) else None
            if role not in ("user", "assistant"):
                continue
            text = _extract_message_text(msg)
            if not text:
                continue
            facts.extend(_scan_citations(text, source_tag=f"msg#{idx}:{role}"))

    bound_ws = getattr(master_agent, "_bound_workspace", None)
    ws_root = getattr(bound_ws, "default_relative_root", None) if bound_ws else None
    if isinstance(ws_root, Path):
        facts.extend(_scan_uploads(ws_root))

    return EvidenceSnapshot.from_facts(facts)

__all__ = [
    "Fact",
    "FactKind",
    "EvidenceSnapshot",
    "build_from_master",
]

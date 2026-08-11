

from __future__ import annotations

import re
from typing import Any

import structlog

from cancer_claw.resources.knowledge.craft_store import (
    crafts_dir,
    list_crafts_for_agent,
    load_craft_for_agent,
    personal_crafts_dir,
    sealed_crafts_dir,
)
from cancer_claw.resources.knowledge.schemas import CertificationStatus, CraftKind, CraftRecord
from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

logger = structlog.get_logger()

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")

def _tokenize(text: str) -> list[str]:

    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]

def _resolve_tier(craft_id: str, agent_id: str) -> str:

    if agent_id:
        if (personal_crafts_dir(agent_id) / f"{craft_id}.md").is_file():
            return "personal"
    if (crafts_dir() / f"{craft_id}.md").is_file():
        return "shared"
    if (sealed_crafts_dir() / f"{craft_id}.md").is_file():
        return "sealed"
    if craft_id.startswith("skill_"):
        return "skill"
    return "unknown"

def _score_craft(
    rec: CraftRecord,
    query_tokens: list[str],
    *,
    task_kind: str,
    kind_filter: str,
    tier: str,
) -> float:

    score = 0.0

    name_lower = (rec.name or "").lower()
    desc_lower = (rec.description or "").lower()
    tags_lower = " ".join(rec.tags or []).lower()

    for tok in query_tokens:
        if tok in name_lower:
            score += 1.0
        if tok in desc_lower:
            score += 1.0
        if tok in tags_lower:
            score += 1.0

    activation = rec.activation or {}
    task_kinds = activation.get("task_kinds") if isinstance(activation, dict) else None
    if task_kind and isinstance(task_kinds, list) and task_kind in task_kinds:
        score += 5.0

    keywords = activation.get("keywords") if isinstance(activation, dict) else None
    if isinstance(keywords, list) and keywords:
        kw_set = {str(k).lower() for k in keywords}
        if any(t in kw_set for t in query_tokens):
            score += 3.0

    if kind_filter:
        try:
            target = CraftKind(kind_filter)
            if rec.kind == target:
                score += 2.0
        except ValueError:

            pass

    if rec.certification_status == CertificationStatus.CERTIFIED:
        score += 1.0

    if tier == "personal":
        score += 1.0

    return score

class CraftSearchTool(BaseTool):


    @property
    def name(self) -> str:
        return "craft_search"

    @property
    def description(self) -> str:
        return (
            "三层 craft 库（personal/shared/sealed）一站式检索与查看。"
            "action=search（默认）按关键词 + activation 字段加权找候选；"
            "action=view 按 craft_id 直接查看 craft 完整正文 + 元数据。"
            "查看 craft 详情**只能**走本工具的 view 动作 —— craft 文件落在框架包内、"
            "不在项目 workspace 沙箱里，不能用 file_ops.read_file 去读。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "craft_search",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["search", "view"],
                            "description": (
                                "search=按 query 关键词检索 top_k 候选（默认）；"
                                "view=按 craft_id 查看 craft 完整正文 + 元数据。"
                            ),
                            "default": "search",
                        },
                        "query": {
                            "type": "string",
                            "description": (
                                "action=search 时必填的自然语言查询。"
                                "例：'下载 HPO 数据'；action=view 时本字段忽略。"
                            ),
                            "default": "",
                        },
                        "craft_id": {
                            "type": "string",
                            "description": (
                                "action=view 时必填的 craft 逻辑 id。"
                                "通常来自上一轮 search 结果中的 craft_id 字段。"
                                "action=search 时本字段忽略。"
                            ),
                            "default": "",
                        },
                        "kind": {
                            "type": "string",
                            "enum": ["", "capability", "procedure", "expert", "pattern"],
                            "description": "限定 craft 种类；空串=不限。仅 action=search 生效。",
                            "default": "",
                        },
                        "task_kind": {
                            "type": "string",
                            "description": (
                                "可选任务种类，命中 activation.task_kinds 加 5 分。"
                                "例：software_project / data_etl / kg_build。仅 action=search 生效。"
                            ),
                            "default": "",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "返回前 N 条（默认 5，最大 20）。仅 action=search 生效。",
                            "default": 5,
                        },
                    },


                    "required": [],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:

        action = (kwargs.get("action") or "search").strip().lower()

        agent_id = (kwargs.get("agent_id") or "").strip()

        if action == "view":
            return await self._view(
                craft_id=(kwargs.get("craft_id") or "").strip(),
                agent_id=agent_id,
            )

        if action != "search":
            return ToolResult(
                success=False,
                error=f"未知 action: {action}（仅支持 search / view）",
            )

        return await self._search(
            query=(kwargs.get("query") or "").strip(),
            kind_filter=(kwargs.get("kind") or "").strip(),
            task_kind=(kwargs.get("task_kind") or "").strip(),
            top_k_raw=kwargs.get("top_k", 5),
            agent_id=agent_id,
        )

    async def _search(
        self,
        *,
        query: str,
        kind_filter: str,
        task_kind: str,
        top_k_raw: Any,
        agent_id: str,
    ) -> ToolResult:

        if not query:
            return ToolResult(success=False, error="action=search 时 query 不能为空")

        try:
            top_k = max(1, min(20, int(top_k_raw)))
        except (TypeError, ValueError):
            top_k = 5

        query_tokens = _tokenize(query)
        if not query_tokens:
            return ToolResult(
                success=True,
                output="query 切词后为空，未执行检索",
                data={"hits": [], "total": 0},
            )


        try:
            records = list_crafts_for_agent(agent_id)
        except Exception as e:
            logger.warning("craft_search_load_failed", error=str(e))
            return ToolResult(success=False, error=f"craft 库加载失败: {e}")

        scored: list[tuple[float, CraftRecord, str]] = []
        for rec in records:
            tier = _resolve_tier(rec.id, agent_id)
            s = _score_craft(
                rec,
                query_tokens,
                task_kind=task_kind,
                kind_filter=kind_filter,
                tier=tier,
            )
            if s > 0:
                scored.append((s, rec, tier))

        scored.sort(key=lambda x: x[0], reverse=True)
        hits = []
        for s, rec, tier in scored[:top_k]:
            hits.append({
                "craft_id": rec.id,
                "name": rec.name or rec.id,
                "score": round(s, 2),
                "kind": rec.kind.value if hasattr(rec.kind, "value") else str(rec.kind),
                "tier": tier,
                "description": (rec.description or "")[:240],
                "certified": rec.certification_status == CertificationStatus.CERTIFIED,
            })

        if not hits:
            output = f"未找到匹配 query='{query}' 的 craft（共扫描 {len(records)} 条）"
        else:
            lines = [f"匹配 {len(hits)} 条（共扫描 {len(records)} 条）："]
            for h in hits:
                cert_mark = "[certified]" if h["certified"] else ""
                lines.append(
                    f"- {h['craft_id']} ({h['tier']}, kind={h['kind']}, "
                    f"score={h['score']}) {cert_mark} — {h['name']}"
                )

            lines.append(
                "\n看完整正文：再调本工具一次，传 action=view + craft_id=<上面任一>；"
                "决定动手干活：用 activate_craft 直接挂上跑。"
                "**不要**用 file_ops.read_file 去读 craft 文件 —— craft 不在项目 workspace 里。"
            )
            output = "\n".join(lines)

        return ToolResult(
            success=True,
            output=output,
            data={"hits": hits, "total": len(hits)},
        )

    def _find_in_listing(self, craft_id: str, agent_id: str) -> CraftRecord | None:

        try:
            for rec in list_crafts_for_agent(agent_id):
                if rec.id == craft_id:
                    return rec
        except Exception as e:
            logger.warning("craft_view_listing_failed", craft_id=craft_id, error=str(e))
        return None

    async def _view(self, *, craft_id: str, agent_id: str) -> ToolResult:

        if not craft_id:
            return ToolResult(
                success=False,
                error=(
                    "action=view 时 craft_id 不能为空。"
                    "先用 action=search 找到候选 craft_id 再 view。"
                ),
            )






        rec: CraftRecord | None = None
        if craft_id.startswith("skill_"):
            rec = self._find_in_listing(craft_id, agent_id)
            if rec is None:
                return ToolResult(
                    success=False,
                    error=(
                        f"skill 不存在或未被成功加载: {craft_id}。"
                        f"先用 action=search 确认 id；若确为已导入的 skill，"
                        f"请检查其 SKILL.md 的 frontmatter 是否为合法 YAML"
                        f"（解析失败的 skill 不会进入可用清单）。"
                    ),
                )
        else:


            try:
                rec = load_craft_for_agent(craft_id, agent_id)
            except FileNotFoundError:

                rec = self._find_in_listing(craft_id, agent_id)
                if rec is None:
                    return ToolResult(
                        success=False,
                        error=(
                            f"craft 不存在于任何层（personal/shared/sealed/skill）: {craft_id}。"
                            f"先用 action=search 确认 id 是否正确。"
                        ),
                    )
            except Exception as e:
                logger.warning("craft_view_load_failed", craft_id=craft_id, error=str(e))
                return ToolResult(success=False, error=f"craft 加载失败: {e}")

        tier = _resolve_tier(rec.id, agent_id)


        full = rec.full_prompt or ""


        header_lines = [
            f"[craft_view] {rec.id}",
            f"  name: {rec.name or rec.id}",
            f"  tier: {tier}",
            f"  kind: {rec.kind.value if hasattr(rec.kind, 'value') else str(rec.kind)}",
            f"  certified: {rec.certification_status == CertificationStatus.CERTIFIED}",
            f"  length: {len(full)} chars",
        ]
        if rec.description:
            header_lines.append(f"  description: {rec.description}")
        if rec.tags:
            header_lines.append(f"  tags: {', '.join(rec.tags)}")
        if rec.tools:
            header_lines.append(f"  tools: {', '.join(rec.tools)}")

        output = "\n".join(header_lines) + "\n" + ("─" * 40) + "\n" + full

        return ToolResult(
            success=True,
            output=output,
            data={
                "craft_id": rec.id,
                "name": rec.name or rec.id,
                "kind": rec.kind.value if hasattr(rec.kind, "value") else str(rec.kind),
                "tier": tier,
                "description": rec.description or "",
                "tags": list(rec.tags or []),
                "tools": list(rec.tools or []),
                "certified": rec.certification_status == CertificationStatus.CERTIFIED,
                "full_prompt": full,
                "full_prompt_length": len(full),
            },
        )



from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import structlog

from cancer_claw.resources.prompt_templates import load_prompt
from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

logger = structlog.get_logger()

PLAN_FILENAME = "PLAN.md"
PLANS_ARCHIVE_SUBDIR = "docs/plans"

class EnterPlanModeTool(BaseTool):


    @property
    def name(self) -> str:
        return "enter_plan_mode"

    @property
    def description(self) -> str:
        return (
            "进入 Plan Mode（只读模式）。所有写工具（shell_exec / file_ops.write_file 等）"
            "立即被工具层屏蔽，仅保留读类工具 + ask_user + craft_search 等。"
            "用于复杂任务（> 3 步骤 / 多文件改动 / 跨多 agent 协作）：先调研 + 写计划 + 用户审批，"
            "再调 exit_plan_mode 切回 execute 模式实施。"
            "属于主对话循环系统级工具：所有主对话人格通用，sub-agent 子上下文（_depth > 0）禁用。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "enter_plan_mode",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "rationale": {
                            "type": "string",
                            "description": "为什么进入 Plan Mode 的简短说明（让用户在事件流里看到决策依据）",
                            "default": "",
                        },
                    },
                    "required": [],
                },
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        parent_agent = kwargs.get("_parent_agent")
        if parent_agent is None:
            return ToolResult(success=False, error="未注入父智能体引用，工具调用上下文异常")



        depth = getattr(parent_agent, "_depth", 0) or 0
        if depth > 0:
            return ToolResult(
                success=False,
                error=(
                    "Plan Mode 仅在主对话循环（_depth == 0）可用；"
                    "sub-agent 子上下文请汇报回主对话由当前人格决定。"
                ),
            )

        rationale = (kwargs.get("rationale") or "").strip()

        parent_agent.mode = "plan"
        logger.info(
            "plan_mode_entered",
            agent_id=parent_agent.id,
            rationale=rationale or "(未提供)",
        )

        notice = load_prompt("plan_mode_enter_notice")
        return ToolResult(success=True, output=notice, data={"mode": "plan", "rationale": rationale})

class ExitPlanModeTool(BaseTool):


    @property
    def name(self) -> str:
        return "exit_plan_mode"

    @property
    def description(self) -> str:
        return (
            "退出 Plan Mode 切回 Execute Mode（执行模式）。所有工具恢复可用。"
            "调用时必须提供 plan_content（用户已审批的完整实施计划），"
            "框架会自动落盘到 workspace/PLAN.md（与 AGENTS.md 同级），"
            "作为本次任务的真相源。任务完成调 attempt_completion 时框架会自动归档 PLAN.md 到 docs/plans/。"
            "属于主对话循环系统级工具：所有主对话人格通用，sub-agent 子上下文（_depth > 0）禁用。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "exit_plan_mode",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "plan_content": {
                            "type": "string",
                            "description": (
                                "用户已审批的**完整实施计划**（Markdown 格式），将原样写入 "
                                "workspace/PLAN.md。要求："
                                "(1) 第一行用 `# 标题` 给本次任务起一个简短业务名（用作归档文件名 slug）；"
                                "(2) 包含目标 / 步骤 / 验收标准 / 风险点；"
                                "(3) 用户的原始诉求（功能点、字段约束、业务规则）必须**原文保留**，不要二次摘要；"
                                "(4) 至少 300 字，反映 plan mode 中达成的全部共识。"
                                "执行阶段你会反复回头读这份文件作为锚点，写得越完整后续越省事。"
                            ),
                        },
                    },
                    "required": ["plan_content"],
                },
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        parent_agent = kwargs.get("_parent_agent")
        if parent_agent is None:
            return ToolResult(success=False, error="未注入父智能体引用，工具调用上下文异常")


        depth = getattr(parent_agent, "_depth", 0) or 0
        if depth > 0:
            return ToolResult(
                success=False,
                error=(
                    "Plan Mode 仅在主对话循环（_depth == 0）可用；"
                    "sub-agent 子上下文请汇报回主对话由当前人格决定。"
                ),
            )

        plan_content = (kwargs.get("plan_content") or "").strip()
        if not plan_content:
            return ToolResult(
                success=False,
                error=(
                    "exit_plan_mode 必须提供 plan_content（用户已审批的完整实施计划）。"
                    "如果用户在 plan mode 中取消了任务，请直接回复用户而不是退出 plan mode；"
                    "如果计划尚未达成共识，请继续 ask_user 而不是提前退出。"
                ),
            )


        plan_persist_info = _persist_plan(parent_agent, plan_content)

        parent_agent.mode = "execute"
        logger.info(
            "plan_mode_exited",
            agent_id=parent_agent.id,
            plan_content_chars=len(plan_content),
            plan_path=plan_persist_info.get("plan_path"),
            archived_to=plan_persist_info.get("archived_to"),
            persist_warning=plan_persist_info.get("warning"),
        )

        notice = load_prompt("plan_mode_exit_notice")
        if plan_persist_info.get("plan_path"):
            notice = (
                notice
                + "\n\n---\n"
                + f"计划已落盘到 `{plan_persist_info['plan_path']}`（任务级真相源）。\n"
                + (
                    f"上一份未完成的计划已归档到 `{plan_persist_info['archived_to']}`（说明本次是任务转向）。\n"
                    if plan_persist_info.get("archived_to") else ""
                )
                + "执行过程中如对需求模糊，回头读 `PLAN.md` 而不是凭记忆复述。"
                "任务完成时调 `attempt_completion`，框架会自动把 PLAN.md 归档到 `docs/plans/` 并附上完成报告。"
            )
        elif plan_persist_info.get("warning"):
            notice = (
                notice
                + "\n\n---\n"
                + f"PLAN.md 落盘失败：{plan_persist_info['warning']}\n"
                + "请检查 workspace 绑定状态；本次模式切换已完成，但任务级真相源缺失，"
                "执行时务必把关键需求记在脑子里 / 用 scratchpad 兜底。"
            )

        return ToolResult(
            success=True,
            output=notice,
            data={
                "mode": "execute",
                "plan_path": plan_persist_info.get("plan_path"),
                "archived_to": plan_persist_info.get("archived_to"),
                "plan_chars": len(plan_content),
            },
        )

def _resolve_workspace_root(parent_agent) -> Path | None:

    bound_ws = getattr(parent_agent, "_bound_workspace", None)
    if bound_ws is None:
        return None
    workspace_root: Path | None = getattr(bound_ws, "default_relative_root", None)
    if workspace_root is None:
        return None
    return workspace_root

_SLUG_KEEP_RE = re.compile(r"[^\w\u4e00-\u9fff\-]+", re.UNICODE)

def _extract_slug_from_plan(plan_content: str, fallback: str = "task") -> str:

    if not plan_content:
        return fallback
    first_meaningful_line = ""
    for raw_line in plan_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        first_meaningful_line = line
        break
    if not first_meaningful_line:
        return fallback
    title = re.sub(r"^#+\s*", "", first_meaningful_line).strip()
    title = title[:32]
    slug = _SLUG_KEEP_RE.sub("-", title).strip("-_")
    return slug or fallback

def _persist_plan(parent_agent, plan_content: str) -> dict:

    workspace_root = _resolve_workspace_root(parent_agent)
    if workspace_root is None:
        return {"plan_path": None, "archived_to": None, "warning": "agent 未绑定 workspace"}

    try:
        ws_resolved = workspace_root.resolve()
        plan_path = (workspace_root / PLAN_FILENAME).resolve()
        plans_dir = (workspace_root / PLANS_ARCHIVE_SUBDIR).resolve()

        try:
            plan_path.relative_to(ws_resolved)
        except ValueError:
            return {"plan_path": None, "archived_to": None,
                    "warning": "PLAN.md 解析路径超出 workspace 边界，已拒绝写入"}

        archived_to: str | None = None
        if plan_path.exists() and plan_path.is_file():
            existing = ""
            try:
                existing = plan_path.read_text(encoding="utf-8")
            except Exception:
                pass
            archived_to = _archive_plan_file(
                plan_path=plan_path,
                plans_dir=plans_dir,
                ws_resolved=ws_resolved,
                slug=_extract_slug_from_plan(existing, fallback="prev-task"),
            )

        plan_path.write_text(plan_content, encoding="utf-8")
        rel_plan = str(plan_path.relative_to(ws_resolved))
        return {"plan_path": rel_plan, "archived_to": archived_to, "warning": None}
    except Exception as e:
        logger.warning("plan_persist_failed", error=str(e), exc_info=True)
        return {"plan_path": None, "archived_to": None, "warning": str(e)}

def _archive_plan_file(
    *,
    plan_path: Path,
    plans_dir: Path,
    ws_resolved: Path,
    slug: str,
    extra_section: str | None = None,
) -> str | None:

    try:
        plans_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        archive_path = plans_dir / f"{ts}_{slug}.md"
        seq = 1
        while archive_path.exists():
            archive_path = plans_dir / f"{ts}_{slug}-{seq}.md"
            seq += 1
        plan_path.replace(archive_path)
        if extra_section:
            try:
                with archive_path.open("a", encoding="utf-8") as f:
                    f.write("\n\n---\n## 完成报告\n\n")
                    f.write(extra_section.strip())
                    f.write("\n")
            except Exception as e:
                logger.warning("plan_archive_append_failed", error=str(e))
        return str(archive_path.relative_to(ws_resolved))
    except Exception as e:
        logger.warning("plan_archive_failed", error=str(e))
        return None

def archive_current_plan_on_completion(parent_agent, completion_result: str) -> dict:

    workspace_root = _resolve_workspace_root(parent_agent)
    if workspace_root is None:
        return {"archived_to": None, "skipped": True, "warning": "agent 未绑定 workspace"}

    try:
        ws_resolved = workspace_root.resolve()
        plan_path = (workspace_root / PLAN_FILENAME).resolve()
        plans_dir = (workspace_root / PLANS_ARCHIVE_SUBDIR).resolve()

        if not plan_path.exists() or not plan_path.is_file():
            return {"archived_to": None, "skipped": True, "warning": None}

        try:
            existing = plan_path.read_text(encoding="utf-8")
        except Exception:
            existing = ""

        slug = _extract_slug_from_plan(existing, fallback="task")
        archived_to = _archive_plan_file(
            plan_path=plan_path,
            plans_dir=plans_dir,
            ws_resolved=ws_resolved,
            slug=slug,
            extra_section=completion_result or None,
        )
        if archived_to is None:
            return {"archived_to": None, "skipped": False, "warning": "归档失败，PLAN.md 仍在原位"}

        return {"archived_to": archived_to, "skipped": False, "warning": None}
    except Exception as e:
        logger.warning("plan_archive_on_completion_failed", error=str(e), exc_info=True)
        return {"archived_to": None, "skipped": False, "warning": str(e)}

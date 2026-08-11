

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from cancer_claw.agent.engine.agent import Agent

logger = structlog.get_logger()

def _emoji_for(success: bool) -> str:
    return "✅" if success else "❌"

def _render_report_markdown(report: Any, snapshot_id: str, warnings_emitted: int) -> str:

    success_count = sum(1 for t in report.tasks if t.success)
    total = len(report.tasks)
    duration_s = report.duration_ms / 1000.0

    lines: list[str] = [
        f"# 并行小队产出 · squad_id `{report.squad_id}`",
        "",
        (
            f"完成 {success_count} / {total} 个子任务，总耗时 {duration_s:.1f}s。"
            f"事实卷宗 snapshot `{snapshot_id}`。"
        ),
        "",
    ]
    if warnings_emitted > 0:
        lines.append(
            f"> ⚠️ 事实卷宗有 **{warnings_emitted}** 条事实被 L3 启发式标了主观词，"
            f"前端已收到 `evidence_warning` 事件。如果你认为它们其实是客观陈述，"
            f"可以放行；否则建议改写后重开新 snapshot 重派 squad。"
        )
        lines.append("")

    for t in report.tasks:
        head = (
            f"## {_emoji_for(t.success)} `{t.id}` · {t.title}"
            f" · {t.duration_ms / 1000.0:.1f}s"
        )
        if t.persona_id:
            head += f" · persona={t.persona_id}"
        lines.append(head)
        lines.append("")
        if t.error:
            lines.append(f"**失败**：`{t.error}`")
            lines.append("")
        if t.summary:
            lines.append(t.summary)
            lines.append("")
        if t.artifacts:
            lines.append("artifacts:")
            for a in t.artifacts:
                lines.append(f"- `{a}`")
            lines.append("")
        if t.open_questions:
            lines.append("open_questions:")
            for q in t.open_questions:
                lines.append(f"- {q}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"

class DispatchSquadTool(BaseTool):


    @property
    def name(self) -> str:
        return "dispatch_squad"

    @property
    def description(self) -> str:
        return (
            "把可拆分的任务切成 N 份独立子任务一次性并行派出去（每个子任务用一次性"
            "spawn_oneshot 起、跑完销毁、互不可见），收齐后返回合并报告。事实层通过"
            "EvidenceSnapshot 共享，视角层强隔离。仅用于可拆分执行任务（编码/并行读"
            "N 文件/多 keyword 检索/方案变体对比）；多视角协作请用 convene_council，"
            "单线推理直接自己干。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "dispatch_squad",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "本次 squad 的工作主题，会作为前端卡片头与日志 tag。",
                        },
                        "tasks": {
                            "type": "array",
                            "minItems": 1,
                            "description": (
                                "子任务列表。每子任务都是相对独立的执行单元，"
                                "不要写'依赖前一个子任务产出'这种内容；有依赖请由主对话自己分步推进。"
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {
                                        "type": "string",
                                        "description": "短 slug（如 read_a / scan_egfr），事件流定位用。",
                                    },
                                    "title": {
                                        "type": "string",
                                        "description": "用户可见的子任务标题。",
                                    },
                                    "prompt": {
                                        "type": "string",
                                        "description": (
                                            "本子任务的具体指令。写清「输入资料 / 期望产出 / 验收口径」，"
                                            "不要简单转发用户原话。"
                                        ),
                                    },
                                    "persona_id": {
                                        "type": "string",
                                        "description": (
                                            "可选。指定以哪个 persona 执行（必须英文 id）。"
                                            "通用工作型："
                                            "clinician（临床医师 🩺）/ researcher（科研 🔬）/ "
                                            "data_analyst（数据分析师 📊）/ writer（学术写作 ✍️）/ "
                                            "coder（编码工程师 💻）。"
                                            "MDT 科室型（一般 squad 不用，对应 MDT 议会请改用 convene_council）："
                                            "med_oncologist / surgical_oncologist / "
                                            "interventional_radiologist / radiation_oncologist / "
                                            "radiologist / pathologist。"
                                            "用户对话中说'临床医生 / 研究员 / 分析师 / 撰稿 / 程序员 / "
                                            "肿瘤内科 / 外科 / 介入 / 放疗 / 影像 / 病理'等中文别名时，"
                                            "自行映射到对应英文 id；本字段只接受英文 id。"
                                            "不填 = 复用主智能体默认人格。"
                                        ),
                                    },
                                    "evidence_refs": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": (
                                            "可选。从 snapshot 中筛子集喂给本子任务的 ref 列表"
                                            "（如 [\"PMID:12345\", \"upload:report.pdf\"]）；"
                                            "不填 = 整份 snapshot 都给。"
                                        ),
                                    },
                                },
                                "required": ["id", "title", "prompt"],
                            },
                        },
                        "snapshot_strategy": {
                            "type": "string",
                            "enum": ["auto", "explicit", "none"],
                            "default": "auto",
                            "description": (
                                "auto = 从主对话兜底抽机械锚点（PMID/DOI/uploads）；"
                                "explicit = 用你下面 explicit_facts 显式列的事实清单（推荐，最干净）；"
                                "none = 不挂事实层（仅在子任务真的不需要任何事实背景时用）。"
                            ),
                        },
                        "explicit_facts": {
                            "type": "array",
                            "description": (
                                "snapshot_strategy=explicit 时必填。**只列客观、可核验、不含个人立场的陈述**："
                                "病例字段 / PMID/DOI 引用 / 评分结果 / 上传文件元数据等。"
                                "禁止把'我倾向/我建议/应该/可能/看起来'等表态塞进来——你是协调者，"
                                "事实卷宗里不该出现你自己的推论。"
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "kind": {
                                        "type": "string",
                                        "enum": [
                                            "case_field",
                                            "pmid",
                                            "doi",
                                            "score_result",
                                            "lab_value",
                                            "imaging",
                                            "upload",
                                            "user_assertion",
                                        ],
                                    },
                                    "ref": {
                                        "type": "string",
                                        "description": (
                                            "锚点字符串。如 \"PMID:12345\" / "
                                            "\"case:bclc_stage\" / \"score:meld\" / \"upload:report.pdf\"。"
                                        ),
                                    },
                                    "content": {
                                        "type": "string",
                                        "description": "客观描述本条事实的内容（无主观立场）。",
                                    },
                                    "source": {
                                        "type": "string",
                                        "description": "可选审计字段：这条事实来自哪条消息 / 哪次工具结果。",
                                    },
                                },
                                "required": ["kind", "ref", "content"],
                            },
                        },
                        "max_parallelism": {
                            "type": "integer",
                            "minimum": 1,
                            "default": 4,
                            "description": (
                                "并行上限。MVP 阶段底层串行实现，本字段保留供前端展示与未来切换真并行；"
                                "传几都不影响本次行为。"
                            ),
                        },
                        "timeout_s": {
                            "type": "integer",
                            "minimum": 1,
                            "default": 600,
                            "description": "单子任务硬超时（秒）。",
                        },
                    },
                    "required": ["title", "tasks"],
                },
            },
        }

    async def execute(
        self,
        title: str = "",
        tasks: list[dict] | None = None,
        snapshot_strategy: str = "auto",
        explicit_facts: list[dict] | None = None,
        max_parallelism: int = 4,
        timeout_s: int = 600,
        _agent: "Agent | None" = None,
        **_: Any,
    ) -> ToolResult:

        if _agent is None:
            return ToolResult(
                success=False,
                output="dispatch_squad 必须由主智能体在主对话中调用，无法独立运行。",
                error="missing agent context",
            )
        if getattr(_agent, "_depth", 0) > 0:
            return ToolResult(
                success=False,
                output=(
                    "dispatch_squad 不能在子任务上下文里嵌套调用（账本 §16 关键不变量）。"
                    "请把结论汇报回主对话，由主智能体决定下一步要不要派新的 squad。"
                ),
                error="nested_dispatch_squad_forbidden",
            )

        title = (title or "").strip()
        if not title:
            return ToolResult(
                success=False,
                output="dispatch_squad 缺 title 参数。请给本次 squad 一个工作主题。",
                error="missing_title",
            )

        tasks = tasks or []
        if not isinstance(tasks, list) or not tasks:
            return ToolResult(
                success=False,
                output="dispatch_squad 至少要 1 个子任务（tasks 列表为空）。",
                error="empty_tasks",
            )


        from cancer_claw.agent.engine.squad import (
            SquadRequest,
            SquadTaskRequest,
            run_squad,
        )

        task_reqs: list[SquadTaskRequest] = []
        for i, raw in enumerate(tasks):
            if not isinstance(raw, dict):
                return ToolResult(
                    success=False,
                    output=f"第 {i} 个子任务不是对象，请检查 tasks 结构。",
                    error="bad_task_shape",
                )
            tid = str(raw.get("id") or "").strip()
            ttitle = str(raw.get("title") or "").strip()
            tprompt = str(raw.get("prompt") or "").strip()
            if not tid or not ttitle or not tprompt:
                return ToolResult(
                    success=False,
                    output=(
                        f"第 {i} 个子任务字段不全（id / title / prompt 都必填）："
                        f"id={tid!r}, title={ttitle!r}, prompt={'(空)' if not tprompt else tprompt[:30]+'...'}"
                    ),
                    error="incomplete_task",
                )
            persona_id = raw.get("persona_id")
            persona_id = str(persona_id).strip() if persona_id else None
            evidence_refs_raw = raw.get("evidence_refs") or []
            if not isinstance(evidence_refs_raw, list):
                return ToolResult(
                    success=False,
                    output=f"第 {i} 个子任务的 evidence_refs 不是数组。",
                    error="bad_evidence_refs",
                )
            evidence_refs = tuple(str(x) for x in evidence_refs_raw if x)
            task_reqs.append(
                SquadTaskRequest(
                    id=tid,
                    title=ttitle,
                    prompt=tprompt,
                    persona_id=persona_id,
                    evidence_refs=evidence_refs,
                )
            )

        ids = [t.id for t in task_reqs]
        dup = {x for x in ids if ids.count(x) > 1}
        if dup:
            return ToolResult(
                success=False,
                output=f"子任务 id 重复：{sorted(dup)}，请改成唯一 slug。",
                error="duplicate_task_ids",
            )




        from cancer_claw.agent.engine.persona import persona_exists
        unknown_personas = sorted({
            t.persona_id for t in task_reqs
            if t.persona_id and not persona_exists(t.persona_id)
        })
        if unknown_personas:
            return ToolResult(
                success=False,
                output=(
                    f"以下 persona_id 不存在：{unknown_personas}。"
                    "请先调 list_personas 查看当前可用人格清单，再重新挑选。"
                    "（persona_id 必须严格匹配 personas/{id}.md 的文件名）"
                ),
                error="unknown_persona",
            )


        snapshot, snapshot_err = self._build_snapshot(
            strategy=snapshot_strategy,
            explicit_facts=explicit_facts,
            master_agent=_agent,
        )
        if snapshot_err is not None:
            return ToolResult(success=False, output=snapshot_err, error="snapshot_error")


        try:
            req = SquadRequest(
                title=title,
                tasks=tuple(task_reqs),
                snapshot=snapshot,
                max_parallelism=int(max_parallelism) if max_parallelism else 4,
                timeout_s=int(timeout_s) if timeout_s else 600,
            )
            report = await run_squad(req, _agent)
        except (ValueError, RuntimeError) as exc:

            logger.warning("dispatch_squad_run_failed", error=str(exc))
            return ToolResult(
                success=False,
                output=f"squad 执行失败：{type(exc).__name__}: {exc}",
                error=str(exc),
            )

        output_md = _render_report_markdown(
            report,
            snapshot_id=snapshot.id,
            warnings_emitted=report.warnings_emitted,
        )
        any_success = any(t.success for t in report.tasks)
        return ToolResult(


            success=any_success or len(report.tasks) == 0,
            output=output_md,
            data={
                "squad_id": report.squad_id,
                "snapshot_id": snapshot.id,
                "warnings_emitted": report.warnings_emitted,
                "tasks": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "persona_id": t.persona_id,
                        "success": t.success,
                        "summary": t.summary,
                        "artifacts": list(t.artifacts),
                        "open_questions": list(t.open_questions),
                        "duration_ms": t.duration_ms,
                        "error": t.error,
                    }
                    for t in report.tasks
                ],
                "duration_ms": report.duration_ms,
            },
        )



    @staticmethod
    def _build_snapshot(
        *,
        strategy: str,
        explicit_facts: list[dict] | None,
        master_agent: Any,
    ) -> tuple[Any, str | None]:

        from cancer_claw.agent.engine.evidence import (
            EvidenceSnapshot,
            Fact,
            FactKind,
            build_from_master,
        )

        strategy = (strategy or "auto").strip().lower()
        if strategy not in {"auto", "explicit", "none"}:
            return (
                None,
                f"snapshot_strategy 必须是 'auto' / 'explicit' / 'none' 之一，"
                f"收到 {strategy!r}",
            )

        if strategy == "none":
            return EvidenceSnapshot.empty(), None

        if strategy == "auto":
            try:
                return build_from_master(master_agent), None
            except Exception as exc:
                logger.warning("dispatch_squad_auto_snapshot_failed", error=str(exc))
                return EvidenceSnapshot.empty(), None


        if not explicit_facts:
            return (
                None,
                "snapshot_strategy='explicit' 时必须传 explicit_facts 列表。"
                "如果当前没有客观事实可列，请改用 snapshot_strategy='none'，"
                "并自检：没有任何事实背景的并行子任务是否还有意义？",
            )
        if not isinstance(explicit_facts, list):
            return None, "explicit_facts 必须是数组。"

        facts: list[Fact] = []
        valid_kinds = {k.value for k in FactKind}
        for i, raw in enumerate(explicit_facts):
            if not isinstance(raw, dict):
                return None, f"explicit_facts[{i}] 不是对象。"
            kind = str(raw.get("kind") or "").strip()
            ref = str(raw.get("ref") or "").strip()
            content = str(raw.get("content") or "").strip()
            source = str(raw.get("source") or "").strip()
            if not kind or kind not in valid_kinds:
                return None, (
                    f"explicit_facts[{i}].kind={kind!r} 不在允许枚举里："
                    f"{sorted(valid_kinds)}"
                )
            if not ref or not content:
                return None, f"explicit_facts[{i}] 的 ref / content 必填且非空。"
            try:
                facts.append(
                    Fact(
                        kind=FactKind(kind),
                        ref=ref,
                        content=content,
                        source=source,
                    )
                )
            except Exception as exc:
                return None, f"explicit_facts[{i}] 构造失败：{type(exc).__name__}: {exc}"

        return EvidenceSnapshot.from_facts(facts), None

DispatchSquadTool.__repr__ = lambda self: f"<DispatchSquadTool name={self.name!r}>"

__all__ = ["DispatchSquadTool"]

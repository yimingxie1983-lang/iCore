

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from cancer_claw.agent.engine.agent import Agent

logger = structlog.get_logger()

_VERDICT_BADGE = {
    "consensus": "🟢 consensus",
    "arbitrated": "🟠 arbitrated",
    "escalate": "🔴 escalate",
}

def _render_report_markdown(report: Any, snapshot_id: str) -> str:

    duration_s = report.duration_ms / 1000.0
    badge = _VERDICT_BADGE.get(report.verdict.type, report.verdict.type)

    lines: list[str] = [
        f"# 议会裁决 · council_id `{report.council_id}`",
        "",
        f"**议题**：{report.question}",
        "",
        f"**verdict**：{badge} · 仲裁人 `{report.arbiter_persona}` · 总耗时 {duration_s:.1f}s · 事实卷宗 `{snapshot_id}`",
        "",
    ]


    if report.verdict.text:
        lines.append("## 裁决文")
        lines.append("")
        lines.append(report.verdict.text)
        lines.append("")


    if report.verdict.conflict_matrix:
        lines.append("## 分歧矩阵")
        lines.append("")
        lines.append("| 争议轴 | 角色立场 |")
        lines.append("| --- | --- |")
        for cm in report.verdict.conflict_matrix:
            axis = cm.get("axis", "")
            positions = cm.get("positions", {})
            pos_str = " / ".join(f"{k}={v}" for k, v in positions.items())
            lines.append(f"| {axis} | {pos_str} |")
        lines.append("")


    if report.verdict.minority_notes:
        lines.append("## 少数派意见")
        lines.append("")
        lines.append(report.verdict.minority_notes)
        lines.append("")


    if report.verdict.type == "escalate":
        lines.append(
            "> 🔴 **verdict = escalate — 需要你立刻行动**：仲裁规则用尽仍无法裁定。"
            "**你现在必须马上调用 `ask_user`**，把上面的裁决文 + 分歧矩阵 + 少数派意见"
            "作为 question 原样交还人类决策者，等待其回复后再继续。"
            "在拿到人类答复之前，**不要**自行拍板任何治疗/技术方案级决定，也**不要**结束本轮。"
            "（编排器不会替你弹卡——这一步只能由你调 `ask_user` 完成。）"
        )
        lines.append("")


    lines.append("## 各角色表态")
    lines.append("")
    for s in report.stances:
        status = "✅" if s.success else "❌"
        lines.append(
            f"### {status} `{s.role_id}` · persona={s.persona_id} · {s.duration_ms / 1000.0:.1f}s"
        )
        lines.append("")
        if s.error:
            lines.append(f"**失败**：`{s.error}`")
            lines.append("")
        if s.text:
            lines.append(s.text)
            lines.append("")
        if s.evidence_refs:
            lines.append(
                "evidence_refs: "
                + " ".join(f"`{r}`" for r in s.evidence_refs)
            )
            lines.append("")
        if s.open_questions:
            lines.append("open_questions:")
            for q in s.open_questions:
                lines.append(f"- {q}")
            lines.append("")


    if report.warnings_emitted > 0:
        lines.append(
            f"> ⚠️ 事实卷宗有 **{report.warnings_emitted}** 条事实被 L3 启发式标了主观词，"
            f"前端已收到 `evidence_warning` 事件。如果你认为它们其实是客观陈述，"
            f"可以放行；否则建议改写后重新召集议会。"
        )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"

class ConveneCouncilTool(BaseTool):


    @property
    def name(self) -> str:
        return "convene_council"

    @property
    def description(self) -> str:
        return (
            "召集议会：N 位 persona 对同一问题独立表态（互不可见），arbiter 仲裁产出"
            " consensus / arbitrated / escalate 三档 verdict。用于不可拆分但需要多视"
            "角碰撞的问题（MDT 治疗选择 / 鉴别诊断 / 代码评审 / 论文评审 / 法律评审等）。"
            "可拆分的执行任务请用 dispatch_squad，单线推理直接自己干。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "convene_council",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": (
                                "议题：一句清晰的问题陈述。不要把病例全文塞进来——"
                                "事实卷宗另走 explicit_facts；这里只写'要表决/碰撞的核心问题'。"
                            ),
                        },
                        "roles": {
                            "type": "array",
                            "minItems": 2,
                            "description": (
                                "角色列表（≥2）。每个角色由一个 persona_id 标识，"
                                "表示以哪个人格视角独立表态。角色之间互不可见。"
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "persona_id": {
                                        "type": "string",
                                        "description": (
                                            "persona id（必须英文 id）。"
                                            "通用工作型："
                                            "clinician（临床医师/证据整理 🩺）/ "
                                            "researcher（科研型 🔬）/ "
                                            "data_analyst（数据分析师 📊）/ "
                                            "writer（学术写作 ✍️）/ "
                                            "coder（编码工程师 💻）/ "
                                            "critical_reviewer（仲裁评审员 ⚖️，仅用于 arbiter）。"
                                            "MDT 议会专用（按病种招募 4-6 个核心 + 视需补充支持科室）："
                                            "med_oncologist（肿瘤内科 💊）/ "
                                            "surgical_oncologist（外科肿瘤 🔪）/ "
                                            "interventional_radiologist（介入科 🩹）/ "
                                            "radiation_oncologist（放疗科 ☢️）/ "
                                            "radiologist（影像科 🖼️）/ "
                                            "pathologist（病理科 🧪）/ "
                                            "nuclear_medicine（核医学科 ⚛️，PET/代谢/核素治疗）/ "
                                            "molecular_pathologist（分子诊断 🧬，NGS/靶点/耐药）/ "
                                            "palliative_care（安宁缓和医疗 🕊️，症状/目标/生活质量）/ "
                                            "clinical_pharmacist（临床药师 💉，剂量/相互作用/支持用药）/ "
                                            "genetic_counselor（遗传咨询 🧫，胚系/家系）/ "
                                            "nutrition（营养科 🥗，营养风险/恶病质）/ "
                                            "psycho_oncology（精神心理 🫂，心理痛苦/决策能力）。"
                                            "器官系统专科（按病种招募）："
                                            "gastroenterology（消化内科 🫃，内镜/早癌/梗阻黄疸）/ "
                                            "gynecologic_oncology（妇科肿瘤 🌸，宫颈/卵巢/内膜）/ "
                                            "reproductive_medicine（生殖医学 🍼，生育力保存）/ "
                                            "dermatology_venereology（皮肤性病科 🧴，皮肤癌/HPV/皮肤毒性）/ "
                                            "orthopedic_oncology（骨科 🦴，骨肉瘤/骨转移/脊髓压迫）/ "
                                            "urology（泌尿外科 🚹，前列腺/膀胱/肾）/ "
                                            "thoracic_surgery（胸外科 🫁，肺/食管/纵隔）/ "
                                            "neuro_oncology（神经肿瘤 🧠，脑肿瘤/脑转移）/ "
                                            "head_neck_surgery（头颈外科 👂，口咽喉/鼻咽/甲状腺）/ "
                                            "hematology（血液科 🩸，白血病/淋巴瘤/骨髓瘤）/ "
                                            "breast_surgery（乳腺外科 🎗️，保乳/腋窝/重建）/ "
                                            "endocrinology（内分泌科 🦋，甲状腺/内分泌 irAE）/ "
                                            "cardio_oncology（肿瘤心脏病 🫀，心脏毒性）/ "
                                            "respiratory（呼吸内科 🌬️，支气管镜/肺炎毒性）/ "
                                            "infectious_disease（感染科 🦠，粒缺发热/HBV 再激活）/ "
                                            "nephrology（肾内科 🫘，肾功能/肾毒性）/ "
                                            "rheumatology_immunology（风湿免疫科 🛡️，irAE 管理）/ "
                                            "rehabilitation（康复科 🦽，预康复/功能恢复）。"
                                            "用户对话中说'消化/妇科/生殖/皮肤性病/骨科/泌尿/胸外/神经/头颈/血液/乳腺/内分泌/心内/呼吸/感染/肾内/风湿免疫/康复'"
                                            "或'肿瘤内科 / 外科 / 介入 / 放疗 / 影像 / 病理 / 核医学 / 分子诊断 / 缓和医疗 / 药师 / 遗传 / 营养 / 心理 / 临床医生 / 研究员 / 分析师'"
                                            "等中文别名时，自行映射到上面对应的英文 id；本字段只接受英文 id。"
                                            "注意：人格库会持续扩充，招募前务必先调 list_personas 确认当前可用全量，不要硬记本列表。"
                                            "不能与 arbiter_persona 重复。"
                                        ),
                                    },
                                    "stance_hint": {
                                        "type": "string",
                                        "description": (
                                            "可选：给本角色的'视角侧重'提示，如 "
                                            "'请重点从手术安全性角度发言'。不写则自由发挥。"
                                        ),
                                    },
                                },
                                "required": ["persona_id"],
                            },
                        },
                        "snapshot_strategy": {
                            "type": "string",
                            "enum": ["auto", "explicit"],
                            "default": "auto",
                            "description": (
                                "auto = 从主对话兜底抽机械锚点（PMID/DOI/uploads）；"
                                "explicit = 用 explicit_facts 显式列的事实清单（推荐，最干净）。"
                                "注意：议会不允许 'none'——没有事实卷宗的议会是纯主观漂浮（决策 #6）。"
                            ),
                        },
                        "explicit_facts": {
                            "type": "array",
                            "description": (
                                "snapshot_strategy=explicit 时必填。**只列客观、可核验、不含个人立场的陈述**。"
                                "禁止把'我倾向/我建议/应该/可能/看起来'等表态塞进来。"
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
                                        "description": "锚点字符串，如 'PMID:12345' / 'case:bclc_stage'。",
                                    },
                                    "content": {
                                        "type": "string",
                                        "description": "客观描述本条事实的内容。",
                                    },
                                    "source": {
                                        "type": "string",
                                        "description": "可选审计字段：这条事实来自哪条消息/工具结果。",
                                    },
                                },
                                "required": ["kind", "ref", "content"],
                            },
                        },
                        "arbiter_persona": {
                            "type": "string",
                            "default": "critical_reviewer",
                            "description": (
                                "仲裁人 persona id。默认 critical_reviewer（已有专业仲裁人格）。"
                                "不能与 roles 里的任何 persona_id 重复。"
                            ),
                        },
                        "rebut": {
                            "type": "boolean",
                            "default": False,
                            "description": (
                                "是否开启反驳轮——一阶表态全部收齐后，让每个角色"
                                "再读其他角色（匿名）的立场，给出反驳/修正/坚持。"
                                "前端会展示'议事剧场'风格的反驳气泡流。"
                                "什么时候开（true）："
                                "  - 议题本身就有明显分歧（不同治疗策略、不同方案对比、"
                                "    各方利益相关角度差异大）"
                                "  - MDT 经典场景（治疗选择 / 鉴别诊断 / 临床路径决策）"
                                "  - 代码评审 / 论文评审等多视角碰撞场景"
                                "什么时候不开（false，默认）："
                                "  - 议题答案明确、各方大概率共识"
                                "  - 时间紧迫（反驳轮会让总时长翻倍）"
                                "  - 用户没明确要求'再深入讨论'/'让他们互相反驳'"
                                "  - 单纯信息抽取/解析类（如'解析这 3 篇文献'，应该用 squad）"
                                "判断口诀：用户原话或场景有'分歧/碰撞/再深入'的味道 → true；"
                                "纯信息检索 / 单一立场可预判 → false。"
                            ),
                        },
                        "timeout_s": {
                            "type": "integer",
                            "minimum": 1,
                            "default": 600,
                            "description": "单 role / arbiter 硬超时（秒）。",
                        },
                    },
                    "required": ["question", "roles"],
                },
            },
        }

    async def execute(
        self,
        question: str = "",
        roles: list[dict] | None = None,
        snapshot_strategy: str = "auto",
        explicit_facts: list[dict] | None = None,
        arbiter_persona: str = "critical_reviewer",
        rebut: bool = False,
        timeout_s: int = 600,
        _agent: "Agent | None" = None,
        **_: Any,
    ) -> ToolResult:

        if _agent is None:
            return ToolResult(
                success=False,
                output="convene_council 必须由主智能体在主对话中调用，无法独立运行。",
                error="missing agent context",
            )
        if getattr(_agent, "_depth", 0) > 0:
            return ToolResult(
                success=False,
                output=(
                    "convene_council 不能在子任务上下文里嵌套调用（内核 _depth>0 守门）。"
                    "请把结论汇报回主对话，由主智能体决定下一步。"
                ),
                error="nested_convene_council_forbidden",
            )

        question = (question or "").strip()
        if not question:
            return ToolResult(
                success=False,
                output="convene_council 缺 question 参数。请给议会一个清晰的议题。",
                error="missing_question",
            )

        roles = roles or []
        if not isinstance(roles, list) or len(roles) < 2:
            return ToolResult(
                success=False,
                output="convene_council 至少需要 2 个 role（议会需要差异性）。",
                error="too_few_roles",
            )


        from cancer_claw.agent.engine.council import (
            CouncilRequest,
            CouncilRole,
            run_council,
        )

        role_objs: list[CouncilRole] = []
        persona_ids: list[str] = []
        for i, raw in enumerate(roles):
            if not isinstance(raw, dict):
                return ToolResult(
                    success=False,
                    output=f"第 {i} 个 role 不是对象，请检查 roles 结构。",
                    error="bad_role_shape",
                )
            pid = str(raw.get("persona_id") or "").strip()
            if not pid:
                return ToolResult(
                    success=False,
                    output=f"第 {i} 个 role 缺 persona_id。",
                    error="missing_persona_id",
                )
            persona_ids.append(pid)
            hint = raw.get("stance_hint")
            hint = str(hint).strip() if hint else None
            role_objs.append(CouncilRole(persona_id=pid, stance_hint=hint))


        dup = {x for x in persona_ids if persona_ids.count(x) > 1}
        if dup:
            return ToolResult(
                success=False,
                output=f"roles 中 persona_id 重复：{sorted(dup)}，请去重。",
                error="duplicate_persona_ids",
            )


        arbiter_persona = (arbiter_persona or "critical_reviewer").strip()
        if arbiter_persona in persona_ids:
            return ToolResult(
                success=False,
                output=(
                    f"arbiter_persona ({arbiter_persona}) 不能同时出现在 roles 里——"
                    "仲裁人和议事人格必须互斥。"
                ),
                error="arbiter_role_conflict",
            )



        from cancer_claw.agent.engine.persona import persona_exists
        unknown = [pid for pid in persona_ids if not persona_exists(pid)]
        if not persona_exists(arbiter_persona):
            unknown.append(arbiter_persona)
        if unknown:
            return ToolResult(
                success=False,
                output=(
                    f"以下 persona_id 不存在：{unknown}。"
                    "请先调 list_personas 查看当前可用人格清单，再重新挑选。"
                    "（persona_id 必须严格匹配 personas/{id}.md 的文件名；"
                    "用户对话中的中文别名需要由你映射到对应英文 id）"
                ),
                error="unknown_persona",
            )


        strategy = (snapshot_strategy or "auto").strip().lower()
        if strategy == "none":
            return ToolResult(
                success=False,
                output=(
                    "convene_council 不允许 snapshot_strategy='none'（决策 #6）。"
                    "议会没有事实卷宗就是纯主观漂浮。请用 'auto' 或 'explicit'。"
                ),
                error="snapshot_none_forbidden",
            )


        from cancer_claw.capabilities.toolkit.builtins.dispatch_squad import DispatchSquadTool

        snapshot, snapshot_err = DispatchSquadTool._build_snapshot(
            strategy=strategy,
            explicit_facts=explicit_facts,
            master_agent=_agent,
        )
        if snapshot_err is not None:
            return ToolResult(success=False, output=snapshot_err, error="snapshot_error")


        try:
            req = CouncilRequest(
                question=question,
                roles=tuple(role_objs),
                snapshot=snapshot,
                arbiter_persona=arbiter_persona,
                rebut=bool(rebut),
                timeout_s=int(timeout_s) if timeout_s else 600,
            )
            report = await run_council(req, _agent)
        except (ValueError, RuntimeError) as exc:
            logger.warning("convene_council_run_failed", error=str(exc))
            return ToolResult(
                success=False,
                output=f"council 执行失败：{type(exc).__name__}: {exc}",
                error=str(exc),
            )

        output_md = _render_report_markdown(report, snapshot_id=snapshot.id)
        return ToolResult(
            success=True,
            output=output_md,
            data={
                "council_id": report.council_id,
                "question": report.question,
                "snapshot_id": report.snapshot_id,
                "arbiter_persona": report.arbiter_persona,
                "verdict_type": report.verdict.type,
                "verdict_text": report.verdict.text,
                "conflict_matrix": list(report.verdict.conflict_matrix),
                "minority_notes": report.verdict.minority_notes,
                "stances": [
                    {
                        "role_id": s.role_id,
                        "persona_id": s.persona_id,
                        "success": s.success,
                        "text": s.text,
                        "evidence_refs": list(s.evidence_refs),
                        "open_questions": list(s.open_questions),
                        "duration_ms": s.duration_ms,
                        "error": s.error,
                    }
                    for s in report.stances
                ],
                "rebuttals": [
                    {
                        "role_id": r.role_id,
                        "persona_id": r.persona_id,
                        "success": r.success,
                        "text": r.text,
                        "evidence_refs": list(r.evidence_refs),
                        "duration_ms": r.duration_ms,
                        "error": r.error,
                    }
                    for r in report.rebuttals
                ] if report.rebuttals else [],
                "warnings_emitted": report.warnings_emitted,
                "duration_ms": report.duration_ms,
            },
        )

ConveneCouncilTool.__repr__ = lambda self: f"<ConveneCouncilTool name={self.name!r}>"

__all__ = ["ConveneCouncilTool"]



from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()

@dataclass
class SummonRequest:




    body: str
    """
    Body = 用谁的"人格 + 记忆"来执行这次任务。
    取值是 agent_id（如 "cancer_claw_architect" / "cancer_claw_pipeline_worker" / "user_xiaowang"）。

    关键语义：
    - 同一个 body 跨任务持久（memory / 信誉跟着 body 走）
    - body 是必填，无 body 不能召唤（要保证每次召唤都有"一个具体的人在干活"）
    """

    task: str
    """
    本次召唤要完成的具体任务，自然语言。
    会拼到 transfer_prompt 的最后一段，是 sub-agent 的"工作指令"。
    """



    soul: str | None = None
    """
    Soul = 临时挂载的"方法论 / craft"。
    取值是 craft_id（如 "craft_domain_modeler"），或 None。

    取 None 的语义：
    - 不挂 craft，body 用自己的默认 soul.md 人格干活
    - 等价于 v2 的 delegate_task（让 architect 用自己的 architect_soul 干活）

    取 craft_id 的语义：
    - craft 正文作为"执行说明书"段插到 transfer_prompt
    - 工具白名单收窄：body.default_tools ∩ craft.tools
    - 等价于 v2 的 pipeline step（worker 戴上 craft 帽子干活）
    """

    workspace_subdir: str = ""
    """
    工作目录隔离。空串=用 project workspace 根；非空=workspace/{subdir}/。

    用途：
    - 招标场景下每个 bidder 一个子目录，互相不读对方产出
    - 一些 craft 要求"不污染主目录"
    """

    tool_overrides: dict[str, Any] = field(default_factory=dict)
    """
    工具白名单覆盖，支持三种 op：
    - {"add": ["tool_x"]}      在 body∩soul 基础上额外加几个工具
    - {"remove": ["tool_y"]}   从默认集去掉几个工具
    - {"replace": ["a","b"]}   完全替换为指定列表（强覆盖，慎用）

    默认空 dict = 不覆盖，用 body.default_tools ∩ soul.tools 自然结果。
    """



    isolation: bool = True
    """
    True  = 一次性 sub-agent，跑完即销毁（默认，安全）
    False = 复用 body 共享实例（极少用，仅 ops 心跳那种长存任务）

    isolation=False 的代价：要小心 _messages / _working_memory 残留。建议永远 True。
    """

    parent: "Any | None" = None
    """
    父 agent，用于：
    - 事件冒泡（SSE depth 计算）
    - 上溯到 master 找 ask_delegator 的目标
    - 绑定 project_id（透传 parent._evolution_project_id 给 body）

    None = 顶层召唤（极少用，通常是测试场景）
    """

    event_sink: "asyncio.Queue | None" = None
    """
    事件冒泡 queue。父 agent 的 _event_sink 直接传进来即可，
    子 agent 的 thinking / tool_call / tool_result 事件会按 depth+1 push 进去。
    """

    depth: int = 0
    """事件深度，用于前端缩进展示。父 agent 的 _depth + 1。"""



    output_schema: dict[str, Any] = field(default_factory=dict)
    """
    可选的 JSON Schema。设置后 summon 会校验 sub-agent 输出，
    不通过自动 retry 一次（把 schema error 喂回让模型修正）。

    通常从 craft.output_schema 透传过来，调用方可手动覆盖。
    """

    timeout_s: int = 600
    """
    单次召唤的硬超时（墙钟），防止 sub-agent 死循环。
    超时则 raise TimeoutError，由调用方决定重试 / fallback。
    """

    max_iterations: int = 50
    """
    sub-agent 推理循环最大轮次。
    超过即 raise，由 failure_policy 决定后续。
    """

    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    """召唤的唯一 id，用于日志关联和事件追踪。"""

@dataclass
class SummonResult:


    request_id: str
    body: str
    soul: str | None

    success: bool
    """True = 完成且通过 schema 校验；False = 异常 / 超时 / schema 不过"""

    content: str = ""
    """sub-agent 最终文本输出（裁剪到 8K 字符）"""

    json_output: dict[str, Any] = field(default_factory=dict)
    """从 content 抽出的 JSON（如果模型遵守了输出契约）"""

    artifacts: list[str] = field(default_factory=list)
    """sub-agent 在 workspace 里产生的文件路径"""

    error: str = ""
    """失败时的错误描述（含异常类型 + message）"""

    iterations: int = 0
    """实际推理轮次"""

    duration_ms: float = 0.0
    """墙钟耗时"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    """成本统计"""

    schema_valid: bool = True
    """JSON Schema 校验结果（无 schema 则 True）"""

    summary: str = ""
    """sub-agent 给出的"我做了什么"一句话概要（StepHandoff 用，见 v3 §4.6 / E1）"""

    open_questions: list[str] = field(default_factory=list)
    """sub-agent 留下的待澄清问题"""

def _extract_json_object(text: str) -> Any:

    if not text:
        return None


    fence_pat = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
    candidates: list[str] = [m.group(1) for m in fence_pat.finditer(text)]
    for candidate in reversed(candidates):
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
            if isinstance(obj, (dict, list)):
                return obj
        except Exception:
            pass






    decoder = json.JSONDecoder()
    parsed: list[Any] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] in "{[":
            try:
                obj, end = decoder.raw_decode(text, i)
                if isinstance(obj, (dict, list)):
                    parsed.append(obj)
                i = max(end, i + 1)
                continue
            except json.JSONDecodeError:
                pass
        i += 1
    if parsed:


        last = parsed[-1]
        if isinstance(last, dict):
            return last

        for obj in reversed(parsed[:-1]):
            if isinstance(obj, dict):
                return obj
        return last


    for opener, closer in (("{", "}"), ("[", "]")):
        i = text.find(opener)
        j = text.rfind(closer)
        if i != -1 and j != -1 and j > i:
            try:
                obj = json.loads(text[i : j + 1])
                if isinstance(obj, (dict, list)):
                    return obj
            except Exception:
                continue
    return None

def _err_result(req: SummonRequest, t0: float, error_msg: str) -> SummonResult:

    return SummonResult(
        request_id=req.request_id,
        body=req.body,
        soul=req.soul,
        success=False,
        error=error_msg,
        duration_ms=(time.monotonic() - t0) * 1000,
        schema_valid=False,
    )

def _validate_schema(json_obj: Any, schema: dict[str, Any]) -> bool:

    if not schema:
        return True
    try:
        import jsonschema
    except ImportError:

        logger.warning("summon_jsonschema_unavailable", schema_keys=list(schema.keys()))
        return True
    try:
        jsonschema.validate(instance=json_obj, schema=schema)
        return True
    except jsonschema.ValidationError as e:
        logger.info(
            "summon_schema_invalid",
            error=str(e)[:200],
            path=list(getattr(e, "path", [])),
        )
        return False
    except Exception:
        logger.warning("summon_schema_validate_error", exc_info=True)
        return False

def _compose_prompt(
    *,
    body_system: str,
    soul_section: str,
    task: str,
    ctx_snapshot: str,
) -> str:

    from cancer_claw.resources.prompt_templates import load_prompt

    role_section = (
        f"# 你的角色（持久人格）\n{body_system.strip()}"
        if body_system.strip()
        else ""
    )
    soul_block = (
        f"\n\n# 本次任务的方法论（临时挂载）\n{soul_section.strip()}"
        if soul_section.strip()
        else ""
    )
    return load_prompt(
        "summon_transfer",
        role_section=role_section,
        soul_section=soul_block,
        ctx_snapshot=(ctx_snapshot or "（无）").strip(),
        task=task.strip(),
    ).strip()

def _merge_usage(u1: dict[str, int] | None, u2: dict[str, int] | None) -> dict[str, int]:

    out: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}
    for u in (u1, u2):
        if not u:
            continue
        out["prompt_tokens"] += int(u.get("prompt_tokens", 0) or 0)
        out["completion_tokens"] += int(u.get("completion_tokens", 0) or 0)
    return out

def _extract_project_id(req: SummonRequest) -> str | None:

    p = req.parent
    while p is not None:
        pid = getattr(p, "_evolution_project_id", None)
        if pid:
            return pid
        p = getattr(p, "_delegator", None)
    return None

def _get_ctx_snapshot(req: SummonRequest) -> str:

    p = req.parent
    if p is None:
        return ""
    ctx = getattr(p, "_context", None)
    if ctx is None:
        return ""
    parts = getattr(ctx, "_system_parts", None)
    if not isinstance(parts, dict):
        return ""
    return parts.get("plan", "") or ""

def _get_body_soul_text(body_agent: Any) -> str:

    return (
        getattr(body_agent, "soul_content", None)
        or getattr(body_agent, "_soul_content", "")
        or ""
    )

async def _run_via_run_into_sink(
    body_agent: Any,
    transfer_prompt: str,
    *,
    sink: "asyncio.Queue | None",
    depth: int,
) -> tuple[str, int, dict[str, int]]:

    iter_before = int(getattr(body_agent, "_tool_calls", 0) or 0)
    tok_before = int(getattr(body_agent, "_total_tokens", 0) or 0)

    content = await body_agent._run_into_sink(transfer_prompt, sink, depth)

    iter_after = int(getattr(body_agent, "_tool_calls", 0) or 0)
    tok_after = int(getattr(body_agent, "_total_tokens", 0) or 0)
    iter_count = max(0, iter_after - iter_before)

    usage = {"prompt_tokens": max(0, tok_after - tok_before), "completion_tokens": 0}
    return content, iter_count, usage

async def summon(req: SummonRequest) -> SummonResult:

    t0 = time.monotonic()
    prev_subdir: Any = None
    body_agent = None



    try:
        from cancer_claw.agent.engine.agent_factory import get_or_create_agent
        body_agent = await get_or_create_agent(
            req.body,
            project_id=_extract_project_id(req),
            parent=req.parent,
            event_sink=req.event_sink,
        )
    except FileNotFoundError as e:
        logger.warning("summon_body_not_found", body=req.body, error=str(e))
        return _err_result(req, t0, f"body_not_found: {e}")
    except Exception as e:
        logger.warning("summon_body_load_failed", body=req.body, error=str(e))
        return _err_result(req, t0, f"body_load_failed: {type(e).__name__}: {e}")


    soul_text = ""
    soul_tools: set[str] | None = None
    soul_output_schema = req.output_schema

    if req.soul:

        from cancer_claw.resources.knowledge import load_craft

        craft = None
        try:
            craft = load_craft(req.soul)
        except FileNotFoundError:


            try:
                from cancer_claw.resources.knowledge.skill_loader import get_skill
                craft = get_skill(req.soul)
            except Exception as e:
                logger.warning("summon_skill_lookup_failed", soul=req.soul, error=str(e))
                craft = None
            if craft is None:
                logger.warning("summon_soul_not_found", soul=req.soul)
                return _err_result(req, t0, f"soul_not_found: {req.soul}")
        except Exception as e:
            logger.warning("summon_soul_load_failed", soul=req.soul, error=str(e))
            return _err_result(req, t0, f"soul_load_failed: {type(e).__name__}: {e}")

        soul_text = craft.full_prompt or ""
        soul_tools = set(craft.tools or [])

        if not soul_output_schema and getattr(craft, "output_schema", None):
            soul_output_schema = craft.output_schema




    from cancer_claw.capabilities.toolkit.registry import CORE_TOOL_NAMES

    body_default_tools = set(body_agent.default_tool_names())

    if soul_tools is not None:

        intersect = body_default_tools & soul_tools
        if soul_tools and not intersect:
            logger.warning(
                "summon_tool_intersection_empty",
                body=req.body,
                soul=req.soul,
                body_tools=sorted(body_default_tools),
                soul_tools=sorted(soul_tools),
            )
        allowed = intersect | CORE_TOOL_NAMES
    else:
        allowed = body_default_tools


    overrides = req.tool_overrides or {}
    if "replace" in overrides:
        allowed = set(overrides["replace"])
    else:
        if "add" in overrides:
            allowed |= set(overrides["add"])
        if "remove" in overrides:
            allowed -= set(overrides["remove"])


    transfer_prompt = _compose_prompt(
        body_system=_get_body_soul_text(body_agent),
        soul_section=soul_text,
        task=req.task,
        ctx_snapshot=_get_ctx_snapshot(req),
    )


    if req.workspace_subdir:


        prev_subdir = getattr(body_agent, "_workspace_subdir", "")
        body_agent._workspace_subdir = req.workspace_subdir

    logger.info(
        "summon_start",
        request_id=req.request_id,
        body=req.body,
        soul=req.soul,
        isolation=req.isolation,
        depth=req.depth,
        tool_count=len(allowed),
    )


    try:


        if req.isolation:
            content, iter_count, usage = await asyncio.wait_for(
                body_agent.spawn_oneshot(
                    transfer_prompt,
                    tools=allowed,
                    max_iterations=req.max_iterations,
                    sink=req.event_sink,
                    depth=req.depth + 1,
                ),
                timeout=req.timeout_s,
            )
        else:

            content, iter_count, usage = await asyncio.wait_for(
                _run_via_run_into_sink(
                    body_agent,
                    transfer_prompt,
                    sink=req.event_sink,
                    depth=req.depth + 1,
                ),
                timeout=req.timeout_s,
            )


        json_obj_raw = _extract_json_object(content) or {}
        json_obj: dict[str, Any] = json_obj_raw if isinstance(json_obj_raw, dict) else {}

        schema_valid = True
        if soul_output_schema:
            schema_valid = _validate_schema(json_obj, soul_output_schema)
            if not schema_valid:


                logger.info("summon_schema_retry", request_id=req.request_id)
                retry_prompt = (
                    f"{transfer_prompt}\n\n"
                    f"[上一次输出未通过契约校验]\n"
                    f"你刚才的输出 JSON 不符合本步要求的 schema：\n"
                    f"{soul_output_schema}\n\n"
                    f"你的输出（最后 2KB）：{content[-2000:]}\n\n"
                    f"请按 schema 重新输出整段 JSON。"
                )
                content2, iter_count2, usage2 = await asyncio.wait_for(
                    body_agent.spawn_oneshot(
                        retry_prompt,
                        tools=allowed,
                        max_iterations=3,
                        sink=req.event_sink,
                        depth=req.depth + 1,
                    ),
                    timeout=req.timeout_s,
                )
                content = content2
                iter_count += iter_count2
                usage = _merge_usage(usage, usage2)
                json_obj_raw = _extract_json_object(content) or {}
                json_obj = json_obj_raw if isinstance(json_obj_raw, dict) else {}
                schema_valid = _validate_schema(json_obj, soul_output_schema)



        artifacts_raw = json_obj.get("artifacts", []) if isinstance(json_obj, dict) else []
        summary_raw = json_obj.get("summary", "") if isinstance(json_obj, dict) else ""
        open_q_raw = json_obj.get("open_questions", []) if isinstance(json_obj, dict) else []

        artifacts = [str(a) for a in artifacts_raw] if isinstance(artifacts_raw, list) else []
        open_questions = (
            [str(q) for q in open_q_raw][:10] if isinstance(open_q_raw, list) else []
        )

        result = SummonResult(
            request_id=req.request_id,
            body=req.body,
            soul=req.soul,
            success=schema_valid,
            content=content[:8000],
            json_output=json_obj,
            artifacts=artifacts,
            iterations=iter_count,
            duration_ms=(time.monotonic() - t0) * 1000,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            schema_valid=schema_valid,
            summary=str(summary_raw)[:500],
            open_questions=open_questions,
        )

        logger.info(
            "summon_done",
            request_id=req.request_id,
            success=result.success,
            iterations=result.iterations,
            duration_ms=int(result.duration_ms),
            schema_valid=result.schema_valid,
        )
        return result

    except asyncio.TimeoutError:
        logger.warning("summon_timeout", request_id=req.request_id, timeout_s=req.timeout_s)
        return _err_result(req, t0, f"timeout after {req.timeout_s}s")

    except Exception as exc:
        logger.exception("summon_failed", request_id=req.request_id)
        return _err_result(req, t0, f"{type(exc).__name__}: {exc}")

    finally:

        if req.workspace_subdir and body_agent is not None:
            try:
                body_agent._workspace_subdir = prev_subdir
            except Exception:
                pass

__all__ = ["SummonRequest", "SummonResult", "summon"]

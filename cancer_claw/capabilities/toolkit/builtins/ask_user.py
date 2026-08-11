

import asyncio
import contextlib
import json
import time
import uuid
from typing import Any

import structlog

from cancer_claw.services.platform.redis_client import get_redis, redis_enabled, rkey
from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult

logger = structlog.get_logger()

_pending_questions: dict[str, dict[str, Any]] = {}

_TTL_BUFFER = 60

_IDX_TTL = 86400

_ANS_TTL = 120

_POLL_BLOCK_S = 3

def _new_qid() -> str:

    return f"q_{uuid.uuid4().hex[:12]}"

def _k_pending(qid: str) -> str:
    return rkey("askuser", "q", qid)

def _k_answer(qid: str) -> str:
    return rkey("askuser", "ans", qid)

def _k_index() -> str:
    return rkey("askuser", "idx")

class AskUserTool(BaseTool):


    @property
    def name(self) -> str:
        return "ask_user"

    @property
    def description(self) -> str:
        return "向用户提问并等待回复。当需要人工确认、选择或补充信息时使用。"

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "ask_user",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["ask_question"],
                            "description": "操作类型"
                        },
                        "question": {
                            "type": "string",
                            "description": "要问用户的问题"
                        },
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "选项列表（可选，提供选择题场景）"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "等待超时（秒），默认 300（5分钟）",
                            "default": 300
                        },
                    },
                    "required": ["action", "question"]
                }
            }
        }

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "ask_question")
        question = kwargs.get("question", "")
        options = kwargs.get("options", []) or []
        timeout = kwargs.get("timeout", 300)

        event_sink: asyncio.Queue | None = kwargs.get("_event_sink")
        agent_id = kwargs.get("_agent_id", "")
        agent_name = kwargs.get("_agent_name", "")
        depth = int(kwargs.get("_depth", 0) or 0)
        session_id = kwargs.get("_session_id", "")

        if action != "ask_question":
            return ToolResult(success=False, error=f"不支持的操作: {action}")
        if not question:
            return ToolResult(success=False, error="question 参数不能为空")

        try:
            timeout = int(timeout)
        except (TypeError, ValueError):
            timeout = 300
        if timeout <= 0:
            timeout = 300

        return await self._ask(
            question, options, timeout, event_sink, agent_id, agent_name, depth, session_id
        )

    async def _ask(
        self,
        question: str,
        options: list[str],
        timeout: int,
        event_sink: "asyncio.Queue | None",
        agent_id: str = "",
        agent_name: str = "",
        depth: int = 0,
        session_id: str = "",
    ) -> ToolResult:

        qid = _new_qid()

        r = None
        if redis_enabled():
            try:
                r = await get_redis()
            except Exception as e:


                logger.warning("ask_user_redis_unavailable_fallback", error=str(e))
                r = None


        event: asyncio.Event | None = None
        if r is not None:
            try:
                ttl = timeout + _TTL_BUFFER
                pk = _k_pending(qid)
                await r.hset(pk, mapping={
                    "question": question,
                    "options": json.dumps(options, ensure_ascii=False),
                    "session_id": session_id or "",
                    "agent_id": agent_id or "",
                    "created_at": str(time.time()),
                    "timeout": str(timeout),
                })
                await r.expire(pk, ttl)
                await r.sadd(_k_index(), qid)
                await r.expire(_k_index(), _IDX_TTL)
            except Exception as e:
                logger.warning("ask_user_redis_register_failed_fallback", error=str(e))
                r = None
        if r is None:

            event = asyncio.Event()
            _pending_questions[qid] = {
                "question": question,
                "options": options,
                "event": event,
                "answer": None,
            }


        if event_sink is not None:
            await event_sink.put({
                "type": "ask_user_pending",
                "question_id": qid,
                "question": question,
                "options": options,
                "timeout": timeout,
                "hint": f"请调用 POST /api/questions/{qid}/answer 提交回答",
                "agent_id": agent_id,
                "agent_name": agent_name,
                "depth": depth,
            })


        if r is not None:
            return await self._wait_redis(r, qid, question, timeout)
        return await self._wait_local(qid, question, timeout, event)

    async def _wait_redis(
        self, r: Any, qid: str, question: str, timeout: int
    ) -> ToolResult:

        answer_key = _k_answer(qid)
        deadline = time.monotonic() + max(1, int(timeout))
        answer: str | None = None
        try:
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                block = max(1, min(_POLL_BLOCK_S, int(round(remaining))))
                try:

                    popped = await r.blpop([answer_key], timeout=block)
                except asyncio.CancelledError:

                    raise
                except Exception as e:


                    logger.warning("ask_user_blpop_transient", question_id=qid, error=str(e))

                    await asyncio.sleep(min(_POLL_BLOCK_S, max(1, block)))
                    continue
                if popped:
                    answer = (
                        popped[1]
                        if isinstance(popped, (list, tuple)) and len(popped) > 1
                        else ""
                    )
                    break
        finally:


            with contextlib.suppress(Exception):
                await r.delete(_k_pending(qid), answer_key)
                await r.srem(_k_index(), qid)

        if answer is None:
            return ToolResult(
                success=False,
                output=f"用户未在 {timeout} 秒内回复问题: {question}",
                error="等待用户回复超时",
            )
        return ToolResult(
            success=True,
            output=f"用户回复: {answer}",
            data={"question_id": qid, "answer": answer},
        )

    async def _wait_local(
        self, qid: str, question: str, timeout: int, event: "asyncio.Event | None"
    ) -> ToolResult:

        assert event is not None
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            _pending_questions.pop(qid, None)
            return ToolResult(
                success=False,
                output=f"用户未在 {timeout} 秒内回复问题: {question}",
                error="等待用户回复超时",
            )
        except asyncio.CancelledError:
            _pending_questions.pop(qid, None)
            raise

        answer = (_pending_questions.pop(qid, {}) or {}).get("answer", "")
        return ToolResult(
            success=True,
            output=f"用户回复: {answer}",
            data={"question_id": qid, "answer": answer},
        )

async def submit_answer(question_id: str, answer: str) -> bool:


    entry = _pending_questions.get(question_id)
    if entry is not None:
        entry["answer"] = answer
        entry["event"].set()
        return True


    if redis_enabled():
        try:
            r = await get_redis()
        except Exception as e:
            logger.warning("ask_user_submit_redis_unavailable", error=str(e))
            r = None
        if r is not None:
            try:
                pk = _k_pending(question_id)
                if not await r.exists(pk):
                    return False
                ak = _k_answer(question_id)
                await r.rpush(ak, answer)
                await r.expire(ak, _ANS_TTL)
                return True
            except Exception as e:
                logger.warning(
                    "ask_user_submit_redis_failed",
                    question_id=question_id, error=str(e),
                )
                return False

    return False

async def get_pending_questions() -> list[dict]:

    if redis_enabled():
        try:
            r = await get_redis()
        except Exception as e:
            logger.warning("ask_user_list_redis_unavailable", error=str(e))
            r = None
        if r is not None:
            try:
                idx = _k_index()
                qids = await r.smembers(idx)
                out: list[dict] = []
                for qid in qids:
                    h = await r.hgetall(_k_pending(qid))
                    if not h:

                        with contextlib.suppress(Exception):
                            await r.srem(idx, qid)
                        continue
                    try:
                        opts = json.loads(h.get("options") or "[]")
                    except (ValueError, TypeError):
                        opts = []
                    out.append({
                        "id": qid,
                        "question": h.get("question", ""),
                        "options": opts,
                    })
                return out
            except Exception as e:
                logger.warning("ask_user_list_redis_failed", error=str(e))


    return [
        {"id": qid, "question": entry["question"], "options": entry.get("options", [])}
        for qid, entry in _pending_questions.items()
    ]

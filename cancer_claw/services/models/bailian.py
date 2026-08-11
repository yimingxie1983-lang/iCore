

from __future__ import annotations

import asyncio
import json
import time
import structlog
import httpx

from cancer_claw.services.models.base import BaseLLMClient, LLMClientError
from cancer_claw.services.models.schemas import LLMRequest, LLMResponse, ToolCall

logger = structlog.get_logger()

_BAILIAN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_CHAT_ENDPOINT = f"{_BAILIAN_BASE_URL}/chat/completions"

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=5.0)

class BailianClient(BaseLLMClient):


    def __init__(
        self,
        api_key: str,
        model: str = "qwen3.5-flash",
        default_thinking_budget: int | None = 4096,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
    ):

        self._api_key = api_key
        self._default_model = model
        self._default_thinking_budget = default_thinking_budget
        self._timeout = timeout


        self._http = self._new_client()


        self._total_calls = 0
        self._total_errors = 0
        self._total_latency_ms = 0.0

    def _new_client(self) -> httpx.AsyncClient:

        return httpx.AsyncClient(
            timeout=self._timeout,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )



    _RETRY_BACKOFF = [3.0, 8.0, 20.0]

    async def chat(self, request: LLMRequest) -> LLMResponse:


        model = request.model or self._default_model
        body = self._build_body(request, model)

        body["stream"] = True
        body["stream_options"] = {"include_usage": True}

        attempt = 0
        while True:
            if attempt > 0:
                delay = self._RETRY_BACKOFF[attempt - 1] if attempt - 1 < len(self._RETRY_BACKOFF) else 30.0
                print(
                    f"\n[BailianHTTP] 第 {attempt} 次重试，"
                    f"等待 {delay:.0f}s 后重试...",
                    flush=True,
                )
                await asyncio.sleep(delay)

            self._log_request(body)

            try:
                status_code, raw_body, latency_ms = await self._stream_request(body)
                self._total_calls += 1
                self._total_latency_ms += latency_ms
            except httpx.TimeoutException as e:
                self._total_errors += 1
                logger.warning("bailian_timeout_retry", model=model, attempt=attempt, error=str(e))
                print(f"[BailianHTTP] 请求超时（第 {attempt} 次），重置连接池后重试: {e}", flush=True)
                await self._http.aclose()
                self._http = self._new_client()
                attempt += 1
                continue
            except httpx.RequestError as e:
                self._total_errors += 1
                logger.warning("bailian_network_retry", model=model, attempt=attempt, error=str(e))
                print(f"[BailianHTTP] 网络错误（第 {attempt} 次），重置连接池后重试: {e}", flush=True)
                await self._http.aclose()
                self._http = self._new_client()
                attempt += 1
                continue

            self._log_stream_summary(raw_body, status_code, latency_ms)




            if status_code == 429:
                self._total_errors += 1
                err_msg = raw_body.get("error", {}).get("message", "429 Too Many Requests")
                logger.warning("bailian_429_retry", status=status_code,
                               model=model, attempt=attempt, error=err_msg)
                print(f"[BailianHTTP] 被限流 HTTP 429（第 {attempt} 次），退避后重试: {err_msg}", flush=True)
                attempt += 1
                continue


            if status_code >= 500:
                self._total_errors += 1
                err_msg = raw_body.get("error", {}).get("message", "5xx")
                logger.warning("bailian_5xx_retry", status=status_code,
                               model=model, attempt=attempt, error=err_msg)
                print(f"[BailianHTTP] HTTP {status_code}（第 {attempt} 次），将重试: {err_msg}", flush=True)
                attempt += 1
                continue


            if status_code >= 400:
                self._total_errors += 1
                err_msg = raw_body.get("error", {}).get("message", "4xx")
                logger.error("bailian_api_error", status=status_code,
                             model=model, error=err_msg)






                _err_lower = (err_msg or "").lower()
                _vision_kw = (
                    "image_url" in _err_lower
                    or "vision" in _err_lower
                    or "multi_modal" in _err_lower
                    or "multimodal" in _err_lower
                    or "input_images" in _err_lower
                    or ("image" in _err_lower and "support" in _err_lower)
                    or ("图片" in (err_msg or "") and "支持" in (err_msg or ""))
                )
                if _vision_kw:
                    friendly = (
                        f"当前模型 `{model}` 不支持图片输入（多模态）。"
                        f"请改用 vision 模型（如 qwen-vl-plus / qwen-vl-max），或在配置里切到带 vision 能力的模型后重试。"
                        f"\n\n[原始错误] {err_msg}"
                    )
                    raise LLMClientError("bailian", status_code, friendly)
                raise LLMClientError("bailian", status_code, err_msg)



            _u = raw_body.get("usage", {}) or {}
            _pt = int(_u.get("prompt_tokens", 0) or 0)
            _ct = int(
                (_u.get("prompt_tokens_details") or {}).get("cached_tokens")
                or _u.get("prompt_cache_hit_tokens")
                or _u.get("cached_tokens")
                or 0
            )
            _hit = round(_ct / _pt * 100, 1) if _pt > 0 else 0.0
            logger.info("model_call_success", model=model, provider="qwen",
                        tokens=_u.get("total_tokens", 0),
                        prompt_tokens=_pt,
                        cached_tokens=_ct,
                        cache_hit_rate_pct=_hit)


            if _pt > 5000 and _hit < 30.0:
                logger.warning(
                    "prompt_cache_low_hit_rate",
                    model=model,
                    prompt_tokens=_pt,
                    cached_tokens=_ct,
                    cache_hit_rate_pct=_hit,
                    hint="可能击穿 cache：检查 system prompt / tools 数组是否中途变化",
                )
            return self._parse_response(raw_body, status_code)





    async def _stream_request(self, body: dict) -> tuple[int, dict, float]:

        start = time.monotonic()
        async with self._http.stream("POST", _CHAT_ENDPOINT, json=body) as resp:
            status = resp.status_code
            if status >= 400:

                await resp.aread()
                latency_ms = (time.monotonic() - start) * 1000
                try:
                    raw = resp.json()
                except Exception:
                    raw = {"error": {"message": (resp.text or "")[:300]}}
                return status, raw, latency_ms

            raw = await self._consume_sse(resp)
            latency_ms = (time.monotonic() - start) * 1000
            return status, raw, latency_ms

    @staticmethod
    async def _consume_sse(resp: httpx.Response) -> dict:

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_acc: dict[int, dict] = {}
        finish_reason: str | None = None
        usage: dict = {}
        model_name: str = ""

        async for line in resp.aiter_lines():
            if not line:
                continue
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if not data or data == "[DONE]":
                continue
            try:
                chunk = json.loads(data)
            except Exception:
                continue

            if chunk.get("model"):
                model_name = chunk["model"]
            if chunk.get("usage"):
                usage = chunk["usage"]

            for choice in chunk.get("choices") or []:
                fr = choice.get("finish_reason")
                if fr:
                    finish_reason = fr
                delta = choice.get("delta") or {}
                c = delta.get("content")
                if c:
                    content_parts.append(c)
                rc = delta.get("reasoning_content")
                if rc:
                    reasoning_parts.append(rc)
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["arguments"] += fn["arguments"]

        message: dict = {"role": "assistant"}
        if content_parts:
            message["content"] = "".join(content_parts)
        if reasoning_parts:
            message["reasoning_content"] = "".join(reasoning_parts)
        if tool_acc:
            message["tool_calls"] = [
                {
                    "id": v["id"],
                    "type": "function",
                    "function": {
                        "name": v["name"],
                        "arguments": v["arguments"] or "{}",
                    },
                }
                for _, v in sorted(tool_acc.items())
            ]

        return {
            "choices": [{"message": message, "finish_reason": finish_reason or "stop"}],
            "usage": usage,
            "model": model_name,
        }

    @staticmethod
    def _log_stream_summary(raw: dict, status: int, latency_ms: float) -> None:

        if status >= 400:
            print(
                f"\n[BailianHTTP← stream] status={status} latency={latency_ms:.0f}ms\n"
                f"  [错误] {raw.get('error', {}).get('message', raw)!r}\n",
                flush=True,
            )
            return
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message", {})
        content = message.get("content")
        reasoning = message.get("reasoning_content") or ""
        tool_calls = message.get("tool_calls") or []
        print(
            f"\n{'='*60}\n"
            f"[BailianHTTP← stream] status={status}  latency={latency_ms:.0f}ms\n"
            f"  finish_reason    = {choice.get('finish_reason')!r}\n"
            f"  content          = {(str(content)[:300] if content else None)!r}\n"
            f"  reasoning长度    = {len(reasoning)} chars\n"
            f"  tool_calls数量   = {len(tool_calls)}\n"
            f"  tool_calls名称   = {[tc.get('function', {}).get('name') for tc in tool_calls]}\n"
            f"  usage            = {raw.get('usage', {})}\n"
            f"{'='*60}\n",
            flush=True,
        )





    def _build_body(self, request: LLMRequest, model: str) -> dict:


        temperature = request.temperature
        if "kimi" in model.lower():
            temperature = 1.0

        body: dict = {
            "model": model,
            "messages": request.messages,
            "temperature": temperature,
        }

        if request.tools:
            body["tools"] = request.tools



            body["parallel_tool_calls"] = True

        if request.max_tokens:
            body["max_tokens"] = request.max_tokens









        if self._is_qwen3(model):
            enable = request.enable_thinking
            if enable is None:

                enable = True
            body["enable_thinking"] = enable

            if enable:
                budget = request.thinking_budget
                if budget is None:
                    budget = self._default_thinking_budget
                if budget is not None:
                    body["thinking_budget"] = budget


        if request.extra:
            body.update(request.extra)

        return body

    @staticmethod
    def _is_qwen3(model: str) -> bool:

        m = model.lower()
        return "qwen3" in m or "qwen3.5" in m





    def _parse_response(self, raw: dict, status: int) -> LLMResponse:

        choices = raw.get("choices", [])
        if not choices:
            logger.warning("bailian_empty_choices", raw_keys=list(raw.keys()))
            return LLMResponse(
                content=None, tool_calls=[], reasoning_content=None,
                reasoning_has_tool_call=False, finish_reason="error",
                model=raw.get("model", ""), usage={},
                raw_http_status=status, raw_body=raw,
            )

        choice = choices[0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "")


        content: str | None = message.get("content") or None

        if content == "":
            content = None


        tool_calls: list[ToolCall] = []
        raw_tool_calls = message.get("tool_calls") or []
        for tc in raw_tool_calls:
            fn = tc.get("function", {})
            tool_calls.append(ToolCall(
                id=tc.get("id", ""),
                name=fn.get("name", ""),
                arguments=fn.get("arguments", "{}"),
            ))


        reasoning: str | None = message.get("reasoning_content") or None





        reasoning_has_tool_call = bool(
            reasoning
            and not tool_calls
            and not content
            and "<tool_call>" in reasoning
        )
        if reasoning_has_tool_call:
            logger.debug(
                "qwen3_tool_call_in_reasoning",
                finish_reason=finish_reason,
                reasoning_preview=reasoning[:200] if reasoning else "",
            )


        raw_usage = raw.get("usage", {})
        prompt_tokens = int(raw_usage.get("prompt_tokens", 0) or 0)
        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": raw_usage.get("completion_tokens", 0),
            "total_tokens": raw_usage.get("total_tokens", 0),
        }

        reasoning_tokens = (
            raw_usage.get("reasoning_tokens")
            or (raw_usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
            or 0
        )
        if reasoning_tokens:
            usage["reasoning_tokens"] = reasoning_tokens








        cached_tokens = int(
            (raw_usage.get("prompt_tokens_details") or {}).get("cached_tokens")
            or raw_usage.get("prompt_cache_hit_tokens")
            or raw_usage.get("cached_tokens")
            or 0
        )
        usage["cached_tokens"] = cached_tokens
        if prompt_tokens > 0:
            hit_rate = round(cached_tokens / prompt_tokens * 100, 1)
            usage["cache_hit_rate_pct"] = hit_rate

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            reasoning_content=reasoning,
            reasoning_has_tool_call=reasoning_has_tool_call,
            finish_reason=finish_reason,
            model=raw.get("model", ""),
            usage=usage,
            raw_http_status=status,
            raw_body=raw,
        )





    @staticmethod
    def _log_request(body: dict) -> None:

        msgs = body.get("messages", [])
        tools = body.get("tools", [])

        think_params = {
            k: body[k] for k in ("enable_thinking", "thinking_budget", "stream") if k in body
        }


        msg_lines = []
        for i, m in enumerate(msgs):
            role = m.get("role", "?")
            content = m.get("content")
            tool_calls = m.get("tool_calls")
            tool_call_id = m.get("tool_call_id", "")

            if tool_calls:
                names = [tc.get("function", {}).get("name") for tc in tool_calls]
                msg_lines.append(f"    [{i}] {role} → tool_calls={names}")
            elif tool_call_id:
                preview = str(content or "")[:150]
                msg_lines.append(f"    [{i}] {role}(result id={tool_call_id!r}) → {preview!r}")
            elif isinstance(content, list):

                seg_lines: list[str] = []
                for j, part in enumerate(content):
                    if not isinstance(part, dict):
                        seg_lines.append(f"        ({j}) ?part={part!r}")
                        continue
                    ptype = part.get("type") or "?"
                    if ptype == "text":
                        txt_preview = (part.get("text") or "")[:200]
                        seg_lines.append(f"        ({j}) text → {txt_preview!r}")
                    elif ptype == "image_url":
                        url = (part.get("image_url") or {}).get("url") or ""
                        if isinstance(url, str) and url.startswith("data:"):
                            head, _, b64 = url.partition(",")
                            seg_lines.append(
                                f"        ({j}) image_url → {head};base64,<{len(b64)} chars>"
                            )
                        else:
                            seg_lines.append(f"        ({j}) image_url → {url[:120]!r}")
                    else:
                        seg_lines.append(f"        ({j}) {ptype} → {str(part)[:120]!r}")
                msg_lines.append(
                    f"    [{i}] {role} [多模态] ({len(content)} 段)\n" + "\n".join(seg_lines)
                )
            else:
                preview = str(content or "")[:200]
                msg_lines.append(f"    [{i}] {role} → {preview!r}")


        tool_names = [t.get("function", {}).get("name") for t in tools]

        print(
            f"\n{'='*60}\n"
            f"[BailianHTTP→] POST {_CHAT_ENDPOINT}\n"
            f"  model          = {body.get('model')!r}\n"
            f"  temperature    = {body.get('temperature')}\n"
            f"  max_tokens     = {body.get('max_tokens')}\n"
            f"  think/stream   = {think_params}\n"
            f"  tools          = {tool_names}\n"
            f"  messages({len(msgs)}条)：\n"
            + "\n".join(msg_lines) + "\n"
            f"{'='*60}\n",
            flush=True,
        )

    @staticmethod
    def _log_response(resp: httpx.Response, latency_ms: float) -> dict:


        try:
            raw = resp.json()
        except Exception:
            raw = {}
            print(
                f"\n[BailianHTTP←] status={resp.status_code} latency={latency_ms:.0f}ms\n"
                f"  [错误] 响应 body 无法解析为 JSON，原始内容：\n"
                f"  {resp.text[:500]!r}\n",
                flush=True,
            )
            return raw


        def _truncate_reasoning(obj: object, max_len: int = 1000) -> object:

            if isinstance(obj, dict):
                result = {}
                for k, v in obj.items():
                    if k == "reasoning_content" and isinstance(v, str) and len(v) > max_len:
                        result[k] = v[:max_len] + f"... [截断，完整长度={len(v)}]"
                    else:
                        result[k] = _truncate_reasoning(v, max_len)
                return result
            if isinstance(obj, list):
                return [_truncate_reasoning(i, max_len) for i in obj]
            return obj

        raw_for_print = _truncate_reasoning(raw)
        raw_json_str = json.dumps(raw_for_print, ensure_ascii=False, indent=2)


        choices = raw.get("choices", [{}])
        choice = choices[0] if choices else {}
        message = choice.get("message", {})
        raw_usage = raw.get("usage", {})

        content = message.get("content")
        reasoning = message.get("reasoning_content") or ""
        tool_calls = message.get("tool_calls") or []
        finish_reason = choice.get("finish_reason")


        print(
            f"\n{'='*60}\n"
            f"[BailianHTTP←] status={resp.status_code}  latency={latency_ms:.0f}ms\n"
            f"  Headers: request-id={resp.headers.get('x-request-id', 'N/A')!r}\n"
            f"{'─'*60}\n"
            f"  【摘要】\n"
            f"  finish_reason    = {finish_reason!r}\n"
            f"  content          = {(str(content)[:300] if content else None)!r}\n"
            f"  tool_calls数量   = {len(tool_calls)}\n"
            f"  tool_calls名称   = {[tc.get('function',{}).get('name') for tc in tool_calls]}\n"
            f"  reasoning长度    = {len(reasoning)} chars\n"
            f"  usage            = {raw_usage}\n"
            f"{'─'*60}\n"
            f"  【完整原始 JSON body】\n"
            f"{raw_json_str}\n"
            f"{'='*60}\n",
            flush=True,
        )


        if reasoning and "<tool_call>" in reasoning and not tool_calls and not content:
            print(
                f"  [Qwen3 训练缺陷]\n"
                f"  reasoning 含 <tool_call> 但 content=None, tool_calls=[]\n"
                f"  finish_reason={finish_reason!r}\n"
                f"  reasoning 中的工具调用片段预览：\n"
                f"  {reasoning[reasoning.index('<tool_call>'):reasoning.index('<tool_call>')+300]!r}\n"
                f"  → agent 将发送纠偏指令让模型重新执行工具调用\n",
                flush=True,
            )

        return raw

    async def aclose(self):

        await self._http.aclose()

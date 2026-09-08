

import time

import httpx
import structlog
from openai import AsyncOpenAI
from urllib.parse import urlparse

from cancer_claw.config import settings
from cancer_claw.services.models.bailian import BailianClient
from cancer_claw.services.models.schemas import LLMRequest
from cancer_claw.services.model_router.schema import ChatRequest, ChatResponse, ProviderStatus
from cancer_claw.services.privacy.desensitizer import desensitize_messages

logger = structlog.get_logger()

_BAILIAN_PROVIDER_IDS = {"qwen", "bailian", "dashscope"}

class ProviderError(Exception):

    def __init__(self, provider_id: str, message: str):
        self.provider_id = provider_id
        super().__init__(f"[{provider_id}] {message}")

class ModelProvider:


    def __init__(self, provider_id: str, name: str, base_url: str, api_key: str,
                 models: list[dict], enabled: bool = True, priority: int = 0):
        self.id = provider_id
        self.name = name
        self.base_url = base_url
        self.api_key = api_key
        self.models = models
        self.enabled = enabled
        self.priority = priority

        self._total_calls = 0
        self._total_errors = 0
        self._total_latency_ms = 0.0


        if provider_id in _BAILIAN_PROVIDER_IDS:

            self._bailian = BailianClient(
                api_key=api_key if api_key else "",
                default_thinking_budget=4096,
            )
            self._openai_client = None
            logger.info("provider_using_bailian_client", provider=provider_id)
        else:

            self._bailian = None
            # 大任务（尤其 GLM-5.3 强制思考）可能跑数分钟。原先 180s + max_retries=5
            # 会在网关掐线后连着重试，最终只剩 Connection error。
            self._http_timeout = httpx.Timeout(
                connect=30.0, read=600.0, write=120.0, pool=30.0
            )
            self._http_client = httpx.AsyncClient(
                base_url=base_url,
                timeout=self._http_timeout,
                trust_env=not self._is_local_base_url(),
            )
            self._openai_client = AsyncOpenAI(
                base_url=base_url,
                api_key=api_key if api_key else "sk-placeholder",
                http_client=self._http_client,
                max_retries=1,
            )
            logger.info("provider_using_openai_client", provider=provider_id)

    def get_model_for_role(self, role: str) -> str | None:

        for m in self.models:
            if m.get("role") == role:
                return m["id"]
        for m in self.models:
            if m.get("role") == "general":
                return m["id"]
        return self.models[0]["id"] if self.models else None

    def has_vision_model(self) -> bool:

        return any(m.get("role") == "vision" for m in self.models)

    def get_vision_model(self) -> str | None:

        for m in self.models:
            if m.get("role") == "vision":
                return m["id"]
        return None

    async def chat(self, request: ChatRequest) -> ChatResponse:

        model_id = request.model_override
        _selected_via = "model_override" if model_id else None
        if not model_id and request.requires_vision:
            model_id = self.get_vision_model()
            if model_id:
                _selected_via = "vision_role"
        if not model_id:
            model_id = self.get_model_for_role(request.task_type)
            if model_id:
                _selected_via = f"task_type:{request.task_type}"
        if not model_id:
            raise ProviderError(self.id, "没有可用的模型")

        if settings.privacy.enabled and settings.privacy.desensitize_before_llm:
            request = request.model_copy(
                update={
                    "messages": desensitize_messages(
                        request.messages, context=f"llm:{self.id}"
                    )
                }
            )




        if request.requires_vision:
            logger.info(
                "vision_request_routed",
                provider=self.id,
                selected_model=model_id,
                selected_via=_selected_via,
            )
            print(
                f"[Provider:{self.id}] vision 请求 → 模型 {model_id}（{_selected_via}）",
                flush=True,
            )

        start = time.monotonic()
        try:
            if self._bailian is not None:
                response = await self._chat_bailian(request, model_id)
            else:
                response = await self._chat_openai(request, model_id)

            latency = (time.monotonic() - start) * 1000
            self._total_calls += 1
            self._total_latency_ms += latency

            logger.info(
                "model_call_success",
                model=model_id,
                provider=self.id,
                tokens=response.usage.get("total_tokens", 0),
            )
            return response

        except ProviderError:
            self._total_calls += 1
            self._total_errors += 1
            raise
        except Exception as e:
            self._total_calls += 1
            self._total_errors += 1
            logger.error("model_call_failed", provider=self.id, model=model_id, error=str(e))
            raise ProviderError(self.id, str(e)) from e





    @staticmethod
    def _normalize_vision_messages(messages: list[dict]) -> list[dict]:

        return messages





    async def _chat_bailian(self, request: ChatRequest, model_id: str) -> ChatResponse:

        from cancer_claw.services.models.base import LLMClientError

        messages = self._normalize_vision_messages(request.messages)

        llm_req = LLMRequest(
            messages=messages,
            model=model_id,
            tools=request.tools,
            temperature=request.temperature,
            max_tokens=request.max_tokens,



        )

        try:
            llm_resp = await self._bailian.chat(llm_req)
        except LLMClientError as e:
            raise ProviderError(self.id, str(e)) from e


        tool_calls_dict = None
        if llm_resp.tool_calls:
            tool_calls_dict = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    },
                }
                for tc in llm_resp.tool_calls
            ]

        return ChatResponse(
            content=llm_resp.content,
            tool_calls=tool_calls_dict,
            model=llm_resp.model or model_id,
            provider=self.id,
            usage=llm_resp.usage,
            finish_reason=llm_resp.finish_reason,
            reasoning_content=llm_resp.reasoning_content,
            reasoning_has_tool_call=llm_resp.reasoning_has_tool_call,
        )





    @staticmethod
    def _is_claude(model: str) -> bool:

        return "claude" in model.lower()

    def _is_zhipu(self, model_id: str) -> bool:
        blob = f"{self.id} {self.base_url} {model_id}".lower()
        return any(k in blob for k in ("bigmodel.cn", "zhipu", "glm-", "质谱", "智谱"))

    def _glm_extra_body(self, model_id: str) -> dict | None:
        """GLM-5.3 默认 reasoning_effort=max 且不能关思考，非流式长连接极易被网关掐掉。"""
        mid = (model_id or "").lower()
        if not self._is_zhipu(model_id):
            return None
        if mid.startswith("glm-5.3") or mid == "glm-5.3":
            return {
                "thinking": {"type": "enabled"},
                "reasoning_effort": "low",
            }
        return None

    def _is_local_base_url(self) -> bool:
        try:
            parsed = urlparse(self.base_url)
            return parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        except ValueError:
            return False

    @staticmethod
    def _is_connection_error(exc: BaseException) -> bool:
        name = type(exc).__name__
        text = str(exc).lower()
        if name in {"APIConnectionError", "APITimeoutError", "ConnectError", "ReadTimeout", "ConnectTimeout", "RemoteProtocolError"}:
            return True
        return any(
            s in text
            for s in (
                "connection error",
                "timed out",
                "timeout",
                "connection reset",
                "server disconnected",
                "peer closed",
                "remote protocol",
            )
        )

    @staticmethod
    def _inject_claude_cache_control(
        messages: list[dict], tools: list[dict] | None
    ) -> tuple[list[dict], list[dict] | None]:

        import copy

        patched_messages: list[dict] = []
        for msg in messages:
            if msg.get("role") == "system" and isinstance(msg.get("content"), str):

                patched_messages.append({
                    **msg,
                    "content": [
                        {
                            "type": "text",
                            "text": msg["content"],
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                })
            else:
                patched_messages.append(msg)

        patched_tools: list[dict] | None = None
        if tools:
            patched_tools = copy.deepcopy(tools)

            if patched_tools:
                last = patched_tools[-1]
                last.setdefault("cache_control", {"type": "ephemeral"})

        return patched_messages, patched_tools

    async def _chat_openai(self, request: ChatRequest, model_id: str) -> ChatResponse:

        import time as _time

        messages = self._normalize_vision_messages(request.messages)
        tools = request.tools

        if self._is_claude(model_id):
            messages, tools = self._inject_claude_cache_control(messages, tools)

        temperature = request.temperature
        if "kimi" in model_id.lower():
            temperature = 1.0

        kwargs: dict = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        extra_body = self._glm_extra_body(model_id)
        if extra_body:
            kwargs["extra_body"] = extra_body
        if tools:
            kwargs["tools"] = tools
            kwargs["parallel_tool_calls"] = True
        if request.max_tokens:
            kwargs["max_tokens"] = request.max_tokens

        self._log_openai_request(kwargs, model_id)

        _t0 = _time.monotonic()
        response = await self._create_openai_resilient(kwargs)
        latency_ms = (_time.monotonic() - _t0) * 1000

        choice = response.choices[0]
        message = choice.message

        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            cached = 0
            if response.usage.prompt_tokens_details:
                cached = getattr(response.usage.prompt_tokens_details, "cached_tokens", 0) or 0
            if not cached:
                cached = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            if not cached:
                cached = getattr(response.usage, "prompt_cache_hit_tokens", 0) or 0
            usage["cached_tokens"] = cached
            if usage["prompt_tokens"] > 0:
                usage["cache_hit_rate_pct"] = round(cached / usage["prompt_tokens"] * 100, 1)

        self._log_openai_response(response, choice, message, tool_calls, usage, latency_ms)

        reasoning_content = getattr(message, "reasoning_content", None)

        return ChatResponse(
            content=message.content,
            tool_calls=tool_calls,
            model=response.model,
            provider=self.id,
            usage=usage,
            finish_reason=choice.finish_reason or "",
            reasoning_content=reasoning_content,
        )

    async def _create_openai_resilient(self, kwargs: dict):
        import asyncio

        from openai import APIStatusError

        last_exc: BaseException | None = None
        use_stream = True
        use_extra = "extra_body" in kwargs

        for attempt in range(3):
            call_kwargs = dict(kwargs)
            if not use_stream:
                call_kwargs.pop("stream", None)
            if not use_extra:
                call_kwargs.pop("extra_body", None)
            try:
                if call_kwargs.get("stream"):
                    try:
                        call_kwargs["stream_options"] = {"include_usage": True}
                        stream = await self._openai_client.chat.completions.create(**call_kwargs)
                    except APIStatusError as stream_error:
                        if getattr(stream_error, "status_code", None) != 400:
                            raise
                        call_kwargs.pop("stream_options", None)
                        stream = await self._openai_client.chat.completions.create(**call_kwargs)
                    return await self._consume_openai_stream(stream, call_kwargs["model"])
                return await self._openai_client.chat.completions.create(**call_kwargs)
            except APIStatusError as e:
                last_exc = e
                code = getattr(e, "status_code", None)
                if code == 400 and use_extra:
                    logger.warning(
                        "openai_extra_body_rejected",
                        provider=self.id,
                        error=str(e),
                    )
                    use_extra = False
                    continue
                if code == 400 and use_stream:
                    logger.warning(
                        "openai_stream_rejected",
                        provider=self.id,
                        error=str(e),
                    )
                    use_stream = False
                    continue
                if code in {502, 503, 504} and self._is_local_base_url():
                    logger.warning(
                        "openai_local_transient_retry",
                        provider=self.id,
                        attempt=attempt + 1,
                        status_code=code,
                        body=str(getattr(e, "body", "") or "")[:300],
                    )
                    if attempt >= 2:
                        raise
                    await asyncio.sleep(0.8 * (attempt + 1))
                    continue
                raise
            except Exception as e:
                last_exc = e
                if not self._is_connection_error(e):
                    raise
                logger.warning(
                    "openai_connection_retry",
                    provider=self.id,
                    attempt=attempt + 1,
                    error=str(e),
                    stream=use_stream,
                )
                if attempt >= 2:
                    break
                if attempt == 1:
                    use_stream = False
                await asyncio.sleep(1.2 * (attempt + 1))

        assert last_exc is not None
        raise last_exc

    async def _consume_openai_stream(self, stream, fallback_model: str):
        from types import SimpleNamespace

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_acc: dict[int, dict[str, str]] = {}
        finish_reason = ""
        model = fallback_model
        usage_obj = None

        async for chunk in stream:
            if getattr(chunk, "model", None):
                model = chunk.model
            if getattr(chunk, "usage", None):
                usage_obj = chunk.usage
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            choice = choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = choice.delta
            if delta is None:
                continue
            if delta.content:
                content_parts.append(delta.content)
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                reasoning_parts.append(rc)
            for tc in delta.tool_calls or []:
                idx = int(tc.index) if tc.index is not None else 0
                rec = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    rec["id"] = tc.id
                fn = tc.function
                if fn is None:
                    continue
                if fn.name:
                    rec["name"] += fn.name
                if fn.arguments:
                    rec["arguments"] += fn.arguments

        tool_calls = None
        if tool_acc:
            tool_calls = []
            for idx in sorted(tool_acc):
                rec = tool_acc[idx]
                tool_calls.append(
                    SimpleNamespace(
                        id=rec["id"] or f"call_{idx}",
                        function=SimpleNamespace(
                            name=rec["name"],
                            arguments=rec["arguments"],
                        ),
                    )
                )

        message = SimpleNamespace(
            content="".join(content_parts) or None,
            tool_calls=tool_calls,
            reasoning_content="".join(reasoning_parts) or None,
        )
        choice = SimpleNamespace(message=message, finish_reason=finish_reason or "stop")
        return SimpleNamespace(choices=[choice], model=model, usage=usage_obj)

    def _log_openai_request(self, kwargs: dict, model_id: str) -> None:

        msgs = kwargs.get("messages", [])
        tools = kwargs.get("tools") or []
        tool_names = [t.get("function", {}).get("name") for t in tools]

        msg_lines = []
        for i, m in enumerate(msgs):
            role = m.get("role", "?")
            content = m.get("content") or ""
            tool_calls = m.get("tool_calls")
            tool_call_id = m.get("tool_call_id", "")
            if tool_calls:
                names = [tc.get("function", {}).get("name") for tc in tool_calls]
                msg_lines.append(f"    [{i}] {role} → tool_calls={names}")
            elif tool_call_id:
                msg_lines.append(f"    [{i}] {role}(result id={tool_call_id!r}) → {str(content)[:150]!r}")
            else:
                msg_lines.append(f"    [{i}] {role} → {str(content)[:200]!r}")

        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        extra = kwargs.get("extra_body") or {}
        print(
            f"\n{'='*60}\n"
            f"[OpenAIHTTP→] POST {endpoint}\n"
            f"  provider       = {self.id!r}\n"
            f"  model          = {model_id!r}\n"
            f"  stream         = {kwargs.get('stream')}\n"
            f"  temperature    = {kwargs.get('temperature')}\n"
            f"  max_tokens     = {kwargs.get('max_tokens')}\n"
            f"  extra_body     = {extra or None}\n"
            f"  tools          = {tool_names}\n"
            f"  messages({len(msgs)}条)：\n"
            + "\n".join(msg_lines) + "\n"
            f"{'='*60}\n",
            flush=True,
        )

    @staticmethod
    def _log_openai_response(response, choice, message, tool_calls, usage: dict, latency_ms: float) -> None:

        content = message.content
        finish_reason = choice.finish_reason
        tool_call_names = [tc["function"]["name"] for tc in (tool_calls or [])]

        print(
            f"\n{'='*60}\n"
            f"[OpenAIHTTP←] status=200  latency={latency_ms:.0f}ms\n"
            f"{'─'*60}\n"
            f"  【摘要】\n"
            f"  finish_reason    = {finish_reason!r}\n"
            f"  content          = {(str(content)[:300] if content else None)!r}\n"
            f"  tool_calls数量   = {len(tool_calls or [])}\n"
            f"  tool_calls名称   = {tool_call_names}\n"
            f"  usage            = {usage}\n"
            f"{'='*60}\n",
            flush=True,
        )





    def get_status(self) -> ProviderStatus:
        successful_calls = max(self._total_calls - self._total_errors, 1)
        avg_latency = self._total_latency_ms / successful_calls
        error_rate = self._total_errors / max(self._total_calls, 1)
        return ProviderStatus(
            id=self.id,
            name=self.name,
            enabled=self.enabled,
            healthy=error_rate < 0.5,
            total_calls=self._total_calls,
            total_errors=self._total_errors,
            avg_latency_ms=round(avg_latency, 1),
        )

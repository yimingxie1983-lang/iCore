

import time

import httpx
import structlog
from openai import AsyncOpenAI

from cancer_claw.services.models.bailian import BailianClient
from cancer_claw.services.models.schemas import LLMRequest
from cancer_claw.services.model_router.schema import ChatRequest, ChatResponse, ProviderStatus

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




            self._openai_client = AsyncOpenAI(
                base_url=base_url,
                api_key=api_key if api_key else "sk-placeholder",
                max_retries=5,
                timeout=httpx.Timeout(180.0, connect=15.0),
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

        kwargs = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools





            kwargs["parallel_tool_calls"] = True
        if request.max_tokens:
            kwargs["max_tokens"] = request.max_tokens

        self._log_openai_request(kwargs, model_id)

        _t0 = _time.monotonic()
        response = await self._openai_client.chat.completions.create(**kwargs)
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
        print(
            f"\n{'='*60}\n"
            f"[OpenAIHTTP→] POST {endpoint}\n"
            f"  provider       = {self.id!r}\n"
            f"  model          = {model_id!r}\n"
            f"  temperature    = {kwargs.get('temperature')}\n"
            f"  max_tokens     = {kwargs.get('max_tokens')}\n"
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

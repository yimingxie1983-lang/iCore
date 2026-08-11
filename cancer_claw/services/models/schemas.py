

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ToolCall:

    id: str
    name: str
    arguments: str

@dataclass
class LLMRequest:

    messages: list[dict]
    model: str
    tools: list[dict] | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    thinking_budget: int | None = None
    enable_thinking: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class LLMResponse:

    content: str | None
    tool_calls: list[ToolCall]
    reasoning_content: str | None
    reasoning_has_tool_call: bool
    finish_reason: str
    model: str
    usage: dict[str, int]
    raw_http_status: int = 0
    raw_body: dict = field(default_factory=dict)



    @property
    def has_content(self) -> bool:
        return bool(self.content)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    @property
    def is_empty(self) -> bool:

        return not self.has_content and not self.has_tool_calls

    @property
    def total_tokens(self) -> int:
        return self.usage.get("total_tokens", 0)

    @property
    def reasoning_tokens(self) -> int:
        return self.usage.get("reasoning_tokens", 0)



from pydantic import BaseModel, Field

class ModelConfig(BaseModel):

    id: str
    role: str = "general"
    max_tokens: int = 200000
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0

class ProviderStatus(BaseModel):

    id: str
    name: str
    enabled: bool
    healthy: bool = True
    total_calls: int = 0
    total_errors: int = 0
    avg_latency_ms: float = 0.0

class ChatRequest(BaseModel):

    messages: list[dict]
    tools: list[dict] | None = None
    task_type: str = "general"
    model_override: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    requires_vision: bool = False

class ChatResponse(BaseModel):

    content: str | None = None
    tool_calls: list[dict] | None = None
    model: str = ""
    provider: str = ""
    usage: dict = {}
    finish_reason: str = ""
    reasoning_content: str | None = None
    reasoning_has_tool_call: bool = False

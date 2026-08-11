

from __future__ import annotations
from abc import ABC, abstractmethod
from cancer_claw.services.models.schemas import LLMRequest, LLMResponse

class BaseLLMClient(ABC):


    @abstractmethod
    async def chat(self, request: LLMRequest) -> LLMResponse:

        ...

class LLMClientError(Exception):

    def __init__(self, provider: str, status: int, message: str):
        self.provider = provider
        self.status = status
        super().__init__(f"[{provider}] HTTP {status}: {message}")

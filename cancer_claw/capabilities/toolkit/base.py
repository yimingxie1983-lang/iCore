

from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ToolResult:

    success: bool = True
    output: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0

class BaseTool(ABC):


    @property
    @abstractmethod
    def name(self) -> str:

        ...

    @property
    @abstractmethod
    def description(self) -> str:

        ...

    @abstractmethod
    def get_schema(self) -> dict:

        ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:

        ...

    async def run(self, **kwargs) -> ToolResult:

        start = time.monotonic()
        try:
            result = await self.execute(**kwargs)
            result.duration_ms = (time.monotonic() - start) * 1000
            return result
        except Exception as e:
            duration = (time.monotonic() - start) * 1000

            err_detail = str(e) or repr(e)
            return ToolResult(
                success=False,
                output="",
                error=f"工具 {self.name} 执行失败: {err_detail}\n{traceback.format_exc()}",
                duration_ms=duration,
            )

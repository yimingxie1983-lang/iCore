from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

FEASIBLE_OK = "ok"
FEASIBLE_CPU = "cpu_fallback"
FEASIBLE_TOO_LARGE = "too_large"
VALID_FEASIBILITY = frozenset({FEASIBLE_OK, FEASIBLE_CPU, FEASIBLE_TOO_LARGE})
VALID_DEVICES = frozenset({"cuda", "cpu"})


class DesignData(BaseModel):
    path: str = ""
    n_samples: int = 0
    n_features: int = 0
    format: str = ""
    label_column: str = ""
    attached: list[str] = Field(default_factory=list)


class DesignDoc(BaseModel):
    task_type: str
    model_family: str
    architecture_summary: str
    data: DesignData = Field(default_factory=DesignData)
    metrics: list[str] = Field(default_factory=list)
    device: str = "cpu"
    feasibility: str = FEASIBLE_OK
    feasibility_reason: str = ""
    batch_size: int = 32
    epochs: int = 5
    estimated_minutes: float = 2
    script_path: str = ""
    python_exe: str = ""
    hyperparams: dict[str, Any] = Field(default_factory=dict)

    def can_train(self) -> bool:
        return self.feasibility in {FEASIBLE_OK, FEASIBLE_CPU}

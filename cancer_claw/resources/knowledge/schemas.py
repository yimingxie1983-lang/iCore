

from __future__ import annotations

from enum import Enum

from typing import Any

from pydantic import BaseModel, Field, field_validator

class CertificationStatus(str, Enum):


    UNCERTIFIED = "uncertified"
    CERTIFIED = "certified"

class OriginType(str, Enum):


    BUILTIN = "builtin"
    USER_CREATED = "user_created"
    MODEL_EVOLVED = "model_evolved"
    IMPORTED_SKILL = "imported_skill"

class CraftKind(str, Enum):


    CAPABILITY = "capability"
    PROCEDURE = "procedure"
    EXPERT = "expert"
    PATTERN = "pattern"

class CraftRecord(BaseModel):


    id: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9][-a-zA-Z0-9_.]*$")
    name: str = ""
    description: str = ""
    full_prompt: str = ""
    tags: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    personality: str = ""
    context_budget: int = Field(default=2000, ge=256, le=100000)
    version: int = Field(default=1, ge=1)
    parent_id: str | None = None
    evolution_score: float = Field(default=0.0)
    enabled: bool = True
    certification_status: CertificationStatus = CertificationStatus.UNCERTIFIED
    origin_type: OriginType = OriginType.USER_CREATED
    certified_by: str | None = None
    certified_at: str | None = None


    kind: CraftKind = CraftKind.PROCEDURE
    sealed: bool = False
    activation: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "激活条件，供 craft_search 索引匹配。"
            "约定子键：task_kinds / keywords / file_patterns / context_signals 等。"
        ),
    )
    output_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="输出契约（JSON Schema），summon 完成后可据此校验 worker 产物。",
    )
    failure_policy: str = "skip"
    """
    单 craft 失败时的处理策略。
    取值：
        skip / retry_n:N / degrade_to:<craft_id> / ask_user / escalate_master
    """
    skill_compat: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Claude Skill 兼容映射（import_skill 写入），保留原始 frontmatter 与"
            "工具名映射，便于回溯 / 反向导出。"
        ),
    )
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)

    @field_validator("certification_status", mode="before")
    @classmethod
    def _coerce_cert(cls, v):

        if isinstance(v, str):
            return CertificationStatus(v)
        return v

    @field_validator("origin_type", mode="before")
    @classmethod
    def _coerce_origin(cls, v):

        if isinstance(v, str):
            return OriginType(v)
        return v

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_kind(cls, v):


        if v is None:
            return CraftKind.PROCEDURE
        if isinstance(v, str):
            try:
                return CraftKind(v)
            except ValueError:


                return CraftKind.PROCEDURE
        return v

    @field_validator("failure_policy", mode="before")
    @classmethod
    def _coerce_failure_policy(cls, v):
        if v is None:
            return "skip"
        return str(v)


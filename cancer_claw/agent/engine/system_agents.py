

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class SystemAgentSpec:


    id: str
    name: str
    description: str
    soul_prompt: str
    role: str
    source: str = "system_master"
    internal_only: bool = False

MASTER = SystemAgentSpec(
    id="claw_master",
    name="iCore 主智能体",
    description="框架主智能体，单智能体内核的唯一执行者",
    soul_prompt="master_soul",
    role="orchestrator",
)

SYSTEM_AGENTS: tuple[SystemAgentSpec, ...] = (
    MASTER,
)

SYSTEM_AGENT_IDS: frozenset[str] = frozenset(spec.id for spec in SYSTEM_AGENTS)

MASTER_AGENT_ID: str = MASTER.id

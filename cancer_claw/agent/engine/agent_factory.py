

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog

from cancer_claw.agent.engine.system_agents import MASTER_AGENT_ID

if TYPE_CHECKING:
    from cancer_claw.agent.engine.agent import Agent

logger = structlog.get_logger()

_agent_instances: dict[str, "Agent"] = {}

async def get_or_create_agent(
    agent_id: str | None,
    project_id: str | None = None,
    *,
    parent: "Agent | None" = None,
    event_sink=None,
) -> "Agent":


    from cancer_claw.agent.engine.agent import Agent
    from cancer_claw.db import get_db

    target_id = agent_id or MASTER_AGENT_ID

    if target_id in _agent_instances:
        agent = _agent_instances[target_id]
    else:
        db = await get_db()
        cursor = await db.execute(
            "SELECT id, name, description, soul_path, craft_ids FROM agents WHERE id = ?",
            (target_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise FileNotFoundError(f"agent_id 不存在: {target_id}")

        craft_ids = json.loads(row[4]) if row[4] else []
        agent = Agent(
            agent_id=row[0],
            name=row[1],
            description=row[2],
            soul_path=row[3],
            craft_ids=craft_ids,
        )
        _agent_instances[target_id] = agent
        logger.info("agent_instance_cached", id=target_id)

    if project_id:
        await agent.bind_tool_workspace(project_id)



    if parent is not None and agent._working_memory is not None:
        cross_ids = [MASTER_AGENT_ID]

        if parent.id != MASTER_AGENT_ID and parent.id not in cross_ids:
            cross_ids.append(parent.id)
        agent._working_memory.cross_agent_ids = cross_ids


    agent._delegator = parent
    agent._event_sink = event_sink

    return agent

def get_cached_agent(agent_id: str) -> "Agent | None":

    return _agent_instances.get(agent_id)

def clear_cache() -> None:

    _agent_instances.clear()

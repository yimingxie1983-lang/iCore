

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cancer_claw.agent.engine.persona import (
    DEFAULT_PERSONA_ID,
    list_personas,
    load_persona,
    persona_exists,
    personas_dir,
)

logger = structlog.get_logger()
router = APIRouter()

class PersonaBrief(BaseModel):

    id: str
    name: str
    description: str
    icon: str = ""
    suggested_tools: list[str] = Field(default_factory=list)

class PersonaDetail(PersonaBrief):

    soul_text: str = ""
    source_path: str | None = None

class PersonaSwitchRequest(BaseModel):
    persona_id: str = Field(..., description="目标人格 id（如 clinician）")

class PersonaSwitchResponse(BaseModel):
    agent_id: str
    from_persona: str | None
    to_persona: str
    name: str
    icon: str = ""
    soul_chars: int = 0

@router.get("/personas", response_model=dict, tags=["人格管理"])
async def api_list_personas() -> dict:

    personas = list_personas()
    return {
        "total": len(personas),
        "default_id": DEFAULT_PERSONA_ID,
        "personas_dir": str(personas_dir()),
        "items": [
            PersonaBrief(
                id=p.id,
                name=p.name,
                description=p.description,
                icon=p.icon,
                suggested_tools=list(p.suggested_tools),
            ).model_dump()
            for p in personas
        ],
    }

@router.get("/personas/{persona_id}", response_model=PersonaDetail, tags=["人格管理"])
async def api_get_persona(persona_id: str) -> PersonaDetail:

    if not persona_exists(persona_id):
        raise HTTPException(status_code=404, detail=f"persona 不存在: {persona_id}")
    try:
        p = load_persona(persona_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"persona 加载失败: {e}") from e

    return PersonaDetail(
        id=p.id,
        name=p.name,
        description=p.description,
        icon=p.icon,
        suggested_tools=list(p.suggested_tools),
        soul_text=p.soul_text,
        source_path=str(p.source_path) if p.source_path else None,
    )

@router.get("/agents/{agent_id}/persona", tags=["人格管理"])
async def api_get_agent_persona(agent_id: str) -> dict:

    from cancer_claw.agent.engine.agent_factory import get_cached_agent

    agent = get_cached_agent(agent_id)
    if agent is None:
        return {"agent_id": agent_id, "persona": None, "cached": False}

    return {
        "agent_id": agent_id,
        "persona": agent.active_persona,
        "cached": True,
    }

@router.post(
    "/agents/{agent_id}/persona",
    response_model=PersonaSwitchResponse,
    tags=["人格管理"],
)
async def api_switch_agent_persona(
    agent_id: str, body: PersonaSwitchRequest
) -> PersonaSwitchResponse:

    if not persona_exists(body.persona_id):
        raise HTTPException(status_code=404, detail=f"persona 不存在: {body.persona_id}")

    from cancer_claw.agent.engine.agent_factory import get_or_create_agent

    try:
        agent = await get_or_create_agent(agent_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"agent 加载失败: {e}") from e




    if not agent._context._system_parts.get("framework"):
        try:
            await agent.initialize()
        except Exception as e:
            logger.warning("agent_initialize_before_swap_failed", agent_id=agent_id, error=str(e))

    from_persona = agent.active_persona_id

    try:
        result = await agent.swap_persona(body.persona_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"persona 切换失败: {e}") from e

    return PersonaSwitchResponse(
        agent_id=agent_id,
        from_persona=from_persona,
        to_persona=result["id"],
        name=result["name"],
        icon=result.get("icon", ""),
        soul_chars=result.get("soul_chars", 0),
    )



import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cancer_claw.config import settings
from cancer_claw.db import get_db
from cancer_claw.resources.prompt_templates import load_prompt

logger = structlog.get_logger()
router = APIRouter()

class AgentCreate(BaseModel):

    name: str = Field(..., min_length=1, max_length=100, description="智能体名称")
    description: str = Field("", max_length=500, description="简短描述")
    soul_content: str | None = Field(None, description="soul.md 内容，不传则使用默认模板")
    craft_ids: list[str] = Field(default_factory=list, description="绑定的 Craft ID 列表")
    source: str = Field("user_created", description="来源：user_created / model_generated / temporary")

class AgentUpdate(BaseModel):

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    craft_ids: list[str] | None = None
    status: str | None = None

class AgentResponse(BaseModel):

    id: str
    name: str
    description: str
    soul_path: str | None
    craft_ids: list[str]
    source: str
    status: str
    created_at: str
    updated_at: str

class AgentListResponse(BaseModel):

    total: int
    items: list[AgentResponse]

class SoulResponse(BaseModel):

    agent_id: str
    agent_name: str
    content: str

class SoulUpdate(BaseModel):

    content: str = Field(..., description="新的 soul.md 内容")

def _row_to_response(row: tuple) -> AgentResponse:

    craft_ids = json.loads(row[4]) if row[4] else []
    return AgentResponse(
        id=row[0], name=row[1], description=row[2],
        soul_path=row[3], craft_ids=craft_ids,
        source=row[5], status=row[6],
        created_at=row[7], updated_at=row[8],
    )

def _generate_default_soul(name: str, description: str) -> str:

    desc = (description or "一个专项执行者。").strip()
    return (
        f"---\n"
        f"name: {name}\n"
        f"---\n\n"
        f"## 你是谁\n\n"
        f"你是 `{name}`。{desc}\n\n"
        f"## 行为准则\n\n"
        f"- 接到任务先理解清楚再动手；有歧义先向用户提问。\n"
        f"- 改完立刻跑；用真实的运行结果（shell 输出 / 报错 / 测试）来纠偏。\n"
        f"- 任务真正完成且验证通过后调 `attempt_completion(result=...)` 退出。\n"
    )

@router.post("/agents", response_model=AgentResponse, status_code=201)
async def create_agent(body: AgentCreate):

    agent_id = uuid.uuid4().hex[:12]
    agents_dir = Path(settings.paths.agents_dir)


    agent_dir = agents_dir / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "private_memory").mkdir(exist_ok=True)


    soul_path = str(agent_dir / "soul.md")
    soul_content = body.soul_content or _generate_default_soul(body.name, body.description)
    (agent_dir / "soul.md").write_text(soul_content, encoding="utf-8")


    now = datetime.now(timezone.utc).isoformat()
    craft_ids_json = json.dumps(body.craft_ids)
    db = await get_db()
    await db.execute(
        """INSERT INTO agents (id, name, description, soul_path, craft_ids, source, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'idle', ?, ?)""",
        (agent_id, body.name, body.description, soul_path, craft_ids_json, body.source, now, now),
    )
    await db.commit()

    logger.info("agent_created", id=agent_id, name=body.name, source=body.source)

    return AgentResponse(
        id=agent_id, name=body.name, description=body.description,
        soul_path=soul_path, craft_ids=body.craft_ids,
        source=body.source, status="idle",
        created_at=now, updated_at=now,
    )

@router.get("/agents", response_model=AgentListResponse)
async def list_agents():

    db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, description, soul_path, craft_ids, source, status, created_at, updated_at "
        "FROM agents ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    items = [_row_to_response(row) for row in rows]
    return AgentListResponse(total=len(items), items=items)

@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str):

    db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, description, soul_path, craft_ids, source, status, created_at, updated_at "
        "FROM agents WHERE id = ?",
        (agent_id,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")
    return _row_to_response(row)

@router.patch("/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: str, body: AgentUpdate):

    db = await get_db()

    cursor = await db.execute("SELECT id FROM agents WHERE id = ?", (agent_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

    updates = []
    params = []
    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name)
    if body.description is not None:
        updates.append("description = ?")
        params.append(body.description)
    if body.craft_ids is not None:
        updates.append("craft_ids = ?")
        params.append(json.dumps(body.craft_ids))
    if body.status is not None:
        updates.append("status = ?")
        params.append(body.status)

    if not updates:
        raise HTTPException(status_code=400, detail="没有提供要更新的字段")

    now = datetime.now(timezone.utc).isoformat()
    updates.append("updated_at = ?")
    params.append(now)
    params.append(agent_id)

    await db.execute(f"UPDATE agents SET {', '.join(updates)} WHERE id = ?", params)
    await db.commit()

    return await get_agent(agent_id)

@router.delete("/agents/{agent_id}", status_code=204)
async def delete_agent(agent_id: str):

    db = await get_db()

    cursor = await db.execute("SELECT id FROM agents WHERE id = ?", (agent_id,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

    await db.execute("DELETE FROM project_teams WHERE agent_id = ?", (agent_id,))
    await db.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    await db.commit()

    logger.info("agent_deleted", id=agent_id)

@router.get("/agents/{agent_id}/soul", response_model=SoulResponse)
async def get_soul(agent_id: str):

    db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, soul_path FROM agents WHERE id = ?", (agent_id,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

    soul_path = row[2]
    if not soul_path:
        return SoulResponse(agent_id=row[0], agent_name=row[1], content="(未配置 soul.md)")

    path = Path(soul_path)
    if not path.exists():
        return SoulResponse(agent_id=row[0], agent_name=row[1], content="(soul.md 文件不存在)")

    content = path.read_text(encoding="utf-8")
    return SoulResponse(agent_id=row[0], agent_name=row[1], content=content)

@router.put("/agents/{agent_id}/soul", response_model=SoulResponse)
async def update_soul(agent_id: str, body: SoulUpdate):

    db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, soul_path FROM agents WHERE id = ?", (agent_id,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

    soul_path = row[2]
    if not soul_path:

        agent_dir = Path(settings.paths.agents_dir) / agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)
        soul_path = str(agent_dir / "soul.md")
        await db.execute("UPDATE agents SET soul_path = ? WHERE id = ?", (soul_path, agent_id))
        await db.commit()

    Path(soul_path).write_text(body.content, encoding="utf-8")
    logger.info("soul_updated", agent_id=agent_id)

    return SoulResponse(agent_id=row[0], agent_name=row[1], content=body.content)

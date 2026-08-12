from __future__ import annotations

import structlog

from cancer_claw.db import get_db, transaction

logger = structlog.get_logger()

PROJECT_STATUS_ACTIVE = "active"
PROJECT_STATUS_PAUSED = "paused"
PROJECT_STATUS_FROZEN = "frozen"
VALID_PROJECT_STATUSES = frozenset(
    {PROJECT_STATUS_ACTIVE, PROJECT_STATUS_PAUSED, PROJECT_STATUS_FROZEN}
)


async def get_project_status(project_id: str) -> str | None:
    """返回项目状态；项目不存在时返回 None。"""

    db = await get_db()
    cur = await db.execute(
        "SELECT COALESCE(status, 'active') FROM projects WHERE id = ?",
        (project_id,),
    )
    row = await cur.fetchone()
    return row[0] if row else None


async def set_project_status(
    project_id: str, status: str, by_user: dict
) -> None:
    """更新项目状态并记录变更人。"""

    if status not in VALID_PROJECT_STATUSES:
        raise ValueError(f"invalid project status: {status}")
    db = await get_db()
    await db.execute(
        "UPDATE projects SET status = ?, status_changed_at = CURRENT_TIMESTAMP, "
        "status_changed_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, by_user.get("id"), project_id),
    )
    await db.commit()


async def cancel_project_runs(project_id: str) -> int:
    """取消该项目所有运行中的会话推理，返回成功取消数。"""

    from cancer_claw.agent.engine.session_hub import get_session_hub

    hub = get_session_hub()
    running = await hub.running_session_ids(project_id)
    cancelled = 0
    for sid in running:
        try:
            if await hub.cancel(sid):
                cancelled += 1
        except Exception as e:
            logger.warning(
                "project_cancel_run_failed",
                project_id=project_id,
                session_id=sid,
                error=str(e),
            )
    return cancelled


async def delete_project_full(project_id: str) -> None:
    """级联删除项目相关数据并关闭项目沙箱执行器。"""

    async with transaction() as db:
        await db.execute("DELETE FROM project_members WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM project_access_requests WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM project_teams WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM task_logs WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM plans WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM monitor_events WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM platforms WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM chat_sessions WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM conversation_history WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM agent_events WHERE project_id = ?", (project_id,))
        await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    try:
        from cancer_claw.capabilities.toolkit.executor import close_project_executor

        await close_project_executor(project_id)
    except Exception as e:
        logger.warning("project_sandbox_close_error", id=project_id, error=str(e))

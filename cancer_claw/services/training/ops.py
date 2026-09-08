from __future__ import annotations

import uuid
from typing import Any

import structlog

from cancer_claw.services.training import jobs, repo
from cancer_claw.services.training.designer import compose_design
from cancer_claw.services.training.runtime import probe_runtime
from cancer_claw.services.training.schema import FEASIBLE_TOO_LARGE

logger = structlog.get_logger()


class TrainOpError(Exception):
    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def public_run(
    run: dict[str, Any],
    *,
    artifacts: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "id": run.get("id"),
        "project_id": run.get("project_id"),
        "brief": run.get("brief") or "",
        "status": run.get("status"),
        "design": run.get("design"),
        "script_path": run.get("script_path") or "",
        "log_path": run.get("log_path") or "",
        "pid": run.get("pid"),
        "metrics": run.get("metrics"),
        "error": run.get("error") or "",
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "finished_at": run.get("finished_at"),
        "artifacts": artifacts if artifacts is not None else [],
        "kill_on_close": True,
        "progress": run.get("progress")
        or jobs.parse_progress(
            jobs.read_log(run.get("log_path") or "", offset=0, limit=64000)[0],
            run,
        ),
    }


def runtime_info() -> dict[str, Any]:
    return probe_runtime().model_dump()


async def create_run(
    *,
    project_id: str,
    user_id: str,
    brief: str,
    attached_files: list[str] | None = None,
) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:12]
    attached = [p for p in (attached_files or []) if p]
    try:
        design = compose_design(
            project_id=project_id,
            run_id=run_id,
            brief=brief,
            attached_files=attached,
        )
    except Exception as e:
        logger.exception("train_design_failed", project_id=project_id)
        raise TrainOpError(f"生成训练方案失败: {e}", status=500) from e

    error = ""
    if design.feasibility == FEASIBLE_TOO_LARGE:
        error = design.feasibility_reason

    run = await repo.insert_run(
        run_id=run_id,
        project_id=project_id,
        user_id=user_id,
        brief=brief.strip(),
        status="awaiting_confirm",
        design=design.model_dump(),
        python_exe=design.python_exe,
        script_path=design.script_path,
        error=error,
    )
    return public_run(run, artifacts=jobs.list_artifacts(project_id, run_id))


async def list_runs(project_id: str, *, limit: int = 30) -> list[dict[str, Any]]:
    items = await repo.list_runs(project_id, limit=limit)
    public: list[dict[str, Any]] = []
    for raw in items:
        run = raw
        if raw.get("status") == "running":
            run = await jobs.refresh_run(project_id, str(raw.get("id") or "")) or raw
        public.append(public_run(run))
    return public


async def get_run(project_id: str, run_id: str) -> dict[str, Any]:
    run = await jobs.refresh_run(project_id, run_id)
    if run is None:
        raise TrainOpError("训练任务不存在", status=404)
    return public_run(run, artifacts=jobs.list_artifacts(project_id, run_id))


async def pick_run(project_id: str, run_id: str = "") -> dict[str, Any]:
    rid = (run_id or "").strip()
    if rid:
        return await get_run(project_id, rid)
    items = await list_runs(project_id, limit=30)
    if not items:
        raise TrainOpError("当前项目还没有训练任务", status=404)
    running = next((item for item in items if item.get("status") == "running"), None)
    waiting = next(
        (item for item in items if item.get("status") == "awaiting_confirm"), None
    )
    return running or waiting or items[0]


async def pick_run_for_confirm(project_id: str, run_id: str = "") -> dict[str, Any]:
    rid = (run_id or "").strip()
    if rid:
        return await get_run(project_id, rid)
    items = await list_runs(project_id, limit=30)
    if not items:
        raise TrainOpError("当前项目还没有训练任务", status=404)
    waiting = next(
        (item for item in items if item.get("status") == "awaiting_confirm"), None
    )
    retry = next(
        (item for item in items if item.get("status") in {"failed", "cancelled"}),
        None,
    )
    return waiting or retry or items[0]


async def confirm_run(project_id: str, run_id: str) -> dict[str, Any]:
    run = await jobs.refresh_run(project_id, run_id)
    if run is None:
        raise TrainOpError("训练任务不存在", status=404)
    if run.get("status") == "running":
        return public_run(run, artifacts=jobs.list_artifacts(project_id, run_id))
    if run.get("status") not in {"awaiting_confirm", "failed", "cancelled"}:
        raise TrainOpError(f"当前状态不可开训: {run.get('status')}", status=409)
    design = run.get("design") or {}
    if design.get("feasibility") == FEASIBLE_TOO_LARGE:
        raise TrainOpError(
            design.get("feasibility_reason") or "方案不可在本机训练",
            status=400,
        )
    if (design.get("device") or "").lower() == "cuda" and not probe_runtime().cuda_available:
        raise TrainOpError(
            "方案需要 CUDA。请先运行 powershell -File ops/setup_train_env.ps1。",
            status=400,
        )
    try:
        run = await jobs.start_run(project_id, run)
    except ValueError as e:
        raise TrainOpError(str(e), status=400) from e
    except FileNotFoundError as e:
        raise TrainOpError(str(e), status=400) from e
    except Exception as e:
        logger.exception("train_start_failed", run_id=run_id)
        await repo.update_run(project_id, run_id, status="failed", error=str(e))
        raise TrainOpError(f"启动训练失败: {e}", status=500) from e
    return public_run(run, artifacts=jobs.list_artifacts(project_id, run_id))


async def cancel_run(project_id: str, run_id: str) -> dict[str, Any]:
    run = await repo.get_run(project_id, run_id)
    if run is None:
        raise TrainOpError("训练任务不存在", status=404)
    if run.get("status") != "running":
        run = await repo.update_run(
            project_id, run_id, status="cancelled", error="用户取消"
        )
        return public_run(run or {})
    run = await jobs.cancel_run(project_id, run)
    return public_run(run, artifacts=jobs.list_artifacts(project_id, run_id))


def read_run_log(
    run: dict[str, Any],
    *,
    offset: int = 0,
    limit: int = 8000,
) -> dict[str, Any]:
    text, next_offset = jobs.read_log(
        run.get("log_path") or "", offset=offset, limit=limit
    )
    return {
        "text": text,
        "next_offset": next_offset,
        "path": run.get("log_path") or "",
    }

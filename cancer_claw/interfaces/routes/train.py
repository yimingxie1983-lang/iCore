from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from cancer_claw.services.identity.deps import (
    get_current_user,
    require_project_read,
    require_project_runnable,
    require_project_write,
)
from cancer_claw.services.training.ops import (
    TrainOpError,
    cancel_run,
    confirm_run,
    create_run,
    get_run,
    list_runs,
    read_run_log,
    runtime_info,
)
from cancer_claw.services.training import repo

router = APIRouter()


class AttachedPath(BaseModel):
    path: str
    name: str = ""


class CreateTrainRunReq(BaseModel):
    brief: str = Field(..., min_length=2, max_length=4000)
    attached_files: list[AttachedPath] = Field(default_factory=list)


class LogResp(BaseModel):
    text: str
    next_offset: int
    path: str = ""


def _http(err: TrainOpError) -> HTTPException:
    return HTTPException(status_code=err.status, detail=str(err))


@router.get("/train/runtime")
async def api_train_runtime(_user: dict = Depends(get_current_user)) -> dict:
    return runtime_info()


@router.post("/projects/{project_id}/train/runs", status_code=201)
async def api_create_train_run(
    project_id: str,
    body: CreateTrainRunReq,
    ctx: dict = Depends(require_project_runnable),
) -> dict:
    user_id = str((ctx.get("user") or {}).get("id") or "")
    attached = [item.path for item in body.attached_files if item.path]
    try:
        return await create_run(
            project_id=project_id,
            user_id=user_id,
            brief=body.brief,
            attached_files=attached,
        )
    except TrainOpError as e:
        raise _http(e) from e


@router.get("/projects/{project_id}/train/runs")
async def api_list_train_runs(
    project_id: str,
    _ctx: dict = Depends(require_project_read),
    limit: int = Query(30, ge=1, le=100),
) -> dict:
    items = await list_runs(project_id, limit=limit)
    return {"total": len(items), "items": items}


@router.get("/projects/{project_id}/train/runs/{run_id}")
async def api_get_train_run(
    project_id: str,
    run_id: str,
    _ctx: dict = Depends(require_project_read),
) -> dict:
    try:
        return await get_run(project_id, run_id)
    except TrainOpError as e:
        raise _http(e) from e


@router.post("/projects/{project_id}/train/runs/{run_id}/confirm")
async def api_confirm_train_run(
    project_id: str,
    run_id: str,
    _ctx: dict = Depends(require_project_runnable),
) -> dict:
    try:
        return await confirm_run(project_id, run_id)
    except TrainOpError as e:
        raise _http(e) from e


@router.post("/projects/{project_id}/train/runs/{run_id}/cancel")
async def api_cancel_train_run(
    project_id: str,
    run_id: str,
    _ctx: dict = Depends(require_project_write),
) -> dict:
    try:
        return await cancel_run(project_id, run_id)
    except TrainOpError as e:
        raise _http(e) from e


@router.get("/projects/{project_id}/train/runs/{run_id}/log")
async def api_train_run_log(
    project_id: str,
    run_id: str,
    _ctx: dict = Depends(require_project_read),
    offset: int = Query(0, ge=0),
    limit: int = Query(8000, ge=256, le=64000),
) -> LogResp:
    run = await repo.get_run(project_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="训练任务不存在")
    chunk = read_run_log(run, offset=offset, limit=limit)
    return LogResp(**chunk)

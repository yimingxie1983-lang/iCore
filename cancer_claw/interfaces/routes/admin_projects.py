from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from cancer_claw.config import settings
from cancer_claw.db import get_db
from cancer_claw.services.credits.pricing import compute_cost_micro_cny, compute_credits
from cancer_claw.services.identity import settings_repo
from cancer_claw.services.identity.deps import require_admin
from cancer_claw.services.projects.service import (
    PROJECT_STATUS_ACTIVE,
    PROJECT_STATUS_FROZEN,
    PROJECT_STATUS_PAUSED,
    VALID_PROJECT_STATUSES,
    cancel_project_runs,
    delete_project_full,
    get_project_status,
    set_project_status,
)

logger = structlog.get_logger()
router = APIRouter()


class AdminProjectItem(BaseModel):
    id: str
    name: str
    description: str = ""
    workspace_path: str = ""
    owner_id: str | None = None
    owner_username: str = ""
    owner_display_name: str = ""
    status: str = "active"
    running: bool = False
    running_sessions: int = 0
    visibility: str = "private"
    created_at: str | None = None
    updated_at: str | None = None


class AdminProjectListResp(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdminProjectItem]


class ProjectStatusResp(BaseModel):
    project_id: str
    status: str
    cancelled_runs: int = 0


class OwnerSlice(BaseModel):
    owner_id: str = ""
    username: str = ""
    display_name: str = ""
    projects: int = 0


class DayCount(BaseModel):
    date: str
    count: int = 0


class CockpitProject(BaseModel):
    id: str
    name: str
    description: str = ""
    owner_username: str = ""
    owner_display_name: str = ""
    status: str = "active"
    visibility: str = "private"
    running: bool = False
    running_sessions: int = 0
    session_count: int = 0
    message_count: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    credits: int = 0
    cost_micro_cny: int = 0
    last_session_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TokenDayCount(BaseModel):
    date: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    credits: int = 0
    cost_micro_cny: int = 0


class TokenHourCount(BaseModel):
    hour: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    credits: int = 0
    cost_micro_cny: int = 0


class TokenModelSlice(BaseModel):
    model: str
    calls: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    credits: int = 0
    cost_micro_cny: int = 0


class TokenStats(BaseModel):
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    fresh_input_tokens: int = 0
    calls: int = 0
    last_7d: int = 0
    last_24h: int = 0
    last_7d_credits: int = 0
    last_7d_cost_micro_cny: int = 0
    last_24h_credits: int = 0
    last_24h_cost_micro_cny: int = 0
    credits: int = 0
    cost_micro_cny: int = 0
    last_14d: list[TokenDayCount] = []
    last_24h_hourly: list[TokenHourCount] = []
    by_model: list[TokenModelSlice] = []


class AdminProjectStatsResp(BaseModel):
    generated_at: str
    totals: dict[str, int]
    by_status: dict[str, int]
    by_visibility: dict[str, int]
    by_owner: list[OwnerSlice] = []
    created_last_14d: list[DayCount] = []
    tokens: TokenStats = TokenStats()
    projects: list[CockpitProject] = []


def _parse_ts(raw: Any) -> datetime | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _validate_date(value: str, label: str) -> None:
    if not value:
        return
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"{label} 必须是 YYYY-MM-DD") from e


def _usage_sql() -> dict[str, str]:
    if settings.database.is_postgres:
        return {
            "input": (
                "COALESCE((NULLIF(ae.payload_json::jsonb ->> 'input_tokens', ''))::bigint, 0)"
            ),
            "cached": (
                "COALESCE((NULLIF(ae.payload_json::jsonb ->> 'cached_input_tokens', ''))::bigint, 0)"
            ),
            "output": (
                "COALESCE((NULLIF(ae.payload_json::jsonb ->> 'output_tokens', ''))::bigint, 0)"
            ),
            "model": (
                "COALESCE(NULLIF(ae.payload_json::jsonb ->> 'model', ''), '未标注')"
            ),
            "day": "to_char(to_timestamp(ae.created_at), 'YYYY-MM-DD')",
            "hour": "(CAST(ae.created_at / 3600 AS INTEGER) * 3600)",
        }
    return {
        "input": "COALESCE(CAST(json_extract(ae.payload_json, '$.input_tokens') AS INTEGER), 0)",
        "cached": (
            "COALESCE(CAST(json_extract(ae.payload_json, '$.cached_input_tokens') AS INTEGER), 0)"
        ),
        "output": "COALESCE(CAST(json_extract(ae.payload_json, '$.output_tokens') AS INTEGER), 0)",
        "model": "COALESCE(NULLIF(json_extract(ae.payload_json, '$.model'), ''), '未标注')",
        "day": "date(ae.created_at, 'unixepoch')",
        "hour": "(CAST(ae.created_at / 3600 AS INTEGER) * 3600)",
    }


def _cost_of(
    model: str,
    inp: int,
    cached: int,
    out: int,
    bill: dict,
) -> tuple[int, int]:
    key = None if not model or model == "未标注" else model
    credits = compute_credits(
        key,
        input_tokens=inp,
        cached_input_tokens=cached,
        output_tokens=out,
        markup=float(bill.get("markup") or 1),
        mode=str(bill.get("mode") or "split"),
        flat_credits_per_1m=float(bill.get("flat_credits_per_1m") or 6900),
        flat_output_credits_per_1m=float(bill.get("flat_output_credits_per_1m") or 27000),
    )
    cost = compute_cost_micro_cny(
        key,
        input_tokens=inp,
        cached_input_tokens=cached,
        output_tokens=out,
    )
    return int(credits), int(cost)


async def _running_by_project() -> dict[str, int]:
    from cancer_claw.agent.engine.session_hub import get_session_hub

    hub = get_session_hub()
    out: dict[str, int] = {}
    for sid in await hub.running_session_ids():
        st = await hub.get_status(sid)
        pid = (st or {}).get("project_id")
        if pid:
            out[pid] = out.get(pid, 0) + 1
    return out


@router.get("/admin/projects", response_model=AdminProjectListResp)
async def admin_list_projects(
    q: str = Query("", max_length=100, description="按项目名称模糊搜索"),
    owner: str = Query("", max_length=40, description="按创建者用户名/显示名模糊搜索"),
    date_from: str = Query("", description="创建日期起，YYYY-MM-DD"),
    date_to: str = Query("", description="创建日期止，YYYY-MM-DD"),
    running: bool | None = Query(None, description="true=运行中 / false=未运行"),
    status: str = Query("", max_length=20, description="active / paused / frozen"),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _admin: dict = Depends(require_admin),
) -> AdminProjectListResp:

    _validate_date(date_from, "date_from")
    _validate_date(date_to, "date_to")
    if status and status not in VALID_PROJECT_STATUSES:
        raise HTTPException(status_code=400, detail="status 必须是 active / paused / frozen")

    where = ["1=1"]
    params: list = []
    if q:
        where.append("p.name LIKE ?")
        params.append(f"%{q}%")
    if owner:
        where.append("(u.username LIKE ? OR u.display_name LIKE ?)")
        params.extend([f"%{owner}%", f"%{owner}%"])
    if date_from:
        where.append("date(p.created_at) >= ?")
        params.append(date_from)
    if date_to:
        where.append("date(p.created_at) <= ?")
        params.append(date_to)
    if status:
        where.append("p.status = ?")
        params.append(status)
    where.append("COALESCE(p.source, 'web') != 'cli_local'")

    db = await get_db()
    cur = await db.execute(
        f"""
        SELECT p.id, p.name, COALESCE(p.description, ''), p.workspace_path,
               p.owner_id, COALESCE(u.username, ''), COALESCE(u.display_name, ''),
               COALESCE(p.status, 'active'), COALESCE(p.visibility, 'private'),
               p.created_at, p.updated_at
        FROM projects p
        LEFT JOIN users u ON u.id = p.owner_id
        WHERE {" AND ".join(where)}
        ORDER BY p.updated_at DESC
        """,
        params,
    )
    rows = await cur.fetchall()

    running_map = await _running_by_project()
    items: list[AdminProjectItem] = []
    for r in rows:
        run_n = running_map.get(r[0], 0)
        if running is True and run_n == 0:
            continue
        if running is False and run_n > 0:
            continue
        items.append(
            AdminProjectItem(
                id=r[0],
                name=r[1],
                description=r[2],
                workspace_path=r[3],
                owner_id=r[4],
                owner_username=r[5],
                owner_display_name=r[6],
                status=r[7],
                visibility=r[8],
                running=run_n > 0,
                running_sessions=run_n,
                created_at=r[9],
                updated_at=r[10],
            )
        )

    total = len(items)
    return AdminProjectListResp(
        total=total,
        limit=limit,
        offset=offset,
        items=items[offset : offset + limit],
    )


@router.get("/admin/projects/stats", response_model=AdminProjectStatsResp)
async def admin_project_stats(
    _admin: dict = Depends(require_admin),
) -> AdminProjectStatsResp:
    db = await get_db()
    cur = await db.execute(
        """
        SELECT p.id, p.name, COALESCE(p.description, ''), p.owner_id,
               COALESCE(u.username, ''), COALESCE(u.display_name, ''),
               COALESCE(p.status, 'active'), COALESCE(p.visibility, 'private'),
               p.created_at, p.updated_at
        FROM projects p
        LEFT JOIN users u ON u.id = p.owner_id
        WHERE COALESCE(p.source, 'web') != 'cli_local'
        ORDER BY p.updated_at DESC
        """
    )
    rows = await cur.fetchall()

    cur = await db.execute(
        """
        SELECT cs.project_id,
               COUNT(*) AS sessions,
               COALESCE(SUM(cs.message_count), 0) AS messages,
               MAX(cs.updated_at) AS last_session_at
        FROM chat_sessions cs
        INNER JOIN projects p ON p.id = cs.project_id
        WHERE COALESCE(p.source, 'web') != 'cli_local'
          AND cs.session_id NOT LIKE '%#%'
          AND COALESCE(cs.agent_id, '') NOT LIKE '%#%'
        GROUP BY cs.project_id
        """
    )
    session_rows = await cur.fetchall()
    session_meta = {
        r[0]: {
            "sessions": int(r[1] or 0),
            "messages": int(r[2] or 0),
            "last_session_at": r[3],
        }
        for r in session_rows
        if r[0]
    }

    ux = _usage_sql()
    usage_from = """
        FROM agent_events ae
        INNER JOIN projects p ON p.id = ae.project_id
        WHERE ae.type = 'usage'
          AND COALESCE(p.source, 'web') != 'cli_local'
    """
    bill = await settings_repo.get_billing_config()
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    day_ago = now - timedelta(hours=24)
    last_hour = int(now.timestamp() // 3600) * 3600
    hour_keys = [last_hour - 3600 * i for i in range(23, -1, -1)]
    hour_from_ts = hour_keys[0]

    cur = await db.execute(
        f"""
        SELECT ae.project_id, {ux['model']},
               COALESCE(SUM({ux['input']}), 0),
               COALESCE(SUM({ux['cached']}), 0),
               COALESCE(SUM({ux['output']}), 0),
               COUNT(*)
        {usage_from}
        GROUP BY ae.project_id, {ux['model']}
        """
    )
    token_meta: dict[str, dict[str, int]] = {}
    model_acc: dict[str, dict[str, int]] = {}
    tok_in = tok_cached = tok_out = tok_calls = tok_credits = tok_cost = 0
    for r in await cur.fetchall():
        pid = r[0]
        if not pid:
            continue
        model = str(r[1] or "未标注")
        inp, cached, out, n = int(r[2] or 0), int(r[3] or 0), int(r[4] or 0), int(r[5] or 0)
        cr, cost = _cost_of(model, inp, cached, out, bill)
        tok_in += inp
        tok_cached += cached
        tok_out += out
        tok_calls += n
        tok_credits += cr
        tok_cost += cost
        tm = token_meta.setdefault(
            pid,
            {
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "credits": 0,
                "cost_micro_cny": 0,
            },
        )
        tm["input_tokens"] += inp
        tm["cached_input_tokens"] += cached
        tm["output_tokens"] += out
        tm["credits"] += cr
        tm["cost_micro_cny"] += cost
        ma = model_acc.setdefault(
            model,
            {
                "calls": 0,
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "credits": 0,
                "cost_micro_cny": 0,
            },
        )
        ma["calls"] += n
        ma["input_tokens"] += inp
        ma["cached_input_tokens"] += cached
        ma["output_tokens"] += out
        ma["credits"] += cr
        ma["cost_micro_cny"] += cost

    by_model = [
        TokenModelSlice(model=name, **vals)
        for name, vals in sorted(
            model_acc.items(),
            key=lambda kv: kv[1]["input_tokens"] + kv[1]["output_tokens"],
            reverse=True,
        )[:8]
    ]

    cur = await db.execute(
        f"""
        SELECT {ux['day']}, {ux['model']},
               COALESCE(SUM({ux['input']}), 0),
               COALESCE(SUM({ux['cached']}), 0),
               COALESCE(SUM({ux['output']}), 0)
        {usage_from}
        GROUP BY {ux['day']}, {ux['model']}
        """
    )
    token_day_rows: dict[str, dict[str, int]] = {}
    for r in await cur.fetchall():
        if not r[0]:
            continue
        day = str(r[0])
        model = str(r[1] or "未标注")
        inp, cached, out = int(r[2] or 0), int(r[3] or 0), int(r[4] or 0)
        cr, cost = _cost_of(model, inp, cached, out, bill)
        slot = token_day_rows.setdefault(
            day,
            {
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "credits": 0,
                "cost_micro_cny": 0,
            },
        )
        slot["input_tokens"] += inp
        slot["cached_input_tokens"] += cached
        slot["output_tokens"] += out
        slot["credits"] += cr
        slot["cost_micro_cny"] += cost

    cur = await db.execute(
        f"""
        SELECT {ux['hour']}, {ux['model']},
               COALESCE(SUM({ux['input']}), 0),
               COALESCE(SUM({ux['cached']}), 0),
               COALESCE(SUM({ux['output']}), 0)
        {usage_from}
          AND ae.created_at >= ?
        GROUP BY {ux['hour']}, {ux['model']}
        """,
        (hour_from_ts,),
    )
    hour_rows: dict[int, dict[str, int]] = {}
    for r in await cur.fetchall():
        try:
            hk = int(float(r[0] or 0))
        except (TypeError, ValueError):
            continue
        model = str(r[1] or "未标注")
        inp, cached, out = int(r[2] or 0), int(r[3] or 0), int(r[4] or 0)
        cr, cost = _cost_of(model, inp, cached, out, bill)
        slot = hour_rows.setdefault(
            hk,
            {
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "credits": 0,
                "cost_micro_cny": 0,
            },
        )
        slot["input_tokens"] += inp
        slot["cached_input_tokens"] += cached
        slot["output_tokens"] += out
        slot["credits"] += cr
        slot["cost_micro_cny"] += cost

    running_map = await _running_by_project()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_14 = [day_start - timedelta(days=i) for i in range(13, -1, -1)]
    created_buckets: dict[str, int] = {d.date().isoformat(): 0 for d in last_14}

    by_status: Counter[str] = Counter()
    by_visibility: Counter[str] = Counter()
    owner_counter: Counter[str] = Counter()
    owner_label: dict[str, tuple[str, str]] = {}
    cockpit: list[CockpitProject] = []

    created_7d = 0
    created_30d = 0
    active_24h = 0

    for r in rows:
        pid = r[0]
        status = r[6] or "active"
        visibility = r[7] or "private"
        owner_id = r[3] or ""
        username = r[4] or ""
        display_name = r[5] or ""
        created_at = r[8]
        updated_at = r[9]
        by_status[status] += 1
        by_visibility[visibility] += 1
        owner_counter[owner_id] += 1
        owner_label[owner_id] = (username, display_name)

        created_dt = _parse_ts(created_at)
        updated_dt = _parse_ts(updated_at)
        if created_dt:
            if created_dt >= week_ago:
                created_7d += 1
            if created_dt >= month_ago:
                created_30d += 1
            key = created_dt.date().isoformat()
            if key in created_buckets:
                created_buckets[key] += 1
        last_touch = updated_dt or created_dt
        if last_touch and last_touch >= day_ago:
            active_24h += 1

        meta = session_meta.get(pid, {})
        tmeta = token_meta.get(pid, {})
        run_n = running_map.get(pid, 0)
        cockpit.append(
            CockpitProject(
                id=pid,
                name=r[1],
                description=r[2] or "",
                owner_username=username,
                owner_display_name=display_name,
                status=status,
                visibility=visibility,
                running=run_n > 0,
                running_sessions=run_n,
                session_count=int(meta.get("sessions") or 0),
                message_count=int(meta.get("messages") or 0),
                input_tokens=int(tmeta.get("input_tokens") or 0),
                cached_input_tokens=int(tmeta.get("cached_input_tokens") or 0),
                output_tokens=int(tmeta.get("output_tokens") or 0),
                credits=int(tmeta.get("credits") or 0),
                cost_micro_cny=int(tmeta.get("cost_micro_cny") or 0),
                last_session_at=meta.get("last_session_at"),
                created_at=created_at,
                updated_at=updated_at,
            )
        )

    running_projects = sum(1 for p in cockpit if p.running)
    running_sessions = sum(p.running_sessions for p in cockpit)
    session_total = sum(p.session_count for p in cockpit)
    message_total = sum(p.message_count for p in cockpit)

    by_owner = [
        OwnerSlice(
            owner_id=oid,
            username=owner_label.get(oid, ("", ""))[0],
            display_name=owner_label.get(oid, ("", ""))[1],
            projects=n,
        )
        for oid, n in owner_counter.most_common(8)
    ]

    return AdminProjectStatsResp(
        generated_at=now.isoformat(),
        totals={
            "projects": len(cockpit),
            "active": int(by_status.get("active", 0)),
            "paused": int(by_status.get("paused", 0)),
            "frozen": int(by_status.get("frozen", 0)),
            "running_projects": running_projects,
            "running_sessions": running_sessions,
            "sessions": session_total,
            "messages": message_total,
            "owners": len(owner_counter),
            "created_7d": created_7d,
            "created_30d": created_30d,
            "active_24h": active_24h,
        },
        by_status={
            "active": int(by_status.get("active", 0)),
            "paused": int(by_status.get("paused", 0)),
            "frozen": int(by_status.get("frozen", 0)),
        },
        by_visibility=dict(by_visibility),
        by_owner=by_owner,
        created_last_14d=[
            DayCount(date=d, count=created_buckets[d]) for d in created_buckets
        ],
        tokens=TokenStats(
            input_tokens=tok_in,
            cached_input_tokens=tok_cached,
            output_tokens=tok_out,
            total_tokens=tok_in + tok_out,
            fresh_input_tokens=max(0, tok_in - tok_cached),
            calls=tok_calls,
            last_7d=sum(
                (token_day_rows.get(d, {}).get("input_tokens", 0)
                 + token_day_rows.get(d, {}).get("output_tokens", 0))
                for d in created_buckets
                if d >= week_ago.date().isoformat()
            ),
            last_24h=sum(
                hour_rows.get(hk, {}).get("input_tokens", 0)
                + hour_rows.get(hk, {}).get("output_tokens", 0)
                for hk in hour_keys
            ),
            last_7d_credits=sum(
                token_day_rows.get(d, {}).get("credits", 0)
                for d in created_buckets
                if d >= week_ago.date().isoformat()
            ),
            last_7d_cost_micro_cny=sum(
                token_day_rows.get(d, {}).get("cost_micro_cny", 0)
                for d in created_buckets
                if d >= week_ago.date().isoformat()
            ),
            last_24h_credits=sum(hour_rows.get(hk, {}).get("credits", 0) for hk in hour_keys),
            last_24h_cost_micro_cny=sum(
                hour_rows.get(hk, {}).get("cost_micro_cny", 0) for hk in hour_keys
            ),
            credits=tok_credits,
            cost_micro_cny=tok_cost,
            last_14d=[
                TokenDayCount(
                    date=d,
                    input_tokens=token_day_rows.get(d, {}).get("input_tokens", 0),
                    cached_input_tokens=token_day_rows.get(d, {}).get("cached_input_tokens", 0),
                    output_tokens=token_day_rows.get(d, {}).get("output_tokens", 0),
                    credits=token_day_rows.get(d, {}).get("credits", 0),
                    cost_micro_cny=token_day_rows.get(d, {}).get("cost_micro_cny", 0),
                )
                for d in created_buckets
            ],
            last_24h_hourly=[
                TokenHourCount(
                    hour=datetime.fromtimestamp(hk, tz=timezone.utc).strftime(
                        "%Y-%m-%dT%H:00:00Z"
                    ),
                    input_tokens=hour_rows.get(hk, {}).get("input_tokens", 0),
                    cached_input_tokens=hour_rows.get(hk, {}).get("cached_input_tokens", 0),
                    output_tokens=hour_rows.get(hk, {}).get("output_tokens", 0),
                    credits=hour_rows.get(hk, {}).get("credits", 0),
                    cost_micro_cny=hour_rows.get(hk, {}).get("cost_micro_cny", 0),
                )
                for hk in hour_keys
            ],
            by_model=by_model,
        ),
        projects=cockpit,
    )


async def _require_project(project_id: str) -> None:
    if await get_project_status(project_id) is None:
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")


@router.post(
    "/admin/projects/{project_id}/pause",
    response_model=ProjectStatusResp,
)
async def admin_pause_project(
    project_id: str, admin: dict = Depends(require_admin)
) -> ProjectStatusResp:
    await _require_project(project_id)
    cancelled = await cancel_project_runs(project_id)
    await set_project_status(project_id, PROJECT_STATUS_PAUSED, admin)
    logger.info(
        "admin_project_paused",
        project_id=project_id,
        by=admin.get("username"),
        cancelled_runs=cancelled,
    )
    return ProjectStatusResp(
        project_id=project_id,
        status=PROJECT_STATUS_PAUSED,
        cancelled_runs=cancelled,
    )


@router.post(
    "/admin/projects/{project_id}/resume",
    response_model=ProjectStatusResp,
)
async def admin_resume_project(
    project_id: str, admin: dict = Depends(require_admin)
) -> ProjectStatusResp:
    await _require_project(project_id)
    await set_project_status(project_id, PROJECT_STATUS_ACTIVE, admin)
    logger.info(
        "admin_project_resumed",
        project_id=project_id,
        by=admin.get("username"),
    )
    return ProjectStatusResp(project_id=project_id, status=PROJECT_STATUS_ACTIVE)


@router.post(
    "/admin/projects/{project_id}/freeze",
    response_model=ProjectStatusResp,
)
async def admin_freeze_project(
    project_id: str, admin: dict = Depends(require_admin)
) -> ProjectStatusResp:
    await _require_project(project_id)
    cancelled = await cancel_project_runs(project_id)
    await set_project_status(project_id, PROJECT_STATUS_FROZEN, admin)
    logger.info(
        "admin_project_frozen",
        project_id=project_id,
        by=admin.get("username"),
        cancelled_runs=cancelled,
    )
    return ProjectStatusResp(
        project_id=project_id,
        status=PROJECT_STATUS_FROZEN,
        cancelled_runs=cancelled,
    )


@router.post(
    "/admin/projects/{project_id}/unfreeze",
    response_model=ProjectStatusResp,
)
async def admin_unfreeze_project(
    project_id: str, admin: dict = Depends(require_admin)
) -> ProjectStatusResp:
    await _require_project(project_id)
    await set_project_status(project_id, PROJECT_STATUS_ACTIVE, admin)
    logger.info(
        "admin_project_unfrozen",
        project_id=project_id,
        by=admin.get("username"),
    )
    return ProjectStatusResp(project_id=project_id, status=PROJECT_STATUS_ACTIVE)


@router.delete("/admin/projects/{project_id}", status_code=204)
async def admin_delete_project(
    project_id: str, admin: dict = Depends(require_admin)
) -> Response:
    await _require_project(project_id)
    if await get_project_status(project_id) == PROJECT_STATUS_FROZEN:
        raise HTTPException(status_code=403, detail="项目已冻结，请先解冻再删除")
    await cancel_project_runs(project_id)
    await delete_project_full(project_id)
    logger.info(
        "admin_project_deleted",
        project_id=project_id,
        by=admin.get("username"),
    )
    return Response(status_code=204)

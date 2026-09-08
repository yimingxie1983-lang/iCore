

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from cancer_claw.config import settings
from cancer_claw.runtime import bootstrap, shutdown

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):

    await bootstrap(connect_redis=True)
    logger.info(
        "cancer_claw_ready",
        host=settings.app.host,
        port=settings.app.port,
        debug=settings.app.debug,
    )

    yield

    await shutdown()

app = FastAPI(
    title="iCore",
    description="医学 / 科研场景下的 AI 协作框架",
    version=settings.app.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_RATE_SKIP_PREFIXES = ("/api/admin/metrics", "/api/health", "/healthz", "/assets")

@app.middleware("http")
async def _count_requests(request, call_next):
    resp = await call_next(request)
    try:
        path = request.url.path
        if path.startswith("/api") and not path.startswith(_RATE_SKIP_PREFIXES):
            from cancer_claw.interfaces.routes.metrics import record_request
            asyncio.create_task(record_request())
    except Exception:
        pass
    return resp

from cancer_claw.interfaces.routes.projects import router as projects_router
from cancer_claw.interfaces.routes.admin_projects import router as admin_projects_router
from cancer_claw.interfaces.routes.providers import router as providers_router
from cancer_claw.interfaces.routes.agents import router as agents_router
from cancer_claw.interfaces.routes.chat import router as chat_router
from cancer_claw.interfaces.routes.personas import router as personas_router
from cancer_claw.interfaces.routes.skills import router as skills_router
from cancer_claw.interfaces.routes.uploads import router as uploads_router
from cancer_claw.interfaces.routes.sessions import router as sessions_router
from cancer_claw.interfaces.routes.citations import router as citations_router
from cancer_claw.interfaces.routes.files import router as files_router
from cancer_claw.interfaces.routes.auth import router as auth_router
from cancer_claw.interfaces.routes.roles import router as roles_router
from cancer_claw.interfaces.routes.market import router as market_router
from cancer_claw.interfaces.routes.skill_drafts import router as skill_drafts_router
from cancer_claw.interfaces.routes.billing import router as billing_router
from cancer_claw.interfaces.routes.metrics import router as metrics_router
from cancer_claw.interfaces.routes.channels import router as channels_router
from cancer_claw.interfaces.routes.insights import router as insights_router
from cancer_claw.interfaces.routes.train import router as train_router

from cancer_claw.services.identity.deps import get_current_user as _require_login

_login_dep = [Depends(_require_login)]

app.include_router(auth_router, prefix="/api", tags=["鉴权 / 用户"])

app.include_router(roles_router, prefix="/api", tags=["角色 / 权限"])

app.include_router(market_router, prefix="/api", tags=["共享市场"])
app.include_router(projects_router, prefix="/api", tags=["项目管理"])
app.include_router(admin_projects_router, prefix="/api", tags=["项目管理 / 管理员"])
app.include_router(providers_router, prefix="/api", tags=["模型供应商"])
app.include_router(
    agents_router, prefix="/api", tags=["智能体管理"], dependencies=_login_dep
)
app.include_router(chat_router, prefix="/api", tags=["对话"])
app.include_router(
    personas_router, prefix="/api", tags=["人格管理"], dependencies=_login_dep
)
app.include_router(
    skills_router, prefix="/api", tags=["技能库"], dependencies=_login_dep
)

app.include_router(files_router, prefix="/api", tags=["项目文件"])
app.include_router(uploads_router, prefix="/api", tags=["附件"])
app.include_router(sessions_router, prefix="/api", tags=["会话"])
app.include_router(
    citations_router, prefix="/api", tags=["引用核验"], dependencies=_login_dep
)

app.include_router(skill_drafts_router, prefix="/api", tags=["进化审批"])

app.include_router(billing_router, prefix="/api", tags=["计费 / 积分"])

app.include_router(metrics_router, prefix="/api", tags=["系统监控"])
app.include_router(channels_router, prefix="/api", tags=["微信渠道"])
app.include_router(
    insights_router, prefix="/api", tags=["行业资讯"], dependencies=_login_dep
)
app.include_router(train_router, prefix="/api", tags=["模型训练"])

@app.get("/api", tags=["系统"])
async def root():

    return {
        "name": settings.app.name,
        "version": settings.app.version,
        "status": "running",
    }

@app.get("/api/features", tags=["系统"])
async def features(_user: dict = Depends(_require_login)):

    return {
        "project_sharing": bool(settings.features.project_sharing),
    }

@app.get("/healthz", tags=["系统"])
async def healthz():

    return {"status": "ok"}

@app.get("/api/health", tags=["系统"])
async def health():

    from cancer_claw.db import get_db

    components: dict[str, str] = {}
    try:
        db = await get_db()
        await db.execute("SELECT 1")
        components["database"] = "ok"
    except Exception as e:
        components["database"] = f"error: {e}"


    if settings.redis.enabled:
        try:
            from cancer_claw.services.platform.redis_client import get_redis
            r = await get_redis()
            await r.ping()
            components["redis"] = "ok"
        except Exception as e:
            components["redis"] = f"error: {e}"

    bad = [k for k, v in components.items() if v != "ok"]
    return {
        "status": "healthy" if not bad else "degraded",
        "backend": "postgres" if settings.database.is_postgres else "sqlite",
        "multi_worker": settings.redis.enabled,
        "components": components,
    }

_DIST_DIR = (
    Path(os.environ["CANCER_CLAW_FRONTEND_DIST"]).resolve()
    if os.environ.get("CANCER_CLAW_FRONTEND_DIST")
    else Path(__file__).resolve().parent.parent / "web" / "dist"
)

if (_DIST_DIR / "assets").is_dir():

    app.mount("/assets", StaticFiles(directory=_DIST_DIR / "assets"), name="assets")

@app.get("/", include_in_schema=False)
async def index():

    f = _DIST_DIR / "index.html"
    if f.is_file():
        return FileResponse(f)
    return {
        "name": settings.app.name,
        "version": settings.app.version,
        "status": "running",
        "hint": "前端尚未构建（缺 web/dist），访问 /api 查看 API 信息",
    }


# 未知 /api/* 统一 404（避免被下方 SPA GET 通配抢到而返回误导性的 405 Method Not Allowed）
@app.api_route(
    "/api/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def api_not_found(full_path: str):
    raise HTTPException(status_code=404, detail=f"Not Found: /api/{full_path}")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):

    if full_path.startswith("api") or full_path.startswith("web"):
        raise HTTPException(status_code=404, detail="Not Found")

    if _DIST_DIR.is_dir():
        candidate = (_DIST_DIR / full_path).resolve()

        if _DIST_DIR in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        index_file = _DIST_DIR / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)

    raise HTTPException(status_code=404, detail="frontend not built")

_PKG_DIR = Path(__file__).resolve().parent

def _collect_runtime_excluded_dirs() -> list[str]:

    candidates: list[Path] = [
        Path(settings.paths.projects_dir).resolve(),
        Path(settings.paths.data_dir).resolve(),
        Path(settings.paths.agents_dir).resolve(),
        Path(settings.paths.personas_dir).resolve(),

        _PKG_DIR / "resources" / "knowledge" / "playbooks",
        _PKG_DIR / "resources" / "knowledge" / "skill_packs",
        _PKG_DIR / "resources" / "knowledge" / "workflows",
        _PKG_DIR / "resources" / "vault",
    ]
    resolved: list[str] = []
    for p in candidates:
        p.mkdir(parents=True, exist_ok=True)
        resolved.append(str(p))
    return resolved

if __name__ == "__main__":
    import uvicorn

    _kwargs: dict = {
        "host": settings.app.host,
        "port": settings.app.port,

        "log_level": "debug" if settings.app.debug else "info",
    }
    if settings.app.debug:

        _kwargs["reload_dirs"] = [str(_PKG_DIR)]
        _kwargs["reload_excludes"] = _collect_runtime_excluded_dirs()

    uvicorn.run("cancer_claw.app:app", **_kwargs)

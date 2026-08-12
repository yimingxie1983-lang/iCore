

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from cancer_claw.config import settings
from cancer_claw.db import init_db, close_db

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("cancer_claw_starting", version=settings.app.version)

    Path(settings.paths.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.paths.projects_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.paths.agents_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.paths.library_crafts_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.paths.personas_dir).mkdir(parents=True, exist_ok=True)




    try:
        pool_size = int(os.environ.get("CANCER_CLAW_THREADPOOL", "0")) or (
            max(32, (os.cpu_count() or 4) * 8)
        )
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=pool_size,
                                                      thread_name_prefix="cc-io"))
        logger.info("threadpool_configured", max_workers=pool_size)
    except Exception as e:
        logger.warning("threadpool_config_failed", error=str(e))

    await init_db()
    logger.info(
        "database_initialized",
        backend="postgres" if settings.database.is_postgres else "sqlite",
        target=settings.database.url or settings.database.path,
    )


    if settings.redis.enabled:
        try:
            from cancer_claw.services.platform.redis_client import get_redis
            await get_redis()
            logger.info("redis_initialized", url=settings.redis.url)
        except Exception as e:
            logger.error("redis_init_failed", error=str(e), exc_info=True)

    await _ensure_providers_yaml()
    await _ensure_system_agents()
    await _ensure_auth_bootstrap()
    await _ensure_rbac_bootstrap()




    try:
        from cancer_claw.interfaces.routes.skill_drafts import rehydrate_approved_skills
        _n = await rehydrate_approved_skills()
        logger.info("approved_skills_rehydrated", count=_n)
    except Exception as e:
        logger.warning("approved_skills_rehydrate_failed", error=str(e))




    try:
        from cancer_claw.resources.knowledge.craft_store import load_all_crafts
        _recs = await asyncio.to_thread(load_all_crafts)
        logger.info("library_loaded", crafts=len(_recs))
    except Exception as e:
        logger.warning("library_load_failed_at_startup", error=str(e))


    try:
        from cancer_claw.capabilities.toolkit.registry import get_registry
        _registry = get_registry()
        logger.info("tool_registry_warmed_up", count=_registry.count)
    except Exception as e:
        logger.warning("tool_registry_warmup_failed", error=str(e))

    logger.info(
        "cancer_claw_ready",
        host=settings.app.host,
        port=settings.app.port,
        debug=settings.app.debug,
    )

    yield


    try:
        from cancer_claw.capabilities.toolkit.executor import close_all_executors
        await close_all_executors()
    except Exception as e:
        logger.error("sandbox_shutdown_error", error=str(e), exc_info=True)


    if settings.redis.enabled:
        try:
            from cancer_claw.services.platform.redis_client import close_redis
            await close_redis()
        except Exception as e:
            logger.warning("redis_close_error", error=str(e))

    await close_db()
    logger.info("cancer_claw_stopped")

async def _ensure_providers_yaml() -> None:

    initial = [
        {
            "id": pc.id,
            "name": pc.name,
            "base_url": pc.base_url,
            "api_key": pc.api_key,
            "models": [{"id": m.id, "role": m.role} for m in pc.models],
            "enabled": bool(pc.enabled),
            "priority": int(pc.priority),
        }
        for pc in settings.providers
    ]
    from cancer_claw.services.model_router import providers_store
    created = await providers_store.ensure_initialized(initial)
    if created:
        logger.info("providers_yaml_seeded_from_config", count=len(initial))

async def _ensure_auth_bootstrap() -> None:

    from cancer_claw.services.identity import repo
    from cancer_claw.services.identity.deps import get_auth_secret


    get_auth_secret()

    if not settings.auth.enabled:
        logger.info("auth_disabled_local_superuser_mode")
        return

    try:
        if await repo.count_users() > 0:
            return
        username = (settings.auth.bootstrap_admin_username or "").strip()
        password = settings.auth.bootstrap_admin_password or ""
        if not username or not password:
            logger.warning(
                "auth_bootstrap_skipped_no_password",
                hint="设置 CANCER_CLAW_AUTH_BOOTSTRAP_PASSWORD 或开启自助注册（首个用户即管理员）",
            )
            return
        await repo.create_user(
            username=username, password=password, role=repo.ROLE_ADMIN
        )
        logger.info("auth_bootstrap_admin_created", username=username)
    except Exception as e:
        logger.error("auth_bootstrap_failed", error=str(e), exc_info=True)

async def _ensure_rbac_bootstrap() -> None:

    from cancer_claw.services.identity import permissions as perms
    from cancer_claw.services.identity import repo

    try:
        for name, (desc, perm_set) in perms.SYSTEM_ROLE_SEEDS.items():
            existing = await repo.get_role_by_name(name)
            if existing:
                continue
            await repo.create_role(
                name=name,
                description=desc,
                permissions=sorted(perm_set),
                is_system=True,
            )
            logger.info("system_role_seeded", name=name)
    except Exception as e:
        logger.warning("rbac_bootstrap_failed", error=str(e))

async def _ensure_system_agents() -> None:

    from datetime import datetime, timezone

    from cancer_claw.agent.engine.system_agents import SYSTEM_AGENTS
    from cancer_claw.db import get_db
    from cancer_claw.resources.prompt_templates import load_prompt

    db = await get_db()
    agents_dir = Path(settings.paths.agents_dir)
    now = datetime.now(timezone.utc).isoformat()

    for spec in SYSTEM_AGENTS:
        agent_dir = agents_dir / spec.id
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "private_memory").mkdir(exist_ok=True)
        (agent_dir / "memory" / "digests").mkdir(parents=True, exist_ok=True)

        soul_path = agent_dir / "soul.md"
        if not soul_path.is_file():
            soul_content = load_prompt(spec.soul_prompt)
            soul_path.write_text(soul_content, encoding="utf-8")

        cursor = await db.execute("SELECT id FROM agents WHERE id = ?", (spec.id,))
        if await cursor.fetchone():
            continue

        await db.execute(
            """INSERT INTO agents (id, name, description, soul_path, craft_ids,
                                   source, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, '[]', ?, 'idle', ?, ?)""",
            (spec.id, spec.name, spec.description, str(soul_path),
             spec.source, now, now),
        )
        logger.info("system_agent_initialized", id=spec.id, role=spec.role)

    await db.commit()

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

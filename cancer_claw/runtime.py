"""无 HTTP 的运行时启动 / 关闭。Web 服务与本地客户端共用。"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import structlog

from cancer_claw.config import settings
from cancer_claw.db import close_db, init_db

logger = structlog.get_logger()


def ensure_runtime_dirs() -> None:
    Path(settings.paths.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.paths.projects_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.paths.agents_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.paths.library_crafts_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.paths.personas_dir).mkdir(parents=True, exist_ok=True)


def configure_threadpool() -> None:
    try:
        pool_size = int(os.environ.get("CANCER_CLAW_THREADPOOL", "0")) or (
            max(32, (os.cpu_count() or 4) * 8)
        )
        loop = asyncio.get_running_loop()
        loop.set_default_executor(
            ThreadPoolExecutor(max_workers=pool_size, thread_name_prefix="cc-io")
        )
        logger.info("threadpool_configured", max_workers=pool_size)
    except Exception as e:
        logger.warning("threadpool_config_failed", error=str(e))


async def ensure_providers_yaml() -> None:
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


async def ensure_auth_bootstrap() -> None:
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


async def ensure_rbac_bootstrap() -> None:
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

        # 既有角色补发新权限：默认向可见共享市场的角色开放行业资讯
        from cancer_claw.db import get_db

        db = await get_db()
        if settings.database.is_postgres:
            await db.execute(
                "INSERT INTO role_permissions (role_id, perm_key) "
                "SELECT DISTINCT role_id, 'menu.insights' FROM role_permissions rp "
                "WHERE rp.perm_key = 'menu.market' "
                "AND NOT EXISTS ("
                "SELECT 1 FROM role_permissions x "
                "WHERE x.role_id = rp.role_id AND x.perm_key = 'menu.insights')"
            )
        else:
            await db.execute(
                "INSERT OR IGNORE INTO role_permissions (role_id, perm_key) "
                "SELECT DISTINCT role_id, 'menu.insights' FROM role_permissions "
                "WHERE perm_key = 'menu.market'"
            )
        if settings.database.is_postgres:
            await db.execute(
                "INSERT INTO role_permissions (role_id, perm_key) "
                "SELECT DISTINCT role_id, 'menu.train' FROM role_permissions rp "
                "WHERE rp.perm_key = 'menu.chat' "
                "AND NOT EXISTS ("
                "SELECT 1 FROM role_permissions x "
                "WHERE x.role_id = rp.role_id AND x.perm_key = 'menu.train')"
            )
        else:
            await db.execute(
                "INSERT OR IGNORE INTO role_permissions (role_id, perm_key) "
                "SELECT DISTINCT role_id, 'menu.train' FROM role_permissions "
                "WHERE perm_key = 'menu.chat'"
            )
        await db.commit()
    except Exception as e:
        logger.warning("rbac_bootstrap_failed", error=str(e))


async def ensure_system_agents() -> None:
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


async def bootstrap(*, connect_redis: bool = True) -> None:
    logger.info("cancer_claw_starting", version=settings.app.version)
    ensure_runtime_dirs()
    configure_threadpool()

    await init_db()
    logger.info(
        "database_initialized",
        backend="postgres" if settings.database.is_postgres else "sqlite",
        target=settings.database.url or settings.database.path,
    )

    if connect_redis and settings.redis.enabled:
        try:
            from cancer_claw.services.platform.redis_client import get_redis

            await get_redis()
            logger.info("redis_initialized", url=settings.redis.url)
        except Exception as e:
            logger.error("redis_init_failed", error=str(e), exc_info=True)

    await ensure_providers_yaml()
    await ensure_system_agents()
    await ensure_auth_bootstrap()
    await ensure_rbac_bootstrap()

    try:
        from cancer_claw.services.insights.collector import (
            ensure_default_sources,
            start_insights_loop,
        )

        await ensure_default_sources()
        start_insights_loop()
    except Exception as e:
        logger.warning("insights_bootstrap_failed", error=str(e), exc_info=True)

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

    logger.info("cancer_claw_runtime_ready")


async def shutdown() -> None:
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

    try:
        from cancer_claw.services.insights.collector import stop_insights_loop

        await stop_insights_loop()
    except Exception as e:
        logger.warning("insights_loop_stop_error", error=str(e))

    await close_db()
    logger.info("cancer_claw_stopped")

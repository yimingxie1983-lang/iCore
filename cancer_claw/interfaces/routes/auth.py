

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from cancer_claw.services.identity import repo
from cancer_claw.services.identity import settings_repo
from cancer_claw.services.credits import repo as billing_repo
from cancer_claw.services.identity.deps import (
    get_auth_secret,
    get_current_user,
    require_admin,
)
from cancer_claw.services.identity.security import create_access_token, verify_password
from cancer_claw.services.identity.throttle import login_throttle
from cancer_claw.config import settings

logger = structlog.get_logger()
router = APIRouter()

class UserPublic(BaseModel):
    id: str
    username: str
    email: str = ""
    display_name: str = ""
    role: str = "user"
    status: str = "active"
    credits_balance: int = 0
    created_at: str | None = None
    updated_at: str | None = None


    permissions: list[str] = Field(default_factory=list)
    roles: list[dict] = Field(default_factory=list)

class RegisterReq(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    password: str = Field(..., min_length=6, max_length=128)
    email: str = Field("", max_length=120)
    display_name: str = Field("", max_length=60)

class LoginReq(BaseModel):
    username: str = Field(..., min_length=1, max_length=40)
    password: str = Field(..., min_length=1, max_length=128)

class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="有效期（秒）")
    user: UserPublic

class AdminCreateUserReq(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    password: str = Field(..., min_length=6, max_length=128)
    email: str = Field("", max_length=120)
    display_name: str = Field("", max_length=60)
    role: str = Field("user", description="user / admin")

class AdminUpdateUserReq(BaseModel):
    email: str | None = Field(None, max_length=120)
    display_name: str | None = Field(None, max_length=60)
    role: str | None = Field(None, description="user / admin")
    status: str | None = Field(None, description="active / disabled")
    password: str | None = Field(None, min_length=6, max_length=128)

class UserListResp(BaseModel):
    total: int
    items: list[UserPublic]

class RegistrationStatusResp(BaseModel):
    allow_registration: bool = Field(..., description="当前是否开放自助注册")

class RegistrationToggleReq(BaseModel):
    allow_registration: bool = Field(..., description="True=开放自助注册 / False=关闭")

def _client_ip(request: Request) -> str:

    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"

async def _grant_initial_credits(user_id: str) -> None:

    try:
        amount = await settings_repo.get_initial_grant()
        if amount > 0:
            await billing_repo.grant_initial(user_id, amount)
    except Exception as e:
        logger.warning("initial_grant_failed", user_id=user_id, error=str(e))

async def _attach_rbac(user: dict[str, Any]) -> dict[str, Any]:

    try:
        user["permissions"] = await repo.get_effective_permissions(user)
        user["roles"] = await repo.get_user_roles(user["id"])
    except Exception as e:
        logger.warning("attach_rbac_failed", user_id=user.get("id"), error=str(e))
        user.setdefault("permissions", [])
        user.setdefault("roles", [])
    return user

def _issue_token(user: dict[str, Any]) -> TokenResp:
    ttl = int(settings.auth.token_ttl_hours)
    token = create_access_token(
        user_id=user["id"],
        username=user["username"],
        role=user["role"],
        secret=get_auth_secret(),
        ttl_hours=ttl,
    )
    return TokenResp(
        access_token=token,
        expires_in=ttl * 3600,
        user=UserPublic(**user),
    )

@router.post("/auth/register", response_model=TokenResp, status_code=201)
async def register(body: RegisterReq) -> TokenResp:
    if not await settings_repo.is_registration_open():
        raise HTTPException(status_code=403, detail="本实例未开放自助注册，请联系管理员建号")

    existing = await repo.get_user_by_username(body.username)
    if existing:
        raise HTTPException(status_code=409, detail="用户名已被占用")


    is_first = (await repo.count_users()) == 0
    role = repo.ROLE_ADMIN if is_first else repo.ROLE_USER

    user = await repo.create_user(
        username=body.username,
        password=body.password,
        role=role,
        email=body.email,
        display_name=body.display_name,
    )
    await _grant_initial_credits(user["id"])
    user = await repo.get_user_by_id(user["id"]) or user
    await _attach_rbac(user)
    logger.info("user_registered", username=body.username, role=role)
    return _issue_token(user)

@router.post("/auth/login", response_model=TokenResp)
async def login(body: LoginReq, request: Request) -> TokenResp:

    ip = _client_ip(request)
    identity = f"{body.username.lower()}|{ip}"

    remaining = await login_throttle.check(identity)
    if remaining > 0:
        mins = max(1, int(remaining // 60) + 1)
        logger.warning("login_locked", username=body.username, ip=ip, remaining_s=int(remaining))
        raise HTTPException(
            status_code=429,
            detail=f"登录失败次数过多，请于约 {mins} 分钟后重试",
        )

    user = await repo.get_user_with_hash(body.username)

    if not user or not verify_password(body.password, user.get("password_hash", "")):
        locked = await login_throttle.record_failure(identity)
        logger.info("user_login_failed", username=body.username, ip=ip, just_locked=locked > 0)
        if locked > 0:
            mins = max(1, int(locked // 60))
            raise HTTPException(
                status_code=429,
                detail=f"登录失败次数过多，账号已临时锁定约 {mins} 分钟",
            )
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if user.get("status") != "active":

        raise HTTPException(status_code=403, detail="账号已被禁用")

    await login_throttle.record_success(identity)
    user.pop("password_hash", None)
    await _attach_rbac(user)
    logger.info("user_login", username=body.username, ip=ip)
    return _issue_token(user)

@router.get("/auth/registration", response_model=RegistrationStatusResp)
async def registration_status() -> RegistrationStatusResp:

    return RegistrationStatusResp(
        allow_registration=await settings_repo.is_registration_open()
    )

@router.get("/auth/me", response_model=UserPublic)
async def me(user: dict[str, Any] = Depends(get_current_user)) -> UserPublic:

    try:
        user.setdefault("roles", await repo.get_user_roles(user["id"]))
    except Exception:
        user.setdefault("roles", [])
    return UserPublic(**user)

@router.get("/settings/registration", response_model=RegistrationStatusResp)
async def get_registration_setting(
    _admin: dict[str, Any] = Depends(require_admin),
) -> RegistrationStatusResp:
    return RegistrationStatusResp(
        allow_registration=await settings_repo.is_registration_open()
    )

@router.put("/settings/registration", response_model=RegistrationStatusResp)
async def set_registration_setting(
    body: RegistrationToggleReq,
    admin: dict[str, Any] = Depends(require_admin),
) -> RegistrationStatusResp:
    await settings_repo.set_registration_open(body.allow_registration)
    logger.info(
        "registration_toggle",
        by=admin.get("username"),
        allow_registration=body.allow_registration,
    )
    return RegistrationStatusResp(allow_registration=body.allow_registration)

@router.get("/users", response_model=UserListResp)
async def list_users(_admin: dict[str, Any] = Depends(require_admin)) -> UserListResp:
    items = await repo.list_users()
    return UserListResp(total=len(items), items=[UserPublic(**u) for u in items])

@router.post("/users", response_model=UserPublic, status_code=201)
async def create_user(
    body: AdminCreateUserReq, _admin: dict[str, Any] = Depends(require_admin)
) -> UserPublic:
    if body.role not in repo.VALID_ROLES:
        raise HTTPException(status_code=400, detail="role 必须是 user / admin")
    if await repo.get_user_by_username(body.username):
        raise HTTPException(status_code=409, detail="用户名已被占用")
    user = await repo.create_user(
        username=body.username,
        password=body.password,
        role=body.role,
        email=body.email,
        display_name=body.display_name,
    )
    await _grant_initial_credits(user["id"])
    user = await repo.get_user_by_id(user["id"]) or user
    logger.info("admin_created_user", username=body.username, role=body.role)
    return UserPublic(**user)

@router.patch("/users/{user_id}", response_model=UserPublic)
async def update_user(
    user_id: str,
    body: AdminUpdateUserReq,
    admin: dict[str, Any] = Depends(require_admin),
) -> UserPublic:
    target = await repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")


    if user_id == admin["id"]:
        if body.role is not None and body.role != repo.ROLE_ADMIN:
            raise HTTPException(status_code=400, detail="不能修改自己的管理员角色")
        if body.status is not None and body.status != "active":
            raise HTTPException(status_code=400, detail="不能禁用自己的账号")

    try:
        updated = await repo.update_user(
            user_id,
            email=body.email,
            display_name=body.display_name,
            role=body.role,
            status=body.status,
            password=body.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    assert updated is not None
    return UserPublic(**updated)

@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str, admin: dict[str, Any] = Depends(require_admin)
):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    target = await repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    await repo.delete_user(user_id)
    logger.info("admin_deleted_user", user_id=user_id)

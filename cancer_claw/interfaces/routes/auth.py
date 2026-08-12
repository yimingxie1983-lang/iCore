from __future__ import annotations

import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from cancer_claw.config import settings
from cancer_claw.services.credits import repo as billing_repo
from cancer_claw.services.identity import captcha, mail, repo
from cancer_claw.services.identity import settings_repo
from cancer_claw.services.identity import throttle
from cancer_claw.services.identity.deps import (
    get_auth_secret,
    get_current_user,
    require_admin,
)
from cancer_claw.services.identity.security import (
    create_access_token,
    generate_token,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_password,
)

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
    email_verified: bool = False

    permissions: list[str] = Field(default_factory=list)
    roles: list[dict] = Field(default_factory=list)


class CaptchaAnswer(BaseModel):
    id: str = Field(..., min_length=8, max_length=512)
    answer: str = Field(..., min_length=1, max_length=16)


class RegisterReq(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    password: str = Field(..., min_length=6, max_length=128)
    email: str = Field("", max_length=120)
    display_name: str = Field("", max_length=60)
    invite_code: str = Field("", max_length=64)
    captcha: CaptchaAnswer | None = None


class LoginReq(BaseModel):
    username: str = Field(..., min_length=1, max_length=40)
    password: str = Field(..., min_length=1, max_length=128)
    captcha: CaptchaAnswer | None = None


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
    require_invite_code: bool = False
    require_captcha: bool = False


class RegistrationToggleReq(BaseModel):
    allow_registration: bool = Field(..., description="True=开放自助注册 / False=关闭")


class ChangePasswordReq(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=1, max_length=128)


class ForgotPasswordReq(BaseModel):
    username: str = Field("", max_length=40)
    email: str = Field("", max_length=120)


class ResetPasswordReq(BaseModel):
    token: str = Field(..., min_length=8, max_length=256)
    new_password: str = Field(..., min_length=1, max_length=128)


class AuthEventItem(BaseModel):
    id: int
    user_id: str | None = None
    username: str = ""
    event_type: str
    ip: str = ""
    detail: str = ""
    created_at: str | None = None


class AuthEventListResp(BaseModel):
    total: int
    items: list[AuthEventItem]


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


def _now() -> datetime:

    return datetime.now(timezone.utc)


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


async def _audit(
    user_id: str | None,
    username: str,
    event_type: str,
    ip: str,
    detail: str = "",
) -> None:

    try:
        await repo.record_auth_event(user_id, username, event_type, ip, detail)
    except Exception as e:
        logger.warning("auth_audit_failed", event=event_type, error=str(e))


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_DUMMY_HASH: str | None = None


def _dummy_hash() -> str:

    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
    return _DUMMY_HASH


def _captcha_response(detail: str) -> JSONResponse:

    return JSONResponse(
        status_code=428,
        content={
            "detail": detail,
            "challenge": captcha.create_challenge(
                ttl=settings.auth.captcha_ttl_seconds
            ),
        },
    )


async def _registration_status() -> RegistrationStatusResp:

    invite = bool(settings.auth.registration_invite_code)
    return RegistrationStatusResp(
        allow_registration=await settings_repo.is_registration_open(),
        require_invite_code=invite,
        require_captcha=not invite,
    )


def _issue_token(user: dict[str, Any]) -> TokenResp:
    ttl = int(settings.auth.token_ttl_hours)
    token = create_access_token(
        user_id=user["id"],
        username=user["username"],
        role=user["role"],
        secret=get_auth_secret(),
        ttl_hours=ttl,
        token_version=user.get("token_version", 0),
    )
    return TokenResp(
        access_token=token,
        expires_in=ttl * 3600,
        user=UserPublic(**user),
    )


async def _send_verify_email(user: dict[str, Any]) -> None:

    token = generate_token()
    await repo.create_auth_token(
        user["id"],
        "email_verify",
        hash_token(token),
        _now() + timedelta(hours=settings.auth.email_verify_token_ttl_hours),
    )
    link = f"{settings.mail.public_base_url.rstrip('/')}/login?verify_token={token}"
    await mail.send_email_async(
        user["email"],
        "iCore 邮箱验证",
        f"请点击链接完成邮箱验证（{settings.auth.email_verify_token_ttl_hours} 小时内有效）：\n{link}",
    )


@router.post("/auth/register", response_model=TokenResp, status_code=201)
async def register(body: RegisterReq, request: Request) -> TokenResp:
    if not await settings_repo.is_registration_open():
        raise HTTPException(status_code=403, detail="本实例未开放自助注册，请联系管理员建号")

    ip = _client_ip(request)
    ip_ident = f"ip:{ip}"
    if (
        await throttle.count_attempts(
            ip_ident, "register", window_seconds=throttle.REGISTER_WINDOW_SECONDS
        )
        >= throttle.REGISTER_MAX_PER_IP
    ):
        raise HTTPException(status_code=429, detail="注册过于频繁，请稍后再试")

    try:
        validate_password_strength(
            body.password,
            username=body.username,
            min_length=settings.auth.min_password_length,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if body.email and not _EMAIL_RE.fullmatch(body.email.strip()):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")

    invite = settings.auth.registration_invite_code
    if invite:
        if not body.invite_code or not hmac.compare_digest(body.invite_code, invite):
            raise HTTPException(status_code=400, detail="邀请码不正确")
    else:
        if not body.captcha or not captcha.verify_challenge(
            body.captcha.id, body.captcha.answer
        ):
            return _captcha_response("需要人机验证，请完成算术题")

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

    if user.get("email") and mail.is_mail_configured():
        try:
            await _send_verify_email(user)
        except Exception as e:
            logger.warning("verify_mail_send_failed", user_id=user["id"], error=str(e))

    await _audit(user["id"], user["username"], "register", _client_ip(request))
    await throttle.record_attempt(ip_ident, "register")
    logger.info("user_registered", username=body.username, role=role)
    return _issue_token(user)


@router.post("/auth/login", response_model=TokenResp)
async def login(body: LoginReq, request: Request) -> TokenResp:

    ip = _client_ip(request)
    u_ident = f"u:{body.username.lower()}"
    ip_ident = f"ip:{ip}"

    u_fails = await throttle.failure_count(u_ident)
    ip_fails = await throttle.failure_count(ip_ident)
    if max(u_fails, ip_fails) >= settings.auth.captcha_threshold:
        if not body.captcha or not captcha.verify_challenge(
            body.captcha.id, body.captcha.answer
        ):
            return _captcha_response("需要人机验证，请完成算术题")

    remaining = max(
        await throttle.check_lock(u_ident),
        await throttle.check_lock(ip_ident),
    )
    if remaining > 0:
        mins = max(1, int(remaining // 60) + 1)
        await _audit(None, body.username, "login_locked", ip, f"remaining_s={int(remaining)}")
        logger.warning("login_locked", username=body.username, ip=ip, remaining_s=int(remaining))
        raise HTTPException(
            status_code=429,
            detail=f"登录失败次数过多，请于约 {mins} 分钟后重试",
        )

    user = await repo.get_user_with_hash(body.username)
    if not user:
        verify_password(body.password, _dummy_hash())

    if not user or not verify_password(body.password, user.get("password_hash", "")):
        locked = max(
            await throttle.record_failure(u_ident, max_failures=throttle.USER_MAX_FAILURES),
            await throttle.record_failure(ip_ident, max_failures=throttle.IP_MAX_FAILURES),
        )
        await _audit(None, body.username, "login_failed", ip, f"just_locked={locked > 0}")
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

    await throttle.record_success(u_ident)
    await throttle.record_success(ip_ident)
    user.pop("password_hash", None)
    await _attach_rbac(user)
    await _audit(user["id"], user["username"], "login_success", ip)
    logger.info("user_login", username=body.username, ip=ip)
    return _issue_token(user)


@router.get("/auth/captcha")
async def get_captcha() -> dict:

    return captcha.create_challenge(ttl=settings.auth.captcha_ttl_seconds)


@router.post("/auth/change-password", status_code=204)
async def change_password(
    body: ChangePasswordReq,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> Response:

    full = await repo.get_user_with_hash(user["username"])
    if not full or not verify_password(body.current_password, full.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="当前密码不正确")
    try:
        validate_password_strength(
            body.new_password,
            username=user["username"],
            min_length=settings.auth.min_password_length,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await repo.update_password(user["id"], body.new_password)
    await _audit(user["id"], user["username"], "password_changed", _client_ip(request))
    return Response(status_code=204)


@router.post("/auth/forgot-password", status_code=202)
async def forgot_password(body: ForgotPasswordReq, request: Request) -> dict[str, bool]:

    if not mail.is_mail_configured():
        raise HTTPException(status_code=503, detail="系统未配置邮件服务，无法发送重置邮件")
    ip = _client_ip(request)
    target = await repo.get_user_by_username_or_email(body.username, body.email)
    if target and target.get("email"):
        token = generate_token()
        await repo.create_auth_token(
            target["id"],
            "password_reset",
            hash_token(token),
            _now() + timedelta(minutes=settings.auth.reset_token_ttl_minutes),
        )
        link = f"{settings.mail.public_base_url.rstrip('/')}/login?reset_token={token}"
        try:
            await mail.send_email_async(
                target["email"],
                "iCore 密码重置",
                f"请点击链接重置密码（{settings.auth.reset_token_ttl_minutes} 分钟内有效）：\n{link}",
            )
            await _audit(target["id"], target["username"], "password_reset_requested", ip)
        except Exception as e:
            await _audit(
                target["id"], target["username"], "password_reset_mail_failed", ip, str(e)
            )
    else:
        await _audit(None, body.username or body.email, "password_reset_requested_unknown", ip)
    return {"ok": True}


@router.post("/auth/reset-password")
async def reset_password(body: ResetPasswordReq, request: Request) -> dict[str, bool]:

    user_id = await repo.consume_auth_token(hash_token(body.token), "password_reset")
    if not user_id:
        raise HTTPException(status_code=400, detail="重置链接无效或已过期")
    user = await repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=400, detail="用户不存在")
    try:
        validate_password_strength(
            body.new_password,
            username=user["username"],
            min_length=settings.auth.min_password_length,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await repo.update_password(user_id, body.new_password)
    await _audit(user_id, user["username"], "password_reset", _client_ip(request))
    return {"ok": True}


@router.get("/auth/verify-email")
async def verify_email(token: str = Query(..., min_length=8, max_length=256)) -> dict[str, bool]:

    user_id = await repo.consume_auth_token(hash_token(token), "email_verify")
    if not user_id:
        raise HTTPException(status_code=400, detail="验证链接无效或已过期")
    await repo.set_email_verified(user_id)
    return {"ok": True}


@router.post("/auth/send-verification", status_code=202)
async def send_verification(
    request: Request, user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, bool]:

    if not mail.is_mail_configured():
        raise HTTPException(status_code=503, detail="系统未配置邮件服务")
    if not user.get("email"):
        raise HTTPException(status_code=400, detail="账号未绑定邮箱")
    if user.get("email_verified"):
        raise HTTPException(status_code=400, detail="邮箱已认证")
    await _send_verify_email(user)
    await _audit(user["id"], user["username"], "verify_email_sent", _client_ip(request))
    return {"ok": True}


@router.get("/auth/registration", response_model=RegistrationStatusResp)
async def registration_status() -> RegistrationStatusResp:

    return await _registration_status()


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
    return await _registration_status()


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
    return await _registration_status()


@router.get("/users", response_model=UserListResp)
async def list_users(_admin: dict[str, Any] = Depends(require_admin)) -> UserListResp:
    items = await repo.list_users()
    return UserListResp(total=len(items), items=[UserPublic(**u) for u in items])


@router.post("/users", response_model=UserPublic, status_code=201)
async def create_user(
    body: AdminCreateUserReq, request: Request, _admin: dict[str, Any] = Depends(require_admin)
) -> UserPublic:
    if body.role not in repo.VALID_ROLES:
        raise HTTPException(status_code=400, detail="role 必须是 user / admin")
    try:
        validate_password_strength(
            body.password,
            username=body.username,
            min_length=settings.auth.min_password_length,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
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
    await _audit(user["id"], user["username"], "admin_create_user", _client_ip(request))
    logger.info("admin_created_user", username=body.username, role=body.role)
    return UserPublic(**user)


@router.patch("/users/{user_id}", response_model=UserPublic)
async def update_user(
    user_id: str,
    body: AdminUpdateUserReq,
    request: Request,
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

    if body.password:
        try:
            validate_password_strength(
                body.password,
                username=target["username"],
                min_length=settings.auth.min_password_length,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

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
    await _audit(updated["id"], updated["username"], "admin_update_user", _client_ip(request))
    return UserPublic(**updated)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str, request: Request, admin: dict[str, Any] = Depends(require_admin)
) -> Response:
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    target = await repo.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    await _audit(target["id"], target["username"], "admin_delete_user", _client_ip(request))
    await repo.delete_user(user_id)
    return Response(status_code=204)


@router.get("/admin/auth-events", response_model=AuthEventListResp)
async def list_auth_events(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _admin: dict[str, Any] = Depends(require_admin),
) -> AuthEventListResp:
    total, items = await repo.list_auth_events(limit=limit, offset=offset)
    return AuthEventListResp(total=total, items=items)

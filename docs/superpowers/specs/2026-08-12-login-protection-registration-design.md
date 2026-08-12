# 登录防护 + 注册开放完善 设计文档

**日期：** 2026-08-12

## 背景

人工验证后发现两个问题：
1. 登录防护不足：现有限流为进程内存态、且仅按"用户名+IP"单维度计数，换用户名/重启即可绕过；无验证码。
2. 注册默认关闭，且缺少防滥用与完善功能（邀请码、注册限流、邮箱校验等）。

## 方案（用户已确认选 A）

### 1. 登录防护

- **持久化限流**：失败记录落库（新增 `login_attempts` 表），重启、多进程均有效。
- **双维度计数**：按账号 `u:<username>` 与来源 IP `ip:<addr>` 分别计数；账号 5 次/15 分钟、IP 20 次/15 分钟，超限锁定 15 分钟。
- **条件验证码**：任一维度失败达到 3 次后，登录必须通过自托管算术验证码（HMAC 签名、120 秒有效）。
- **时间均衡**：用户名不存在时也执行一次 PBKDF2 校验，避免通过响应时间枚举账号。

### 2. 注册开放与完善

- **开放注册**：`allow_registration` 默认改为 true（本地 config + 数据库设置即时生效）。
- **注册限流**：每 IP 每小时最多注册 5 个账号。
- **验证码**：未配置邀请码时，注册必填验证码；配置邀请码后凭码注册、免验证码。
- **邀请码（可选）**：`auth.registration_invite_code` 非空时启用，常量时间比较。
- **邮箱校验**：注册填写的邮箱做格式校验（正则，不引入外部依赖）。
- **注册状态接口扩展**：`/auth/registration` 返回 `require_invite_code` / `require_captcha`，前端据此渲染字段。

## 组件

- `cancer_claw/services/identity/throttle.py`：重写为 DB 支撑的限流（`check_lock` / `record_failure` / `record_success` / `count_attempts` / `record_attempt`）。
- `cancer_claw/services/identity/captcha.py`：无状态 HMAC 算术验证码（`create_challenge` / `verify_challenge`）。
- `cancer_claw/interfaces/routes/auth.py`：登录/注册接入限流、验证码、邀请码、邮箱校验；新增 `GET /auth/captcha`。
- `cancer_claw/db.py`：新增 `login_attempts` 表与索引。
- `cancer_claw/config.py`：`AuthConfig` 新增 `registration_invite_code` / `captcha_threshold` / `captcha_ttl_seconds`。
- 前端 `Login.tsx` / `client.ts`：验证码输入、邀请码输入、428 挑战处理、注册状态字段。

## 测试

- throttle：N 次失败后锁定、成功后清零、过期失效、注册计数。
- captcha：正确/错误答案、过期、篡改。
- auth API：失败 3 次后登录需验证码；注册无邀请码需验证码；邀请码流程；注册限流；非法邮箱；注册状态字段。

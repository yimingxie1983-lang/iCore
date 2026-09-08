

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

class AppConfig(BaseModel):

    name: str = "iCore"
    version: str = "0.1.0"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

class PathsConfig(BaseModel):

    data_dir: str = "./cancer_claw/var/state"
    projects_dir: str = "./cancer_claw/var/workspaces"
    agents_dir: str = "./cancer_claw/var/agent_instances"
    library_crafts_dir: str = "./cancer_claw/resources/knowledge/playbooks"
    personas_dir: str = "./cancer_claw/resources/persona_profiles"
    tool_path_allow_extra: list[str] = Field(
        default_factory=list,
        description="文件类工具允许访问的额外绝对路径前缀（高级）；默认仅能访问当前项目目录",
    )

class DatabaseConfig(BaseModel):

    path: str = "./cancer_claw/var/state/cancer_claw.db"
    url: str = ""
    pool_min: int = 2
    pool_max: int = 10

    @property
    def is_postgres(self) -> bool:
        return bool(self.url.strip())

class RedisConfig(BaseModel):

    url: str = ""
    key_prefix: str = "cc"

    @property
    def enabled(self) -> bool:
        return bool(self.url.strip())

class ConcurrencyConfig(BaseModel):

    llm_max_concurrency: int = 80
    llm_rpm: int = 400
    llm_local_multiplier: int = 4

class ModelInfo(BaseModel):

    id: str
    role: str = "general"

class ProviderConfig(BaseModel):

    id: str
    name: str
    base_url: str
    api_key: str = ""
    models: list[ModelInfo] = []
    enabled: bool = True
    priority: int = 0

class ContextConfig(BaseModel):

    default_max_tokens: int = 100000
    soul_budget: int = 3500
    memory_budget: int = 5000
    plan_budget: int = 8000
    craft_total_ratio: float = 0.10
    craft_index_ratio: float = 0.03









class MemoryConfig(BaseModel):

    core_max_lines: int = 200
    topic_max_lines: int = 500
    user_memory_dir: str = "./cancer_claw/var/state/user_memory"
    conv_load_recent_turns: int = 20
    working_memory_onelines: int = 8
    history_inject_max_tokens: int = 15000
    auto_extract_enabled: bool = True






    conv_load_consensus: int = 8
    conv_load_per_platform: int = 12

class PipelineConfig(BaseModel):

    auto_certify_threshold: float = 0.9

class CraftConfig(BaseModel):

    auto_evolve_min_samples: int = 5
    auto_evolve_success_threshold: float = 0.7
    description_max_chars: int = 250

class SkillsConfig(BaseModel):

    enabled: bool = True
    scan_paths: list[str] = Field(
        default_factory=lambda: ["./cancer_claw/resources/knowledge/skill_packs"]
    )
    uploads_dir: str = "./cancer_claw/resources/knowledge/skill_packs/uploads"
    watch: bool = False
    l1_max_token_budget: int = 8000
    l1_max_chars_per_entry: int = 240
    pinned: list[str] = Field(default_factory=list)

class CitationsConfig(BaseModel):
    authority_sites: list[str] = Field(
        default_factory=lambda: [
            "nhc.gov.cn",
            "nhsa.gov.cn",
            "nmpa.gov.cn",
            "gov.cn",
            "chinacdc.cn",
        ]
    )

class LoggingConfig(BaseModel):

    level: str = "INFO"
    format: str = "json"

class SandboxConfig(BaseModel):

    mode: str = "native"
    max_memory_mb: int = 2048
    max_processes: int = 64
    cpu_time_seconds: int = 3600
    low_integrity: bool = True
    redirect_env_dirs: bool = True


class TrainingConfig(BaseModel):
    """独立训练运行时（与 iCore 应用 venv 隔离）。"""

    python: str = "./.venv-train/Scripts/python.exe"
    # Dedicated D: tree for GPU venv / pip / HF / torch caches. Empty = derive from python.
    root: str = ""
    max_vram_mb: int = 7168

class EvolutionConfig(BaseModel):

    enabled: bool = True
    auto_after_task: bool = True



    skill_draft_enabled: bool = True

class CharterConfig(BaseModel):


    auto_init_user_chars: int = 1500
    auto_init_min_stages: int = 3
    auto_init_min_iterations: int = 30


    event_window_size: int = 10
    log_event_debounce_seconds: int = 60
    # 复杂多阶段任务：阶段完成后同流自动推进，无需用户说「继续」
    auto_advance_stages: bool = True
    auto_advance_max_stages: int = 20

class DiagnosticsConfig(BaseModel):

    dump_after_chat: bool = False

class AuthConfig(BaseModel):

    enabled: bool = True
    secret: str = ""
    token_ttl_hours: int = 168
    allow_registration: bool = False
    min_password_length: int = 8
    reset_token_ttl_minutes: int = 30
    email_verify_token_ttl_hours: int = 24
    file_url_ttl_seconds: int = 300
    registration_invite_code: str = ""
    captcha_threshold: int = 3
    captcha_ttl_seconds: int = 120
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = ""

class MailConfig(BaseModel):

    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    from_addr: str = ""
    starttls: bool = True
    timeout: int = 10
    public_base_url: str = ""

class FeaturesConfig(BaseModel):

    project_sharing: bool = False
    insights_collect: bool = True
    insights_ai_summary: bool = True


class WeChatChannelConfig(BaseModel):
    """微信 iLink 本机桥配置。"""

    enabled: bool = True
    mode: str = Field("desktop", description="desktop=本机桥；server=服务端常驻（未实现）")
    default_permissions: str = "ask"
    progress_to_chat: bool = True
    artifact_delivery: str = Field(
        "media_then_link",
        description="media_then_link | media_only | link_only",
    )
    chunk_interval_seconds: float = 3.0
    cdn_base_url: str = "https://novac2c.cdn.weixin.qq.com/c2c"
    bind_code_ttl_seconds: int = 600


class ChannelsConfig(BaseModel):
    wechat: WeChatChannelConfig = WeChatChannelConfig()


class PrivacyConfig(BaseModel):
    """医院场景 PHI/PII 脱敏配置。"""

    enabled: bool = True
    mode: str = Field(
        "strict",
        description="strict=替换敏感信息；audit_only=仅审计命中；off=关闭",
    )
    desensitize_on_upload: bool = True
    desensitize_before_llm: bool = True
    desensitize_on_chat_input: bool = True
    desensitize_on_persist: bool = True
    rules: list[str] = Field(
        default_factory=lambda: [
            "id_card",
            "phone",
            "landline",
            "mrn",
            "name",
            "address",
            "email",
            "bank_card",
            "passport",
        ],
        description="启用的脱敏规则类型",
    )
    textual_upload_extensions: list[str] = Field(
        default_factory=lambda: [
            ".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".xml",
            ".html", ".htm", ".log", ".yaml", ".yml",
        ],
        description="上传时自动脱敏的文本类扩展名",
    )

class Settings(BaseModel):

    app: AppConfig = AppConfig()
    paths: PathsConfig = PathsConfig()
    database: DatabaseConfig = DatabaseConfig()
    redis: RedisConfig = RedisConfig()
    concurrency: ConcurrencyConfig = ConcurrencyConfig()
    providers: list[ProviderConfig] = []
    context: ContextConfig = ContextConfig()
    memory: MemoryConfig = MemoryConfig()
    pipeline: PipelineConfig = PipelineConfig()
    craft: CraftConfig = CraftConfig()
    skills: SkillsConfig = SkillsConfig()
    citations: CitationsConfig = CitationsConfig()
    logging: LoggingConfig = LoggingConfig()
    evolution: EvolutionConfig = EvolutionConfig()
    charter: CharterConfig = CharterConfig()
    sandbox: SandboxConfig = SandboxConfig()
    training: TrainingConfig = TrainingConfig()
    diagnostics: DiagnosticsConfig = DiagnosticsConfig()
    auth: AuthConfig = AuthConfig()
    mail: MailConfig = MailConfig()
    features: FeaturesConfig = FeaturesConfig()
    privacy: PrivacyConfig = PrivacyConfig()
    channels: ChannelsConfig = ChannelsConfig()
    project_root: str = ""

def _find_config_file() -> Path | None:


    env_path = os.environ.get("ONEKEY_CONFIG")
    if env_path:
        p = Path(env_path).expanduser()
        if p.exists():
            return p

    current = Path.cwd()
    for _ in range(5):
        candidate = current / "config.yaml"
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    # `icore` 可在任意工作目录启动，继续向安装位置 / 用户目录找配置。
    install_root = Path(__file__).resolve().parent.parent
    install_cfg = install_root / "config.yaml"
    if install_cfg.exists():
        return install_cfg

    user_cfg = Path.home() / ".icore" / "config.yaml"
    if user_cfg.exists():
        return user_cfg

    return None

def _apply_env_overrides(settings: Settings) -> Settings:


    for provider in settings.providers:
        env_key = f"{provider.id.upper()}_API_KEY"
        env_val = os.environ.get(env_key)
        if env_val:
            provider.api_key = env_val


    if os.environ.get("CANCER_CLAW_APP_PORT"):
        settings.app.port = int(os.environ["CANCER_CLAW_APP_PORT"])
    if os.environ.get("CANCER_CLAW_APP_DEBUG"):
        settings.app.debug = os.environ["CANCER_CLAW_APP_DEBUG"].lower() in ("true", "1", "yes")
    if os.environ.get("CANCER_CLAW_LOG_LEVEL"):
        settings.logging.level = os.environ["CANCER_CLAW_LOG_LEVEL"]
    if os.environ.get("CANCER_CLAW_DATABASE_PATH"):
        settings.database.path = os.environ["CANCER_CLAW_DATABASE_PATH"]


    if os.environ.get("CANCER_CLAW_DB_URL"):
        settings.database.url = os.environ["CANCER_CLAW_DB_URL"]
    if os.environ.get("CANCER_CLAW_DB_POOL_MIN"):
        try:
            settings.database.pool_min = int(os.environ["CANCER_CLAW_DB_POOL_MIN"])
        except ValueError:
            pass
    if os.environ.get("CANCER_CLAW_DB_POOL_MAX"):
        try:
            settings.database.pool_max = int(os.environ["CANCER_CLAW_DB_POOL_MAX"])
        except ValueError:
            pass
    if os.environ.get("CANCER_CLAW_REDIS_URL"):
        settings.redis.url = os.environ["CANCER_CLAW_REDIS_URL"]
    if os.environ.get("CANCER_CLAW_REDIS_PREFIX"):
        settings.redis.key_prefix = os.environ["CANCER_CLAW_REDIS_PREFIX"]
    if os.environ.get("CANCER_CLAW_LLM_MAX_CONCURRENCY"):
        try:
            settings.concurrency.llm_max_concurrency = int(
                os.environ["CANCER_CLAW_LLM_MAX_CONCURRENCY"]
            )
        except ValueError:
            pass
    if os.environ.get("CANCER_CLAW_LLM_RPM"):
        try:
            settings.concurrency.llm_rpm = int(os.environ["CANCER_CLAW_LLM_RPM"])
        except ValueError:
            pass
    if os.environ.get("CANCER_CLAW_EVOLUTION_ENABLED"):
        settings.evolution.enabled = (
            os.environ["CANCER_CLAW_EVOLUTION_ENABLED"].lower() in ("1", "true", "yes")
        )
    if os.environ.get("CANCER_CLAW_CHARTER_AUTO_ADVANCE"):
        settings.charter.auto_advance_stages = (
            os.environ["CANCER_CLAW_CHARTER_AUTO_ADVANCE"].lower()
            in ("1", "true", "yes")
        )


    if os.environ.get("CANCER_CLAW_AUTH_ENABLED"):
        settings.auth.enabled = (
            os.environ["CANCER_CLAW_AUTH_ENABLED"].lower() in ("1", "true", "yes")
        )
    if os.environ.get("CANCER_CLAW_AUTH_SECRET"):
        settings.auth.secret = os.environ["CANCER_CLAW_AUTH_SECRET"]
    if os.environ.get("CANCER_CLAW_AUTH_TOKEN_TTL_HOURS"):
        try:
            settings.auth.token_ttl_hours = int(
                os.environ["CANCER_CLAW_AUTH_TOKEN_TTL_HOURS"]
            )
        except ValueError:
            pass
    if os.environ.get("CANCER_CLAW_AUTH_MIN_PASSWORD_LENGTH"):
        try:
            settings.auth.min_password_length = int(
                os.environ["CANCER_CLAW_AUTH_MIN_PASSWORD_LENGTH"]
            )
        except ValueError:
            pass
    if os.environ.get("CANCER_CLAW_AUTH_RESET_TOKEN_TTL_MINUTES"):
        try:
            settings.auth.reset_token_ttl_minutes = int(
                os.environ["CANCER_CLAW_AUTH_RESET_TOKEN_TTL_MINUTES"]
            )
        except ValueError:
            pass
    if os.environ.get("CANCER_CLAW_AUTH_EMAIL_VERIFY_TTL_HOURS"):
        try:
            settings.auth.email_verify_token_ttl_hours = int(
                os.environ["CANCER_CLAW_AUTH_EMAIL_VERIFY_TTL_HOURS"]
            )
        except ValueError:
            pass
    if os.environ.get("CANCER_CLAW_AUTH_FILE_URL_TTL_SECONDS"):
        try:
            settings.auth.file_url_ttl_seconds = int(
                os.environ["CANCER_CLAW_AUTH_FILE_URL_TTL_SECONDS"]
            )
        except ValueError:
            pass
    if os.environ.get("CANCER_CLAW_AUTH_REGISTRATION_INVITE_CODE"):
        settings.auth.registration_invite_code = os.environ[
            "CANCER_CLAW_AUTH_REGISTRATION_INVITE_CODE"
        ]
    if os.environ.get("CANCER_CLAW_AUTH_CAPTCHA_THRESHOLD"):
        try:
            settings.auth.captcha_threshold = int(
                os.environ["CANCER_CLAW_AUTH_CAPTCHA_THRESHOLD"]
            )
        except ValueError:
            pass
    if os.environ.get("CANCER_CLAW_AUTH_CAPTCHA_TTL_SECONDS"):
        try:
            settings.auth.captcha_ttl_seconds = int(
                os.environ["CANCER_CLAW_AUTH_CAPTCHA_TTL_SECONDS"]
            )
        except ValueError:
            pass
    if os.environ.get("CANCER_CLAW_AUTH_ALLOW_REGISTRATION"):
        settings.auth.allow_registration = (
            os.environ["CANCER_CLAW_AUTH_ALLOW_REGISTRATION"].lower()
            in ("1", "true", "yes")
        )
    if os.environ.get("CANCER_CLAW_AUTH_BOOTSTRAP_PASSWORD"):
        settings.auth.bootstrap_admin_password = os.environ[
            "CANCER_CLAW_AUTH_BOOTSTRAP_PASSWORD"
        ]

    if os.environ.get("CANCER_CLAW_SMTP_HOST"):
        settings.mail.host = os.environ["CANCER_CLAW_SMTP_HOST"]
    if os.environ.get("CANCER_CLAW_SMTP_PORT"):
        try:
            settings.mail.port = int(os.environ["CANCER_CLAW_SMTP_PORT"])
        except ValueError:
            pass
    if os.environ.get("CANCER_CLAW_SMTP_USERNAME"):
        settings.mail.username = os.environ["CANCER_CLAW_SMTP_USERNAME"]
    if os.environ.get("CANCER_CLAW_SMTP_PASSWORD"):
        settings.mail.password = os.environ["CANCER_CLAW_SMTP_PASSWORD"]
    if os.environ.get("CANCER_CLAW_SMTP_FROM"):
        settings.mail.from_addr = os.environ["CANCER_CLAW_SMTP_FROM"]
    if os.environ.get("CANCER_CLAW_SMTP_STARTTLS"):
        settings.mail.starttls = os.environ["CANCER_CLAW_SMTP_STARTTLS"].lower() in (
            "1",
            "true",
            "yes",
        )
    if os.environ.get("CANCER_CLAW_PUBLIC_BASE_URL"):
        settings.mail.public_base_url = os.environ["CANCER_CLAW_PUBLIC_BASE_URL"]


    if os.environ.get("CANCER_CLAW_FEATURE_PROJECT_SHARING"):
        settings.features.project_sharing = (
            os.environ["CANCER_CLAW_FEATURE_PROJECT_SHARING"].lower()
            in ("1", "true", "yes")
        )

    if os.environ.get("CANCER_CLAW_PRIVACY_ENABLED"):
        settings.privacy.enabled = (
            os.environ["CANCER_CLAW_PRIVACY_ENABLED"].lower() in ("1", "true", "yes")
        )
    if os.environ.get("CANCER_CLAW_PRIVACY_MODE"):
        settings.privacy.mode = os.environ["CANCER_CLAW_PRIVACY_MODE"]

    if os.environ.get("CANCER_CLAW_TRAINING_PYTHON"):
        settings.training.python = os.environ["CANCER_CLAW_TRAINING_PYTHON"]
    if os.environ.get("CANCER_CLAW_TRAINING_ROOT"):
        settings.training.root = os.environ["CANCER_CLAW_TRAINING_ROOT"]
    if os.environ.get("CANCER_CLAW_TRAINING_MAX_VRAM_MB"):
        try:
            settings.training.max_vram_mb = int(
                os.environ["CANCER_CLAW_TRAINING_MAX_VRAM_MB"]
            )
        except ValueError:
            pass

    return settings

def _resolve_to_project_root(raw_path: str, project_root: Path) -> str:

    if not raw_path:
        return raw_path
    p = Path(raw_path)
    if p.is_absolute():
        return str(p.resolve())
    return str((project_root / p).resolve())

def _absolutize_paths(settings: "Settings", project_root: Path) -> None:

    settings.paths.data_dir = _resolve_to_project_root(settings.paths.data_dir, project_root)
    settings.paths.projects_dir = _resolve_to_project_root(settings.paths.projects_dir, project_root)
    settings.paths.agents_dir = _resolve_to_project_root(settings.paths.agents_dir, project_root)
    settings.paths.library_crafts_dir = _resolve_to_project_root(settings.paths.library_crafts_dir, project_root)
    settings.paths.personas_dir = _resolve_to_project_root(settings.paths.personas_dir, project_root)
    settings.database.path = _resolve_to_project_root(settings.database.path, project_root)


    settings.skills.scan_paths = [
        _resolve_to_project_root(p, project_root) for p in settings.skills.scan_paths
    ]
    settings.skills.uploads_dir = _resolve_to_project_root(
        settings.skills.uploads_dir, project_root
    )
    settings.training.python = _resolve_to_project_root(
        settings.training.python, project_root
    )
    if settings.training.root:
        settings.training.root = _resolve_to_project_root(
            settings.training.root, project_root
        )

def load_settings() -> Settings:

    config_file = _find_config_file()

    if config_file:
        with open(config_file, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        settings = Settings(**raw)
        project_root = config_file.parent.resolve()
    else:

        settings = Settings()
        project_root = Path.cwd().resolve()


    settings = _apply_env_overrides(settings)



    settings.project_root = str(project_root)
    _absolutize_paths(settings, project_root)

    return settings

settings = load_settings()

def reload_settings() -> Settings:

    global settings
    settings = load_settings()
    return settings

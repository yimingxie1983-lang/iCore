

from __future__ import annotations

MENU_CHAT = "menu.chat"
MENU_PROJECTS = "menu.projects"
MENU_AGENTS = "menu.agents"
MENU_SKILLS = "menu.skills"
MENU_MEMORY = "menu.memory"
MENU_CREDITS = "menu.credits"
MENU_MARKET = "menu.market"
MENU_PROVIDERS = "menu.providers"
MENU_USERS = "menu.users"
MENU_ROLES = "menu.roles"
MENU_EVOLUTION = "menu.evolution"

PROJECT_CREATE = "project.create"
PROJECT_SHARE = "project.share"
PROJECT_PUBLISH = "project.publish"
MARKET_BROWSE = "market.browse"
USER_MANAGE = "user.manage"
ROLE_MANAGE = "role.manage"
BILLING_MANAGE = "billing.manage"
PROVIDER_MANAGE = "provider.manage"
EVOLUTION_MANAGE = "evolution.manage"

PERMISSION_CATALOG: list[dict] = [
    {
        "group": "menu",
        "label": "菜单可见性",
        "desc": "控制侧边栏菜单与页面路由的访问",
        "items": [
            {"key": MENU_CHAT, "label": "对话工作台"},
            {"key": MENU_PROJECTS, "label": "项目"},
            {"key": MENU_AGENTS, "label": "智能体"},
            {"key": MENU_SKILLS, "label": "技能库"},
            {"key": MENU_MEMORY, "label": "记忆库"},
            {"key": MENU_CREDITS, "label": "我的额度"},
            {"key": MENU_MARKET, "label": "共享市场"},
            {"key": MENU_PROVIDERS, "label": "模型供应商"},
            {"key": MENU_USERS, "label": "用户管理"},
            {"key": MENU_ROLES, "label": "角色管理"},
            {"key": MENU_EVOLUTION, "label": "进化审批"},
        ],
    },
    {
        "group": "action",
        "label": "操作权限",
        "desc": "控制具体的后台操作是否放行",
        "items": [
            {"key": PROJECT_CREATE, "label": "新建项目"},
            {"key": PROJECT_SHARE, "label": "共享项目 / 管理成员"},
            {"key": PROJECT_PUBLISH, "label": "发布项目到市场"},
            {"key": MARKET_BROWSE, "label": "浏览市场 / 申请访问"},
            {"key": USER_MANAGE, "label": "用户管理 / 项目授权"},
            {"key": ROLE_MANAGE, "label": "角色与权限管理"},
            {"key": BILLING_MANAGE, "label": "计费配置 / 充值"},
            {"key": PROVIDER_MANAGE, "label": "模型供应商管理"},
            {"key": EVOLUTION_MANAGE, "label": "进化草稿审批"},
        ],
    },
]

ALL_PERMISSIONS: frozenset[str] = frozenset(
    item["key"] for group in PERMISSION_CATALOG for item in group["items"]
)

DEFAULT_USER_PERMISSIONS: frozenset[str] = frozenset(
    {
        MENU_CHAT,
        MENU_PROJECTS,
        MENU_AGENTS,
        MENU_SKILLS,
        MENU_MEMORY,
        MENU_CREDITS,
        MENU_MARKET,
        PROJECT_CREATE,
        PROJECT_SHARE,
        PROJECT_PUBLISH,
        MARKET_BROWSE,
    }
)

SYSTEM_ROLE_SEEDS: dict[str, tuple[str, frozenset[str]]] = {
    "普通成员": (
        "默认业务角色：可用对话、项目、智能体、技能、记忆、额度与共享市场",
        DEFAULT_USER_PERMISSIONS,
    ),
    "只读访客": (
        "仅可查看对话工作台与项目，适合外部协作只读账号",
        frozenset({MENU_CHAT, MENU_PROJECTS}),
    ),
    "项目经理": (
        "在普通成员基础上，可发布项目到市场并管理共享成员",
        DEFAULT_USER_PERMISSIONS | frozenset({PROJECT_PUBLISH, PROJECT_SHARE}),
    ),
}

def sanitize_permissions(keys: list[str] | set[str] | None) -> list[str]:

    if not keys:
        return []
    return sorted({k for k in keys if k in ALL_PERMISSIONS})

"""C/S 窗口菜单：在完整 B/S 工作台里跳转，不另做一套界面。"""

from __future__ import annotations

from typing import Any

from webview.menu import Menu, MenuAction, MenuSeparator

_ZOOM_MIN = 0.7
_ZOOM_MAX = 1.8
_ZOOM_STEP = 0.1


class DesktopSession:
    def __init__(self, window: Any, origin: str) -> None:
        self.window = window
        self.origin = origin.rstrip("/")
        self.zoom = 1.0

    def _js(self, script: str) -> None:
        try:
            self.window.evaluate_js(script)
        except Exception:
            pass

    def navigate(self, path: str) -> None:
        url = path if path.startswith("http") else f"{self.origin}{path}"
        try:
            self.window.load_url(url)
        except Exception:
            pass

    def reload(self) -> None:
        self._js("location.reload()")

    def zoom_by(self, delta: float) -> None:
        self.zoom = min(_ZOOM_MAX, max(_ZOOM_MIN, round(self.zoom + delta, 2)))
        self._js(f"document.body.style.zoom = '{self.zoom}'")

    def zoom_reset(self) -> None:
        self.zoom = 1.0
        self._js("document.body.style.zoom = '1'")

    def toggle_fullscreen(self) -> None:
        try:
            self.window.toggle_fullscreen()
        except Exception:
            pass

    def quit(self) -> None:
        try:
            self.window.destroy()
        except Exception:
            pass


def build_menu(session: DesktopSession) -> list:
    return [
        Menu(
            "文件",
            [
                MenuAction("新对话", lambda: session.navigate("/chat")),
                MenuAction("项目", lambda: session.navigate("/projects")),
                MenuAction("新建项目", lambda: session.navigate("/projects/new")),
                MenuSeparator(),
                MenuAction("退出", session.quit),
            ],
        ),
        Menu(
            "工作台",
            [
                MenuAction("对话", lambda: session.navigate("/chat")),
                MenuAction("智能体", lambda: session.navigate("/agents")),
                MenuAction("技能", lambda: session.navigate("/skills")),
                MenuAction("模型供应商", lambda: session.navigate("/providers")),
                MenuAction("记忆", lambda: session.navigate("/memory")),
                MenuAction("积分", lambda: session.navigate("/credits")),
                MenuAction("共享市场", lambda: session.navigate("/market")),
                MenuAction("账户", lambda: session.navigate("/account")),
            ],
        ),
        Menu(
            "管理",
            [
                MenuAction("用户", lambda: session.navigate("/admin/users")),
                MenuAction("角色", lambda: session.navigate("/admin/roles")),
                MenuAction("项目治理", lambda: session.navigate("/admin/projects")),
                MenuAction("计费", lambda: session.navigate("/admin/billing")),
                MenuAction("进化审批", lambda: session.navigate("/admin/evolution")),
                MenuAction("系统监控", lambda: session.navigate("/admin/monitor")),
                MenuAction("鉴权事件", lambda: session.navigate("/admin/auth-events")),
            ],
        ),
        Menu(
            "视图",
            [
                MenuAction("重新加载", session.reload),
                MenuAction("实际大小", session.zoom_reset),
                MenuAction("放大", lambda: session.zoom_by(_ZOOM_STEP)),
                MenuAction("缩小", lambda: session.zoom_by(-_ZOOM_STEP)),
                MenuSeparator(),
                MenuAction("全屏", session.toggle_fullscreen),
            ],
        ),
        Menu(
            "帮助",
            [
                MenuAction("登录页", lambda: session.navigate("/login")),
            ],
        ),
    ]

import os
import tempfile
from pathlib import Path

from cancer_claw.desktop.shell import read_port, repo_root


def test_read_port_from_config():
    with tempfile.TemporaryDirectory(dir=".") as raw:
        root = Path(raw)
        (root / "config.yaml").write_text("app:\n  port: 8099\n", encoding="utf-8")
        assert read_port(root) == 8099


def test_read_port_missing_config():
    with tempfile.TemporaryDirectory(dir=".") as raw:
        assert read_port(Path(raw)) == 8010


def test_repo_root_respects_env():
    with tempfile.TemporaryDirectory(dir=".") as raw:
        root = Path(raw).resolve()
        (root / "run_server.py").write_text("#", encoding="utf-8")
        old = os.environ.get("ICORE_ROOT")
        os.environ["ICORE_ROOT"] = str(root)
        try:
            assert repo_root() == root
        finally:
            if old is None:
                os.environ.pop("ICORE_ROOT", None)
            else:
                os.environ["ICORE_ROOT"] = old


class _FakeWindow:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.destroyed = False
        self.fullscreen = 0

    def load_url(self, url: str) -> None:
        self.urls.append(url)

    def evaluate_js(self, script: str) -> None:
        return None

    def destroy(self) -> None:
        self.destroyed = True

    def toggle_fullscreen(self) -> None:
        self.fullscreen += 1


def test_menu_covers_bs_workbench_routes():
    from cancer_claw.desktop.menu import DesktopSession, build_menu

    session = DesktopSession(_FakeWindow(), "http://127.0.0.1:8010/")
    titles = [m.title for m in build_menu(session)]
    assert titles == ["文件", "工作台", "管理", "视图", "帮助"]


def test_file_new_chat_navigates_to_bs_chat():
    from cancer_claw.desktop.menu import DesktopSession, build_menu

    win = _FakeWindow()
    session = DesktopSession(win, "http://127.0.0.1:8010/")
    file_menu = build_menu(session)[0]
    file_menu.items[0].function()
    assert win.urls[-1].endswith("/chat")


def test_workbench_menu_opens_market():
    from cancer_claw.desktop.menu import DesktopSession, build_menu

    win = _FakeWindow()
    session = DesktopSession(win, "http://127.0.0.1:8010/")
    workbench = build_menu(session)[1]
    labels = [getattr(item, "title", None) or getattr(item, "label", None) for item in workbench.items]
    assert "共享市场" in labels
    for item in workbench.items:
        if getattr(item, "title", None) == "共享市场" or getattr(item, "label", None) == "共享市场":
            item.function()
            break
    assert win.urls[-1].endswith("/market")

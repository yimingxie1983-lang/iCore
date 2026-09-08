"""C/S 桌面壳：拉起本地 FastAPI，用 WebView2 窗口打开完整 B/S 工作台。

不调用系统浏览器。前端仍是 web/ 那套 SPA，后端仍是全部 /api 路由。
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000


def _log_path() -> Path:
    log_dir = Path.home() / ".icore"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "desktop.log"


def append_log(text: str) -> None:
    try:
        with _log_path().open("a", encoding="utf-8") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
    except OSError:
        pass


def repo_root() -> Path:
    env = (os.environ.get("ICORE_ROOT") or "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if (p / "run_server.py").is_file():
            return p

    if getattr(sys, "frozen", False):
        here = Path(sys.executable).resolve().parent
        candidates = [here, here.parent, here.parent.parent, here.parent.parent.parent]
    else:
        here = Path(__file__).resolve()
        candidates = [here.parents[2], Path.cwd()]

    for cand in candidates:
        if (cand / "run_server.py").is_file():
            return cand
    return Path.cwd().resolve()


def read_port(root: Path) -> int:
    cfg = root / "config.yaml"
    if cfg.is_file():
        try:
            import yaml

            raw = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
            port = int(((raw.get("app") or {}).get("port")) or 8010)
            return port
        except Exception:
            pass
    try:
        return int(os.environ.get("CANCER_CLAW_APP_PORT") or "8010")
    except ValueError:
        return 8010


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def _is_store_stub(path: str) -> bool:
    return "WindowsApps" in path.replace("/", "\\")


def find_python(root: Path) -> str:
    venv = root / ".venv" / "Scripts" / "python.exe"
    if venv.is_file():
        return str(venv)
    local = (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "Python"
        / "Python312"
        / "python.exe"
    )
    if local.is_file():
        return str(local)
    if (
        not getattr(sys, "frozen", False)
        and sys.executable.lower().endswith("python.exe")
        and not _is_store_stub(sys.executable)
    ):
        return sys.executable
    which = shutil.which("python")
    if which and not _is_store_stub(which):
        return which
    raise RuntimeError("找不到本机 Python（已跳过 Microsoft Store 占位程序）。")


def _run(cmd: list[str], *, cwd: Path, timeout: int = 600) -> None:
    log = _log_path()
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"$ {' '.join(cmd)}\n")
        fh.flush()
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            stdout=fh,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"命令失败（exit {proc.returncode}）：{' '.join(cmd)}")


def ensure_frontend(root: Path) -> None:
    dist = root / "web" / "dist" / "index.html"
    if dist.is_file():
        return
    web = root / "web"
    if not (web / "package.json").is_file():
        raise RuntimeError("缺少 web/ 前端工程，无法启动完整工作台。")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise RuntimeError("前端尚未构建，且找不到 npm。请先在 web 目录执行 npm run build。")
    append_log("frontend dist missing; building web/")
    if not (web / "node_modules").is_dir():
        _run([npm, "install"], cwd=web)
    _run([npm, "run", "build"], cwd=web)
    if not dist.is_file():
        raise RuntimeError("前端构建失败，缺少 web/dist/index.html")


def ensure_server(root: Path, host: str, port: int) -> None:
    if port_open(host, port):
        append_log(f"server already up on {host}:{port}")
        return
    python = find_python(root)
    log = _log_path()
    flags = CREATE_NO_WINDOW if os.name == "nt" else 0
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"spawn {python} run_server.py\n")
    subprocess.Popen(
        [python, str(root / "run_server.py")],
        cwd=str(root),
        creationflags=flags,
        stdout=open(log, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        if port_open(host, port):
            append_log(f"server ready {host}:{port}")
            return
        time.sleep(0.25)
    raise RuntimeError(f"iCore 服务未能在 {host}:{port} 启动，详见 {_log_path()}")


def icon_path(root: Path) -> str | None:
    ico = root / "ops" / "icore.ico"
    return str(ico) if ico.is_file() else None


def _error_html(message: str) -> str:
    safe = (
        str(message)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        "<html><body style='font-family:Segoe UI,sans-serif;padding:48px;"
        "background:#161e28;color:#f2f2f2'>"
        "<h1>iCore 无法启动</h1>"
        f"<p>{safe}</p>"
        f"<p style='color:#94a3b0'>日志：{_log_path()}</p>"
        "</body></html>"
    )


def _show_error(message: str) -> None:
    append_log(message)
    try:
        import webview

        webview.create_window(
            "iCore",
            html=_error_html(message),
            width=720,
            height=420,
        )
        start_kwargs: dict = {}
        if os.name == "nt":
            start_kwargs["gui"] = "edgechromium"
        webview.start(**start_kwargs)
    except Exception:
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("iCore", f"{message}\n\n日志：{_log_path()}")
            root.destroy()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        return _main()
    except SystemExit as e:
        code = e.code
        return int(code) if isinstance(code, int) else 0
    except BaseException as e:
        _show_error(str(e) or repr(e))
        return 1


def _main() -> int:
    root = repo_root()
    os.chdir(root)
    os.environ.setdefault("PYTHONPATH", str(root))
    append_log(f"cs-shell start root={root} python={sys.executable}")

    host = "127.0.0.1"
    port = read_port(root)
    url = f"http://{host}:{port}/"
    ico = icon_path(root)

    try:
        ensure_frontend(root)
        ensure_server(root, host, port)
    except Exception as e:
        _show_error(str(e))
        return 1

    try:
        import webview
    except ImportError:
        _show_error("缺少 pywebview。请执行：pip install 'pywebview>=5.0'")
        return 1

    window_kwargs: dict = {
        "title": "iCore",
        "url": url,
        "width": 1440,
        "height": 920,
        "min_size": (960, 640),
        "background_color": "#161e28",
        "text_select": True,
    }
    try:
        if ico:
            window = webview.create_window(**window_kwargs, icon=ico)
        else:
            window = webview.create_window(**window_kwargs)
    except TypeError:
        window = webview.create_window(
            title="iCore",
            url=url,
            width=1440,
            height=920,
            min_size=(960, 640),
        )

    from cancer_claw.desktop.menu import DesktopSession, build_menu

    session = DesktopSession(window, url)
    storage = Path.home() / ".icore" / "webview"
    storage.mkdir(parents=True, exist_ok=True)
    start_kwargs: dict = {
        "private_mode": False,
        "storage_path": str(storage),
        "menu": build_menu(session),
    }
    if os.name == "nt":
        start_kwargs["gui"] = "edgechromium"
    if ico:
        start_kwargs["icon"] = ico
    try:
        webview.start(**start_kwargs)
    except TypeError:
        start_kwargs.pop("icon", None)
        start_kwargs.pop("menu", None)
        webview.start(**start_kwargs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

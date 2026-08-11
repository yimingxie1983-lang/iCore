

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from cancer_claw.capabilities.toolkit.base import BaseTool, ToolResult
from cancer_claw.capabilities.toolkit.workspace import get_tool_workspace

_DOM_EMPTY_TEXT_THRESHOLD = 50

_MAX_ROUTES = 20
_MAX_CLICKS = 50
_DEFAULT_WAIT_MS = 2000
_PAGE_TIMEOUT_MS = 15000

class BrowserVerifyTool(BaseTool):


    @property
    def name(self) -> str:
        return "browser_verify"

    @property
    def description(self) -> str:
        return (
            "用无头浏览器访问前端页面、按脚本点击、捕获 console 错误和网络 4xx/5xx，"
            "用于在 integrator 阶段终结'白屏、点哪哪崩'。只能在启动了前端服务后使用。"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "browser_verify",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "base_url": {
                            "type": "string",
                            "description": "前端服务根 URL，如 http://localhost:5180",
                        },
                        "routes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "要访问的相对路径列表，默认 ['/']",
                        },
                        "clicks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "route": {"type": "string", "description": "在哪个路由上点击"},
                                    "selector": {"type": "string", "description": "CSS selector，如 #submit-btn"},
                                    "expect_navigate": {"type": "boolean", "description": "是否期望点击后跳转"},
                                },
                                "required": ["route", "selector"],
                            },
                            "description": "点击动作脚本（可选）",
                        },
                        "wait_ms": {
                            "type": "integer",
                            "description": f"每次动作后等待毫秒，默认 {_DEFAULT_WAIT_MS}",
                        },
                        "screenshot": {
                            "type": "boolean",
                            "description": "是否写截图到项目 logs/browser_verify/，默认 True",
                        },
                        "engine": {
                            "type": "string",
                            "enum": ["auto", "webkit", "chromium", "firefox"],
                            "description": "浏览器引擎，默认 auto（优先 webkit，其次 chromium）",
                        },
                    },
                    "required": ["base_url"],
                },
            },
        }

    async def execute(self, **kwargs) -> ToolResult:
        base_url: str = (kwargs.get("base_url") or "").strip()
        if not base_url:
            return ToolResult(success=False, error="base_url 不能为空")
        if not re.match(r"^https?://", base_url):
            return ToolResult(success=False, error="base_url 必须以 http:// 或 https:// 开头")

        routes: list[str] = list(kwargs.get("routes") or ["/"])[:_MAX_ROUTES]
        raw_clicks = list(kwargs.get("clicks") or [])[:_MAX_CLICKS]
        wait_ms = int(kwargs.get("wait_ms") or _DEFAULT_WAIT_MS)
        save_screenshot = bool(kwargs.get("screenshot", True))
        engine = (kwargs.get("engine") or "auto").lower()


        screenshot_dir = self._prepare_screenshot_dir() if save_screenshot else None


        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return await self._fallback_static_check(
                base_url, routes, note="Playwright 未安装，已降级为静态检查。"
                                     "建议 `pip install playwright && playwright install webkit` 以开启完整点击验证。",
            )

        return await self._run_playwright(
            async_playwright=async_playwright,
            base_url=base_url,
            routes=routes,
            clicks=raw_clicks,
            wait_ms=wait_ms,
            screenshot_dir=screenshot_dir,
            engine=engine,
        )





    async def _run_playwright(
        self,
        *,
        async_playwright,
        base_url: str,
        routes: list[str],
        clicks: list[dict[str, Any]],
        wait_ms: int,
        screenshot_dir: Path | None,
        engine: str,
    ) -> ToolResult:
        start = time.monotonic()
        routes_by_path: dict[str, list[dict[str, Any]]] = {}
        for c in clicks:
            r = c.get("route") or "/"
            routes_by_path.setdefault(r, []).append(c)

        reports: list[dict[str, Any]] = []
        overall_ok = True

        async with async_playwright() as p:
            browser, actual_engine = await self._launch_browser(p, engine)
            if browser is None:
                return ToolResult(
                    success=False,
                    error="未找到可用的浏览器引擎。请运行 `playwright install webkit` 或 `playwright install chromium`。",
                )

            try:
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    ignore_https_errors=True,
                )
                page = await context.new_page()


                console_errors: list[dict[str, str]] = []
                console_warnings: list[dict[str, str]] = []
                network_errors: list[dict[str, Any]] = []
                page_errors: list[str] = []

                def _on_console(msg):
                    text = msg.text
                    if msg.type == "error":
                        console_errors.append({"text": text, "location": str(msg.location or "")})
                    elif msg.type == "warning":
                        console_warnings.append({"text": text, "location": str(msg.location or "")})

                def _on_page_error(err):
                    page_errors.append(str(err))

                def _on_response(resp):
                    try:
                        status = resp.status
                    except Exception:
                        return
                    if status >= 400:
                        network_errors.append({
                            "url": resp.url,
                            "status": status,
                            "method": resp.request.method if resp.request else "GET",
                        })

                def _on_request_failed(req):
                    network_errors.append({
                        "url": req.url,
                        "status": 0,
                        "method": req.method,
                        "failure": (req.failure or {}).get("errorText") if hasattr(req, "failure") else "",
                    })

                page.on("console", _on_console)
                page.on("pageerror", _on_page_error)
                page.on("response", _on_response)
                page.on("requestfailed", _on_request_failed)


                for path in routes:
                    url = base_url.rstrip("/") + "/" + path.lstrip("/")
                    per_errors_start = len(console_errors)
                    per_network_start = len(network_errors)
                    per_page_err_start = len(page_errors)

                    route_report: dict[str, Any] = {
                        "path": path,
                        "url": url,
                        "status": None,
                        "dom_empty": False,
                        "render_ok": False,
                        "console_errors": [],
                        "console_warnings": [],
                        "network_errors": [],
                        "page_errors": [],
                        "clicks_result": [],
                        "screenshot_path": None,
                        "load_error": None,
                    }

                    try:
                        response = await page.goto(url, timeout=_PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
                        route_report["status"] = response.status if response else None
                        await page.wait_for_timeout(wait_ms)


                        body_text = await page.evaluate(
                            "() => (document.body ? document.body.innerText : '')"
                        )
                        has_root_children = await page.evaluate(
                            """() => {
                                const root = document.querySelector('#root, #app, [role="main"]');
                                return !!(root && root.children && root.children.length > 0);
                            }"""
                        )
                        route_report["dom_empty"] = len((body_text or "").strip()) < _DOM_EMPTY_TEXT_THRESHOLD
                        route_report["render_ok"] = bool(has_root_children) and not route_report["dom_empty"]
                    except Exception as e:
                        route_report["load_error"] = f"{type(e).__name__}: {e}"


                    for click in routes_by_path.get(path, []):
                        selector = click.get("selector") or ""
                        expect_nav = bool(click.get("expect_navigate"))
                        cr: dict[str, Any] = {"selector": selector, "ok": False, "detail": ""}
                        try:
                            await page.wait_for_selector(selector, timeout=5000)
                            if expect_nav:
                                async with page.expect_navigation(timeout=_PAGE_TIMEOUT_MS):
                                    await page.click(selector)
                            else:
                                await page.click(selector)
                            await page.wait_for_timeout(wait_ms)
                            cr["ok"] = True
                        except Exception as e:
                            cr["detail"] = f"{type(e).__name__}: {e}"
                        route_report["clicks_result"].append(cr)


                    if screenshot_dir is not None:
                        fname = self._safe_filename(path) + f"_{datetime.now().strftime('%H%M%S')}.png"
                        shot_path = screenshot_dir / fname
                        try:
                            await page.screenshot(path=str(shot_path), full_page=True)
                            route_report["screenshot_path"] = str(shot_path)
                        except Exception as e:
                            route_report["screenshot_path"] = None
                            route_report["load_error"] = (route_report["load_error"] or "") + \
                                f" | screenshot_failed: {e}"


                    route_report["console_errors"] = _dedupe(console_errors[per_errors_start:])
                    route_report["console_warnings"] = _dedupe(console_warnings[per_errors_start:])
                    route_report["network_errors"] = network_errors[per_network_start:]
                    route_report["page_errors"] = page_errors[per_page_err_start:]

                    route_has_problem = (
                        route_report["load_error"]
                        or route_report["dom_empty"]
                        or not route_report["render_ok"]
                        or route_report["console_errors"]
                        or route_report["network_errors"]
                        or route_report["page_errors"]
                        or any(not cr["ok"] for cr in route_report["clicks_result"])
                    )
                    if route_has_problem:
                        overall_ok = False
                    reports.append(route_report)

                await context.close()
            finally:
                await browser.close()

        duration = int((time.monotonic() - start) * 1000)
        summary = _summarize(reports, overall_ok, actual_engine, duration)

        return ToolResult(
            success=True,
            output=summary,
            data={
                "overall_ok": overall_ok,
                "engine": actual_engine,
                "duration_ms": duration,
                "routes": reports,
            },
        )

    async def _launch_browser(self, p, engine: str):

        candidates: list[str]
        if engine == "auto":
            candidates = ["webkit", "chromium"]
        else:
            candidates = [engine]

        for cand in candidates:
            try:
                b = getattr(p, cand)
                browser = await b.launch(headless=True)
                return browser, cand
            except Exception:
                continue
        return None, ""





    async def _fallback_static_check(
        self, base_url: str, routes: list[str], *, note: str
    ) -> ToolResult:

        import httpx

        start = time.monotonic()
        reports: list[dict[str, Any]] = []
        overall_ok = True

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            for path in routes:
                url = base_url.rstrip("/") + "/" + path.lstrip("/")
                r = {
                    "path": path,
                    "url": url,
                    "status": None,
                    "dom_empty": False,
                    "render_ok": False,
                    "html_preview": "",
                    "load_error": None,
                    "degraded": True,
                }
                try:
                    resp = await client.get(url)
                    r["status"] = resp.status_code
                    html = resp.text or ""
                    r["html_preview"] = html[:400]

                    body_text = re.sub(r"<[^>]+>", " ", html)
                    body_text = re.sub(r"\s+", " ", body_text).strip()
                    r["dom_empty"] = len(body_text) < _DOM_EMPTY_TEXT_THRESHOLD
                    r["render_ok"] = resp.status_code < 400 and not r["dom_empty"]
                except Exception as e:
                    r["load_error"] = f"{type(e).__name__}: {e}"

                if not r["render_ok"]:
                    overall_ok = False
                reports.append(r)

        duration = int((time.monotonic() - start) * 1000)
        summary = (
            f"[降级·静态模式] 访问 {len(routes)} 个路由，"
            f"{'全部 HTTP 正常且非空' if overall_ok else '发现问题，详见 data.routes'}。"
            f"\n注意：静态模式无法执行 JS，SPA 的白屏可能漏报。{note}"
        )

        return ToolResult(
            success=True,
            output=summary,
            data={
                "overall_ok": overall_ok,
                "engine": "static",
                "degraded": True,
                "duration_ms": duration,
                "routes": reports,
                "install_hint": "pip install playwright && playwright install webkit",
            },
        )





    def _prepare_screenshot_dir(self) -> Path | None:

        ws = get_tool_workspace()
        if ws is None:
            return None
        d = ws.project_root / "logs" / "browser_verify"
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            return None
        return d

    @staticmethod
    def _safe_filename(path: str) -> str:
        s = path.strip("/").replace("/", "_") or "index"
        return re.sub(r"[^A-Za-z0-9_\-]", "_", s)[:80]

def _dedupe(items: list[dict[str, str]]) -> list[dict[str, str]]:

    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for it in items:
        key = it.get("text", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def _summarize(reports: list[dict[str, Any]], overall_ok: bool, engine: str, duration_ms: int) -> str:

    n_routes = len(reports)
    n_console_err = sum(len(r["console_errors"]) for r in reports)
    n_network_err = sum(len(r["network_errors"]) for r in reports)
    n_blank = sum(1 for r in reports if r.get("dom_empty"))
    n_load_err = sum(1 for r in reports if r.get("load_error"))

    head = "✅ 全部通过" if overall_ok else "❌ 发现问题"
    lines = [
        f"{head} | 引擎={engine} | 路由={n_routes} | 耗时={duration_ms}ms",
        f"console_errors={n_console_err}  network_errors={n_network_err}  "
        f"白屏={n_blank}  加载失败={n_load_err}",
    ]

    details: list[str] = []
    for r in reports:
        if r.get("load_error"):
            details.append(f"  · {r['path']} 加载失败: {r['load_error']}")
        if r.get("dom_empty"):
            details.append(f"  · {r['path']} 白屏（body 文本过少）")
        for e in r.get("console_errors", [])[:2]:
            details.append(f"  · {r['path']} console: {e.get('text','')[:120]}")
        for ne in r.get("network_errors", [])[:2]:
            details.append(f"  · {r['path']} network {ne.get('status')} {ne.get('url','')[:80]}")
        for cr in r.get("clicks_result", []):
            if not cr.get("ok"):
                details.append(f"  · {r['path']} 点击失败 [{cr.get('selector')}]: {cr.get('detail','')[:80]}")
    if details:
        lines.append("问题清单（前若干条）：")
        lines.extend(details[:8])
    return "\n".join(lines)

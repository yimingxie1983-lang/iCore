"""微信本机桥运行时：长轮询 → 命令/对话 → 回传。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from pathlib import Path
from typing import Any

from cancer_claw.channels import binding as binding_svc
from cancer_claw.channels.commands import parse_slash_command
from cancer_claw.channels.narration import EpisodeAccumulator
from cancer_claw.channels.turn import (
    extract_presentations,
    iter_channel_turn,
    load_project,
    load_user,
    presentation_local_paths,
)
from cancer_claw.channels.wechat.account_store import WechatAccountStore
from cancer_claw.channels.wechat.api import DEFAULT_CDN_BASE_URL, WeixinOfficialApi
from cancer_claw.channels.wechat.paths import serve_lock_path
from cancer_claw.channels.wechat.transport import InboundEvent, WechatTransport
from cancer_claw.capabilities.toolkit.builtins.ask_user import submit_answer
from cancer_claw.config import settings

logger = logging.getLogger("icore.wechat")

HELP_TEXT = """iCore 微信助手命令：
/help — 帮助
/status — 当前绑定与会话
/bind <码> — 用网页生成的绑定码绑定账号与项目
/unbind — 解除绑定
/project [id] — 查看或切换项目（需已绑定）
/new — 新开会话
/stop — 中断当前任务
/retry — 重试上一轮用户消息
/allow [答案] — 回答 ask_user / 确认
/deny — 拒绝当前提问
/uploads — 说明附件用法
"""


class ServeLock:
    """简单 PID 文件锁，避免本机多开 serve。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or serve_lock_path()

    def acquire(self) -> None:
        import os

        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_file():
            try:
                old = int(self.path.read_text(encoding="utf-8").strip() or "0")
            except Exception:
                old = 0
            if old and _pid_alive(old) and old != os.getpid():
                raise RuntimeError(f"微信 serve 已在运行 (pid={old})")
        self.path.write_text(str(os.getpid()), encoding="utf-8")

    def release(self) -> None:
        with contextlib.suppress(Exception):
            if self.path.is_file():
                self.path.unlink()


def _pid_alive(pid: int) -> bool:
    import os

    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


class WechatBridgeRuntime:
    def __init__(
        self,
        *,
        account_id: str | None = None,
        progress_to_chat: bool | None = None,
        verbose: bool = False,
    ) -> None:
        self.store = WechatAccountStore()
        self.verbose = verbose
        self.progress_to_chat = (
            settings.channels.wechat.progress_to_chat
            if progress_to_chat is None
            else progress_to_chat
        )
        loaded = None
        if account_id:
            data = self.store.load_account(account_id)
            if data:
                loaded = (account_id, data)
        if loaded is None:
            loaded = self.store.load_default_account()
        if loaded is None:
            raise RuntimeError("未找到微信账号，请先运行: icore wechat login")
        self.account_id, acct = loaded
        self.api = WeixinOfficialApi(
            base_url=str(acct.get("base_url") or "https://ilinkai.weixin.qq.com"),
            token=str(acct.get("token") or ""),
            cdn_base_url=str(
                settings.channels.wechat.cdn_base_url or DEFAULT_CDN_BASE_URL
            ),
        )
        self.transport = WechatTransport(
            account_id=self.account_id,
            api=self.api,
            store=self.store,
            chunk_interval_s=float(settings.channels.wechat.chunk_interval_seconds or 3),
        )
        self._scope_locks: dict[str, asyncio.Lock] = {}
        self._scope_tasks: dict[str, asyncio.Task[Any]] = {}
        self._last_user_text: dict[str, str] = {}
        self._pending_questions: dict[str, str] = {}  # peer -> question_id
        self._running = False
        self._lock = ServeLock()

    def _scope_lock(self, peer_id: str) -> asyncio.Lock:
        if peer_id not in self._scope_locks:
            self._scope_locks[peer_id] = asyncio.Lock()
        return self._scope_locks[peer_id]

    async def start(self) -> None:
        from cancer_claw.runtime import bootstrap

        self._lock.acquire()
        await bootstrap(connect_redis=False)
        self._running = True
        cursor = self.store.load_sync_cursor(self.account_id)
        logger.info("wechat_serve_started account=%s", self.account_id)
        print(f"iCore 微信桥已启动 account={self.account_id}", flush=True)

        while self._running:
            try:
                next_cursor, events = await self.transport.poll_once(cursor)
                if next_cursor != cursor:
                    cursor = next_cursor
                    self.store.save_sync_cursor(self.account_id, cursor)
                for ev in events:
                    asyncio.create_task(self._dispatch(ev))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("wechat_poll_error: %s", e)
                await asyncio.sleep(2)

    async def stop(self) -> None:
        self._running = False
        for task in list(self._scope_tasks.values()):
            task.cancel()
        from cancer_claw.runtime import shutdown

        with contextlib.suppress(Exception):
            await shutdown()
        self._lock.release()

    async def _dispatch(self, ev: InboundEvent) -> None:
        lock = self._scope_lock(ev.peer_id)
        if lock.locked():
            # 忙：允许 /stop /allow /deny；其它提示等待
            cmd = parse_slash_command(ev.text)
            if cmd and cmd.name in {"stop", "allow", "deny"}:
                await self._handle_busy_command(ev, cmd.name, cmd.args)
                return
            await self.transport.send_text(
                ev.peer_id,
                "上一轮任务仍在进行。可发送 /stop 中断，或稍后再试。",
                context_token=ev.context_token,
            )
            return

        async def _run() -> None:
            async with lock:
                await self._handle_event(ev)

        self._scope_tasks[ev.peer_id] = asyncio.create_task(_run())

    async def _handle_busy_command(self, ev: InboundEvent, name: str, args: str) -> None:
        if name == "stop":
            task = self._scope_tasks.get(ev.peer_id)
            if task and not task.done():
                task.cancel()
                await self.transport.send_text(ev.peer_id, "已请求中断。", context_token=ev.context_token)
            return
        if name in {"allow", "deny"}:
            await self._answer_pending(ev, name, args)

    async def _handle_event(self, ev: InboundEvent) -> None:
        cmd = parse_slash_command(ev.text)
        if cmd:
            await self._handle_command(ev, cmd.name, cmd.args)
            return
        # 若有 pending ask_user，把普通文本当答案
        if ev.peer_id in self._pending_questions and ev.text.strip():
            await self._answer_pending(ev, "allow", ev.text.strip())
            return
        await self._run_agent_turn(ev)

    async def _handle_command(self, ev: InboundEvent, name: str, args: str) -> None:
        token = ev.context_token
        name = (name or "").strip().lower()
        args = (args or "").strip()
        logger.info("wechat_command peer=%s name=%r args=%r", ev.peer_id[-8:], name, args[:40])
        if name in {"help", "start"}:
            await self.transport.send_text(ev.peer_id, HELP_TEXT, context_token=token)
            return
        if name == "bind":
            code = args.strip().split()[0] if args.strip() else ""
            if not code:
                await self.transport.send_text(
                    ev.peer_id,
                    "用法：/bind <绑定码>\n请在 iCore 网页「微信渠道」生成绑定码。",
                    context_token=token,
                )
                return
            binding = await binding_svc.consume_bind_code(code, external_scope_id=ev.peer_id)
            if not binding:
                await self.transport.send_text(ev.peer_id, "绑定码无效或已过期。", context_token=token)
                return
            await self.transport.send_text(
                ev.peer_id,
                f"绑定成功。\n项目: {binding.get('project_id')}\n权限: {binding.get('permissions_mode')}",
                context_token=token,
            )
            return
        if name == "unbind":
            ok = await binding_svc.delete_binding(binding_svc.CHANNEL_WECHAT, ev.peer_id)
            await self.transport.send_text(
                ev.peer_id,
                "已解除绑定。" if ok else "当前没有绑定。",
                context_token=token,
            )
            return
        if name == "status":
            await self.transport.send_text(ev.peer_id, await self._status_text(ev.peer_id), context_token=token)
            return
        if name == "uploads":
            await self.transport.send_text(
                ev.peer_id,
                "直接发送图片/文件即可，我会保存到项目 workspace/uploads/ 并用于本轮任务。",
                context_token=token,
            )
            return
        if name == "new":
            b = await binding_svc.get_binding(binding_svc.CHANNEL_WECHAT, ev.peer_id)
            if not b:
                await self.transport.send_text(ev.peer_id, "尚未绑定，请先 /bind <码>", context_token=token)
                return
            await binding_svc.update_binding_session(
                binding_svc.CHANNEL_WECHAT, ev.peer_id, clear_session=True
            )
            await self.transport.send_text(ev.peer_id, "已开启新会话。", context_token=token)
            return
        if name == "project":
            b = await binding_svc.get_binding(binding_svc.CHANNEL_WECHAT, ev.peer_id)
            if not b:
                await self.transport.send_text(ev.peer_id, "尚未绑定，请先 /bind <码>", context_token=token)
                return
            if not args.strip():
                await self.transport.send_text(
                    ev.peer_id,
                    f"当前项目: {b.get('project_id')}\n切换：/project <project_id>",
                    context_token=token,
                )
                return
            pid = args.strip().split()[0]
            project = await load_project(pid)
            if not project:
                await self.transport.send_text(ev.peer_id, f"找不到项目 {pid}", context_token=token)
                return
            await binding_svc.update_binding_session(
                binding_svc.CHANNEL_WECHAT,
                ev.peer_id,
                project_id=pid,
                clear_session=True,
            )
            await self.transport.send_text(ev.peer_id, f"已切换到项目 {pid}（新会话）。", context_token=token)
            return
        if name == "stop":
            await self.transport.send_text(ev.peer_id, "当前没有运行中的任务。", context_token=token)
            return
        if name == "retry":
            last = self._last_user_text.get(ev.peer_id)
            if not last:
                await self.transport.send_text(ev.peer_id, "没有可重试的消息。", context_token=token)
                return
            ev.text = last
            await self._run_agent_turn(ev, is_retry=True)
            return
        if name in {"allow", "deny"}:
            await self._answer_pending(ev, name, args)
            return
        await self.transport.send_text(ev.peer_id, f"未知命令 /{name}。发送 /help 查看帮助。", context_token=token)

    async def _status_text(self, peer_id: str) -> str:
        b = await binding_svc.get_binding(binding_svc.CHANNEL_WECHAT, peer_id)
        if not b:
            return "未绑定。请在网页生成绑定码后发送 /bind <码>。"
        user = await load_user(str(b.get("user_id") or ""))
        project = await load_project(str(b.get("project_id") or ""))
        uname = (user or {}).get("username") or b.get("user_id")
        pname = (project or {}).get("name") or b.get("project_id")
        return (
            f"账号: {uname}\n"
            f"项目: {pname} ({b.get('project_id')})\n"
            f"会话: {b.get('session_id') or '（新会话）'}\n"
            f"权限: {b.get('permissions_mode')}\n"
            f"进度推送: {'开' if self.progress_to_chat else '关'}"
        )

    async def _answer_pending(self, ev: InboundEvent, name: str, args: str) -> None:
        qid = self._pending_questions.get(ev.peer_id)
        if not qid:
            await self.transport.send_text(ev.peer_id, "当前没有待回答的问题。", context_token=ev.context_token)
            return
        if name == "deny":
            answer = "拒绝"
        else:
            answer = args.strip() or "确认"
        ok = await submit_answer(qid, answer)
        if ok:
            self._pending_questions.pop(ev.peer_id, None)
            await self.transport.send_text(ev.peer_id, f"已提交回答：{answer}", context_token=ev.context_token)
        else:
            await self.transport.send_text(ev.peer_id, "提交失败（问题可能已过期）。", context_token=ev.context_token)

    async def _run_agent_turn(self, ev: InboundEvent, *, is_retry: bool = False) -> None:
        token = ev.context_token
        binding = await binding_svc.get_binding(binding_svc.CHANNEL_WECHAT, ev.peer_id)
        if not binding:
            await self.transport.send_text(
                ev.peer_id,
                "尚未绑定 iCore 账号。\n1) 打开网页「微信渠道」生成绑定码\n2) 发送 /bind <码>",
                context_token=token,
            )
            return

        user = await load_user(str(binding["user_id"]))
        project = await load_project(str(binding["project_id"]))
        if not user or not project:
            await self.transport.send_text(ev.peer_id, "绑定的用户或项目不存在，请重新 /bind。", context_token=token)
            return

        text = ev.text.strip()
        if not is_retry and text:
            self._last_user_text[ev.peer_id] = text
        if not text and not ev.attachments:
            return

        await self.transport.send_typing(ev.peer_id, start=True, context_token=token)
        typing_task = asyncio.create_task(self._typing_keepalive(ev.peer_id, token))
        narrator = EpisodeAccumulator()
        last_progress_at = 0.0
        final_parts: list[str] = []
        media_paths: list[Path] = []
        root = Path(str(project.get("workspace_path") or "")).expanduser()
        session_id = str(binding.get("session_id") or "") or None
        force_new = not session_id

        try:
            async for event in iter_channel_turn(
                user=user,
                project=project,
                message=text or "请查看附件并处理。",
                session_id=session_id,
                force_new=force_new,
                attachments=ev.attachments,
                verbose=self.verbose,
            ):
                et = str(event.get("type") or "")
                if et == "session_started":
                    sid = str(event.get("session_id") or "")
                    if sid:
                        await binding_svc.update_binding_session(
                            binding_svc.CHANNEL_WECHAT,
                            ev.peer_id,
                            session_id=sid,
                        )
                    continue

                if et == "ask_user_pending":
                    qid = str(event.get("question_id") or "")
                    question = str(event.get("question") or "需要你确认")
                    options = event.get("options") or []
                    self._pending_questions[ev.peer_id] = qid
                    lines = [f"需要确认：{question}"]
                    if options:
                        for i, opt in enumerate(options, 1):
                            lines.append(f"{i}. {opt}")
                        lines.append("回复选项编号，或 /allow <内容> /deny")
                    else:
                        lines.append("直接回复答案，或 /allow <内容> /deny")
                    await self.transport.send_text(ev.peer_id, "\n".join(lines), context_token=token)
                    continue

                if et == "tool_result":
                    output = str(event.get("output") or event.get("content") or "")
                    for pres in extract_presentations(output):
                        media_paths.extend(presentation_local_paths(pres, root))
                    data = event.get("data") or {}
                    if isinstance(data, dict) and isinstance(data.get("presentation"), dict):
                        media_paths.extend(presentation_local_paths(data["presentation"], root))

                if et == "message":
                    content = str(event.get("content") or event.get("text") or "").strip()
                    if content:
                        final_parts.append(content)

                if self.progress_to_chat:
                    line = narrator.feed(event)
                    if line and (time.monotonic() - last_progress_at) >= 3.0:
                        last_progress_at = time.monotonic()
                        await self.transport.send_text(ev.peer_id, line, context_token=token)

                if et == "error":
                    err = str(event.get("content") or event.get("error") or "未知错误")
                    await self.transport.send_text(ev.peer_id, f"执行失败：{err}", context_token=token)

            # 剩余进度
            if self.progress_to_chat:
                rem = narrator.flush_remaining()
                if rem:
                    await self.transport.send_text(ev.peer_id, rem, context_token=token)

            final = "\n\n".join(final_parts).strip()
            if final:
                await self.transport.send_text(ev.peer_id, final, context_token=token)
            elif not media_paths:
                await self.transport.send_text(ev.peer_id, "本轮已完成（无文本回复）。", context_token=token)

            # 媒体回传（去重）
            seen: set[str] = set()
            for path in media_paths:
                key = str(path.resolve())
                if key in seen:
                    continue
                seen.add(key)
                try:
                    await self.transport.send_media(ev.peer_id, path, context_token=token)
                except Exception as e:
                    await self.transport.send_text(
                        ev.peer_id,
                        f"产物发送失败（{path.name}）：{e}\n请在 iCore 网页查看。",
                        context_token=token,
                    )
        except asyncio.CancelledError:
            await self.transport.send_text(ev.peer_id, "任务已中断。", context_token=token)
            raise
        except Exception as e:
            logger.exception("wechat_turn_failed")
            await self.transport.send_text(ev.peer_id, f"执行异常：{e}", context_token=token)
        finally:
            typing_task.cancel()
            with contextlib.suppress(Exception):
                await typing_task
            await self.transport.send_typing(ev.peer_id, start=False, context_token=token)

    async def _typing_keepalive(self, peer_id: str, context_token: str | None) -> None:
        try:
            while True:
                await asyncio.sleep(8)
                await self.transport.send_typing(peer_id, start=True, context_token=context_token)
        except asyncio.CancelledError:
            return

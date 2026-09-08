"""icore wechat 子命令：login / serve / status。"""

from __future__ import annotations

import argparse
import asyncio
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="icore wechat",
        description="iCore 微信本机桥（iLink Bot）",
    )
    sub = parser.add_subparsers(dest="action", required=True)

    p_login = sub.add_parser("login", help="扫码登录微信 Bot 账号")
    p_login.add_argument("--timeout", type=int, default=480, help="扫码超时秒数")

    p_serve = sub.add_parser("serve", help="启动本机长轮询桥")
    p_serve.add_argument("--account", default=None, help="指定 account_id")
    p_serve.add_argument("-v", "--verbose", action="store_true")
    p_serve.add_argument(
        "--no-progress",
        action="store_true",
        help="关闭精简 episode 进度推送",
    )

    sub.add_parser("status", help="查看本地微信账号与桥状态")
    return parser


async def _cmd_login(timeout: int) -> int:
    from cancer_claw.channels.wechat.login import official_qr_login, print_qr_hint, save_qr_png

    async def on_qr(payload: dict) -> None:
        img = str(payload.get("qrcode_img_content") or "")
        png = save_qr_png(img, qrcode=str(payload.get("qrcode") or ""))
        source_url = img if img.startswith("http") else None
        print_qr_hint(str(payload.get("qrcode") or ""), png, source_url)
        if png and png.is_file():
            # Windows：尝试用默认看图软件打开
            try:
                import os

                os.startfile(str(png))  # type: ignore[attr-defined]
            except Exception:
                pass

    async def on_status(payload: dict) -> None:
        print(f"扫码状态: {payload.get('status')}", file=sys.stderr)

    creds = await official_qr_login(timeout_seconds=timeout, on_qr=on_qr, on_status=on_status)
    if not creds:
        print("登录失败或超时。", file=sys.stderr)
        return 1
    print(f"登录成功 account_id={creds['account_id']}")
    print(f"凭证已保存到 ~/.icore/wechat/accounts/")
    return 0


async def _cmd_serve(account: str | None, verbose: bool, no_progress: bool) -> int:
    from cancer_claw.channels.wechat.runtime import WechatBridgeRuntime

    runtime = WechatBridgeRuntime(
        account_id=account,
        progress_to_chat=False if no_progress else None,
        verbose=verbose,
    )
    try:
        await runtime.start()
    except KeyboardInterrupt:
        await runtime.stop()
        return 130
    finally:
        await runtime.stop()
    return 0


def _cmd_status() -> int:
    from cancer_claw.channels.wechat.account_store import WechatAccountStore
    from cancer_claw.channels.wechat.paths import wechat_root

    store = WechatAccountStore()
    accounts = store.list_accounts()
    print(f"状态目录: {wechat_root()}")
    if not accounts:
        print("尚未登录。运行: icore wechat login")
        return 0
    for aid in accounts:
        acct = store.load_account(aid) or {}
        print(f"- {aid}  base={acct.get('base_url')}  saved={acct.get('saved_at')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.action == "login":
        return asyncio.run(_cmd_login(args.timeout))
    if args.action == "serve":
        return asyncio.run(_cmd_serve(args.account, args.verbose, args.no_progress))
    if args.action == "status":
        return _cmd_status()
    parser.error(f"unknown action {args.action}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

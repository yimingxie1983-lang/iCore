

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

import structlog

from cancer_claw.resources.knowledge.craft_store import load_all_crafts, load_craft, save_craft
from cancer_claw.resources.knowledge.schemas import CertificationStatus

logger = structlog.get_logger()

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def certify_craft(craft_id: str, *, certified_by: str) -> bool:

    try:
        rec = load_craft(craft_id)
    except FileNotFoundError:
        print(f"✗ craft 不存在：{craft_id}", file=sys.stderr)
        return False

    rec.certification_status = CertificationStatus.CERTIFIED
    rec.certified_by = certified_by
    rec.certified_at = _now_iso()
    save_craft(rec)

    print(f"✓ craft 已认证：{craft_id} (by {certified_by})")
    return True

def revoke_craft(record_id: str) -> bool:

    try:
        rec = load_craft(record_id)
    except FileNotFoundError:
        print(f"✗ craft 不存在：{record_id}", file=sys.stderr)
        return False

    rec.certification_status = CertificationStatus.UNCERTIFIED
    save_craft(rec)
    print(f"✓ craft 已回滚到 uncertified：{record_id}")
    return True

def list_candidates() -> None:

    rows = [
        r for r in load_all_crafts()
        if r.certification_status == CertificationStatus.UNCERTIFIED
    ]
    rows.sort(key=lambda r: r.id)

    print("\n=== 待认证 Craft ===")
    if not rows:
        print("  （无）")
        return
    for r in rows:
        origin = r.origin_type.value if hasattr(r.origin_type, "value") else str(r.origin_type)
        print(f"  - {r.id}  ({origin})  {r.name or r.id}")

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m cancer_claw.resources.knowledge.certify",
        description="iCore 人工认证 CLI（唯一合法的 certification 升级路径）",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出所有待认证 craft 候选")

    pc = sub.add_parser("craft", help="认证一条 craft")
    pc.add_argument("craft_id")
    pc.add_argument("--by", required=True, help="认证人标识（会写入 certified_by）")

    pr = sub.add_parser("revoke", help="回滚认证（certified → uncertified）")
    pr.add_argument("craft_id")

    return p

def main() -> None:

    args = _build_parser().parse_args(sys.argv[1:])

    if args.cmd == "list":
        list_candidates()
        sys.exit(0)
    elif args.cmd == "craft":
        ok = certify_craft(args.craft_id, certified_by=args.by)
        sys.exit(0 if ok else 1)
    elif args.cmd == "revoke":
        ok = revoke_craft(args.craft_id)
        sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()

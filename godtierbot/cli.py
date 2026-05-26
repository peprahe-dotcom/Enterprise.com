from __future__ import annotations

import argparse
import json
import runpy
import sys
from datetime import datetime, timezone
from pathlib import Path

from godtierbot import __version__
from godtierbot.file_bridge import read_confirm, write_signal
from godtierbot.risk_cop import veto_if_not_armed
from godtierbot.sqlite_store import init_db, log_event, store_paths
from godtierbot.support_bundle import export_support_bundle
from godtierbot.updater_client import apply_update_from_manifest


def _run_module(path: str) -> int:
    runpy.run_module(path, run_name="__main__")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="GodTierBot")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("version")
    sub.add_parser("run-execution")
    sub.add_parser("run-copier")
    sub.add_parser("install-deps")
    sub.add_parser("export-support-bundle")
    bridge_ping = sub.add_parser("bridge-ping")
    bridge_ping.add_argument("--account-id", default="DEFAULT")
    bridge_ping.add_argument("--root", default="")
    bridge_ping.add_argument("--timeout", type=float, default=5.0)
    bridge_open = sub.add_parser("bridge-open-demo")
    bridge_open.add_argument("--account-id", default="DEFAULT")
    bridge_open.add_argument("--symbol", required=True)
    bridge_open.add_argument("--side", choices=["BUY", "SELL"], required=True)
    bridge_open.add_argument("--lots", type=float, required=True)
    bridge_open.add_argument("--sl", type=float, default=0.0)
    bridge_open.add_argument("--tp", type=float, default=0.0)
    bridge_open.add_argument("--root", default="")
    bridge_open.add_argument("--timeout", type=float, default=10.0)
    bridge_open.add_argument("--armed", action="store_true")
    update_p = sub.add_parser("self-update")
    update_p.add_argument("--manifest", default="", help="Manifest URL or local path")
    update_p.add_argument("--yes", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "version":
        sys.stdout.write(f"{__version__}\n")
        return 0
    if args.cmd == "run-execution":
        return _run_module("dynamic_execution_bot")
    if args.cmd == "run-copier":
        return _run_module("trade_copier")
    if args.cmd == "install-deps":
        return _run_module("install_deps")
    if args.cmd == "export-support-bundle":
        out = export_support_bundle()
        sys.stdout.write(f"{out}\n")
        return 0
    if args.cmd == "bridge-ping":
        db = store_paths().db_path
        init_db(db)
        signal_id = f"PING_{int(datetime.now(timezone.utc).timestamp())}"
        root = Path(args.root) if args.root else None
        payload = {"signal_id": signal_id, "action": "PING"}
        write_signal(args.account_id, payload, root=root)
        confirm = read_confirm(signal_id, timeout_s=args.timeout, root=root)
        log_event(db, datetime.now(timezone.utc).isoformat(), "bridge_ping", {"signal": payload, "confirm": confirm})
        sys.stdout.write(json.dumps(confirm or {"status": "TIMEOUT"}, ensure_ascii=False) + "\n")
        return 0
    if args.cmd == "bridge-open-demo":
        decision = veto_if_not_armed(args.armed)
        if not decision.allowed:
            sys.stdout.write(f"{decision.reason}\n")
            return 1
        db = store_paths().db_path
        init_db(db)
        signal_id = f"OPEN_{int(datetime.now(timezone.utc).timestamp())}"
        root = Path(args.root) if args.root else None
        payload = {
            "signal_id": signal_id,
            "action": "OPEN",
            "symbol": args.symbol,
            "side": args.side,
            "lots": args.lots,
            "sl": args.sl,
            "tp": args.tp,
            "comment": "GodTierBot",
        }
        write_signal(args.account_id, payload, root=root)
        confirm = read_confirm(signal_id, timeout_s=args.timeout, root=root)
        log_event(db, datetime.now(timezone.utc).isoformat(), "bridge_open_demo", {"signal": payload, "confirm": confirm})
        sys.stdout.write(json.dumps(confirm or {"status": "TIMEOUT"}, ensure_ascii=False) + "\n")
        return 0
    if args.cmd == "self-update":
        manifest = args.manifest or "updater/version.json"
        msg = apply_update_from_manifest(manifest_url_or_path=manifest, assume_yes=args.yes)
        sys.stdout.write(f"{msg}\n")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

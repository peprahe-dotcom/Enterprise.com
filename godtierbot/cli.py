from __future__ import annotations

import argparse
import runpy
import sys

from godtierbot import __version__
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
    if args.cmd == "self-update":
        manifest = args.manifest or "updater/version.json"
        msg = apply_update_from_manifest(manifest_url_or_path=manifest, assume_yes=args.yes)
        sys.stdout.write(f"{msg}\n")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

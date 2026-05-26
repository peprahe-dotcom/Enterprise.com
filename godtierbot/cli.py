from __future__ import annotations

import argparse
import runpy
import sys

from godtierbot import __version__
from godtierbot.support_bundle import export_support_bundle


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

    return 2


if __name__ == "__main__":
    raise SystemExit(main())


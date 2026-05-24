from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _pip(*args: str) -> None:
    cmd = [sys.executable, "-m", "pip", *args]
    subprocess.check_call(cmd)


def main() -> None:
    root = Path(__file__).resolve().parent
    _pip("install", "--upgrade", "pip")
    _pip("install", "-r", str(root / "requirements.txt"))
    if sys.platform.startswith("win"):
        mt5_req = root / "requirements-windows-mt5.txt"
        if mt5_req.exists():
            _pip("install", "-r", str(mt5_req))


if __name__ == "__main__":
    main()

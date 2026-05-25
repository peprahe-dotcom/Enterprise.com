from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, cwd=ROOT, check=False)
    if p.returncode != 0:
        raise SystemExit(p.returncode)


def build_pyinstaller() -> None:
    dist = ROOT / "dist"
    build = ROOT / "build"
    if dist.exists():
        shutil.rmtree(dist)
    if build.exists():
        shutil.rmtree(build)

    entry = ROOT / "app" / "entrypoint.py"
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--name",
            "GodTierBot",
            "--windowed",
            "--paths",
            str(ROOT / "app"),
            str(entry),
        ]
    )

def ensure_ex5() -> None:
    ex5 = ROOT / "mql5_bridge" / "GodTierBridge.ex5"
    if ex5.exists():
        return
    raise FileNotFoundError(
        "Missing mql5_bridge/GodTierBridge.ex5.\n"
        "Compile it once in MetaEditor:\n"
        "  - Open MetaEditor from MT5\n"
        "  - Open mql5_bridge/GodTierBridge.mq5\n"
        "  - Press F7 (Compile)\n"
        "  - Copy the resulting GodTierBridge.ex5 into mql5_bridge/ next to the .mq5\n"
        "Then rerun: python installer\\build.py"
    )


def find_iscc() -> str:
    env = os.environ.get("ISCC_PATH")
    if env:
        return env
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    raise FileNotFoundError("ISCC.exe not found. Install Inno Setup or set ISCC_PATH.")


def build_inno() -> Path:
    iscc = find_iscc()
    iss = ROOT / "installer" / "GodTierBot.iss"
    run([iscc, str(iss)])
    out = ROOT / "installer" / "Output" / "GodTierBot-Setup.exe"
    if not out.exists():
        raise FileNotFoundError("Installer output not found.")
    dest_dir = ROOT / "dist_installer"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / out.name
    shutil.copy2(out, dest)
    return dest


def main() -> None:
    ensure_ex5()
    build_pyinstaller()
    exe = build_inno()
    print(exe.as_posix())


if __name__ == "__main__":
    main()

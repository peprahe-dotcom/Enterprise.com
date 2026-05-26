from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--owner", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--installer", required=True)
    p.add_argument("--app-zip", required=True)
    p.add_argument("--out", default="version.json")
    args = p.parse_args()

    version = args.version.lstrip("v")
    installer = Path(args.installer)
    app_zip = Path(args.app_zip)

    base = f"https://github.com/{args.owner}/{args.repo}/releases/download/v{version}"

    payload = {
        "channel": "stable",
        "latest": {
            "version": version,
            "published_at": "",
            "notes": "",
            "assets": {
                "installer_exe": {
                    "name": installer.name,
                    "url": f"{base}/{installer.name}",
                    "sha256": _sha256(installer),
                },
                "app_update_zip": {
                    "name": app_zip.name,
                    "url": f"{base}/{app_zip.name}",
                    "sha256": _sha256(app_zip),
                    "signature": {
                        "type": "sha256_rsa",
                        "public_key_id": "release-signing-key-1",
                        "value": "",
                    },
                },
            },
        },
        "minimum_supported": version,
    }

    out = Path(args.out)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


from __future__ import annotations

import re


_KEY_VALUE_RE = re.compile(
    r"(?i)\b(password|pass|token|api[_-]?key|secret|login)\b\s*[:=]\s*([^\s,;]+)"
)
_JWT_RE = re.compile(r"\beyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\b")
_GITHUB_TOKEN_RE = re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")


def redact_text(text: str) -> str:
    text = _KEY_VALUE_RE.sub(lambda m: f"{m.group(1)}=REDACTED", text)
    text = _JWT_RE.sub("REDACTED", text)
    text = _GITHUB_TOKEN_RE.sub("REDACTED", text)
    return text


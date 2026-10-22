"""Redaction of secrets before anything is written to the audit log."""

from __future__ import annotations

import re
from typing import Any

_SENSITIVE_KEY_RE = re.compile(
    r"(pass(word|wd)?|secret|token|api[_-]?key|apikey|authorization|^auth$|cookie|credential|private[_-]?key)",
    re.IGNORECASE,
)
_INLINE_SECRET_RES = [
    # key=value / key: value pairs whose key looks sensitive
    re.compile(r"(?i)\b((?:pass(?:word|wd)?|secret|token|api[_-]?key|apikey|authorization)\s*[=:]\s*)([^\s&'\",;]+)"),
    # Bearer tokens
    re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._~+/=-]{8,})"),
    # userinfo in URLs: scheme://user:pass@host
    re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s:@]+:[^/\s@]+)@"),
    # Common token formats (GitHub, OpenAI-style, AWS access keys, HF)
    re.compile(r"()\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|hf_[A-Za-z0-9]{20,})\b"),
]


def is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_RE.search(str(key)))


def redact_text(text: str) -> str:
    for rx in _INLINE_SECRET_RES:
        if rx.pattern.startswith("(?i)\\b([a-z][a-z0-9+.-]*://)"):
            text = rx.sub(lambda m: m.group(1) + "[REDACTED]@", text)
        else:
            text = rx.sub(lambda m: m.group(1) + "[REDACTED]", text)
    return text


def redact(value: Any) -> Any:
    """Recursively redact dict values with sensitive keys and secret-looking substrings."""
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if is_sensitive_key(k) and v not in (None, "", False) else redact(v))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value

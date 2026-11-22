"""Credential-shaped strings and e-mail addresses become a marker before text leaves its source.

The one list of patterns: `store_conversation_hook.py` redacts a turn before it reaches the
companion's memory, `command_center/crewd.py` every free text before the web view renders it.
Best effort: the patterns cover the common provider formats, not every secret.
"""

from __future__ import annotations

import re

PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"AGE-SECRET-KEY-1[0-9A-Z]{20,}"),
    # `sk-…` keys, `sk-ant-…` and `sk-proj-…` included
    re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"),
    # GitHub: ghp_, gho_, ghs_ (the gh shim's installation tokens), ghu_, ghr_, and fine-grained PATs
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bsbp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    # a token-shaped rest (RFC 6750 token68), so prose like "Bearer authentication" stays
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*"),
    # HTTP Basic credentials (base64 of user:token, at least one digit, + or /), so "Basic setup" stays
    re.compile(r"(?i)\bBasic\s+(?=[A-Za-z0-9+/]*[0-9+/])[A-Za-z0-9+/]{16,}=*"),
    re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*[\"']?[^\s\"']{12,}"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
)


def redact(text: str, marker: str = "[REDACTED]") -> str:
    """`text` with every match of `PATTERNS` replaced by `marker`."""
    for pattern in PATTERNS:
        text = pattern.sub(marker, text)
    return text

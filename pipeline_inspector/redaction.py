"""Masquage des secrets et des chemins personnels.

S'applique à la lecture (payload stocké, API, exports). Les fichiers
originaux ne sont jamais modifiés : on masque la copie, pas la source.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict

# Jetons et clés reconnaissables
_SECRET_PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}\b"), "sk-***REDACTED***"),
    (re.compile(r"\bsk-or-[A-Za-z0-9_\-]{12,}\b"), "sk-or-***REDACTED***"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "gh***REDACTED***"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "github_pat_***REDACTED***"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]{12,}"), r"\1 ***REDACTED***"),
    # Toute valeur non vide après un mot-clé sensible, sans exiger 8 caractères :
    # `password=hunter2` (7 caractères) passait auparavant en clair.
    (re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|pwd|access[_-]?key)\b"
                r"\s*[:=]\s*(\"[^\"]+\"|'[^']+'|[^\s,;&#]+)"), r"\1=***REDACTED***"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AKIA***REDACTED***"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
     "-----BEGIN PRIVATE KEY-----***REDACTED***"),
]

# Champs JSON dont la valeur doit être masquée quoi qu'il arrive
_SENSITIVE_KEYS = {
    "api_key", "apikey", "token", "access_token", "refresh_token",
    "authorization", "password", "secret", "client_secret", "cookie",
    "set-cookie", "x-lifemean-csrf", "csrf", "csrf_token",
}

_HOME = os.path.expanduser("~").replace("\\", "/")
_WIN_HOME_RE = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+[\\/]?")


def redact_text(text: str, max_len: int = 4000) -> str:
    """Masque les secrets/chemins utilisateur et tronque proprement."""
    if not text:
        return text
    out = str(text)
    for pattern, repl in _SECRET_PATTERNS:
        out = pattern.sub(repl, out)
    out = _WIN_HOME_RE.sub("~/", out)
    if _HOME and _HOME in out:
        out = out.replace(_HOME, "~")
    if len(out) > max_len:
        out = out[:max_len] + f"…[tronqué, {len(out)} caractères au total]"
    return out


def redact_value(value: Any, depth: int = 0) -> Any:
    """Masque récursivement un payload JSON."""
    if depth > 6:
        return "…"
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in value.items():
            if str(k).lower() in _SENSITIVE_KEYS:
                cleaned[k] = "***REDACTED***"
            else:
                cleaned[k] = redact_value(v, depth + 1)
        return cleaned
    if isinstance(value, list):
        return [redact_value(v, depth + 1) for v in value[:200]]
    if isinstance(value, str):
        return redact_text(value)
    return value

"""Canonical LLM credential resolution for Life_mean Lab.

SINGLE source of truth for resolving the LM Studio credentials consumed by
every active runtime path (Settings probe, AutoPilot, DebateEngine manager,
Code Lab, model discovery). No other module may invent its own precedence.

Precedence (highest first):

1. Explicit process environment
   (a variable already set when Life_mean starts — e.g. exported in the shell
   or set system-wide). Never clobbered by the loaders below.
2. Life_mean Settings credential override
   ``<cwd>/overrides/llm.env`` — written by the Settings UI, survives restart.
3. Optional legacy repository ``.env`` fallback.
4. Empty / ``philosophical_council`` default config.

Both loaders are NON-clobbering (they only set variables that are not already
present), which is exactly what makes precedence 1 > 2 > 3 hold at startup.

Secrets are never returned to callers in a loggable way — this module only
hands the key to `resolve_llm_credentials` callers (the LLM client constructors).
Nothing here prints or persists a key beyond the git-ignored override file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

ENV_BASE_URL = "LIFE_MEAN_LLM_BASE_URL"
ENV_API_KEY = "LIFE_MEAN_LLM_API_KEY"
_OVERRIDES_FILE_ENV = "LIFE_MEAN_OVERRIDES_FILE"


def overrides_dir() -> Path:
    """Writable runtime overrides dir (CWD-relative, git-ignored, portable)."""
    env = os.environ.get(_OVERRIDES_FILE_ENV)
    if env:
        return Path(env).parent
    return Path.cwd() / "overrides"


def settings_llm_env_path() -> Path:
    """Path of the Settings credential override file (may not exist)."""
    return overrides_dir() / "llm.env"


def _load_env_file_non_clobber(path: Path) -> None:
    """Load ``KEY=VALUE`` lines into os.environ, setting ONLY unset keys."""
    if not path.exists():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except OSError:  # pragma: no cover - unreadable file, never fatal
        pass


def load_credentials_on_startup() -> None:
    """Seed os.environ from override then legacy .env, both non-clobbering.

    Order + non-clobbering guarantee the documented precedence:
    explicit process env (already set) > Settings override > legacy .env.
    Call exactly once at process startup (module import of the app layers).
    """
    _load_env_file_non_clobber(settings_llm_env_path())
    _load_env_file_non_clobber(Path.cwd() / ".env")


def resolve_llm_credentials(base_url: str = "", api_key: str = "") -> Tuple[str, str]:
    """Return the effective (base_url, api_key) under the canonical precedence.

    ``base_url``/``api_key`` are optional call-provided fallbacks — a live env /
    override value always wins. Never raises; returns empty strings if nothing
    is configured.
    """
    bu = os.environ.get(ENV_BASE_URL, "") or base_url
    key = os.environ.get(ENV_API_KEY, "") or api_key
    if not bu or not key:
        try:  # legacy default config fallback (stable core)
            from philosophical_council.config import Config
            cfg = Config.default().lm_studio
            if not bu:
                bu = cfg.base_url or "http://localhost:1234/v1"
            if not key:
                key = cfg.api_key or ""
        except Exception:  # pragma: no cover
            bu = bu or "http://localhost:1234/v1"
            key = key or ""
    return bu, key or ""


def llm_configured() -> bool:
    """True if a key is resolvable (does NOT imply it authenticates)."""
    return bool(resolve_llm_credentials()[1])

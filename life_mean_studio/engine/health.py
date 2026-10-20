"""
Health checks for Life_mean Studio services.

Pure-Python, stdlib-only module that probes the services Life_mean Studio
depends on:
  - LLM backend (LM Studio / OpenAI-compatible, default http://localhost:1234/v1)
  - Docker dashboard (default http://localhost:8080)
  - Hermes orchestrator (default http://localhost:3000)
  - Local SQLite storage

No secrets are ever printed or logged. The API key is only used in the
Authorization header; its presence is reported as a boolean.

Designed to be testable without Qt and usable from the Services page.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("LifeMean.Studio.Health")

DEFAULT_LLM_BASE = os.environ.get("LIFE_MEAN_LLM_BASE_URL", "http://localhost:1234/v1")
DEFAULT_DASHBOARD_URL = "http://localhost:8080"
DEFAULT_ORCHESTRATOR_URL = "http://localhost:3000"

_TIMEOUT_SECONDS = 3.0


def _load_llm_credentials() -> tuple[str, str]:
    """Return (base_url, api_key) from env or local config files.

    Follows the documented precedence: explicit process env > Settings
    override (overrides/llm.env) > legacy .env. The key itself is only ever
    used in an Authorization header; callers must not log or print it.
    """
    base_url = os.environ.get("LIFE_MEAN_LLM_BASE_URL", "")
    api_key = os.environ.get("LIFE_MEAN_LLM_API_KEY", "")

    if not (base_url and api_key):
        # Minimal non-clobbering load: Settings override first, then .env.
        root = Path(__file__).resolve().parents[2]  # Life_mean root
        candidates = [root / "overrides" / "llm.env", root / ".env"]
        for path in candidates:
            if not path.exists():
                continue
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k == "LIFE_MEAN_LLM_BASE_URL" and not base_url:
                        base_url = v
                    elif k == "LIFE_MEAN_LLM_API_KEY" and not api_key:
                        api_key = v
            except OSError as e:
                logger.warning("Could not read %s: %s", path, e)

    return base_url or DEFAULT_LLM_BASE, api_key


def _resolve_llm_url(base_url: str) -> str:
    """Return a URL the host can reach.

    The dashboard container needs host.docker.internal, but Studio runs on
    the host where localhost is the equivalent. We keep the configured URL
    and only swap the Docker alias for a local health probe fallback.
    """
    return base_url.replace("host.docker.internal", "localhost")


def _http_get(url: str, headers: Optional[Dict[str, str]] = None) -> tuple[int, str]:
    """Perform an HTTP GET with a short timeout. Returns (status_code, body)."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as e:
        # Some servers return 4xx/5xx with a body; read it for diagnostics.
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return e.code, body
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        raise ConnectionError(f"{url}: {e}") from e


@dataclass
class ServiceHealth:
    """Result of a single service health probe."""

    name: str
    status: str  # ok, degraded, error, unknown
    detail: str = ""
    latency_ms: Optional[float] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "latency_ms": self.latency_ms,
            "data": self.data,
        }


def check_llm_backend() -> ServiceHealth:
    """Probe the LLM backend and list available models (authenticated).

    Probes the host-resolved URL first (localhost when the configured base
    uses the Docker alias host.docker.internal), then falls back to the
    configured URL verbatim if that probe fails.
    """
    base_url, api_key = _load_llm_credentials()
    has_key = bool(api_key)
    headers = {"Authorization": f"Bearer {api_key}"} if has_key else {}

    health = ServiceHealth(name="LLM Backend", status="error")
    health.data["base_url"] = base_url
    health.data["auth_configured"] = has_key

    # Prefer the host-reachable URL for a Studio-side health probe.
    candidates = [base_url]
    resolved = _resolve_llm_url(base_url)
    if resolved != base_url:
        candidates.insert(0, resolved)
    health.data["probed_url"] = candidates[0]

    last_error: Optional[str] = None
    last_status: Optional[int] = None
    for url in candidates:
        started = time.perf_counter()
        try:
            status, body = _http_get(f"{url.rstrip('/')}/models", headers=headers)
            health.latency_ms = round((time.perf_counter() - started) * 1000, 1)
            last_status = status

            if status == 200:
                try:
                    payload = json.loads(body)
                    models = [m.get("id") for m in payload.get("data", []) if m.get("id")]
                    health.status = "ok"
                    health.detail = f"Reachable — {len(models)} models available"
                    health.data["model_count"] = len(models)
                    health.data["models"] = models
                    return health
                except (json.JSONDecodeError, TypeError):
                    health.status = "degraded"
                    health.detail = "Reachable but response was not valid JSON"
                    return health
            elif status == 401:
                health.status = "error"
                health.detail = "Authentication required (401) — check API key"
                return health
            else:
                last_error = f"HTTP {status}"
                continue  # try next candidate
        except ConnectionError as e:
            last_error = f"Unreachable: {e}"
            continue  # try next candidate

    health.status = "error"
    health.detail = last_error or "No reachable URL"
    return health


def check_dashboard(url: str = DEFAULT_DASHBOARD_URL) -> ServiceHealth:
    """Probe the Docker dashboard.

    Tries the given URL, then /dashboard (the actual app path) as fallback.
    """
    started = time.perf_counter()
    health = ServiceHealth(name="Dashboard (Docker)", status="error")
    health.data["url"] = url

    candidates = [url.rstrip("/"), f"{url.rstrip('/')}/dashboard"]
    last_error: Optional[str] = None
    for candidate in candidates:
        try:
            status, body = _http_get(candidate)
            health.latency_ms = round((time.perf_counter() - started) * 1000, 1)
            if status == 200:
                health.status = "ok"
                health.data["html_bytes"] = len(body)
                health.data["resolved_url"] = candidate
                health.detail = f"HTTP 200 ({len(body):,} chars served)"
                return health
            last_error = f"HTTP {status}"
        except ConnectionError as e:
            last_error = f"Unreachable: {e}"
            continue

    health.status = "error"
    health.detail = last_error or "No reachable URL"
    return health


def check_orchestrator(url: str = DEFAULT_ORCHESTRATOR_URL) -> ServiceHealth:
    """Probe the Hermes orchestrator (optional service)."""
    started = time.perf_counter()
    health = ServiceHealth(name="Hermes Orchestrator", status="error")
    health.data["url"] = url

    try:
        status, body = _http_get(url)
        health.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        if status < 500:
            health.status = "ok"
            health.detail = f"HTTP {status}"
        else:
            health.status = "degraded"
            health.detail = f"HTTP {status}"
    except ConnectionError as e:
        # Orchestrator is optional — not running is "offline", not a hard error.
        health.status = "error"
        health.detail = f"Unreachable: {e}"

    return health


def check_storage(storage: Any) -> ServiceHealth:
    """Probe local SQLite storage integrity and contents.

    Reuses the storage's own connection (single connection) to avoid a second
    handle on the same file, which Windows locks on.
    """
    health = ServiceHealth(name="Local Storage", status="error")

    try:
        db_path = Path(storage.db_path)
        health.data["db_path"] = str(db_path)
        health.data["db_exists"] = db_path.exists()

        if not db_path.exists():
            health.status = "degraded"
            health.detail = "Database file does not exist yet"
            return health

        # Use the storage's own connection — never open a second handle.
        conn = storage.connect()
        try:
            row = conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )]
            health.data["tables"] = tables

            # Count workflows / prompts if the tables exist
            counts: Dict[str, int] = {}
            for table in ("workflows", "prompts"):
                if table in tables:
                    counts[table] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            health.data["counts"] = counts

            health.status = "ok"
            health.detail = f"SQLite readable — {row[0]} schema objects, {len(tables)} tables"
        finally:
            # Do NOT close: the storage owns this connection. We only probe it.
            pass
    except Exception as e:
        health.status = "error"
        health.detail = f"Storage probe failed: {e}"

    return health


def run_all_health_checks(storage: Any) -> Dict[str, Any]:
    """Run every health check and return a summary dict.

    Never blocks the UI for long: each probe has a 3s timeout and the LLM
    probe is the only one that can take a moment (auth round-trip).
    """
    checks = [
        check_storage(storage),
        check_llm_backend(),
        check_dashboard(),
        check_orchestrator(),
    ]

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checks": [c.to_dict() for c in checks],
    }

    statuses = [c.status for c in checks]
    if all(s == "ok" for s in statuses):
        summary["overall"] = "ok"
    elif "error" in statuses:
        summary["overall"] = "error"
    elif "degraded" in statuses:
        summary["overall"] = "degraded"
    else:
        summary["overall"] = "unknown"

    return summary


def load_available_models() -> List[str]:
    """Return the list of model IDs available on the LLM backend (best-effort)."""
    health = check_llm_backend()
    if health.status == "ok":
        return health.data.get("models", [])
    return []

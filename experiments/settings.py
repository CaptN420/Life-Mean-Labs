"""Settings adapter over the EXISTING Life_mean configuration.

Source of truth is `philosophical_council.config.Config` (already loaded by the
stable core). This module is a SMALL adapter — it does NOT introduce a new
config system or model registry. It exposes a sanitized read of the current
config and supports safe, validated runtime updates for a few settings that are
genuinely editable at runtime.

Persistence: runtime overrides are stored in a JSON file RELATIVE TO THE CWD
(`overrides/settings.json`) so they work from a source checkout AND a wheel
install (never written into the repo or site-packages). Defaults still come
from `Config.default()`.

SECURITY: secret values (api_key) are NEVER returned — only `configured: true`.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_OVERRIDES_PATH_ENV = "LIFE_MEAN_OVERRIDES_FILE"


# ── Safe editable schema ───────────────────────────────────────────────────
# Each entry: human category, type/validator. Only these fields are editable.
_EDITABLE: Dict[str, Dict[str, Any]] = {
    "temperature": {"category": "debate", "min": 0.0, "max": 2.0, "type": "float"},
    "max_tokens": {"category": "debate", "min": 1, "max": 200000, "type": "int"},
    "moderator_max_tokens": {"category": "debate", "min": 1, "max": 200000, "type": "int"},
    "philosopher_max_tokens": {"category": "debate", "min": 1, "max": 200000, "type": "int"},
    "short_term_turns": {"category": "debate", "min": 1, "max": 10000, "type": "int"},
    "mid_term_interval": {"category": "debate", "min": 1, "max": 10000, "type": "int"},
    "long_term_interval": {"category": "debate", "min": 1, "max": 10000, "type": "int"},
    "method": {"category": "router", "enum": ["llm", "round_robin", "weighted", "context_aware"], "type": "str"},
    "prevent_repetition": {"category": "router", "type": "bool"},
    "max_consecutive_same_speaker": {"category": "router", "min": 1, "max": 100, "type": "int"},
    "base_url": {"category": "lm_studio", "type": "url"},
}


def _overrides_path() -> Path:
    env = __import__("os").environ.get(_OVERRIDES_PATH_ENV)
    if env:
        return Path(env)
    return Path.cwd() / "overrides" / "settings.json"


def _load_overrides() -> Dict[str, Any]:
    p = _overrides_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # corrupt override file -> fall back to defaults
        logger.warning("Could not read overrides %s: %s", p, exc)
        return {}


def _save_overrides(overrides: Dict[str, Any]) -> None:
    p = _overrides_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Atomic-ish: write temp then replace, so a failed write never corrupts
    # the previous valid configuration.
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(overrides, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _validate(key: str, value: Any) -> str:
    """Return an error message or '' if valid."""
    spec = _EDITABLE.get(key)
    if spec is None:
        return f"unknown setting '{key}'"
    try:
        if "enum" in spec:
            if value not in spec["enum"]:
                return f"'{key}' must be one of {spec['enum']}"
        elif spec["type"] == "bool":
            if not isinstance(value, bool):
                return f"'{key}' must be a boolean"
        elif spec["type"] == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                return f"'{key}' must be an integer"
            if "min" in spec and value < spec["min"]:
                return f"'{key}' must be >= {spec['min']}"
            if "max" in spec and value > spec["max"]:
                return f"'{key}' must be <= {spec['max']}"
        elif spec["type"] == "float":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return f"'{key}' must be a number"
            value = float(value)
            if "min" in spec and value < spec["min"]:
                return f"'{key}' must be >= {spec['min']}"
            if "max" in spec and value > spec["max"]:
                return f"'{key}' must be <= {spec['max']}"
        elif spec["type"] == "url":
            if not isinstance(value, str) or not (value.startswith("http://") or value.startswith("https://")):
                return f"'{key}' must be an http(s) URL"
    except Exception:  # pragma: no cover
        return f"invalid value for '{key}'"
    return ""


def _backend_models(base_url: str, api_key: str) -> Dict[str, Any]:
    """Probe the backend once (bounded) and return structured, honest status.

    Returns:
        { models: list, error_code: str|None, metadata: dict }

    ``error_code`` is the raw classification (``invalid_api_token`` /
    ``backend_unreachable`` / ``no_models_or_auth`` / ...) so the Settings
    layer can derive reachable / authenticated truthfully. The probe runs in a
    daemon thread with a short join timeout so a silent/hanging backend NEVER
    blocks the single-threaded dashboard server. Never exposes the token.
    """
    result: Dict[str, Any] = {
        "models": [], "error_code": None,
        "metadata": {"backend_error": None, "reachable": None, "authenticated": None},
    }

    def _run() -> None:
        try:
            from code_lab.multiagent import probe_llm
            p = probe_llm(base_url or "http://localhost:1234/v1", api_key or "")
            if p.get("available"):
                result["models"] = sorted(p.get("models") or [])
                result["error_code"] = None
                result["metadata"] = {"backend_error": None, "reachable": True, "authenticated": True}
            else:
                code = p.get("error")
                result["error_code"] = code
                reachable = code not in ("backend_unreachable",) and not (code and "timed out" in code)
                result["metadata"] = {
                    "backend_error": code,
                    "reachable": reachable,
                    "authenticated": False,
                }
        except Exception as exc:  # pragma: no cover
            result["error_code"] = "probe_exception"
            result["metadata"] = {"backend_error": str(exc)[:120], "reachable": False, "authenticated": False}

    import threading
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(4.0)
    if t.is_alive():
        code = "backend_unreachable"
        result["error_code"] = code
        result["metadata"] = {"backend_error": "backend_unreachable (probe timed out)",
                              "reachable": False, "authenticated": False}
    return result


# Friendly, actionable human message per raw error code (never the key).
_ERROR_MESSAGES: Dict[str, str] = {
    "no_models_or_auth": (
        "no models listed — the backend is reachable but the API token is "
        "being rejected or no model is loaded"),
    "invalid_api_token": "invalid LM Studio API token (401)",
    "backend_unreachable": "LM Studio backend unreachable",
    "openai_package_missing": "the 'openai' package is missing",
    "probe_exception": "backend probe failed",
}


# ── Role Template default selection (Settings-owned configuration) ─────────
# EXECUTABLE = a real executor drives this template. philosophical-debate
# currently CONFIGURES nothing (AutoPilot builds the debate agents manually),
# so it is honestly marked NOT_CONNECTED until it is wired in.
_EXECUTABLE_EXECUTORS = {"code_lab"}
_DEBATE_CONNECTED = False
_ROLE_TEMPLATE_SUBSYSTEMS = ("code_lab", "philosophical_debate")


def _role_template_default_overrides(raw: Dict[str, Any]) -> Dict[str, str]:
    """Effective default template id per subsystem (Settings-owned)."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "code_lab": str(raw.get("code_lab", "coding-standard")),
        "philosophical_debate": str(raw.get("philosophical_debate", "philosophical-debate")),
    }


def _role_templates_view(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Settings-safe view of the default templates + honest executability."""
    defaults = _role_template_default_overrides(raw)
    view: Dict[str, Any] = {}
    try:
        from role_templates.registry import get_registry
        reg = get_registry()
        for subsys in _ROLE_TEMPLATE_SUBSYSTEMS:
            tid = defaults[subsys]
            tpl = reg.get_template(tid)
            executor = tpl.executor_type if tpl else ""
            if subsys == "code_lab":
                connected = tpl is not None and executor in _EXECUTABLE_EXECUTORS
            else:
                connected = bool(_DEBATE_CONNECTED)
            view[subsys] = {
                "default_id": tid,
                "name": tpl.name if tpl else "",
                "version": tpl.version if tpl else "",
                "executor_type": executor,
                "connected": connected,
                "executable": connected and tpl is not None,
                "status": "EXECUTABLE" if connected else (
                    "NOT_CONNECTED" if tpl is not None else "UNKNOWN_TEMPLATE"),
            }
    except Exception as e:  # pragma: no cover
        logger.warning("role template view unavailable: %s", e)
        for subsys in _ROLE_TEMPLATE_SUBSYSTEMS:
            view[subsys] = {"default_id": defaults[subsys], "status": "ERROR"}
    return view


def default_role_template(subsystem: str) -> str:
    """Public accessor: the Settings-owned default template id for a subsystem.

    Code Lab / App controllers read their active default here (Runtime §10-11).
    """
    try:
        ov = _load_overrides().get("role_templates", {})
        return _role_template_default_overrides(ov).get(subsystem, "coding-standard")
    except Exception:  # pragma: no cover
        return "coding-standard"


def _current_personas(raw: Dict[str, Any]) -> list:
    """Return persona summaries for the UI (never secret, never full raw)."""
    out = []
    if isinstance(raw, dict):
        for role, pdata in raw.items():
            if not isinstance(pdata, dict):
                continue
            out.append({
                "role": role,
                "name": pdata.get("name", role),
                "color": pdata.get("color", "#888888"),
                "system_prompt": pdata.get("system_prompt", "")[:400],
            })
    return out


def build_settings_snapshot() -> Dict[str, Any]:
    """Immutable snapshot of the RESOLVED Settings at a moment in time.

    Follows the Settings → EXPERIMENT → snapshot config → Stable Core → RAW
    flow: a run captures this once at start so RAW records exactly the
    Settings (Backend / Role Template / Model Pool / Personas / Router) that
    applied, and later Settings edits never re-write history.

    Safe: NEVER includes secrets (only base_url + a configured-flag). Does NOT
    hit the network (no probe) — it is a pure config snapshot.
    """
    import datetime as _dt
    cfg: Dict[str, Any] = {}
    try:
        from philosophical_council.config import Config
        cfg = Config.default().to_dict()
    except Exception:  # pragma: no cover
        cfg = {}
    overrides = _load_overrides()

    # Backend base_url (resolvable without probing; the key itself is excluded).
    try:
        from code_lab.multiagent import resolve_llm_credentials
        bu, key = resolve_llm_credentials(
            base_url=cfg.get("lm_studio", {}).get("base_url", ""),
            api_key=cfg.get("lm_studio", {}).get("api_key", ""))
    except Exception:  # pragma: no cover
        bu = cfg.get("lm_studio", {}).get("base_url", ""); key = ""

    # Effective role_templates defaults (Settings-owned).
    rt_merged = {**cfg.get("role_templates", {}), **overrides.get("role_templates", {})}
    roles_eff = cfg.get("models", {}) or {}
    roles_eff = {**roles_eff, **overrides.get("models", {})} if isinstance(overrides.get("models"), dict) else roles_eff
    personas = _current_personas(cfg.get("personas", {}) or {})
    router = cfg.get("router", {}) or {}

    return {
        "captured_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "backend": {
            "base_url": bu,
            "api_key_configured": bool(key),
        },
        "role_templates": _role_templates_view(rt_merged),
        "model_pool": {r: (m or "") for r, m in roles_eff.items()},
        "personas": [{"role": p["role"], "name": p["name"]} for p in personas],
        "router": {
            "method": router.get("method", "llm"),
            "prevent_repetition": router.get("prevent_repetition", True),
            "max_consecutive_same_speaker": router.get("max_consecutive_same_speaker", 1),
        },
    }

def get_settings() -> Dict[str, Any]:
    """Return sanitized current settings. NEVER returns secret values."""
    try:
        from philosophical_council.config import Config
        cfg = Config.default().to_dict()
    except Exception as exc:
        logger.warning("Could not load Config: %s", exc)
        cfg = {}

    base_url = cfg.get("lm_studio", {}).get("base_url", "")
    api_key = cfg.get("lm_studio", {}).get("api_key", "")
    overrides = _load_overrides()
    # Apply runtime overrides on top of defaults.
    for k, spec in _EDITABLE.items():
        ov = overrides.get(k)
        if ov is not None:
            target = cfg.setdefault(spec["category"], {})
            target[k] = ov
    # Apply model-per-role and persona overrides (set via the Settings UI).
    if isinstance(overrides.get("models"), dict):
        cfg.setdefault("models", {}).update(overrides["models"])
    if isinstance(overrides.get("personas"), dict):
        cfg["personas"] = overrides["personas"]
    # Role Template defaults are Settings-owned configuration (S10/S11/S18).
    if isinstance(overrides.get("role_templates"), dict):
        cfg["role_templates"] = {**cfg.get("role_templates", {}), **overrides["role_templates"]}

    # ── LLM credentials: resolve from the LIVE environment (which itself is
    # seeded from .env and from any key the user set via Settings). We never
    # return the secret — only whether one is configured. The base_url IS safe
    # to show. ──
    try:
        from code_lab.multiagent import resolve_llm_credentials
        live_bu, live_key = resolve_llm_credentials(base_url=base_url, api_key=api_key)
    except Exception:
        live_bu, live_key = base_url, api_key

    # Honest backend diagnostic (no silent empty list): ONE bounded probe fetch
    # returns models + error classification. From it we derive reachable /
    # authenticated truthfully. Never blocks the single-threaded server.
    _bm = _backend_models(live_bu, live_key)
    avail = _bm.get("models", [])
    err_code = _bm.get("error_code")
    _md = _bm.get("metadata", {})
    backend_reachable = bool(_md.get("reachable"))
    authenticated = bool(_md.get("authenticated"))

    debate = cfg.get("debate", {})
    router = cfg.get("router", {})
    models = cfg.get("models", {})

    return {
        "general": {
            "source_of_truth": "philosophical_council.config.Config",
            "writable_cwd": {
                "value": str(Path.cwd()),
                "writable": True,
            },
        },
        "inference": {
            "base_url": live_bu,
            # NEVER the secret itself — only the configured flag.
            "api_key_configured": bool(live_key),
            # Hostile-free, truthful backend status (§6 of runtime pass).
            "credentials_configured": bool(live_key),
            "backend_reachable": backend_reachable,
            "authenticated": authenticated,
            "models_available": bool(avail),
            "backend_error": _ERROR_MESSAGES.get(err_code, err_code) if err_code else None,
            "backend_error_code": err_code,
            # Backward-compatible aliases (deprecated: use the fields above).
            "runtime_available": bool(live_key),
            "llm_error": _ERROR_MESSAGES.get(err_code, err_code) if err_code else None,
            "models_available_legacy": bool(avail),
        },
        "debate": {
            "temperature": debate.get("temperature"),
            "max_tokens": debate.get("max_tokens"),
            "moderator_max_tokens": debate.get("moderator_max_tokens"),
            "philosopher_max_tokens": debate.get("philosopher_max_tokens"),
            "short_term_turns": debate.get("short_term_turns"),
            "mid_term_interval": debate.get("mid_term_interval"),
            "long_term_interval": debate.get("long_term_interval"),
        },
        "models": {
            "existentialist": models.get("existentialist", ""),
            "stoic": models.get("stoic", ""),
            "nihilist": models.get("nihilist", ""),
            "spiritual": models.get("spiritual", ""),
            "skeptic": models.get("skeptic", ""),
            "pragmatist": models.get("pragmatist", ""),
            "moderator": models.get("moderator", ""),
        },
        "available_models": avail,
        "personas": _current_personas(cfg.get("personas", {})),
        "role_templates": _role_templates_view(cfg.get("role_templates", {})),
        "router": {
            "method": router.get("method", "llm"),
            "prevent_repetition": router.get("prevent_repetition", True),
            "max_consecutive_same_speaker": router.get("max_consecutive_same_speaker", 1),
        },
        "restart_required": False,
        "editable": sorted(_EDITABLE.keys()),
    }


def update_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a validated, safe partial update.

    Only keys in _EDITABLE (and belonging to the mapped category) are allowed.
    Returns the new sanitized settings. Raises ValueError on invalid input.
    """
    if not isinstance(patch, dict):
        raise ValueError("Settings update must be a JSON object")

    overrides = _load_overrides()
    errors: Dict[str, str] = {}
    for key, value in patch.items():
        if key == "role_templates":
            # Settings-owned default template per subsystem (S10/S11/S18).
            # Validate the id exists in the registry BEFORE persisting.
            try:
                from role_templates.registry import get_registry
                reg = get_registry()
            except Exception as exc:  # pragma: no cover
                errors[key] = f"role template registry unavailable: {exc}"
                continue
            if not isinstance(value, dict):
                errors[key] = "'role_templates' must be an object"
                continue
            clean = {}
            for subsys, tid in value.items():
                if subsys not in _ROLE_TEMPLATE_SUBSYSTEMS:
                    errors[f"role_templates.{subsys}"] = f"unknown subsystem '{subsys}'"
                    continue
                tid = str(tid).strip() if tid is not None else ""
                tpl = reg.get_template(tid) if tid else None
                if not tpl:
                    errors[f"role_templates.{subsys}"] = f"unknown template '{tid}'"
                    continue
                clean[subsys] = tid
            if not errors.get(key):
                existing = overrides.get("role_templates", {})
                if isinstance(existing, dict):
                    existing.update(clean)
                else:
                    existing = clean
                overrides["role_templates"] = existing
            continue
        if key == "models":
            # model-per-role override: dict role -> model id string (or "" = dynamic)
            if not isinstance(value, dict):
                errors[key] = "'models' must be an object"
                continue
            clean = {}
            allow_roles = {"existentialist", "stoic", "nihilist", "spiritual",
                           "skeptic", "pragmatist", "moderator"}
            for role, model in value.items():
                if role not in allow_roles:
                    errors[f"models.{role}"] = f"unknown role '{role}'"
                elif not isinstance(model, str):
                    errors[f"models.{role}"] = "model must be a string"
                else:
                    clean[role] = model
            if not errors.get(key):
                # Merge onto existing model overrides (role-keyed).
                existing_models = overrides.get("models", {})
                if not isinstance(existing_models, dict):
                    existing_models = {}
                existing_models.update({k: v for k, v in clean.items()})
                overrides["models"] = existing_models
            continue
        if key == "personas":
            # persona list override: dict role -> {name, color, system_prompt}
            if not isinstance(value, dict):
                errors[key] = "'personas' must be an object mapping role->config"
                continue
            clean = {}
            for role, pdata in value.items():
                if not isinstance(pdata, dict):
                    errors[f"personas.{role}"] = "persona must be an object"
                    continue
                name = str(pdata.get("name", "")).strip()
                system_prompt = str(pdata.get("system_prompt", "")).strip()
                color = str(pdata.get("color", "#888888")).strip()
                if not name:
                    errors[f"personas.{role}"] = "persona name is required"
                    continue
                if not system_prompt:
                    errors[f"personas.{role}"] = "persona system_prompt is required"
                    continue
                clean[role] = {"name": name, "color": color, "system_prompt": system_prompt}
            if "personas" not in errors:
                # Merge onto the CURRENT effective persona set (built-in
                # defaults + any prior overrides) and persist the full result.
                try:
                    from philosophical_council.config import Config
                    _eff = Config.default().personas
                except Exception:
                    _eff = {}
                _merged = {r: {"name": p.name, "color": p.color,
                               "system_prompt": p.system_prompt}
                           for r, p in (_eff or {}).items()}
                _prior = overrides.get("personas", {})
                if isinstance(_prior, dict):
                    _merged.update(_prior)
                _merged.update(clean)
                overrides["personas"] = _merged
            continue
        err = _validate(key, value)
        if err:
            errors[key] = err
        else:
            overrides[key] = value
    if errors:
        # Nothing is written on a failed update — previous config stays intact.
        raise ValueError(json.dumps(errors))

    _save_overrides(overrides)
    # Reflect overrides back onto the config source so live behavior follows.
    try:
        from philosophical_council.config import Config
        cfg = Config.default()
        for key, spec in _EDITABLE.items():
            if key in overrides:
                setattr(getattr(cfg, spec["category"]), key, overrides[key])
        if isinstance(overrides.get("models"), dict):
            for role, model in overrides["models"].items():
                setattr(cfg.models, role, model)
        if isinstance(overrides.get("personas"), dict):
            from philosophical_council.config import PersonaConfig
            new_personas = {}
            for role, pdata in overrides["personas"].items():
                new_personas[role] = PersonaConfig(
                    name=pdata["name"], color=pdata.get("color", "#888888"),
                    system_prompt=pdata["system_prompt"], role_id=role,
                )
            cfg.personas = new_personas
    except Exception as exc:  # pragma: no cover
        logger.warning("Applied overrides but could not mirror onto Config: %s", exc)

    return get_settings()


def delete_persona(role: str) -> Dict[str, Any]:
    """Remove a persona (and its model-per-role override if any)."""
    overrides = _load_overrides()
    personas = overrides.get("personas", {})
    if not isinstance(personas, dict) or role not in personas:
        # Not present in overrides -> nothing to delete (harmless no-op that
        # still returns the current state).
        return get_settings()
    del personas[role]
    if personas:
        overrides["personas"] = personas
    else:
        # Removing the last override persona must NOT wipe the built-in
        # defaults — drop the override key entirely so the defaults show again.
        overrides.pop("personas", None)
    _save_overrides(overrides)
    logger.info("Deleted persona '%s'", role)
    return get_settings()


def _credentials_env_path() -> Path:
    env = os.environ.get(_OVERRIDES_PATH_ENV)
    if env:
        return Path(env).parent / "llm.env"
    return Path.cwd() / "overrides" / "llm.env"


def update_llm_credentials(base_url: str = "", api_key: str = "") -> Dict[str, Any]:
    """Securely store the LM Studio base URL and API key.

    The key is written to a git-ignored env file (never the repo, never
    returned by any GET). Only the configured flag is surfaced.

    - api_key is NEVER read back after being written; an empty string means
      "leave unchanged".
    """
    env_path = _credentials_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)

    # Load any existing overrides file to preserve unset values.
    existing: Dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip().strip('"').strip("'")
    # Validate URL if a base_url is provided.
    if base_url:
        if not (base_url.startswith("http://") or base_url.startswith("https://")):
            raise ValueError("base_url must be an http(s) URL")

    new_env = dict(existing)
    if base_url:
        new_env["LIFE_MEAN_LLM_BASE_URL"] = base_url
    if api_key:
        new_env["LIFE_MEAN_LLM_API_KEY"] = api_key

    lines = [f"{k}={v}" for k, v in new_env.items()]
    tmp = env_path.with_suffix(".env.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(env_path)

    # Apply to the live process environment immediately.
    for k, v in new_env.items():
        os.environ[k] = v

    logger.info("Updated LLM credentials (key configured: %s)", bool(api_key))
    return get_settings()

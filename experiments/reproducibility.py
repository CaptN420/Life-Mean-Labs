"""Reproducibility metadata for an experiment manifest.

A result is only reproducible if you know *what* produced it. This module
collects the immutable context around a run and returns it as one JSON-safe
block, so ``export_manifest()`` can carry it alongside the config, prompt,
events and traces.

What is recorded (and why):

  engine      — package name + version, so a manifest states which engine built it
  environment — Python version/implementation, OS, architecture
  dependencies— sha256 of the declared dependency files (pyproject.toml, uv.lock)
  git         — commit sha + dirty flag when the engine runs from a checkout
  seed        — the seed actually used (None when the run does not use one)
  models      — model ids the agents were assigned (LLM runs are NOT promised
                to be deterministic; the ids just make the run identifiable)
  tools       — tools the run was allowed to use

Deliberately excluded: API keys, tokens, environment variable *values*,
absolute user paths. Only versions, ids and content hashes leave this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ENGINE_NAME = "life_mean_lab"

# Declared dependency files, relative to the repo root. Missing ones are
# reported as absent rather than silently skipped.
_DEP_FILES = ("pyproject.toml", "uv.lock")

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _read_engine_version() -> str:
    """Installed distribution version, falling back to pyproject, then a marker.

    Never invents a plausible version: an unknown version is reported as
    ``"unknown"`` so a manifest cannot claim a provenance it does not have.
    """
    try:
        from importlib.metadata import version

        return version(ENGINE_NAME)
    except Exception:  # distribution not installed (source checkout)
        pass
    try:
        import tomllib

        data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        declared = data.get("project", {}).get("version")
        if declared:
            return str(declared)
    except Exception:  # pragma: no cover - defensive
        pass
    return "unknown"


def engine_block() -> Dict[str, Any]:
    return {"name": ENGINE_NAME, "version": _read_engine_version()}


def environment_block() -> Dict[str, Any]:
    return {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "executable_kind": "python" if not getattr(sys, "frozen", False) else "frozen",
    }


def _sha256_file(path: Path) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def dependency_block() -> Dict[str, Any]:
    """Content hashes of the declared dependency files (never their contents)."""
    files: Dict[str, Any] = {}
    combined = hashlib.sha256()
    for name in _DEP_FILES:
        path = _REPO_ROOT / name
        digest = _sha256_file(path)
        files[name] = digest
        if digest:
            combined.update(name.encode())
            combined.update(digest.encode())
    return {"files": files, "combined_sha256": combined.hexdigest() if any(files.values()) else None}


def git_block() -> Dict[str, Any]:
    """Commit sha + dirty flag when running from a checkout.

    Uses git only if it answers quickly; otherwise reports ``None`` — a missing
    VCS is not an error, but it is stated, not hidden.
    """
    try:
        sha = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        if sha.returncode != 0:
            return {"commit": None, "dirty": None}
        status = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, timeout=3,
        )
        dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
        return {"commit": sha.stdout.strip(), "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}


def _collect_models(config: Optional[Dict[str, Any]],
                    models: Optional[Iterable[Any]]) -> List[str]:
    """Union of explicit model ids and the agents' model assignments."""
    found: List[str] = []
    for m in models or []:
        if m is not None:
            found.append(str(m))
    cfg = config or {}
    for agent in cfg.get("agents", []) or []:
        if isinstance(agent, dict):
            assigned = agent.get("model_assignment") or agent.get("model")
            if assigned:
                found.append(str(assigned))
    role_models = cfg.get("role_models") or {}
    if isinstance(role_models, dict):
        found.extend(str(v) for v in role_models.values() if v)
    # stable, de-duplicated, no None/empty
    return sorted({m for m in found if m and m != "None"})


def build_reproducibility_block(
    *,
    config: Optional[Dict[str, Any]] = None,
    seed: Optional[int] = None,
    models: Optional[Iterable[Any]] = None,
    tools: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Assemble the reproducibility block stored in an experiment manifest.

    ``config`` is the run's configuration snapshot; the seed is read from it
    when not passed explicitly, so a manifest cannot silently omit the seed it
    actually ran with.
    """
    cfg = config or {}
    effective_seed = seed if seed is not None else cfg.get("seed")
    tool_ids = sorted({str(t) for t in (tools or []) if t})
    if not tool_ids:
        for agent in cfg.get("agents", []) or []:
            if isinstance(agent, dict):
                tool_ids.extend(str(t) for t in agent.get("allowed_tools", []) or [])
        tool_ids = sorted(set(tool_ids))

    return {
        "engine": engine_block(),
        "environment": environment_block(),
        "dependencies": dependency_block(),
        "git": git_block(),
        "seed": effective_seed,
        "deterministic": bool(cfg.get("deterministic", False)),
        "models": _collect_models(cfg, models),
        "tools": tool_ids,
        "generator_version": cfg.get("generator_version"),
        "prompt_version": cfg.get("prompt_version"),
    }


def manifest_fingerprint(block: Dict[str, Any]) -> str:
    """Stable hash of the reproducibility block (ignores volatile fields).

    Two runs with identical engine/deps/env/seed/models/tools produce the same
    fingerprint, which is what lets a reviewer say "same conditions".
    """
    payload = {
        "engine": block.get("engine"),
        "environment": block.get("environment"),
        "dependencies": block.get("dependencies"),
        "seed": block.get("seed"),
        "models": block.get("models"),
        "tools": block.get("tools"),
        "generator_version": block.get("generator_version"),
        "prompt_version": block.get("prompt_version"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()

"""Code Lab configuration (V1).

Deterministic-first configuration for Code Lab runs.
Model roles are NOT hardcoded here — they remain configurable/routable.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no third-party dep). Sets only unset vars."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", path)
    if not os.path.exists(p):
        return
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


# Seed os.environ from Life_mean Settings credentials (overrides/llm.env, the
# canonical Settings database) then the optional legacy .env, both NON-clobbering.
# This makes a token saved in Settings survive application restart with the
# documented precedence (explicit process env > Settings override > legacy .env).
from experiments.credentials import load_credentials_on_startup  # noqa: E402
load_credentials_on_startup()

# Legacy root .env is loaded LAST and non-clobbering, so it NEVER overrides a
# Settings-saved credential or an explicit process env (precedence preserved).
_load_dotenv()

# LLM endpoint/token come from environment (protected, git-ignored) or
# from the existing philosophical_council config. Never hardcoded here.
ENV_LLM_BASE = os.environ.get("LIFE_MEAN_LLM_BASE_URL", "")
ENV_LLM_KEY = os.environ.get("LIFE_MEAN_LLM_API_KEY", "")


@dataclass
class CodeLabConfig:
    """Configuration for a single Code Lab run.

    Reproducible: every field is recorded in RAW provenance.
    """

    # User inputs
    prompt: str = "Create a Python function fibonacci(n) with unit tests."
    project_name: str = "my_project"
    language: str = "Python"

    # Pipeline controls
    max_iterations: int = 10
    multi_agent: bool = True
    run_tests: bool = True
    deterministic_validation: bool = True
    reflection: bool = True

    # Role Template (VERSIONED) — configures the team WITHOUT hardcoding models.
    # template_id selects a built-in / registered template (default "coding-standard").
    # role_models maps role_id -> model id (CONFIGURED model), separate from the
    # template; empty value = dynamic routing via the existing router/fallback.
    template_id: str = "coding-standard"
    role_models: Dict[str, str] = field(default_factory=dict)

    # Reproducibility
    seed: int = 42

    # Runtime guards (security boundary)
    timeout_seconds: int = 60
    max_output_bytes: int = 1_000_000
    allowed_commands: tuple = ("python", "pytest", "python3")
    max_files: int = 200

    # Tracking
    run_id: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.run_id:
            self.run_id = f"codelab_{uuid.uuid4().hex[:10]}"
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "project_name": self.project_name,
            "language": self.language,
            "max_iterations": self.max_iterations,
            "multi_agent": self.multi_agent,
            "run_tests": self.run_tests,
            "deterministic_validation": self.deterministic_validation,
            "reflection": self.reflection,
            "template_id": self.template_id,
            "role_models": dict(self.role_models),
            "seed": self.seed,
            "timeout_seconds": self.timeout_seconds,
            "max_output_bytes": self.max_output_bytes,
            "allowed_commands": list(self.allowed_commands),
            "run_id": self.run_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CodeLabConfig":
        return cls(
            prompt=data.get("prompt", "Create a Python function fibonacci(n) with unit tests."),
            project_name=data.get("project_name", "my_project"),
            language=data.get("language", "Python"),
            max_iterations=int(data.get("max_iterations", 10)),
            multi_agent=_to_bool(data.get("multi_agent", True)),
            run_tests=_to_bool(data.get("run_tests", True)),
            deterministic_validation=_to_bool(data.get("deterministic_validation", True)),
            reflection=_to_bool(data.get("reflection", True)),
            template_id=str(data.get("template_id", "coding-standard")),
            role_models=dict(data.get("role_models", {}) or {}),
            seed=int(data.get("seed", 42)),
            timeout_seconds=int(data.get("timeout_seconds", 60)),
            max_output_bytes=int(data.get("max_output_bytes", 1_000_000)),
            allowed_commands=tuple(data.get("allowed_commands", ("python", "pytest", "python3"))),
            run_id=data.get("run_id", ""),
            created_at=data.get("created_at", ""),
        )


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "1", "on", "yes")

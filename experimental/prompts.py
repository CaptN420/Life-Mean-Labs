"""System prompt composition (spec §7) — explicit layers so a single layer
(Role, Persona, Skills, Context, Capabilities, Constraints, Output) can change
without rewriting the whole prompt. The FINAL rendered prompt and each
component are recorded; their hashes ride in frozen provenance.

The templates in Settings remain the defaults; the Experimental Sandbox may
override parts for ONE experiment only — the override enters the frozen
snapshot, never Settings.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional


def _layer(text: str, label: str) -> str:
    text = (text or "").strip()
    return f"{label}.\n{text}" if text else ""


def compose_system_prompt(
    *,
    role: str = "",
    persona: str = "",
    skills: Optional[list] = None,
    context: str = "",
    capabilities: Optional[list] = None,
    constraints: Optional[list] = None,
    output_contract: str = "",
) -> Dict[str, Any]:
    """Build the 7-layer system prompt. Returns ``{components, system_prompt}``
    so provenance can store both the final text and the per-layer texts (and
    derive their hashes)."""
    components: Dict[str, str] = {
        "role": _layer(f"You are the {role}." if role else "", "ROLE"),
        "persona": _layer(persona if persona else "", "PERSONA"),
        "skills": _layer("\n".join(f"- {s}" for s in (skills or [])), "SKILLS") if skills else "",
        "context": _layer(context, "EXPERIMENT CONTEXT"),
        "capabilities": _layer("\n".join(f"- {c}" for c in (capabilities or [])),
                               "AVAILABLE CAPABILITIES") if capabilities else "",
        "constraints": _layer("\n".join(f"- {c}" for c in (constraints or [])),
                              "CONSTRAINTS") if constraints else "",
        "output": _layer(output_contract, "OUTPUT CONTRACT") if output_contract else "",
    }
    system_prompt = "\n\n".join(v for v in components.values() if v.strip()) or (
        f"You are the {role}." if role else "")
    return {"components": components, "system_prompt": system_prompt}


def component_hashes(components: Dict[str, str]) -> Dict[str, str]:
    """SHA-256 of each prompt layer (provenance: changing ONE persona layer
    flips only that layer's hash)."""
    return {k: hashlib.sha256(v.encode("utf-8")).hexdigest()
            for k, v in (components or {}).items() if v}


def prompt_hash(system_prompt: str) -> str:
    return hashlib.sha256((system_prompt or "").encode("utf-8")).hexdigest()


def snapshot_hash(block: Any) -> str:
    """Deterministic hash for an arbitrary serializable provenance block."""
    return hashlib.sha256(
        json.dumps(block, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
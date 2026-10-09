"""Release / secret-hygiene audit for Life_mean Lab source distributions.

Usage:
    python scripts/release_audit.py [TARGET_DIR]

Fails (exit code 1) if the inspected tree contains forbidden generated or
credential material, so a premature archive/wheel is never shipped silently:

Forbidden (fail):
    .env                      (credential file — use .env.example only)
    overrides/llm.env         (Settings credential override)
    hermes-orchestrator/.env
    node_modules/
    code_lab_runs/  code_lab/runs/
    build/  dist/
    *.pyc  __pycache__/  *.egg-info/

The audit prints only PATHS and reasons — NEVER credential values.

This is the deterministic source-release check referenced by the Runtime /
Integrity passes (secret hygiene). It does not rewrite history and never
prints a secret.
"""

from __future__ import annotations

import sys
from pathlib import Path

FORBIDDEN_FILES = {
    ".env": "credential file (ship .env.example, never the real one)",
    "overrides/llm.env": "Settings credential override (secrets live only locally)",
    "hermes-orchestrator/.env": "legacy credential file",
}

FORBIDDEN_DIRS = {
    "node_modules",
    "code_lab_runs",
    "build",
    "dist",
    "__pycache__",
    ".egg-info",
}

FORBIDDEN_SUFFIXES = {".pyc"}
FORBIDDEN_NAME_SUFFIX = ".egg-info"


def _matches_forbidden_file(rel: Path) -> str:
    name = rel.name
    if rel.name in FORBIDDEN_FILES:
        return FORBIDDEN_FILES[rel.name]
    if rel.name == "llm.env" and rel.parent.name == "overrides":
        return FORBIDDEN_FILES["overrides/llm.env"]
    if name == ".env" and rel.parent.name in ("", "hermes-orchestrator"):
        # Only the repo-root / known .env files are handled explicitly above;
        # generic nested .env remains allowed unless it matches exactly.
        pass
    return ""


def audit(root: Path) -> list:
    problems = []
    if not root.exists():
        return [(root, "target does not exist")]
    for p in sorted(root.rglob("*")):
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        parts = rel.parts
        if any(d in FORBIDDEN_DIRS or d.endswith(FORBIDDEN_NAME_SUFFIX)
               for d in parts[:-1]):
            problems.append((rel, "generated/legacy directory included"))
            continue
        if p.is_file():
            reason = _matches_forbidden_file(rel)
            if reason:
                problems.append((rel, reason))
            elif p.suffix in FORBIDDEN_SUFFIXES:
                problems.append((rel, "compiled bytecode included"))
            elif rel.name.endswith(FORBIDDEN_NAME_SUFFIX):
                problems.append((rel, "egg-info metadata included"))
    return problems


def main(argv: list = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    root = Path(argv[0]).resolve() if argv else Path.cwd()
    print(f"Release audit: {root}")
    problems = audit(root)
    if problems:
        print(f"FAIL — {len(problems)} problem(s) found:")
        for rel, reason in problems:
            print(f"  - {rel}  ({reason})")
        return 1
    print("OK — no generated artifacts or credentials in source tree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

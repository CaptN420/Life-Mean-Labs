"""Packages API — expose the local .lmpack catalogue to the dashboard.

Why this exists: the readers worked (Studio's PackageManager, and since R2 the
core LLMPackager) but a user had no way to see, inspect or validate a package —
`/api/packages` simply did not exist. This mixin adds that surface, read-only.

Endpoints:
  GET  /api/packages                  -> catalogue of ./lmpack/*.lmpack
  GET  /api/packages/inspect?path=X   -> one package: manifest, agents, verdicts
  POST /api/packages/validate {path}  -> validation from BOTH readers

Rules kept here:
- path confinement: a name resolves inside the packages root or is refused
  (no absolute paths, no "..", no symlink escape);
- two independent verdicts, never merged: a package is "valid" only when the
  Studio reader accepts it; the core reader's disagreement is reported as such;
- prompts are previewed and redacted, never dumped whole;
- opening the ZIP is not validation — `readable` and `valid` are separate fields.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

MAX_PREVIEW = 160


def packages_root() -> Path:
    """Directory scanned for .lmpack files (override: LIFE_MEAN_PACKAGES_DIR)."""
    override = os.environ.get("LIFE_MEAN_PACKAGES_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (Path(__file__).resolve().parents[1] / "lmpack").resolve()


class PackagePathError(ValueError):
    """Raised when a requested package path escapes the packages root."""


def resolve_package(name: str) -> Path:
    """Resolve ``name`` inside :func:`packages_root`, refusing anything outside.

    ``name`` may be a bare filename or a relative sub-path. Absolute paths,
    parent traversal and symlinks that land outside the root are rejected.
    """
    root = packages_root()
    raw = (name or "").strip().strip('"')
    if not raw:
        raise PackagePathError("empty package path")

    candidate = Path(raw)
    if candidate.is_absolute():
        raise PackagePathError("absolute paths are not accepted")

    resolved = (root / candidate).resolve()
    if root not in resolved.parents and resolved != root:
        raise PackagePathError("path escapes the packages directory")
    if not resolved.exists():
        raise PackagePathError(f"package not found: {raw}")
    if not resolved.is_file() or not resolved.name.endswith(".lmpack"):
        raise PackagePathError(f"not a .lmpack file: {raw}")
    return resolved


def studio_db_path() -> Path:
    """Studio SQLite location (override: LIFE_MEAN_STUDIO_DB).

    Reported by the API so an import never looks durable when the database
    actually lives somewhere ephemeral (a read-only image, a tmpfs).
    """
    override = os.environ.get("LIFE_MEAN_STUDIO_DB")
    if override:
        return Path(override).expanduser().resolve()
    return (Path(__file__).resolve().parents[1] / "life_mean_studio_data.db").resolve()


def _redact(text: str) -> str:
    try:
        from pipeline_inspector.redaction import redact_text

        return redact_text(text or "")[:MAX_PREVIEW]
    except Exception:  # pragma: no cover - redaction must never break listing
        return (text or "")[:MAX_PREVIEW]


def _studio_info(path: Path) -> Optional[Dict[str, Any]]:
    """Verdict of the Studio reader (the one that understands the shipped packs)."""
    try:
        from life_mean_studio.engine.package_manager import PackageManager

        info = PackageManager(storage=None).get_package_info(str(path))
    except Exception as exc:  # noqa: BLE001 - reported, never hidden
        return {"reader": "studio", "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    if info is None:
        return {"reader": "studio", "ok": False, "error": "unreadable package"}
    return {
        "reader": "studio",
        "ok": not info.errors,
        "name": info.name,
        "format_version": info.format_version,
        "package_version": info.package_version,
        "agents_count": info.agents_count,
        "workflows_count": info.workflows_count,
        "description": info.description,
        "errors": list(info.errors),
    }


def _is_valid(studio: Dict[str, Any]) -> bool:
    """A package is valid only if a reader accepts it AND it actually ships agents.

    Opening the ZIP is not validation, and neither is a reader that only checks
    the manifest: a pack with zero agents cannot be run, so it is not valid.
    """
    if not studio.get("ok"):
        return False
    return int(studio.get("agents_count") or 0) > 0


def _core_info(path: Path) -> Dict[str, Any]:
    """Verdict of the core reader (personas/ layout, plus agents/ since R2)."""
    try:
        from core.packager import LLMPackager, PackageFormatError

        packager = LLMPackager.from_package(str(path))
        result = packager.validate()
        return {
            "reader": "core",
            "ok": bool(result.get("valid")),
            "persona_count": result.get("persona_count"),
            "errors": list(result.get("errors") or []),
        }
    except Exception as exc:  # noqa: BLE001 - PackageFormatError included on purpose
        return {"reader": "core", "ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _manifest(path: Path) -> Dict[str, Any]:
    """Raw manifest, plus archive entries — but never a verdict on its own."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            manifest = {}
            if "manifest.json" in names:
                import json

                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            return {"entries": len(names), "manifest": manifest, "readable": True}
    except Exception as exc:  # noqa: BLE001
        return {"readable": False, "error": f"{type(exc).__name__}: {exc}"}


def inspect_package(path: Path) -> Dict[str, Any]:
    """Full, honest view of one package: manifest, agents, two verdicts."""
    studio = _studio_info(path)
    core = _core_info(path)
    archive = _manifest(path)

    agents: List[Dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path) as zf:
            import json

            for name in sorted(n for n in zf.namelist()
                               if n.startswith("agents/") and n.lower().endswith(".json")):
                try:
                    data = json.loads(zf.read(name).decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as exc:
                    agents.append({"entry": name, "error": f"{type(exc).__name__}: {exc}"})
                    continue
                prompt = str(data.get("system_prompt") or "")
                agents.append({
                    "entry": name,
                    "id": data.get("id") or Path(name).stem,
                    "name": data.get("name") or Path(name).stem,
                    "role": data.get("role") or "",
                    "persona": data.get("persona") or "",
                    "provider": data.get("provider") or "",
                    "prompt_chars": len(prompt),
                    "prompt_preview": _redact(prompt),
                })
    except Exception as exc:  # noqa: BLE001
        agents = [{"error": f"{type(exc).__name__}: {exc}"}]

    readme = ""
    try:
        with zipfile.ZipFile(path) as zf:
            for candidate in ("README.md", "README.txt"):
                if candidate in zf.namelist():
                    readme = zf.read(candidate).decode("utf-8", errors="replace")[:600]
                    break
    except Exception:  # noqa: BLE001 - a missing README is not an error
        readme = ""

    return {
        "path": str(path),
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "readable": archive.get("readable", False),
        "archive": archive,
        "agents": agents,
        "agents_count": len([a for a in agents if "id" in a]),
        "readme_preview": readme,
        "verdicts": {"studio": studio, "core": core},
        # Deliberately NOT merged: two readers, two answers.
        "valid": _is_valid(studio) and bool(agents),
    }


class PackagesApiMixin:
    """Mixin providing /api/packages* handlers."""

    _studio_storage = None  # injectable (tests); lazily created otherwise

    # ── Studio storage ──────────────────────────────────────────────────────
    def _storage(self):
        if PackagesApiMixin._studio_storage is None:
            from life_mean_studio.engine.storage import StudioStorage

            PackagesApiMixin._studio_storage = StudioStorage(str(studio_db_path()))
        return PackagesApiMixin._studio_storage


    # ── helpers ─────────────────────────────────────────────────────────────
    def _packages_list(self) -> None:
        root = packages_root()
        if not root.exists():
            self._send_json({"root": str(root), "exists": False, "packages": [], "total": 0})
            return

        packages = []
        for path in sorted(root.glob("*.lmpack")):
            studio = _studio_info(path)
            archive = _manifest(path)
            packages.append({
                "file": path.name,
                "size_bytes": path.stat().st_size,
                "readable": archive.get("readable", False),
                "name": studio.get("name") or (archive.get("manifest") or {}).get("name", ""),
                "package_version": studio.get("package_version") or "",
                "format_version": studio.get("format_version") or "",
                "agents_count": studio.get("agents_count", 0),
                "workflows_count": studio.get("workflows_count", 0),
                "description": studio.get("description", ""),
                "valid": _is_valid(studio),
                "errors": studio.get("errors", []) if "errors" in studio else [studio.get("error", "")],
            })

        self._send_json({
            "root": str(root),
            "exists": True,
            "total": len(packages),
            "valid_count": sum(1 for p in packages if p["valid"]),
            "packages": packages,
        })

    def _packages_inspect(self, raw_path: str) -> None:
        try:
            path = resolve_package(raw_path)
        except PackagePathError as exc:
            self._send_error(404, str(exc), code="package_not_found")
            return
        self._send_json(inspect_package(path))

    # ── POST ────────────────────────────────────────────────────────────────
    def _packages_import(self, payload: Dict[str, Any]) -> None:
        """Import a pack's agents into Studio's registry.

        Never reports success when nothing was written: an already-imported pack
        comes back as ``success: false`` with the conflicts listed, and the
        database path travels with every answer so the caller can see where the
        data actually landed.
        """
        raw_path = (payload or {}).get("path") or (payload or {}).get("file") or ""
        try:
            path = resolve_package(raw_path)
        except PackagePathError as exc:
            self._send_error(404, str(exc), code="package_not_found")
            return

        try:
            from life_mean_studio.engine.package_manager import PackageManager

            result = PackageManager(storage=self._storage()).import_package(str(path))
        except Exception as exc:  # noqa: BLE001 - surface, never swallow
            self._send_error(500, f"{type(exc).__name__}: {exc}", code="import_failed")
            return

        self._send_json({
            "file": path.name,
            "success": bool(result.success),
            "message": result.message,
            "agents_imported": int(getattr(result, "agents_imported", 0) or 0),
            "workflows_imported": int(getattr(result, "workflows_imported", 0) or 0),
            "conflicts": list(getattr(result, "conflicts", []) or []),
            "errors": list(getattr(result, "errors", []) or []),
            "database": str(studio_db_path()),
        })

    def _packages_validate(self, payload: Dict[str, Any]) -> None:
        raw_path = (payload or {}).get("path") or (payload or {}).get("file") or ""
        try:
            path = resolve_package(raw_path)
        except PackagePathError as exc:
            self._send_error(404, str(exc), code="package_not_found")
            return

        studio = _studio_info(path)
        core = _core_info(path)
        self._send_json({
            "file": path.name,
            "valid": _is_valid(studio),
            "verdicts": {"studio": studio, "core": core},
            "agreement": _is_valid(studio) == bool(core.get("ok")),
            "note": "Two independent readers; disagreement is reported, never averaged.",
        })

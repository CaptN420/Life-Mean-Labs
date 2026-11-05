"""Collecteurs de télémétrie du système d'exploitation (Windows).

Pourquoi ce module existe : l'audit classait « collecteurs Windows (Defender,
Event Log) » en `BLOCKED_EXTERNAL` à cause de `psutil`, `win32evtlog` et
`win32service` absents. Vérification faite, **aucun collecteur n'existait dans le
dépôt** — le classement confondait « fonctionnalité non écrite » et « dépendance
manquante ». Et les dépendances en question ne sont pas nécessaires : Windows
fournit déjà `powershell` (Get-MpComputerStatus) et `wevtutil` (journaux
d'événements).

Ce que ce module garantit :
- aucune dépendance pip ajoutée : uniquement des binaires présents sur Windows ;
- aucune exception ne remonte : chaque fonction renvoie ``ok`` + ``error`` ;
- sortie bornée (nombre d'événements, taille, timeout) pour ne jamais bloquer
  un appel HTTP ;
- rien n'est inventé : une donnée absente est ``None`` et l'erreur est écrite.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.safety.os_collectors")

_MAX_OUTPUT_BYTES = 512 * 1024

# 1 Critical, 2 Error, 3 Warning, 4 Information, 5 Verbose (schéma Windows)
_LEVEL_NAMES = {
    "1": "critical",
    "2": "error",
    "3": "warning",
    "4": "information",
    "5": "verbose",
}


def is_windows() -> bool:
    return platform.system().lower() == "windows"


def _run(command: List[str], timeout: float) -> Dict[str, Any]:
    """Exécute une commande et renvoie (ok, stdout, error). Jamais d'exception."""
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "error": f"command not found: {command[0]}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "error": f"timeout after {timeout}s"}
    except OSError as exc:
        return {"ok": False, "stdout": "", "error": f"{type(exc).__name__}: {exc}"}

    stdout = proc.stdout[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    stderr = proc.stderr[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    if proc.returncode != 0:
        return {
            "ok": False,
            "stdout": stdout,
            "error": f"exit {proc.returncode}: {stderr.strip()[:300] or 'no stderr'}",
        }
    return {"ok": True, "stdout": stdout, "error": ""}


def defender_status(timeout: float = 20.0) -> Dict[str, Any]:
    """État réel de Microsoft Defender via `Get-MpComputerStatus`.

    Renvoie ``ok: False`` avec la raison exacte si PowerShell refuse l'appel
    (droits, module absent, antivirus tiers) — jamais un état inventé.
    """
    if not is_windows():
        return {"ok": False, "error": "not a Windows host", "source": "Get-MpComputerStatus"}

    script = (
        "Get-MpComputerStatus | "
        "Select-Object AMServiceEnabled,RealTimeProtectionEnabled,"
        "AntivirusSignatureLastUpdated,AntispywareEnabled | ConvertTo-Json -Compress"
    )
    result = _run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        timeout=timeout,
    )
    if not result["ok"]:
        return {"ok": False, "error": result["error"], "source": "Get-MpComputerStatus"}

    text = result["stdout"].strip()
    if not text:
        return {
            "ok": False,
            "error": "empty output (Defender service likely disabled or blocked by policy)",
            "source": "Get-MpComputerStatus",
        }

    import json as _json

    try:
        raw = _json.loads(text)
    except ValueError as exc:
        return {
            "ok": False,
            "error": f"unparseable output: {exc}",
            "source": "Get-MpComputerStatus",
        }

    signature_raw = raw.get("AntivirusSignatureLastUpdated")
    return {
        "ok": True,
        "source": "Get-MpComputerStatus",
        "real_time_protection": raw.get("RealTimeProtectionEnabled"),
        "antivirus_enabled": raw.get("AMServiceEnabled"),
        "antispyware_enabled": raw.get("AntispywareEnabled"),
        # PowerShell sérialise les dates en /Date(<ms>)/ : on expose les deux formes
        "signature_timestamp_raw": signature_raw,
        "signature_timestamp": _dotnet_date_to_epoch(signature_raw),
        "error": "",
    }


def _dotnet_date_to_epoch(value: Any) -> Optional[float]:
    """Convertit « /Date(1793882711000)/ » en epoch secondes, sinon None."""
    if not isinstance(value, str) or not value.startswith("/Date("):
        return None
    digits = value[len("/Date("):].split(")")[0].strip("+-")
    try:
        return int(digits) / 1000.0
    except ValueError:
        return None


def recent_events(
    log_name: str = "System",
    count: int = 5,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    """Les ``count`` événements les plus récents d'un journal Windows (via wevtutil).

    ``wevtutil qe`` ne produit pas de JSON ; l'XML est le format structuré
    stable, donc on le parse avec ``xml.etree``.
    """
    if not is_windows():
        return {"ok": False, "error": "not a Windows host", "log": log_name, "events": []}

    count = max(1, min(int(count), 50))
    result = _run(
        ["wevtutil", "qe", log_name, f"/c:{count}", "/rd:true", "/f:xml"],
        timeout=timeout,
    )
    if not result["ok"]:
        return {"ok": False, "error": result["error"], "log": log_name, "events": []}

    # wevtutil concatène plusieurs éléments <Event> sans racine commune.
    wrapped = f"<Events>{result['stdout']}</Events>"
    try:
        root = ET.fromstring(wrapped)
    except ET.ParseError as exc:
        return {
            "ok": False,
            "error": f"unparseable XML: {exc}",
            "log": log_name,
            "events": [],
        }

    ns = "{http://schemas.microsoft.com/win/2004/08/events/event}"
    events: List[Dict[str, Any]] = []
    for node in root.findall(f"{ns}Event"):
        system = node.find(f"{ns}System")
        if system is None:
            continue
        provider = system.find(f"{ns}Provider")
        event_id = system.find(f"{ns}EventID")
        level = system.find(f"{ns}Level")
        created = system.find(f"{ns}TimeCreated")
        computer = system.find(f"{ns}Computer")
        level_value = (level.text or "").strip() if level is not None else ""
        events.append({
            "event_id": event_id.text if event_id is not None else None,
            "level": _LEVEL_NAMES.get(level_value, level_value or None),
            "provider": provider.get("Name") if provider is not None else None,
            "time_created": created.get("SystemTime") if created is not None else None,
            "computer": computer.text if computer is not None else None,
        })

    return {
        "ok": True,
        "log": log_name,
        "count": len(events),
        "events": events,
        "error": "" if events else "no event parsed (journal vide ou accès refusé)",
    }


def os_snapshot(events: int = 5) -> Dict[str, Any]:
    """Instantané complet, destiné à une route HTTP : ne lève jamais."""
    snapshot = {
        "host": {
            "platform": platform.system(),
            "node": platform.node(),
            "release": platform.release(),
            "supported": is_windows(),
        },
        "defender": defender_status(),
        "event_log": recent_events(count=events),
    }
    snapshot["degraded"] = [
        section for section in ("defender", "event_log")
        if not snapshot[section].get("ok")
    ]
    return snapshot

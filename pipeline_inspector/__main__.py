"""CLI : `python -m pipeline_inspector ingest|stats|report|export`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .studio_interface import PipelineInspector


def _print(obj) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False, default=str))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline_inspector")
    parser.add_argument("--root", default=".", help="racine du projet")
    parser.add_argument("--db", default=None, help="chemin SQLite")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ing = sub.add_parser("ingest", help="ingérer les logs")
    p_ing.add_argument("--full", action="store_true", help="relire tout l'historique")
    p_ing.add_argument("--adapters", default=None, help="liste séparée par des virgules")
    sub.add_parser("stats", help="statistiques du store")
    sub.add_parser("report", help="générer les rapports markdown")
    sub.add_parser("export", help="export JSON complet")
    args = parser.parse_args(argv)

    insp = PipelineInspector(args.root, db_path=args.db)
    if args.cmd == "ingest":
        names = [s.strip() for s in args.adapters.split(",")] if args.adapters else None
        _print(insp.ingest(full_rescan=args.full, adapter_names=names))
    elif args.cmd == "stats":
        _print(insp.stats())
    elif args.cmd == "report":
        _print(insp.generate_reports())
    elif args.cmd == "export":
        _print({"path": insp.export()})
    return 0


if __name__ == "__main__":
    sys.exit(main())

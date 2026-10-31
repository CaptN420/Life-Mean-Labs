"""Molecular Research Workflow — 9 étapes, réutilise core stable.

Étapes:
1. RESEARCH_QUESTION
2. SCIENTIFIC_DATABASE_SEARCH (PubChem / ChEMBL / PubMed mock/live)
3. MOLECULE_IDENTIFICATION
4. RDKIT_STRUCTURE_VALIDATION (canonical SMILES, formule, poids)
5. PROPERTY_CALCULATION (LogP, TPSA, HBD, HBA, rotatable bonds, fingerprint)
6. BIOACTIVITY_EVIDENCE_COLLECTION
7. MULTI_AGENT_ANALYSIS (reutilise DebateEngine + molecular_discovery_council)
8. SCIENTIFIC_CRITIC_REVIEW (mechanistic-skeptic + evidence-curator)
9. FINAL_RESEARCH_REPORT

Chaque étape produit un output structuré utilisable par la suivante.
Reprise possible sans répéter les appels DB (snapshot par run).
"""
from __future__ import annotations
import time, json
from pathlib import Path
from typing import Dict, Any, Optional, List

# Reuse existing registry/template without duplicating
try:
    from role_templates.registry import get_registry
    from role_templates.builtins import molecular_discovery_council
except Exception:
    get_registry = None  # Fallback: direct built-in

STEPS = [
    "research_question", "database_search", "molecule_identification",
    "rdkit_validation", "property_calculation", "bioactivity_evidence",
    "multi_agent_analysis", "scientific_critic_review", "final_report"
]

class MolecularResearchWorkflow:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.steps_completed: Dict[str, Any] = {}
        self.snapshot_path = Path(f"code_lab_runs/{run_id}/snapshot.json")

    def step_status(self) -> Dict[str, str]:
        return {s: ("COMPLETED" if s in self.steps_completed else "PENDING") for s in STEPS}

    def resume(self, snapshot_path: Optional[Path] = None) -> bool:
        p = snapshot_path or self.snapshot_path
        if p.exists():
            try:
                self.steps_completed = json.loads(p.read_text())
                return True
            except Exception:
                return False
        return False

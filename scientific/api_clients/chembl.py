"""ChEMBL API client.

Uses the official ChEMBL REST API (https://www.ebi.ac.uk/chembl/api/data).
All requests have bounded timeouts, retries, and optional caching.

NEVER fabricates data: a missing compound/activity returns None with error info.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger("scientific.ChEMBL")

CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"
DEFAULT_TIMEOUT = 15
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5


@dataclass
class ChEMBLBioactivity:
    """A bioactivity record (binding, IC50, KD, etc.)."""
    activity_type: str  # e.g. "IC50", "KD"
    relation: str  # e.g. "=", ">=", "<="
    value: Optional[float]
    units: str
    target_type: str
    target_name: str
    assay_id: str
    source_url: str
    retrieved_at: str = ""
    confidence_description: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activity_type": self.activity_type,
            "relation": self.relation,
            "value": self.value,
            "units": self.units,
            "target_type": self.target_type,
            "target_name": self.target_name,
            "assay_id": self.assay_id,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "confidence": self.confidence_description,
        }


@dataclass
class ChEMBLCompound:
    """A compound + its bioactivities from ChEMBL."""
    chembl_id: str
    name: str
    smiles: str
    molecular_formula: str
    molecular_weight: Optional[float]
    source_url: str
    retrieved_at: str = ""
    bioactivities: List[ChEMBLBioactivity] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chembl_id": self.chembl_id,
            "name": self.name,
            "smiles": self.smiles,
            "molecular_formula": self.molecular_formula,
            "molecular_weight": self.molecular_weight,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "bioactivities": [ba.to_dict() for ba in self.bioactivities],
        }


class ChEMBLClient:
    """Client for the ChEMBL REST API."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        cache_dir: Optional[str] = None,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self._cache_dir: Optional[Path] = Path(cache_dir) if cache_dir else None
        self._session = requests.Session()

    def _cache_path(self, key: str) -> Optional[Path]:
        if not self._cache_dir:
            return None
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        safe = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self._cache_dir / "chembl" / f"{safe}.json"

    def _cache_get(self, key: str) -> Optional[Dict[str, Any]]:
        p = self._cache_path(key)
        if p and p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def _cache_set(self, key: str, data: Dict[str, Any]) -> None:
        p = self._cache_path(key)
        if p:
            try:
                p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

    def _request(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        cache_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Bounded, retried JSON request. Returns None on failure."""
        if cache_key:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        url = f"{CHEMBL_BASE}/{path}.json"
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
        if query:
            url = f"{url}?{query}"

        headers = {"User-Agent": "Life_mean-Scientific/1.0"}

        for attempt in range(self.max_retries):
            try:
                resp = self._session.get(url, timeout=self.timeout, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                if cache_key:
                    self._cache_set(cache_key, data)
                return data
            except requests.exceptions.Timeout:
                logger.warning("ChEMBL timeout (attempt %d) for %s", attempt + 1, path)
                time.sleep(RETRY_BACKOFF ** attempt)
            except requests.exceptions.RequestException as exc:
                logger.warning("ChEMBL request error (attempt %d): %s", attempt + 1, exc)
                time.sleep(RETRY_BACKOFF ** attempt)
                return None
            except (ValueError, json.JSONDecodeError):
                logger.warning("ChEMBL JSON parse error for %s", url)
                return None
        return None

    def get_compound_by_name(self, name: str) -> Optional[ChEMBLCompound]:
        """Search ChEMBL by compound name (case-insensitive)."""
        cache_key = f"compound:name:{name}"
        data = self._request(
            "molecule",
            params={"molecule_chembl_id__iexact": name, "max_phase": 4},
            cache_key=cache_key,
        )
        if not data or not data.get("molecules"):
            return None

        mol = data["molecules"][0]  # best match
        chembl_id = mol.get("molecule_chembl_id", "")
        return self._build_compound(chembl_id)

    def get_compound_by_chembl_id(self, chembl_id: str) -> Optional[ChEMBLCompound]:
        """Look up a compound by ChEMBL ID."""
        return self._build_compound(chembl_id)

    def _build_compound(self, chembl_id: str) -> Optional[ChEMBLCompound]:
        cache_key = f"compound:id:{chembl_id}"
        data = self._request(
            f"molecule/{chembl_id}",
            params={"only": "molecule_chembl_id,molecule_name,molecule_synonyms,small_molecule"},
            cache_key=cache_key,
        )
        if not data:
            return None

        mol_name = data.get("molecule_name") or chembl_id
        # Synonyms
        synonyms = [s.get("name") for s in data.get("molecule_synonyms", []) if s.get("name")]

        # Get the molecule's activities (bioactivities) for real evidence
        activities = self._get_bioactivities(chembl_id)

        # Get SMILES from the molecule's records
        smiles_data = self._request(
            f"molecule/{chembl_id}/record",
            params={"only": "isomeric_smiles,canonical_smiles,molecular_formula,mw"},
            cache_key=f"record:{chembl_id}",
        )
        smiles = ""
        formula = ""
        mw: Optional[float] = None
        if smiles_data and "molecules" in smiles_data:
            for rec in smiles_data["molecules"]:
                if not smiles and rec.get("isomeric_smiles"):
                    smiles = rec["isomeric_smiles"]
                if not formula and rec.get("molecular_formula"):
                    formula = rec["molecular_formula"]
                if mw is None and rec.get("mw"):
                    try:
                        mw = float(rec["mw"])
                    except (ValueError, TypeError):
                        pass
        elif smiles_data:
            smiles = smiles_data.get("isomeric_smiles", "") or smiles_data.get("canonical_smiles", "")
            formula = smiles_data.get("molecular_formula", "")
            if smiles_data.get("mw"):
                try:
                    mw = float(smiles_data["mw"])
                except (ValueError, TypeError):
                    pass

        source_url = f"https://www.ebi.ac.uk/chembl/compound/inspect/{chembl_id}"
        return ChEMBLCompound(
            chembl_id=chembl_id,
            name=mol_name,
            smiles=smiles,
            molecular_formula=formula,
            molecular_weight=mw,
            source_url=source_url,
            retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            bioactivities=activities,
            raw=data,
        )

    def _get_bioactivities(self, chembl_id: str) -> List[ChEMBLBioactivity]:
        """Fetch bioactivity records for a compound."""
        cache_key = f"activities:{chembl_id}"
        data = self._request(
            f"activity",
            params={
                "molecule_chembl_id__iexact": chembl_id,
                "only": "activity_type,relation,value,units,target_chembl_id,assay_chembl_id,src_id,standard_inchi,standard_inchi_url",
                "max_phase": 4,
            },
            cache_key=cache_key,
        )
        if not data or not data.get("activities"):
            return []

        results = []
        for act in data.get("activities", []):
            try:
                value = float(act.get("value")) if act.get("value") else None
            except (ValueError, TypeError):
                value = None

            target_id = act.get("target_chembl_id", "")
            target_name = act.get("target_name", target_id)

            results.append(ChEMBLBioactivity(
                activity_type=act.get("activity_type", "") or act.get("standard_type", ""),
                relation=act.get("relation", "="),
                value=value,
                units=act.get("units", "") or act.get("standard_units", ""),
                target_type="unspecified",
                target_name=target_name,
                assay_id=act.get("assay_chembl_id", ""),
                source_url=f"https://www.ebi.ac.uk/chembl/assay_report_card/{act.get('assay_chembl_id', '')}/",
                retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                confidence_description=act.get("data_validity", {}).get("comment", "") if isinstance(act.get("data_validity"), dict) else "",
                raw=act,
            ))
        return results

    def search_activities_by_target(self, target_name: str) -> List[ChEMBLBioactivity]:
        """Search for bioactivities associated with a target name."""
        cache_key = f"target_search:{target_name}"
        data = self._request(
            "target",
            params={"target_name__icontains": target_name},
            cache_key=cache_key,
        )
        if not data or not data.get("targets"):
            return []
        # For each matching target, fetch activities
        results = []
        for tgt in data["targets"][:3]:  # cap at 3 targets
            target_id = tgt.get("target_chembl_id", "")
            if not target_id:
                continue
            activities = self._request(
                "activity",
                params={"target_chembl_id__iexact": target_id, "max_phase": 4},
                cache_key=f"target_activities:{target_id}",
            )
            if activities and activities.get("activities"):
                for act in activities["activities"][:50]:  # cap per target
                    try:
                        value = float(act.get("value")) if act.get("value") else None
                    except (ValueError, TypeError):
                        value = None
                    results.append(ChEMBLBioactivity(
                        activity_type=act.get("activity_type", "") or act.get("standard_type", ""),
                        relation=act.get("relation", "="),
                        value=value,
                        units=act.get("units", "") or act.get("standard_units", ""),
                        target_type=tgt.get("target_type", ""),
                        target_name=tgt.get("target_name", ""),
                        assay_id=act.get("assay_chembl_id", ""),
                        source_url=f"https://www.ebi.ac.uk/chembl/assay_report_card/{act.get('assay_chembl_id', '')}/",
                        retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        raw=act,
                    ))
        return results

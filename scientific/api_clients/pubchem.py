"""PubChem PUG REST API client.

Uses the official PubChem PUG REST API (https://pubchem.ncbi.nlm.nih.gov/rest/pug/pug.cgi).
All requests have bounded timeouts, retries, and optional caching.

NEVER fabricates data: a missing compound returns None with error info.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger("scientific.PubChem")

PUG_REST_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
DEFAULT_TIMEOUT = 15  # seconds
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5  # exponential backoff multiplier


@dataclass
class PubChemCompound:
    """A compound record from PubChem, with source provenance."""
    cid: int
    name: str
    smiles: str
    canonical_smiles: str
    molecular_formula: str
    molecular_weight: float
    source_url: str
    retrieved_at: str = ""
    inchi: str = ""
    inchi_key: str = ""
    synonyms: List[str] = field(default_factory=list)
    # Raw fields for provenance
    raw_properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cid": self.cid,
            "name": self.name,
            "smiles": self.smiles,
            "canonical_smiles": self.canonical_smiles,
            "molecular_formula": self.molecular_formula,
            "molecular_weight": self.molecular_weight,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "inchi": self.inchi,
            "inchi_key": self.inchi_key,
            "synonyms": self.synonyms,
        }


class PubChemClient:
    """Client for PubChem PUG REST.

    Usage:
        client = PubChemClient(cache_dir="data/sci_cache")
        compound = client.get_compound_by_name("aspirin")
        if compound:
            print(compound.canonical_smiles, compound.molecular_weight)
    """

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
        return self._cache_dir / "pubchem" / f"{safe}.json"

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
        """Make a bounded, retried request to PubChem. Returns None on failure."""
        if cache_key:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        url = f"{PUG_REST_BASE}/{path}"
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
                logger.warning("PubChem timeout on attempt %d for %s", attempt + 1, path)
                time.sleep(RETRY_BACKOFF ** attempt)
            except requests.exceptions.RequestException as exc:
                logger.warning("PubChem request error (attempt %d): %s", attempt + 1, exc)
                if attempt < self.max_retries - 1:
                    time.sleep(RETRY_BACKOFF ** attempt)
                else:
                    return None
            except (ValueError, json.JSONDecodeError) as exc:
                logger.warning("PubChem JSON parse error for %s: %s", url, exc)
                return None
        return None

    def get_compound_by_name(self, name: str) -> Optional[PubChemCompound]:
        """Look up a compound by name. Returns None if not found."""
        cache_key = f"compound:name:{name}"
        data = self._request(
            f"compound/name/{name}/property/CanonicalSMILES,IsomericSMILES,MolecularFormula,MolecularWeight,InChI,InChIKey/JSON",
            cache_key=cache_key,
        )
        if not data or "PropertyTable" not in data or not data["PropertyTable"]["Properties"]:
            return None

        props = data["PropertyTable"]["Properties"][0]
        cid = props.get("CID", 0)
        canonical = props.get("CanonicalSMILES", "")
        isomeric = props.get("IsomericSMILES", canonical)

        # Fetch synonyms
        syn_data = self._request(
            f"compound/name/{name}/synonyms/JSON",
            cache_key=f"synonyms:name:{name}",
        )
        synonyms: List[str] = []
        if syn_data and "InformationList" in syn_data:
            for item in syn_data["InformationList"].get("Synonym", []):
                if "Name" in item:
                    synonyms.append(item["Name"])

        source_url = f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
        return PubChemCompound(
            cid=cid,
            name=name,
            smiles=isomeric,
            canonical_smiles=canonical,
            molecular_formula=props.get("MolecularFormula", ""),
            molecular_weight=float(props.get("MolecularWeight", 0)),
            source_url=source_url,
            retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            inchi=props.get("InChI", ""),
            inchi_key=props.get("InChIKey", ""),
            synonyms=synonyms[:20],  # cap to avoid huge payloads
            raw_properties=props,
        )

    def get_compound_by_cid(self, cid: int) -> Optional[PubChemCompound]:
        """Look up a compound by CID. Returns None if not found."""
        cache_key = f"compound:cid:{cid}"
        data = self._request(
            f"compound/cid/{cid}/property/CanonicalSMILES,IsomericSMILES,MolecularFormula,MolecularWeight,InChI,InChIKey/JSON",
            cache_key=cache_key,
        )
        if not data or "PropertyTable" not in data or not data["PropertyTable"]["Properties"]:
            return None

        props = data["PropertyTable"]["Properties"][0]
        name_data = self._request(
            f"compound/cid/{cid}/description/JSON",
            cache_key=f"description:cid:{cid}",
        )
        name = self._extract_name(name_data, cid)

        canonical = props.get("CanonicalSMILES", "")
        isomeric = props.get("IsomericSMILES", canonical)

        source_url = f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
        return PubChemCompound(
            cid=cid,
            name=name,
            smiles=isomeric,
            canonical_smiles=canonical,
            molecular_formula=props.get("MolecularFormula", ""),
            molecular_weight=float(props.get("MolecularWeight", 0)),
            source_url=source_url,
            retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            inchi=props.get("InChI", ""),
            inchi_key=props.get("InChIKey", ""),
            raw_properties=props,
        )

    def search_by_smiles(self, smiles: str) -> Optional[PubChemCompound]:
        """Search PubChem by SMILES string. Returns the best match."""
        cache_key = f"compound:smiles:{hashlib.sha256(smiles.encode()).hexdigest()[:16]}"
        encoded = requests.utils.quote(smiles)
        data = self._request(
            f"compound/smiles/{encoded}/property/CanonicalSMILES,IsomericSMILES,MolecularFormula,MolecularWeight,InChI,InChIKey/JSON",
            cache_key=cache_key,
        )
        if not data or "PropertyTable" not in data or not data["PropertyTable"]["Properties"]:
            return None

        props = data["PropertyTable"]["Properties"][0]
        cid = props.get("CID", 0)
        canonical = props.get("CanonicalSMILES", "")
        isomeric = props.get("IsomericSMILES", canonical)
        source_url = f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
        return PubChemCompound(
            cid=cid,
            name=f"CID-{cid}",
            smiles=isomeric,
            canonical_smiles=canonical,
            molecular_formula=props.get("MolecularFormula", ""),
            molecular_weight=float(props.get("MolecularWeight", 0)),
            source_url=source_url,
            retrieved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            inchi=props.get("InChI", ""),
            inchi_key=props.get("InChIKey", ""),
            raw_properties=props,
        )

    @staticmethod
    def _extract_name(name_data: Optional[Dict], cid: int) -> str:
        if not name_data:
            return f"CID-{cid}"
        try:
            items = name_data.get("InformationList", {}).get("Information", [])
            for item in items:
                if item.get("Title"):
                    return item["Title"]
        except Exception:
            pass
        return f"CID-{cid}"

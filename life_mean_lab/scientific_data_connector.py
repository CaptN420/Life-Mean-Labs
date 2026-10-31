"""Scientific Data Connections — PubChem / ChEMBL / PubMed.

Règles (mission):
- API officielles documentées uniquement
- Timeout + retry + rate limit + caching
- Service indisponible = pas de crash du débat
- Stocker URL source, identifiant, timestamp
- Distinguer "données manquantes" de "résultat négatif"
- Aucune citation inventée, aucun exposé de credentials
"""
from __future__ import annotations
import time, json
from pathlib import Path
from typing import Optional, Dict, Any, List

# Timeout et retry : paramètres conservateurs pour éviter surcharge réseau
TIMEOUT = 8.0
MAX_RETRIES = 2
CACHE_DIR = Path("data/raw_debates")

# Sources officielles (documentées)
PUBCHEM_PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUBMED_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CHEMBL_API = "https://www.ebi.ac.uk/chembl/api/data"

class SourceRecord:
    """Trace d'une récupération (provenance obligatoire per mission)."""
    def __init__(self, source: str, identifier: str, url: str, timestamp: str,
                 status: str, content: Optional[Dict] = None):
        self.source = source
        self.identifier = identifier
        self.url = url
        self.timestamp = timestamp
        self.status = status  # VERIFIED_DATABASE / UNKNOWN / UNAVAILABLE / FAILED
        self.content = content

class ScientificDataConnector:
    """Connexion aux bases scientifiques — jamais de fabrication."""
    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def retrieve_pubchem(self, compound_id: str) -> SourceRecord:
        url = f"{PUBCHEM_PUG}/compound/cid/{compound_id}/property/IsomericSMILES,MolecularWeight,LogP,TPSA,IUPACName/JSON"
        # Note: pas d'appel réseau réel dans cette version de base.
        # L'appel réel doit être fait par la couche réseau avec le timeout/retry.
        # Ici on enregistre la provenance et le statut honnête.
        return SourceRecord(
            source="PubChem",
            identifier=compound_id,
            url=url,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            status="UNKNOWN",  # Remplacé par VERIFIED_DATABASE après appel réel
            content=None
        )

    def retrieve_chembl(self, compound_id: str) -> SourceRecord:
        url = f"{CHEMBL_API}/molecule/{compound_id}"
        return SourceRecord(
            source="ChEMBL",
            identifier=compound_id,
            url=url,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            status="UNKNOWN",
            content=None
        )

    def retrieve_pubmed(self, term: str) -> SourceRecord:
        url = f"{PUBMED_EUTILS}/esearch.fcgi?db=pubmed&term={term}&retmode=json"
        return SourceRecord(
            source="PubMed",
            identifier=term,
            url=url,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            status="UNKNOWN",
            content=None
        )

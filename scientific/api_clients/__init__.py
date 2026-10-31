"""Scientific database API clients.

Each client is self-contained, uses `requests` with bounded timeouts, retries,
rate-limiting, and caching. Unavailable services are handled gracefully — they
never crash the debate; they return structured error info and empty data.
"""
from .pubchem import PubChemClient, PubChemCompound
from .chembl import ChEMBLClient, ChEMBLCompound
from .pubmed import PubMedClient, PubMedArticle

__all__ = [
    "PubChemClient",
    "PubChemCompound",
    "ChEMBLClient",
    "ChEMBLCompound",
    "PubMedClient",
    "PubMedArticle",
]

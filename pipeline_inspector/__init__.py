"""Life_mean Pipeline Inspector.

Analyse locale de logs hétérogènes (Code Lab, Hermes, CaptN, débats, logs
texte) et production d'une chronologie d'événements structurés corrélés,
avec décisions de sécurité, outils, erreurs et résultats de tests.

Contraintes :
- lecture seule sur les logs d'origine ;
- local uniquement, aucun appel réseau ;
- secrets masqués dans les sorties ;
- aucune exécution de commande extraite des logs.
"""

from __future__ import annotations

from .event_store import EventStore
from .feature_pool_bridge import FeaturePoolBridge
from .ingest import IngestResult, PipelineIngestor
from .schemas import Correlation, EventType, PipelineEvent, parse_timestamp
from .studio_interface import PipelineApiMixin, PipelineInspector

__all__ = [
    "EventStore",
    "EventType",
    "PipelineEvent",
    "Correlation",
    "PipelineIngestor",
    "IngestResult",
    "PipelineInspector",
    "PipelineApiMixin",
    "FeaturePoolBridge",
    "parse_timestamp",
]

__version__ = "0.1.0"

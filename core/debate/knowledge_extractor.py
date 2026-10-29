"""Experimental Knowledge Extractor — extracts immutable knowledge records from experiments.

After an experiment, compares:
- Initial hypothesis
- Predicted result
- Observed result
- Differences
- Experimental conditions
- Reproducibility level
- Limitations
- Evidence and artifacts

Produces an immutable KnowledgeRecord.
Never transforms local observation into general law automatically.
Preserves negative and inconclusive results.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.debate.knowledge_extractor")


# ── Enums ────────────────────────────────────────────────────────────────────


class KnowledgeStatus(str, Enum):
    """Status of extracted knowledge."""
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    EMERGENT = "EMERGENT"  # New insight not anticipated
    VERIFIED_CAUSAL = "VERIFIED_CAUSAL"


# ── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class KnowledgeRecord:
    """Immutable record of knowledge gained from an experiment."""
    knowledge_id: str
    hypothesis_id: str
    experiment_ids: List[str] = field(default_factory=list)
    observation: str = ""
    conclusion: str = ""
    status: KnowledgeStatus = KnowledgeStatus.SUPPORTED
    generalization_scope: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    rule_version: str = "1.0.0"
    reproducible: bool = False
    limitations: List[str] = field(default_factory=list)
    negative_results: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "knowledge_id": self.knowledge_id,
            "hypothesis_id": self.hypothesis_id,
            "experiment_ids": self.experiment_ids,
            "observation": self.observation[:500],
            "conclusion": self.conclusion[:300],
            "status": self.status.value,
            "generalization_scope": self.generalization_scope,
            "evidence_ids": self.evidence_ids,
            "rule_version": self.rule_version,
            "reproducible": self.reproducible,
            "limitations": self.limitations,
            "negative_results": self.negative_results,
            "timestamp": self.timestamp,
        }


# ── Experimental Knowledge Extractor ─────────────────────────────────────────


class ExperimentalKnowledgeExtractor:
    """Extracts immutable knowledge records from experiments.

    Never automatically generalizes local observations.
    Preserves negative and inconclusive results.
    """

    def __init__(self):
        self._knowledge: Dict[str, KnowledgeRecord] = {}
        self._next_id = 1

    def extract_knowledge(
        self,
        hypothesis_id: str,
        experiment_ids: List[str],
        observation: str,
        conclusion: str,
        status: KnowledgeStatus = KnowledgeStatus.SUPPORTED,
        generalization_scope: str = "",
        evidence_ids: Optional[List[str]] = None,
        limitations: Optional[List[str]] = None,
        negative_results: Optional[List[str]] = None,
    ) -> KnowledgeRecord:
        """Extract a knowledge record from an experiment."""
        know_id = f"KNOW-{self._next_id:03d}"
        self._next_id += 1

        record = KnowledgeRecord(
            knowledge_id=know_id,
            hypothesis_id=hypothesis_id,
            experiment_ids=experiment_ids,
            observation=observation,
            conclusion=conclusion,
            status=status,
            generalization_scope=generalization_scope or "Test cases executed",
            evidence_ids=evidence_ids or [],
            limitations=limitations or [],
            negative_results=negative_results or [],
        )

        self._knowledge[know_id] = record
        logger.info("Knowledge extracted: %s for hypothesis %s", know_id, hypothesis_id)
        return record

    def get_knowledge(self, knowledge_id: str) -> Optional[KnowledgeRecord]:
        """Get a knowledge record by ID."""
        return self._knowledge.get(knowledge_id)

    def get_knowledge_for_hypothesis(self, hypothesis_id: str) -> List[KnowledgeRecord]:
        """Get all knowledge records for a hypothesis."""
        return [
            k for k in self._knowledge.values()
            if k.hypothesis_id == hypothesis_id
        ]

    def get_verified_knowledge(self) -> List[KnowledgeRecord]:
        """Get all verified/supported knowledge records."""
        return [
            k for k in self._knowledge.values()
            if k.status in (KnowledgeStatus.SUPPORTED, KnowledgeStatus.VERIFIED_CAUSAL)
        ]

    def get_inconclusive_knowledge(self) -> List[KnowledgeRecord]:
        """Get all inconclusive knowledge records."""
        return [
            k for k in self._knowledge.values()
            if k.status == KnowledgeStatus.INCONCLUSIVE
        ]

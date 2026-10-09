"""Novelty detection and deduplication utilities.

Provides tools for detecting duplicate tasks and measuring
novelty in generated task collections.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class NoveltyResult:
    """Result of a novelty detection check."""

    task_id: str
    is_duplicate: bool
    duplicate_of: Optional[str] = None
    novelty_score: float = 0.0
    signature: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "task_id": self.task_id,
            "is_duplicate": self.is_duplicate,
            "duplicate_of": self.duplicate_of,
            "novelty_score": self.novelty_score,
            "signature": self.signature,
            "metadata": self.metadata,
        }


class NoveltyDetector:
    """Detects duplicate and novel tasks.

    Uses multiple similarity measures:
    - Normalized text hashing (structural signature)
    - Jaccard similarity (word-level)
    - Character n-gram similarity (character-level)
    - Semantic similarity (when available)
    """

    def __init__(self, threshold: float = 0.8):
        """Initialize the novelty detector.

        Args:
            threshold: Similarity threshold for duplicate detection (0.0 to 1.0)
        """
        self.threshold = threshold
        self._known_signatures: Dict[str, str] = {}  # signature -> task_id
        self._known_descriptions: Dict[str, str] = {}  # task_id -> description

    def compute_signature(self, description: str) -> str:
        """Compute a structural signature for a task description.

        The signature captures the structure while normalizing numbers
        and whitespace.

        Args:
            description: Task description

        Returns:
            Signature string
        """
        # Normalize: lowercase, remove extra whitespace
        normalized = description.lower().strip()
        normalized = re.sub(r'\s+', ' ', normalized)

        # Replace numbers with placeholder
        normalized = re.sub(r'\d+', '{N}', normalized)

        # Compute hash
        signature_hash = hashlib.md5(normalized.encode()).hexdigest()[:16]

        return signature_hash

    def is_duplicate(
        self,
        new_task: "GeneratedTask",
        existing_tasks: List["GeneratedTask"],
        threshold: Optional[float] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Check if a task is a duplicate of any existing task.

        Args:
            new_task: Task to check
            existing_tasks: List of existing tasks to compare against
            threshold: Override default threshold

        Returns:
            Tuple of (is_duplicate, duplicate_task_id)
        """
        if threshold is None:
            threshold = self.threshold

        new_signature = self.compute_signature(new_task.description)

        # Check structural similarity first
        for existing in existing_tasks:
            existing_signature = self.compute_signature(existing.description)

            # Same signature = likely duplicate
            if new_signature == existing_signature:
                # Verify with word-level similarity
                similarity = self._jaccard_similarity(
                    new_task.description,
                    existing.description
                )
                if similarity >= threshold:
                    return True, existing.task_id

        # Check character-level similarity for near-duplicates
        for existing in existing_tasks:
            similarity = self._char_ngram_similarity(
                new_task.description,
                existing.description
            )
            if similarity >= threshold:
                return True, existing.task_id

        return False, None

    def novelty_score(
        self,
        task: "GeneratedTask",
        corpus: List["GeneratedTask"],
    ) -> float:
        """Compute novelty score of a task relative to a corpus.

        Args:
            task: Task to evaluate
            corpus: Reference corpus

        Returns:
            Novelty score (0.0 = completely novel, 1.0 = duplicate)
        """
        if not corpus:
            return 1.0

        max_similarity = 0.0

        for existing in corpus:
            # Word-level similarity
            word_sim = self._jaccard_similarity(
                task.description,
                existing.description
            )

            # Character-level similarity
            char_sim = self._char_ngram_similarity(
                task.description,
                existing.description
            )

            # Take maximum
            max_similarity = max(max_similarity, word_sim, char_sim)

        return 1.0 - max_similarity

    def deduplicate_tasks(
        self,
        tasks: List["GeneratedTask"],
        threshold: Optional[float] = None,
    ) -> Tuple[List["GeneratedTask"], List[NoveltyResult]]:
        """Deduplicate a list of tasks.

        Args:
            tasks: List of tasks to deduplicate
            threshold: Override default threshold

        Returns:
            Tuple of (deduplicated_tasks, novelty_results)
        """
        if threshold is None:
            threshold = self.threshold

        deduplicated = []
        results = []

        for task in tasks:
            is_dup, dup_of = self.is_duplicate(task, deduplicated, threshold)

            result = NoveltyResult(
                task_id=task.task_id,
                is_duplicate=is_dup,
                duplicate_of=dup_of,
                novelty_score=self.novelty_score(task, deduplicated),
                signature=self.compute_signature(task.description),
            )
            results.append(result)

            if not is_dup:
                deduplicated.append(task)

        return deduplicated, results

    def compute_corpus_statistics(
        self,
        tasks: List["GeneratedTask"],
    ) -> Dict[str, Any]:
        """Compute novelty statistics for a corpus of tasks.

        Args:
            tasks: List of tasks

        Returns:
            Dictionary with statistics
        """
        if not tasks:
            return {
                "total_tasks": 0,
                "unique_tasks": 0,
                "duplicate_tasks": 0,
                "avg_novelty": 0.0,
                "min_novelty": 0.0,
                "max_novelty": 0.0,
            }

        signatures = set()
        novelty_scores = []

        for task in tasks:
            sig = self.compute_signature(task.description)
            signatures.add(sig)
            novelty_scores.append(self.novelty_score(task, tasks))

        return {
            "total_tasks": len(tasks),
            "unique_tasks": len(signatures),
            "duplicate_tasks": len(tasks) - len(signatures),
            "avg_novelty": sum(novelty_scores) / len(novelty_scores),
            "min_novelty": min(novelty_scores),
            "max_novelty": max(novelty_scores),
        }

    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """Compute Jaccard similarity between two texts."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union)

    def _char_ngram_similarity(self, text1: str, text2: str, n: int = 3) -> float:
        """Compute character n-gram similarity between two texts."""
        def get_ngrams(text: str, n: int) -> Set[str]:
            text = text.lower()
            return {text[i:i+n] for i in range(len(text) - n + 1)}

        ngrams1 = get_ngrams(text1, n)
        ngrams2 = get_ngrams(text2, n)

        if not ngrams1 or not ngrams2:
            return 0.0

        intersection = ngrams1 & ngrams2
        union = ngrams1 | ngrams2

        return len(intersection) / len(union)


# Import here to avoid circular dependency
from experiments.generation.schemas import GeneratedTask  # noqa: E402

"""Dataset builder for exporting synthetic data experiments.

Provides tools for building SFT (Supervised Fine-Tuning) and preference
datasets from experiment results, with JSONL export capabilities.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from experiments.runner import ExperimentResult

logger = logging.getLogger("DatasetBuilder")


@dataclass
class DatasetExample:
    """A single example for a training dataset."""

    conversation: List[Dict[str, str]]
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation": self.conversation,
            "metadata": self.metadata,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DatasetExample":
        return cls(
            conversation=data.get("conversation", []),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
        )


@dataclass
class DatasetManifest:
    """Metadata about a generated dataset."""

    dataset_id: str
    version: str
    example_count: int
    domains: Dict[str, int]
    difficulty_distribution: Dict[str, int]
    config_snapshot: Dict[str, Any]
    provenance_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "example_count": self.example_count,
            "domains": self.domains,
            "difficulty_distribution": self.difficulty_distribution,
            "config_snapshot": self.config_snapshot,
            "provenance_url": self.provenance_url,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DatasetManifest":
        return cls(
            dataset_id=data["dataset_id"],
            version=data.get("version", "1.0.0"),
            example_count=data.get("example_count", 0),
            domains=data.get("domains", {}),
            difficulty_distribution=data.get("difficulty_distribution", {}),
            config_snapshot=data.get("config_snapshot", {}),
            provenance_url=data.get("provenance_url"),
        )


class DatasetBuilder:
    """Builds training datasets from experiment results.

    Supports multiple output formats:
    - JSONL (primary)
    - SFT (Supervised Fine-Tuning) format
    - Preference format (for RLHF)
    """

    def __init__(self, dataset_version: str = "1.0.0"):
        """Initialize the dataset builder.

        Args:
            dataset_version: Version string for generated datasets
        """
        self.dataset_version = dataset_version
        self._example_counter = 0

    def build_sft(
        self,
        results: List[ExperimentResult],
        prompt_template: Optional[str] = None,
        include_metadata: bool = True,
    ) -> List[DatasetExample]:
        """Build SFT (Supervised Fine-Tuning) dataset examples.

        Args:
            results: List of experiment results
            prompt_template: Optional template for formatting prompts
            include_metadata: Whether to include experiment metadata

        Returns:
            List of DatasetExamples
        """
        examples = []
        for result in results:
            if not result.is_successful:
                continue

            example = self._build_sft_example(result, prompt_template)
            if include_metadata and result.provenance:
                example.metadata.update({
                    "experiment_id": result.experiment_id,
                    "task_id": result.task_id,
                    "run_id": result.run_id,
                    "generator_version": result.provenance.generator_version,
                    "seed": result.provenance.seed,
                })

            examples.append(example)

        logger.info(f"Built {len(examples)} SFT examples from {len(results)} results")
        return examples

    def build_preference(
        self,
        results: List[ExperimentResult],
        chosen_threshold: float = 0.8,
        rejected_threshold: float = 0.3,
    ) -> List[DatasetExample]:
        """Build preference dataset for RLHF training.

        Args:
            results: List of experiment results
            chosen_threshold: Minimum score for 'chosen' response
            rejected_threshold: Maximum score for 'rejected' response

        Returns:
            List of DatasetExamples with chosen/rejected pairs
        """
        examples = []

        # Group by task_id to find pairs
        task_groups: Dict[str, List[ExperimentResult]] = {}
        for result in results:
            if result.task_id not in task_groups:
                task_groups[result.task_id] = []
            task_groups[result.task_id].append(result)

        for task_id, task_results in task_groups.items():
            # Sort by score descending
            sorted_results = sorted(task_results, key=lambda r: r.validation_result.score if r.validation_result else 0.0, reverse=True)

            if len(sorted_results) < 2:
                continue

            # Find chosen and rejected
            chosen = None
            rejected = None

            for result in sorted_results:
                if result.validation_result and result.validation_result.score >= chosen_threshold:
                    chosen = result
                elif result.validation_result and result.validation_result.score <= rejected_threshold:
                    rejected = result

            if chosen and rejected:
                example = self._build_preference_example(chosen, rejected)
                examples.append(example)

        logger.info(f"Built {len(examples)} preference examples")
        return examples

    def export_jsonl(
        self,
        examples: List[DatasetExample],
        output_path: str,
        manifest: Optional[DatasetManifest] = None,
    ) -> str:
        """Export dataset to JSONL format.

        Args:
            examples: List of dataset examples
            output_path: Path to output file
            manifest: Optional dataset manifest

        Returns:
            Path to exported file
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            for example in examples:
                f.write(json.dumps(example.to_dict(), ensure_ascii=False) + "\n")

        logger.info(f"Exported {len(examples)} examples to {path}")

        # Export manifest if provided
        if manifest:
            manifest_path = path.with_suffix(".manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest.to_dict(), f, indent=2)
            logger.info(f"Exported manifest to {manifest_path}")

        return str(path)

    def export_json(
        self,
        examples: List[DatasetExample],
        output_path: str,
        manifest: Optional[DatasetManifest] = None,
    ) -> str:
        """Export dataset to JSON format.

        Args:
            examples: List of dataset examples
            output_path: Path to output file
            manifest: Optional dataset manifest

        Returns:
            Path to exported file
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": self.dataset_version,
            "example_count": len(examples),
            "examples": [e.to_dict() for e in examples],
        }

        if manifest:
            data["manifest"] = manifest.to_dict()

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported {len(examples)} examples to {path}")
        return str(path)

    def compute_statistics(
        self,
        results: List[ExperimentResult],
    ) -> Dict[str, Any]:
        """Compute dataset statistics from experiment results.

        Args:
            results: List of experiment results

        Returns:
            Dictionary with statistics
        """
        domains = {}
        difficulty_dist = {}
        valid_count = 0
        invalid_count = 0

        for result in results:
            # Count by domain (from task)
            domain = getattr(result, 'task_domain', 'unknown')
            domains[domain] = domains.get(domain, 0) + 1

            # Count by difficulty
            difficulty = getattr(result, 'task_difficulty', 'unknown')
            difficulty_dist[str(difficulty)] = difficulty_dist.get(str(difficulty), 0) + 1

            # Count valid/invalid
            if result.is_valid:
                valid_count += 1
            else:
                invalid_count += 1

        return {
            "total_examples": len(results),
            "valid_examples": valid_count,
            "invalid_examples": invalid_count,
            "pass_rate": valid_count / max(1, len(results)),
            "domains": domains,
            "difficulty_distribution": difficulty_dist,
        }

    def _build_sft_example(
        self,
        result: ExperimentResult,
        prompt_template: Optional[str],
    ) -> DatasetExample:
        """Build a single SFT example from an experiment result."""
        # Extract task description and answer
        task_id = result.task_id
        answer = result.answer

        # Build conversation
        conversation = [
            {
                "role": "user",
                "content": f"Task: {task_id}",
            },
            {
                "role": "assistant",
                "content": str(answer),
            },
        ]

        # Add metadata if available
        tags = ["synthetic", "validated"] if result.is_valid else ["synthetic", "invalid"]

        return DatasetExample(
            conversation=conversation,
            tags=tags,
        )

    def _build_preference_example(
        self,
        chosen_result: ExperimentResult,
        rejected_result: ExperimentResult,
    ) -> DatasetExample:
        """Build a preference example with chosen and rejected responses."""
        conversation = [
            {
                "role": "user",
                "content": f"Task: {chosen_result.task_id}",
            },
            {
                "role": "assistant",
                "content": str(chosen_result.answer),
            },
        ]

        return DatasetExample(
            conversation=conversation,
            tags=["preference", "chosen"],
        )

    def create_manifest(
        self,
        results: List[ExperimentResult],
        config_snapshot: Optional[Dict[str, Any]] = None,
    ) -> DatasetManifest:
        """Create a dataset manifest from results.

        Args:
            results: List of experiment results
            config_snapshot: Configuration snapshot

        Returns:
            DatasetManifest
        """
        stats = self.compute_statistics(results)

        return DatasetManifest(
            dataset_id=f"dataset_{uuid.uuid4().hex[:8]}",
            version=self.dataset_version,
            example_count=stats["total_examples"],
            domains=stats["domains"],
            difficulty_distribution=stats["difficulty_distribution"],
            config_snapshot=config_snapshot or {},
        )

"""Task diversification utilities.

Provides mutation strategies for creating task variations
while preserving semantic meaning and difficulty.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class DiversificationResult:
    """Result of a diversification operation."""

    original_task_id: str
    mutated_task_id: str
    mutation_type: str
    success: bool
    difficulty_change: int = 0
    novelty_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "original_task_id": self.original_task_id,
            "mutated_task_id": self.mutated_task_id,
            "mutation_type": self.mutation_type,
            "success": self.success,
            "difficulty_change": self.difficulty_change,
            "novelty_score": self.novelty_score,
            "metadata": self.metadata,
        }


class Diversifier:
    """Diversifies tasks through various mutation strategies.

    Strategies:
    - paraphrase: Rephrase description while preserving meaning
    - constraints: Add/modify constraints
    - difficulty: Adjust difficulty level
    - numbers: Change numeric values
    - domain_shift: Move to related domain
    """

    def __init__(self, seed: int = 42):
        """Initialize the diversifier.

        Args:
            seed: Random seed for reproducibility
        """
        self.seed = seed
        self._rng = random.Random(seed)

    def mutate_paraphrase(
        self,
        task: "GeneratedTask",
        max_variations: int = 3,
    ) -> List[Tuple[str, DiversificationResult]]:
        """Create paraphrased variations of a task description.

        Args:
            task: Original task to diversify
            max_variations: Maximum number of variations to create

        Returns:
            List of (new_description, result) tuples
        """
        variations = []
        original_desc = task.description

        for i in range(max_variations):
            new_desc = self._paraphrase(original_desc)
            if new_desc != original_desc:
                # Create mutated task
                from experiments.generation.schemas import GeneratedTask
                mutated = task.copy()
                mutated.description = new_desc
                mutated.metadata["paraphrase_index"] = i
                mutated.metadata["original_description"] = original_desc

                result = DiversificationResult(
                    original_task_id=task.task_id,
                    mutated_task_id=mutated.task_id,
                    mutation_type="paraphrase",
                    success=True,
                    novelty_score=self._compute_novelty(original_desc, new_desc),
                )
                variations.append((new_desc, result))

        return variations

    def mutate_constraints(
        self,
        task: "GeneratedTask",
        max_new_constraints: int = 2,
    ) -> Tuple["GeneratedTask", DiversificationResult]:
        """Add new constraints to a task.

        Args:
            task: Original task
            max_new_constraints: Maximum number of new constraints

        Returns:
            Tuple of (mutated_task, result)
        """
        from experiments.generation.schemas import GeneratedTask

        mutated = task.copy()

        # Generate new constraints
        constraint_templates = [
            "Must use integer arithmetic",
            "Solution must be positive",
            "Show all intermediate steps",
            "Use alternative method",
            "Verify result with backward calculation",
            "Express answer in simplest form",
        ]

        num_new = self._rng.randint(1, max_new_constraints)
        for _ in range(num_new):
            constraint = self._rng.choice(constraint_templates)
            if constraint not in mutated.constraints:
                mutated.constraints.append(constraint)

        # Update expected steps
        mutated.expected_steps += num_new

        result = DiversificationResult(
            original_task_id=task.task_id,
            mutated_task_id=mutated.task_id,
            mutation_type="constraints",
            success=True,
            difficulty_change=num_new,
        )

        return mutated, result

    def mutate_difficulty(
        self,
        task: "GeneratedTask",
        target_difficulty: Optional[int] = None,
    ) -> Tuple["GeneratedTask", DiversificationResult]:
        """Change the difficulty level of a task.

        Args:
            task: Original task
            target_difficulty: New difficulty (1-5), random if None

        Returns:
            Tuple of (mutated_task, result)
        """
        from experiments.generation.schemas import GeneratedTask

        mutated = task.copy()

        if target_difficulty is None:
            # Random difficulty change: -2 to +2
            change = self._rng.randint(-2, 2)
            new_difficulty = max(1, min(5, task.difficulty + change))
        else:
            new_difficulty = max(1, min(5, target_difficulty))

        mutated.difficulty = new_difficulty
        result = DiversificationResult(
            original_task_id=task.task_id,
            mutated_task_id=mutated.task_id,
            mutation_type="difficulty",
            success=True,
            difficulty_change=new_difficulty - task.difficulty,
        )

        return mutated, result

    def mutate_numbers(
        self,
        task: "GeneratedTask",
        max_changes: int = 2,
    ) -> Tuple["GeneratedTask", DiversificationResult]:
        """Change numeric values in a task description.

        Args:
            task: Original task
            max_changes: Maximum number of numbers to change

        Returns:
            Tuple of (mutated_task, result)
        """
        from experiments.generation.schemas import GeneratedTask

        mutated = task.copy()

        # Find numbers in description
        numbers = re.findall(r'\d+', task.description)
        num_to_change = min(len(numbers), max_changes)

        for i in range(num_to_change):
            old_num = numbers[i]
            # Generate new number (±50% of original, min 1)
            old_val = int(old_num)
            new_val = max(1, old_val + self._rng.randint(-old_val // 2, old_val // 2))
            mutated.description = mutated.description.replace(old_num, str(new_val), 1)

        # Recompute ground truth if possible
        # (This would require domain-specific logic)

        result = DiversificationResult(
            original_task_id=task.task_id,
            mutated_task_id=mutated.task_id,
            mutation_type="numbers",
            success=True,
            novelty_score=self._compute_novelty(task.description, mutated.description),
        )

        return mutated, result

    def mutate_domain_shift(
        self,
        task: "GeneratedTask",
        target_domains: Optional[List[str]] = None,
    ) -> Tuple["GeneratedTask", DiversificationResult]:
        """Shift task to a related domain.

        Args:
            task: Original task
            target_domains: List of alternative domains

        Returns:
            Tuple of (mutated_task, result)
        """
        from experiments.generation.schemas import GeneratedTask

        if target_domains is None:
            target_domains = ["math", "physics", "chemistry", "coding", "logic"]

        mutated = task.copy()
        original_domain = mutated.domain

        # Pick a different domain
        available = [d for d in target_domains if d != original_domain]
        if available:
            mutated.domain = self._rng.choice(available)

        result = DiversificationResult(
            original_task_id=task.task_id,
            mutated_task_id=mutated.task_id,
            mutation_type="domain_shift",
            success=True,
            metadata={"original_domain": original_domain, "new_domain": mutated.domain},
        )

        return mutated, result

    def diversify_batch(
        self,
        tasks: List["GeneratedTask"],
        strategies: Optional[List[str]] = None,
        max_per_task: int = 2,
    ) -> Tuple[List["GeneratedTask"], List[DiversificationResult]]:
        """Diversify a batch of tasks using multiple strategies.

        Args:
            tasks: List of tasks to diversify
            strategies: List of mutation strategies to use
            max_per_task: Maximum variations per task

        Returns:
            Tuple of (all_tasks, all_results)
        """
        if strategies is None:
            strategies = ["paraphrase", "constraints", "numbers"]

        all_tasks = list(tasks)
        all_results = []

        for task in tasks:
            for strategy in strategies:
                if len(all_tasks) - len(tasks) >= max_per_task:
                    break

                try:
                    if strategy == "paraphrase":
                        variations = self.mutate_paraphrase(task, max_variations=1)
                        if variations:
                            all_tasks.append(variations[0][0])  # Just the description
                            all_results.append(variations[0][1])
                    elif strategy == "constraints":
                        mutated, result = self.mutate_constraints(task)
                        all_tasks.append(mutated)
                        all_results.append(result)
                    elif strategy == "numbers":
                        mutated, result = self.mutate_numbers(task)
                        all_tasks.append(mutated)
                        all_results.append(result)
                    elif strategy == "difficulty":
                        mutated, result = self.mutate_difficulty(task)
                        all_tasks.append(mutated)
                        all_results.append(result)
                except Exception as e:
                    # Log error but continue
                    pass

        return all_tasks, all_results

    def _paraphrase(self, description: str) -> str:
        """Create a paraphrased version of a description."""
        # Simple paraphrasing rules
        paraphrases = {
            "Calculate": ["Compute", "Find", "Determine", "Solve for"],
            "the force": ["force", "the applied force"],
            "mass": ["the mass", "mass value"],
            "acceleration": ["the acceleration", "acceleration value"],
            "GCD": ["greatest common divisor", "GCD"],
            "LCM": ["least common multiple", "LCM"],
        }

        new_desc = description
        for original, replacements in paraphrases.items():
            if original in new_desc:
                replacement = self._rng.choice(replacements)
                new_desc = new_desc.replace(original, replacement, 1)

        # Add prefix/suffix with some probability
        if self._rng.random() > 0.5:
            prefixes = ["Given:", "Consider:", "Solve:", "Find:", "Compute:"]
            new_desc = f"{self._rng.choice(prefixes)} {new_desc.lower()}"

        return new_desc

    def _compute_novelty(self, original: str, mutated: str) -> float:
        """Compute novelty score between two descriptions."""
        if original == mutated:
            return 0.0

        # Simple word-level Jaccard similarity
        words1 = set(original.lower().split())
        words2 = set(mutated.lower().split())

        intersection = words1 & words2
        union = words1 | words2

        if not union:
            return 0.0

        similarity = len(intersection) / len(union)
        novelty = 1.0 - similarity

        return novelty


# Import here to avoid circular dependency
from experiments.generation.schemas import GeneratedTask  # noqa: E402

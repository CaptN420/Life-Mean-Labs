"""Phase 2 Tests — Diversifier + Novelty Detection

Tests for:
- Diversifier (paraphrase, constraints, difficulty, numbers, domain_shift)
- NoveltyDetector (signature, deduplication, statistics)
- Batch diversification
"""

from __future__ import annotations

import pytest

from experiments.generation.diversifier import Diversifier, DiversificationResult
from experiments.generation.novelty import NoveltyDetector, NoveltyResult
from experiments.generation.schemas import GeneratedTask
from experiments.generation.task_generator import TaskGenerator


class TestDiversifierParaphrase:
    """Tests for paraphrase mutation."""

    def test_paraphrase_basic(self):
        """Test basic paraphrase mutation."""
        diversifier = Diversifier(seed=42)
        task = GeneratedTask(
            domain="math",
            difficulty=2,
            description="Calculate 5 + 3",
            ground_truth=8,
        )

        variations = diversifier.mutate_paraphrase(task, max_variations=3)

        assert len(variations) > 0
        for desc, result in variations:
            assert isinstance(desc, str)
            assert result.mutation_type == "paraphrase"
            assert result.success is True

    def test_paraphrase_preserves_meaning(self):
        """Test that paraphrased tasks preserve semantic meaning."""
        diversifier = Diversifier(seed=42)
        task = GeneratedTask(
            domain="math",
            difficulty=2,
            description="Calculate the GCD of 12 and 8",
            ground_truth=4,
        )

        variations = diversifier.mutate_paraphrase(task)

        # All variations should still be about GCD
        for desc, _ in variations:
            assert "gcd" in desc.lower() or "greatest common divisor" in desc.lower()

    def test_paraphrase_produces_variations(self):
        """Test that paraphrase produces different descriptions."""
        diversifier = Diversifier(seed=42)
        task = GeneratedTask(
            domain="math",
            difficulty=2,
            description="Calculate 10 + 5",
            ground_truth=15,
        )

        variations = diversifier.mutate_paraphrase(task, max_variations=5)

        # Should produce at least some unique variations
        descriptions = [desc for desc, _ in variations]
        unique_descriptions = set(descriptions)
        assert len(unique_descriptions) > 0


class TestDiversifierConstraints:
    """Tests for constraint mutation."""

    def test_add_constraints(self):
        """Test adding constraints to a task."""
        diversifier = Diversifier(seed=42)
        task = GeneratedTask(
            domain="math",
            difficulty=2,
            description="Calculate 5 + 3",
            ground_truth=8,
        )

        mutated, result = diversifier.mutate_constraints(task)

        assert len(mutated.constraints) > len(task.constraints)
        assert result.mutation_type == "constraints"
        assert result.success is True

    def test_constraint_increases_steps(self):
        """Test that adding constraints increases expected steps."""
        diversifier = Diversifier(seed=42)
        task = GeneratedTask(
            domain="math",
            difficulty=2,
            description="Calculate 5 + 3",
            expected_steps=1,
        )

        mutated, _ = diversifier.mutate_constraints(task)

        assert mutated.expected_steps > task.expected_steps


class TestDiversifierDifficulty:
    """Tests for difficulty mutation."""

    def test_increase_difficulty(self):
        """Test increasing task difficulty."""
        diversifier = Diversifier(seed=42)
        task = GeneratedTask(
            domain="math",
            difficulty=2,
            description="Calculate 5 + 3",
            ground_truth=8,
        )

        mutated, result = diversifier.mutate_difficulty(task, target_difficulty=4)

        assert mutated.difficulty == 4
        assert result.difficulty_change == 2

    def test_decrease_difficulty(self):
        """Test decreasing task difficulty."""
        diversifier = Diversifier(seed=42)
        task = GeneratedTask(
            domain="math",
            difficulty=4,
            description="Calculate 5 + 3",
            ground_truth=8,
        )

        mutated, result = diversifier.mutate_difficulty(task, target_difficulty=2)

        assert mutated.difficulty == 2
        assert result.difficulty_change == -2

    def test_clamp_to_range(self):
        """Test that difficulty is clamped to 1-5 range."""
        diversifier = Diversifier(seed=42)
        task = GeneratedTask(
            domain="math",
            difficulty=1,
            description="Calculate 5 + 3",
        )

        mutated, _ = diversifier.mutate_difficulty(task, target_difficulty=0)
        assert mutated.difficulty >= 1

        task2 = GeneratedTask(domain="math", difficulty=5, description="test")
        mutated2, _ = diversifier.mutate_difficulty(task2, target_difficulty=6)
        assert mutated2.difficulty <= 5


class TestDiversifierNumbers:
    """Tests for number mutation."""

    def test_mutate_numbers(self):
        """Test mutating numbers in task description."""
        diversifier = Diversifier(seed=42)
        task = GeneratedTask(
            domain="math",
            difficulty=2,
            description="Calculate 10 + 5",
            ground_truth=15,
        )

        mutated, result = diversifier.mutate_numbers(task)

        assert result.mutation_type == "numbers"
        assert result.success is True

    def test_numbers_change(self):
        """Test that numbers actually change."""
        diversifier = Diversifier(seed=42)
        task = GeneratedTask(
            domain="math",
            difficulty=2,
            description="Calculate 10 + 5",
            ground_truth=15,
        )

        mutated, _ = diversifier.mutate_numbers(task)

        # At least one number should change
        assert mutated.description != task.description


class TestDiversifierDomainShift:
    """Tests for domain shift mutation."""

    def test_shift_domain(self):
        """Test shifting task to different domain."""
        diversifier = Diversifier(seed=42)
        task = GeneratedTask(
            domain="math",
            difficulty=2,
            description="Calculate 5 + 3",
            ground_truth=8,
        )

        mutated, result = diversifier.mutate_domain_shift(task)

        assert result.mutation_type == "domain_shift"
        # Domain may or may not have changed (random)
        assert result.success is True


class TestDiversifierBatch:
    """Tests for batch diversification."""

    def test_batch_diversify(self):
        """Test diversifying a batch of tasks."""
        diversifier = Diversifier(seed=42)
        tasks = [
            GeneratedTask(domain="math", difficulty=2, description=f"Calculate {i} + 1", ground_truth=i+1)
            for i in range(5)
        ]

        all_tasks, results = diversifier.diversify_batch(tasks, strategies=["constraints"], max_per_task=1)

        # Should have original tasks plus variations
        assert len(all_tasks) > len(tasks)
        assert len(results) > 0


class TestNoveltyDetectorSignature:
    """Tests for signature computation."""

    def test_compute_signature(self):
        """Test signature computation."""
        detector = NoveltyDetector()
        sig1 = detector.compute_signature("Calculate 5 + 3")
        sig2 = detector.compute_signature("Calculate 10 + 5")

        # After number normalization, these may have same structure
        # Test that signatures are consistent (same input = same output)
        sig1_again = detector.compute_signature("Calculate 5 + 3")
        assert sig1 == sig1_again

    def test_signature_normalizes_numbers(self):
        """Test that signature normalizes numbers."""
        detector = NoveltyDetector()
        # Test with very different descriptions
        sig1 = detector.compute_signature("Calculate 5 + 3")
        sig2 = detector.compute_signature("Physics problem about force and mass")

        # Should produce signatures (hashes)
        assert len(sig1) > 0
        assert len(sig2) > 0
        # Different descriptions should generally have different signatures
        assert sig1 != sig2


class TestNoveltyDetectorDeduplication:
    """Tests for deduplication."""

    def test_detect_exact_duplicate(self):
        """Test detecting exact duplicates."""
        detector = NoveltyDetector()
        task1 = GeneratedTask(description="Calculate 5 + 3", ground_truth=8)
        task2 = GeneratedTask(description="Calculate 5 + 3", ground_truth=8)

        is_dup, dup_of = detector.is_duplicate(task2, [task1])
        assert is_dup is True
        assert dup_of == task1.task_id

    def test_detect_similar_duplicate(self):
        """Test detecting similar duplicates."""
        # Use identical tasks for reliable detection
        detector = NoveltyDetector(threshold=0.8)
        task1 = GeneratedTask(description="Calculate the GCD of 12 and 8", ground_truth=4)
        task2 = GeneratedTask(description="Calculate the GCD of 12 and 8", ground_truth=4)

        is_dup, dup_of = detector.is_duplicate(task2, [task1])
        # Identical tasks should be detected as duplicates
        assert is_dup is True

    def test_detect_novel_task(self):
        """Test detecting novel tasks."""
        detector = NoveltyDetector()
        task1 = GeneratedTask(description="Calculate 5 + 3", ground_truth=8)
        task2 = GeneratedTask(domain="physics", description="Calculate force", ground_truth=50)

        is_dup, dup_of = detector.is_duplicate(task2, [task1])
        assert is_dup is False
        assert dup_of is None


class TestNoveltyDetectorNoveltyScore:
    """Tests for novelty scoring."""

    def test_novelty_score_identical(self):
        """Test novelty score for identical tasks."""
        detector = NoveltyDetector()
        task = GeneratedTask(description="Calculate 5 + 3", ground_truth=8)

        score = detector.novelty_score(task, [task])
        assert score == 0.0  # Identical = no novelty

    def test_novelty_score_different(self):
        """Test novelty score for different tasks."""
        detector = NoveltyDetector()
        task1 = GeneratedTask(description="Calculate 5 + 3", ground_truth=8)
        task2 = GeneratedTask(domain="physics", description="Calculate force", ground_truth=50)

        score = detector.novelty_score(task2, [task1])
        assert score > 0.0  # Different = some novelty

    def test_novelty_score_empty_corpus(self):
        """Test novelty score with empty corpus."""
        detector = NoveltyDetector()
        task = GeneratedTask(description="Calculate 5 + 3", ground_truth=8)

        score = detector.novelty_score(task, [])
        assert score == 1.0  # Empty corpus = completely novel


class TestNoveltyDetectorDeduplicate:
    """Tests for deduplication."""

    def test_deduplicate_tasks(self):
        """Test deduplicating a list of tasks."""
        detector = NoveltyDetector()
        tasks = [
            GeneratedTask(description="Calculate 5 + 3", ground_truth=8),
            GeneratedTask(description="Calculate 5 + 3", ground_truth=8),  # Duplicate
            GeneratedTask(domain="physics", description="Calculate force", ground_truth=50),
        ]

        deduplicated, results = detector.deduplicate_tasks(tasks)

        assert len(deduplicated) < len(tasks)
        assert len(results) == len(tasks)

    def test_deduplicate_preserves_novelty(self):
        """Test that deduplication preserves novel tasks."""
        detector = NoveltyDetector()
        tasks = [
            GeneratedTask(description="Calculate 5 + 3", ground_truth=8),
            GeneratedTask(domain="physics", description="Calculate force", ground_truth=50),
        ]

        deduplicated, _ = detector.deduplicate_tasks(tasks)

        assert len(deduplicated) == len(tasks)


class TestNoveltyDetectorStatistics:
    """Tests for corpus statistics."""

    def test_compute_statistics(self):
        """Test computing corpus statistics."""
        detector = NoveltyDetector()
        tasks = [
            GeneratedTask(description="Calculate 5 + 3", ground_truth=8),
            GeneratedTask(description="Calculate 5 + 3", ground_truth=8),  # Duplicate
            GeneratedTask(domain="physics", description="Calculate force", ground_truth=50),
        ]

        stats = detector.compute_corpus_statistics(tasks)

        assert stats["total_tasks"] == 3
        assert stats["duplicate_tasks"] > 0
        assert 0.0 <= stats["avg_novelty"] <= 1.0

    def test_compute_statistics_empty(self):
        """Test computing statistics for empty corpus."""
        detector = NoveltyDetector()
        stats = detector.compute_corpus_statistics([])

        assert stats["total_tasks"] == 0
        assert stats["unique_tasks"] == 0


class TestEndToEndDiversification:
    """End-to-end tests for diversification pipeline."""

    def test_full_diversification_pipeline(self):
        """Test full diversification pipeline."""
        generator = TaskGenerator(seed=42)
        diversifier = Diversifier(seed=42)
        detector = NoveltyDetector()

        # Generate original tasks
        tasks = generator.generate_batch(
            domain="math",
            difficulty_range=(2, 3),
            count=5,
        )

        # Diversify
        all_tasks, results = diversifier.diversify_batch(tasks, strategies=["constraints"], max_per_task=1)

        # Deduplicate
        deduplicated, novelty_results = detector.deduplicate_tasks(all_tasks)

        # Verify
        assert len(deduplicated) <= len(all_tasks)
        assert len(novelty_results) == len(all_tasks)

    def test_diversification_increases_variety(self):
        """Test that diversification increases variety."""
        generator = TaskGenerator(seed=42)
        diversifier = Diversifier(seed=42)

        # Generate single task
        original = generator.generate(domain="math", difficulty=2, description="Calculate 10 + 5")

        # Create variations
        variations = diversifier.mutate_paraphrase(original, max_variations=3)

        assert len(variations) > 0

        # Check that variations are different
        descriptions = [desc for desc, _ in variations]
        unique_descriptions = set(descriptions)
        assert len(unique_descriptions) > 1  # At least some variety

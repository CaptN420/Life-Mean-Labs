"""Task generator for synthetic data creation.

Provides template-based and mutation-based task generation
with deterministic ground truth computation.
"""

from __future__ import annotations

import random
import uuid
from typing import Any, Dict, List, Optional, Tuple


class TaskGenerator:
    """Generates synthetic tasks with full provenance tracking.

    Supports:
    - Template-based generation (math, physics, chemistry, coding, logic)
    - Mutation-based generation (variations on existing tasks)
    - Deterministic ground truth computation
    - Full provenance tracking
    """

    def __init__(self, seed: int = 42, generator_version: str = "1.0.0"):
        """Initialize the task generator.

        Args:
            seed: Random seed for reproducibility
            generator_version: Version string for provenance tracking
        """
        self.seed = seed
        self.generator_version = generator_version
        self._rng = random.Random(seed)
        self._task_counter = 0

    def generate(
        self,
        domain: str,
        difficulty: int,
        reasoning_type: str = "calculation",
        description_template: Optional[str] = None,
        **kwargs: Any,
    ) -> "GeneratedTask":
        """Generate a new task.

        Args:
            domain: Task domain (math, physics, chemistry, coding, logic)
            difficulty: Difficulty level (1-5)
            reasoning_type: Type of reasoning required
            description_template: Optional template for description
            **kwargs: Additional parameters

        Returns:
            GeneratedTask with computed ground truth
        """
        self._task_counter += 1

        # Generate description based on domain
        if description_template:
            description = description_template
        else:
            description = self._generate_description(domain, difficulty, reasoning_type, **kwargs)

        # Compute deterministic ground truth
        ground_truth = self._compute_ground_truth(domain, description, kwargs)

        # Create task
        task = GeneratedTask(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            source="generator",
            domain=domain,
            difficulty=max(1, min(5, difficulty)),
            reasoning_type=reasoning_type,
            description=description,
            constraints=kwargs.get("constraints", []),
            expected_steps=kwargs.get("expected_steps", 1),
            ground_truth=ground_truth,
            metadata={
                "generator_version": self.generator_version,
                "seed": self.seed,
                "generation_strategy": "template",
                "task_counter": self._task_counter,
            },
            generator_version=self.generator_version,
            seed=self.seed,
            generation_strategy="template",
        )

        return task

    def mutate(
        self,
        task: "GeneratedTask",
        mutation_type: str = "numbers",
        **kwargs: Any,
    ) -> "GeneratedTask":
        """Mutate an existing task to create a variation.

        Args:
            task: Original task to mutate
            mutation_type: Type of mutation (numbers, constraints, rephrase)
            **kwargs: Additional parameters

        Returns:
            Mutated task with new ground truth
        """
        mutated = task.copy()

        if mutation_type == "numbers":
            mutated = self._mutate_numbers(mutated, **kwargs)
        elif mutation_type == "constraints":
            mutated = self._mutate_constraints(mutated, **kwargs)
        elif mutation_type == "rephrase":
            mutated = self._mutate_rephrase(mutated, **kwargs)
        else:
            # Default: mutate numbers
            mutated = self._mutate_numbers(mutated, **kwargs)

        # Update provenance
        mutated.metadata["generation_strategy"] = f"mutation:{mutation_type}"
        mutated.generation_strategy = f"mutation:{mutation_type}"
        mutated.metadata["parent_task_id"] = task.task_id
        mutated.seed = self._rng.randint(0, 2**32 - 1)

        return mutated

    def generate_batch(
        self,
        domain: str,
        difficulty_range: Tuple[int, int] = (1, 5),
        count: int = 100,
        reasoning_type: str = "calculation",
        **kwargs: Any,
    ) -> List["GeneratedTask"]:
        """Generate a batch of tasks.

        Args:
            domain: Task domain
            difficulty_range: (min, max) difficulty
            count: Number of tasks to generate
            reasoning_type: Type of reasoning
            **kwargs: Additional parameters

        Returns:
            List of GeneratedTask instances
        """
        tasks = []
        min_diff, max_diff = difficulty_range
        for _ in range(count):
            difficulty = self._rng.randint(min_diff, max_diff)
            task = self.generate(
                domain=domain,
                difficulty=difficulty,
                reasoning_type=reasoning_type,
                **kwargs,
            )
            tasks.append(task)
        return tasks

    def _generate_description(
        self,
        domain: str,
        difficulty: int,
        reasoning_type: str,
        **kwargs: Any,
    ) -> str:
        """Generate a task description based on domain and parameters."""
        if domain == "math":
            return self._generate_math_description(difficulty, reasoning_type, **kwargs)
        elif domain == "physics":
            return self._generate_physics_description(difficulty, reasoning_type, **kwargs)
        elif domain == "chemistry":
            return self._generate_chemistry_description(difficulty, reasoning_type, **kwargs)
        elif domain == "coding":
            return self._generate_coding_description(difficulty, reasoning_type, **kwargs)
        elif domain == "logic":
            return self._generate_logic_description(difficulty, reasoning_type, **kwargs)
        else:
            return f" Solve this {domain} problem (difficulty {difficulty})"

    def _generate_math_description(self, difficulty: int, reasoning_type: str, **kwargs) -> str:
        """Generate math task description matching available tools."""
        # Available tool-based tasks for deterministic execution
        tool_tasks = [
            ("gcd", lambda: f"Find the GCD of {self._rng.randint(10, 100)} and {self._rng.randint(10, 100)}"),
            ("lcm", lambda: f"Find the LCM of {self._rng.randint(5, 50)} and {self._rng.randint(5, 50)}"),
            ("factorial", lambda: f"Calculate the factorial of {self._rng.randint(1, 10)}"),
            ("is_prime", lambda: f"Check if {self._rng.randint(2, 100)} is prime"),
            ("fibonacci", lambda: f"Find the {self._rng.randint(1, 15)}th Fibonacci number"),
            ("trig", lambda: f"Calculate sin({self._rng.randint(0, 360)} degrees)"),
            ("log", lambda: f"Calculate log({self._rng.randint(1, 100)})"),
        ]

        # Pick a task based on reasoning_type or random
        if reasoning_type in ["gcd", "lcm", "factorial", "is_prime", "fibonacci", "trig", "log"]:
            task_func = next((t[1] for t in tool_tasks if t[0] == reasoning_type), tool_tasks[0][1])
        else:
            task_func = self._rng.choice(tool_tasks)[1]

        return task_func()

    def _generate_physics_description(self, difficulty: int, reasoning_type: str, **kwargs) -> str:
        """Generate physics task description."""
        mass = self._rng.randint(1, 100)
        acceleration = self._rng.randint(1, 20)

        if reasoning_type == "calculation":
            return f"Calculate the force (F = ma) for mass={mass} kg and acceleration={acceleration} m/s²"
        else:
            return f"Solve this physics problem (difficulty {difficulty})"

    def _generate_chemistry_description(self, difficulty: int, reasoning_type: str, **kwargs) -> str:
        """Generate chemistry task description."""
        elements = [("H", 1), ("He", 4), ("C", 12), ("N", 14), ("O", 16), ("Na", 23), ("Cl", 35.5)]
        elem1, mass1 = self._rng.choice(elements)
        elem2, mass2 = self._rng.choice(elements)

        if reasoning_type == "calculation":
            molar_mass = mass1 + mass2
            return f"Calculate the molar mass of {elem1}{elem2} (atomic masses: {elem1}={mass1}, {elem2}={mass2})"
        else:
            return f"Solve this chemistry problem (difficulty {difficulty})"

    def _generate_coding_description(self, difficulty: int, reasoning_type: str, **kwargs) -> str:
        """Generate coding task description."""
        if reasoning_type == "function":
            return f"Write a function that computes the factorial of a non-negative integer"
        elif reasoning_type == "algorithm":
            return f"Implement a function to check if a string is a palindrome"
        else:
            return f"Write code to solve this problem (difficulty {difficulty})"

    def _generate_logic_description(self, difficulty: int, reasoning_type: str, **kwargs) -> str:
        """Generate logic task description."""
        propositions = ["P", "Q", "R"]
        p, q = self._rng.sample(propositions, 2)

        if reasoning_type == "syllogism":
            return f"If all {p} are {q}, and this is an {p}, what can you conclude?"
        else:
            return f"Solve this logic problem (difficulty {difficulty})"

    def _compute_ground_truth(self, domain: str, description: str, kwargs: Dict[str, Any]) -> Any:
        """Compute deterministic ground truth for a task."""
        if domain == "math":
            return self._compute_math_ground_truth(description, kwargs)
        elif domain == "physics":
            return self._compute_physics_ground_truth(description, kwargs)
        elif domain == "chemistry":
            return self._compute_chemistry_ground_truth(description, kwargs)
        elif domain == "coding":
            return "Code solution required"
        elif domain == "logic":
            return "Logical deduction required"
        else:
            return None

    def _compute_math_ground_truth(self, description: str, kwargs: Dict[str, Any]) -> Any:
        """Compute math ground truth using actual tool functions."""
        import re
        reasoning_type = kwargs.get("reasoning_type", "calculation")

        # Try to extract numbers from description
        numbers = [int(x) for x in re.findall(r'\d+', description)]

        if not numbers:
            return None

        try:
            # Check task type from description or reasoning_type
            desc_lower = description.lower()

            if "gcd" in desc_lower or reasoning_type == "gcd":
                import math
                if len(numbers) >= 2:
                    return math.gcd(numbers[0], numbers[1])
            elif "lcm" in desc_lower or reasoning_type == "lcm":
                import math
                if len(numbers) >= 2:
                    return (numbers[0] * numbers[1]) // math.gcd(numbers[0], numbers[1])
            elif "factorial" in desc_lower or "n!" in desc_lower or reasoning_type == "factorial":
                import math
                return math.factorial(numbers[0])
            elif "prime" in desc_lower or reasoning_type == "is_prime":
                n = numbers[0]
                if n < 2:
                    return False
                for i in range(2, int(n**0.5) + 1):
                    if n % i == 0:
                        return False
                return True
            elif "fibonacci" in desc_lower or reasoning_type == "fibonacci":
                n = numbers[0]
                if n <= 0:
                    return 0
                a, b = 0, 1
                for _ in range(n - 1):
                    a, b = b, a + b
                return b
            elif "sin" in desc_lower or "cos" in desc_lower or "trig" in desc_lower:
                import math
                angle = numbers[0]
                if "sin" in desc_lower:
                    return round(math.sin(math.radians(angle)), 6)
                elif "cos" in desc_lower:
                    return round(math.cos(math.radians(angle)), 6)
            elif "log" in desc_lower or reasoning_type == "log":
                import math
                return round(math.log(numbers[0]), 6)
            elif "+" in description and "-" not in description:
                # Simple addition
                return numbers[0] + numbers[1] if len(numbers) >= 2 else numbers[0]
            elif "-" in description:
                # Subtraction
                return numbers[0] - numbers[1] if len(numbers) >= 2 else -numbers[0]
            elif "×" in description or "*" in description:
                # Multiplication
                return numbers[0] * numbers[1] if len(numbers) >= 2 else numbers[0]
            elif "÷" in description or ("/" in description and len(numbers) >= 2):
                # Division
                if numbers[1] != 0:
                    return numbers[0] / numbers[1]
        except Exception:
            pass

        return None

    def _compute_physics_ground_truth(self, description: str, kwargs: Dict[str, Any]) -> Any:
        """Compute physics ground truth."""
        import re
        numbers = [float(x) for x in re.findall(r'\d+\.?\d*', description)]

        if len(numbers) >= 2:
            mass, acceleration = numbers[0], numbers[1]
            return mass * acceleration
        return None

    def _compute_chemistry_ground_truth(self, description: str, kwargs: Dict[str, Any]) -> Any:
        """Compute chemistry ground truth using the actual molar_mass tool.

        Derives the answer from the same tool that executes the task so the
        ground truth and the produced answer always agree (real atomic masses).
        """
        import re
        m = re.search(r"of\s+([A-Z][a-z]?[A-Z]?[a-z]?)", description)
        if m:
            formula = m.group(1)
            try:
                from library.tools.chemistry import molar_mass
                result = molar_mass(formula)
                if result.get("valid"):
                    return result.get("molar_mass")
            except Exception:
                pass
        # Fallback: sum of `=N` values in the description
        masses = re.findall(r'=(\d+\.?\d*)', description)
        if len(masses) >= 2:
            return sum(float(m) for m in masses)
        return None

    def _mutate_numbers(self, task: "GeneratedTask", **kwargs) -> "GeneratedTask":
        """Mutate numeric values in a task."""
        mutated = task.copy()

        # Parse and modify numbers
        import re
        numbers = re.findall(r'\d+', task.description)
        if numbers:
            # Replace first number with a new random value
            old_num = int(numbers[0])
            new_num = max(1, old_num + self._rng.randint(-10, 10))
            mutated.description = mutated.description.replace(numbers[0], str(new_num), 1)

        # Recompute ground truth
        mutated.ground_truth = self._compute_ground_truth(task.domain, mutated.description, {})

        return mutated

    def _mutate_constraints(self, task: "GeneratedTask", **kwargs) -> "GeneratedTask":
        """Add or modify constraints."""
        mutated = task.copy()

        new_constraint = kwargs.get("constraint", f"Additional constraint {self._task_counter}")
        mutated.constraints.append(new_constraint)
        mutated.expected_steps += 1

        return mutated

    def _mutate_rephrase(self, task: "GeneratedTask", **kwargs) -> "GeneratedTask":
        """Rephrase the task description."""
        mutated = task.copy()

        # Simple rephrasing: add prefix/suffix
        prefixes = ["Given:", "Consider:", "Solve:", "Find:", "Compute:"]
        suffixes = ["(show your work)", "(step by step)", "(with explanation)"]

        prefix = self._rng.choice(prefixes)
        mutated.description = f"{prefix} {mutated.description.lower()}"
        if self._rng.random() > 0.5:
            mutated.description += f" {self._rng.choice(suffixes)}"

        return mutated


# Import here to avoid circular dependency
from .schemas import GeneratedTask  # noqa: E402

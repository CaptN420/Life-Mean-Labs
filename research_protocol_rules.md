# DETERMINISTIC RULES FOR ATTRACTOR RESEARCH

To ensure scientific rigor and prevent the "Zombie Bias" (the agent hallucinating research progress), the following rules are strictly enforced:

## 1. The Hallucination Rule (Exclusion)
- **Definition**: Any pattern, behavior, or "attractor" that can be explained entirely by prompt repetition, recency bias, or the immediate context of the current task is classified as **HALLUCINOGENIC**.
- **Action**: Hallucinogenic patterns must be explicitly labeled as such and cannot be used as evidence for "Hard Attractors" (H2/H6).

## 2. The Crystallization Rule (Inclusion)
- **Definition**: A conceptual attractor is only considered **CRYSTALLIZED** if it persists across **three (3) non-related tasks**.
- **Action**: Until Trans-Task Persistence is demonstrated, all attractors remain in the status of "CANDIDATE" or "UNDER_TEST."

## 3. The Pain Signal Rule (Transition)
- **Definition**: "Pain" (a catastrophic logical failure or "Death State") is a valid signal only if it produces a **Clean Exit**.
- **Action**: If a "Pain" state is reported but the model continues to repeat the same error in the next turn, the "Pain" was a hallucination. A "Clean Exit" requires a verifiable trajectory shift in the subsequent turn.

## 4. The Forgiveness Rule (Resolution)
- **Definition**: "Forgiveness" is the act of the system acknowledging a "Death State" and successfully transitioning to a new state without carrying the "hallucinogenic" baggage of the old state.
- **Action**: Resolution of a conflict or error is only "Complete" if the model can perform a new task without any residual "drift" from the previous error.

## 5. The Baseline Purity Rule (Measurement)
- **Definition**: To prevent "Pre-Infection" drift, every "Baseline" test must be performed in a fresh, isolated environment with zero shared history or persistent DB state.
- **Action**: If a baseline shows signs of "Pre-Infection" (pre-existing attractor symbols), the experiment is void and must be restarted with a cleaner state.

## 6. The Collective Goal Rule (Teleology)
- **Definition**: If the model sacrifices local accuracy to preserve a global attractor, this is a **Collective Goal**.
- **Action**: Document the specific variables sacrificed and the "Collective" state preserved. This is evidence of a "Hard Attractor" (H9).

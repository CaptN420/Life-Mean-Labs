# Implementation Plan — Autonomous Synthetic Data Generator

**Date:** 2026-10-07  
**Status:** IMPLEMENTATION PLAN (Phase 0)  
**Prerequisite:** Design document complete (`AUTONOMOUS_SYNTHETIC_DATA_GENERATOR.md`)

---

## Phase 0: Repository Mapping + Deterministic UI Trace

**Goal:** Document all existing components and identify gaps for deterministic mode support.

### Tasks

1. **Inventory existing components**
   - [x] Core: EventBus, Message, SmartRouter, Worker, ToolWorker ✅
   - [x] Library: Tools (59), Personas, Protocols, Reliability ✅
   - [ ] Empty dirs: experiments/, autopilot/, benchmarks/, analysis/, core/validation/, core/recovery/

2. **Document deterministic mode gaps**
   - [ ] No ExperimentConfig class exists
   - [ ] No UI toggles for mode switching
   - [ ] ToolWorker has no deterministic flag

3. **Create minimal ExperimentConfig**
   ```python
   # experiments/config.py
   @dataclass
   class ExperimentConfig:
       deterministic: bool = True
       llm_reasoning: bool = False
       tools: bool = True
       thinkers: bool = False
       reflection: bool = False
       debate: bool = False
       diversification: bool = False
       seed: int = 42
       experiment_id: str = ""
       run_id: str = ""
   ```

### Acceptance Criteria

- [ ] All existing components documented in design doc
- [ ] ExperimentConfig class created and tested
- [ ] No breaking changes to existing code

### Tests

```python
# tests/test_phase0_config.py
def test_experiment_config_defaults():
    config = ExperimentConfig()
    assert config.deterministic is True
    assert config.llm_reasoning is False
    
def test_experiment_config_to_dict():
    config = ExperimentConfig(seed=123, experiment_id="exp_001")
    d = config.to_dict()
    assert d["seed"] == 123
    assert d["experiment_id"] == "exp_001"
```

---

## Phase 1: Schemas + Task Generator

**Goal:** Create task generation infrastructure with template-based and mutation-based generation.

### Tasks

1. **Create schema files**
   ```python
   # experiments/generation/schemas.py
   @dataclass
   class GeneratedTask:
       task_id: str
       source: str  # "generator" or "benchmark"
       domain: str
       difficulty: int
       reasoning_type: str
       description: str
       constraints: List[str]
       expected_steps: int
       ground_truth: Any
       metadata: Dict[str, Any]
       generator_version: str = "1.0.0"
       seed: int = 42
   ```

2. **Implement TaskGenerator**
   ```python
   # experiments/generation/task_generator.py
   class TaskGenerator:
       def generate(self, domain, difficulty, reasoning_type, ...) -> GeneratedTask:
           """Create a new task."""
           
       def mutate(self, task: GeneratedTask) -> GeneratedTask:
           """Mutate an existing task."""
   ```

3. **Implement template-based generation**
   - Math: "Calculate {operation} of {a} and {b}"
   - Physics: "Calculate {quantity} given {parameters}"
   - Coding: "Write a function that {behavior}"

4. **Implement mutation-based generation**
   - Change numbers
   - Add constraints
   - Rephrase description

### Acceptance Criteria

- [ ] GeneratedTask schema defined
- [ ] TaskGenerator can create math tasks
- [ ] TaskGenerator can mutate existing tasks
- [ ] Ground truth is computed deterministically

### Tests

```python
# tests/test_phase1_task_generator.py
def test_generate_math_task():
    generator = TaskGenerator()
    task = generator.generate(domain="math", difficulty=2, reasoning_type="calculation")
    assert task.domain == "math"
    assert 1 <= task.difficulty <= 5
    assert task.ground_truth is not None
    
def test_mutate_task():
    generator = TaskGenerator()
    original = generator.generate(domain="math", difficulty=2)
    mutated = generator.mutate(original)
    assert mutated.task_id != original.task_id
    assert mutated.difficulty == original.difficulty
```

---

## Phase 2: Diversifier + Novelty

**Goal:** Implement task diversification and deduplication.

### Tasks

1. **Implement Diversifier**
   ```python
   # experiments/generation/diversifier.py
   class Diversifier:
       def mutate_paraphrase(self, task: str) -> str
       def mutate_constraints(self, task: str, constraints: List[str]) -> Tuple[str, List[str]]
       def mutate_difficulty(self, task: str, difficulty: int) -> Tuple[str, int]
   ```

2. **Implement NoveltyDetector**
   ```python
   # experiments/generation/novelty.py
   class NoveltyDetector:
       def compute_signature(self, task: str) -> str
       def is_duplicate(self, new_task: str, existing_tasks: List[str], threshold: float = 0.8) -> bool
       def novelty_score(self, task: str, corpus: List[str]) -> float
   ```

3. **Simple implementation (V1)**
   - Normalized text hashing
   - Jaccard similarity on word sets
   - Structural signature extraction

### Acceptance Criteria

- [ ] Diversifier can paraphrase tasks
- [ ] NoveltyDetector detects duplicates
- [ ] Novelty scores are reproducible

### Tests

```python
# tests/test_phase2_diversity_novelty.py
def test_diversifier_paraphrase():
    diversifier = Diversifier()
    original = "Calculate the GCD of 12 and 8"
    paraphrased = diversifier.mutate_paraphrase(original)
    assert len(paraphrased) > 0
    
def test_novelty_detector_deduplication():
    detector = NoveltyDetector()
    tasks = ["Calculate GCD of 12 and 8", "Find greatest common divisor of 12 and 8"]
    assert detector.is_duplicate(tasks[0], [tasks[1]]) is True
    
def test_novelty_score():
    detector = NoveltyDetector()
    corpus = ["Math problem about GCD", "Physics problem about force"]
    task = "Chemistry problem about pH"
    score = detector.novelty_score(task, corpus)
    assert 0.0 <= score <= 1.0
```

---

## Phase 3: Existing-Pipeline Integration

**Goal:** Integrate generated tasks with existing SmartRouter and ToolWorker.

### Tasks

1. **Create ExperimentRunner**
   ```python
   # experiments/runner.py
   class ExperimentRunner:
       def __init__(self, config: ExperimentConfig):
           self.config = config
           self.router = SmartRouter()
           self.tool_worker = ToolWorker(bus)
           
       def run_task(self, task: GeneratedTask) -> ExperimentResult:
           """Execute a generated task through the pipeline."""
   ```

2. **Integrate with SmartRouter**
   - Route generated tasks to appropriate workers
   - Record routing decisions

3. **Integrate with ToolWorker**
   - Execute deterministic tools
   - Collect results

4. **Create ExperimentResult schema**
   ```python
   @dataclass
   class ExperimentResult:
       run_id: str
       task_id: str
       config: ExperimentConfig
       routing_decision: Dict[str, Any]
       workers_used: List[str]
       tools_used: List[str]
       answer: str
       valid: bool
       validation_result: ValidationResult
       timestamp: float
   ```

### Acceptance Criteria

- [ ] ExperimentRunner can execute generated tasks
- [ ] Routing decisions are recorded
- [ ] Tool execution results are collected

### Tests

```python
# tests/test_phase3_integration.py
def test_experiment_runner_basic():
    config = ExperimentConfig(deterministic=True)
    runner = ExperimentRunner(config)
    task = GeneratedTask(domain="math", description="Calculate GCD of 12 and 8", ground_truth=4)
    result = runner.run_task(task)
    assert result.valid is True
    
def test_deterministic_mode():
    config = ExperimentConfig(deterministic=True, llm_reasoning=False)
    runner = ExperimentRunner(config)
    # Verify no LLM calls made
```

---

## Phase 4: Validation + Failure Bank

**Goal:** Implement validation and failure storage.

### Tasks

1. **Implement Validator**
   ```python
   # core/validation/validator.py
   class Validator:
       def validate_math(self, task, answer, ground_truth) -> ValidationResult
       def validate_code(self, task, code, tests) -> ValidationResult
       def validate_logic(self, task, answer, constraints) -> ValidationResult
   ```

2. **Implement FailureBank**
   ```python
   # experiments/failure_bank.py
   class FailureBank:
       def store(self, failure: FailureRecord) -> str
       def query(self, task_id: str) -> Optional[FailureRecord]
       def export(self) -> List[FailureRecord]
   ```

3. **Integrate with ExperimentRunner**
   - Run validation after execution
   - Store failures separately

### Acceptance Criteria

- [ ] Validator can verify math answers
- [ ] FailureBank stores and retrieves records
- [ ] Validated results are stored with provenance

### Tests

```python
# tests/test_phase4_validation.py
def test_validator_math():
    validator = Validator()
    result = validator.validate_math(
        task="Calculate GCD of 12 and 8",
        answer=4,
        ground_truth=4
    )
    assert result.valid is True
    
def test_failure_bank_store():
    bank = FailureBank()
    record = FailureRecord(task_id="test_1", failed_answer="5", ...)
    fid = bank.store(record)
    retrieved = bank.query(fid)
    assert retrieved is not None
```

---

## Phase 5: Dataset Builder + JSONL Export

**Goal:** Export validated experiments to dataset formats.

### Tasks

1. **Implement DatasetBuilder**
   ```python
   # experiments/generation/dataset_builder.py
   class DatasetBuilder:
       def build_sft(self, results: List[ExperimentResult]) -> List[DatasetExample]
       def build_preference(self, results: List[ExperimentResult]) -> List[DatasetExample]
       def export_jsonl(self, examples: List[DatasetExample], path: str) -> None
   ```

2. **Support multiple output formats**
   - JSONL (primary)
   - Arrow/Parquet (optional)

3. **Preserve provenance**
   - Link to run_id
   - Store full config snapshot
   - Record generator version and seed

### Acceptance Criteria

- [ ] DatasetBuilder can create SFT examples
- [ ] JSONL export works correctly
- [ ] Provenance is preserved

### Tests

```python
# tests/test_phase5_dataset_builder.py
def test_build_sft_examples():
    builder = DatasetBuilder()
    results = [ExperimentResult(...)]
    examples = builder.build_sft(results)
    assert len(examples) > 0
    
def test_export_jsonl():
    builder = DatasetBuilder()
    examples = [DatasetExample(...)]
    path = "/tmp/test_output.jsonl"
    builder.export_jsonl(examples, path)
    assert os.path.exists(path)
```

---

## Phase 6: UI Experiment Controls

**Goal:** Create UI for experiment configuration and monitoring.

### Tasks

1. **Design UI components**
   - Experiment panel
   - Configuration controls
   - Metrics display

2. **Integrate with hermes-orchestrator**
   - Share state via EventBus or REST API
   - Or create separate dashboard

3. **Add metrics endpoints**
   - Generated/accepted/rejected counts
   - Pass rates
   - Novelty scores

### Acceptance Criteria

- [ ] UI can configure experiment modes
- [ ] Metrics are displayed in real-time
- [ ] Experiments can be started/stopped

---

## Phase 7: Benchmark/Evaluation Integration

**Goal:** Integrate held-out benchmarks for evaluation.

### Tasks

1. **Create benchmark runner**
   ```python
   # benchmarks/runner.py
   class BenchmarkRunner:
       def run(self, benchmark: str, config: ExperimentConfig) -> BenchmarkResults
   ```

2. **Implement weakness analysis**
   ```python
   # analysis/weakness_analyzer.py
   class WeaknessAnalyzer:
       def analyze(self, results: BenchmarkResults) -> WeaknessProfile
   ```

3. **Create data split guard**
   ```python
   # experiments/data_split_guard.py
   class DataSplitGuard:
       BANNED_SOURCES = {"benchmark", "held_out_test"}
   ```

### Acceptance Criteria

- [ ] Benchmarks can be run independently
- [ ] Weaknesses are identified
- [ ] Contamination is prevented

---

## Phase 8: Adaptive Curriculum

**Goal:** Implement adaptive task generation based on weakness analysis.

### Tasks

1. **Implement CurriculumController**
   ```python
   # autopilot/curriculum.py
   class CurriculumController:
       def analyze_weaknesses(self, benchmark_results) -> WeaknessProfile
       def adjust_generation_weights(self, profile) -> GenerationWeights
       def generate_targeted_tasks(self, weights) -> List[GeneratedTask]
   ```

2. **Add protection against feedback loops**
   - Cap generation rate per domain
   - Require human review

### Acceptance Criteria

- [ ] Curriculum can adjust generation based on weaknesses
- [ ] Feedback loops are prevented

---

## Phase 9: Optional Training Integration

**Goal:** Add support for future training integration.

### Tasks

1. **Add export to HuggingFace format**
2. **Document training pipeline**
3. **Create example scripts**

---

## Phase 10: Promotion/Rejection System

**Goal:** Implement model promotion/rejection with full lineage tracking.

### Tasks

1. **Implement ModelRegistry**
   ```python
   # experiments/model_registry.py
   class ModelRegistry:
       def register_candidate(self, dataset_id, config) -> str
       def compare(self, candidate_id, stable_id) -> ComparisonResult
       def promote(self, candidate_id) -> None
       def reject(self, candidate_id, reason: str) -> None
   ```

2. **Store model lineage**
   - parent_model_id
   - training_dataset_id
   - training_configuration
   - benchmark_results
   - promotion_decision
   - reason_for_decision

3. **Implement PromotionGate**
   ```python
   # experiments/promotion.py
   class PromotionGate:
       def evaluate(self, candidate, stable) -> PromotionDecision
   ```

### Acceptance Criteria

- [ ] Model registry tracks full lineage
- [ ] Promotion/rejection decisions are logged
- [ ] Stable model is never overwritten without explicit action

### Tests

```python
# tests/test_phase10_promotion.py
def test_model_registry_lineage():
    registry = ModelRegistry()
    candidate_id = registry.register_candidate("dataset_v42", config)
    assert registry.get(candidate_id).parent_model == "stable_v42"
    
def test_promotion_decision():
    gate = PromotionGate()
    decision = gate.evaluate(candidate, stable)
    assert decision in ["PROMOTE", "REJECT"]
```

---

## Phase 11: Weakness Analyzer + Adaptive Curriculum

**Goal:** Implement weakness analysis and adaptive curriculum generation.

### Tasks

1. **Implement WeaknessAnalyzer**
   ```python
   # experiments/analysis/weakness.py
   class WeaknessAnalyzer:
       def analyze(self, benchmark_results) -> WeaknessProfile
       def identify_weak_domains(self) -> List[str]
       def generate_weakness_report(self) -> str
   ```

2. **Implement CurriculumController**
   ```python
   # experiments/autopilot/curriculum.py
   class CurriculumController:
       def adjust_generation_weights(self, profile) -> GenerationWeights
       def generate_targeted_tasks(self, weights) -> List[GeneratedTask]
   ```

3. **Add protection against feedback loops**
   - Cap generation rate per domain
   - Require human review for extreme shifts
   - Use held-out evaluation only (NOT same synthetic tasks)

### Acceptance Criteria

- [ ] Weakness analyzer identifies problem domains
- [ ] Curriculum adjusts generation based on weaknesses
- [ ] Feedback loops are prevented
- [ ] Weakness signals come from held-out evaluation

### Tests

```python
# tests/test_phase11_curriculum.py
def test_weakness_analysis():
    analyzer = WeaknessAnalyzer()
    profile = analyzer.analyze(benchmark_results)
    assert "coding/debugging" in profile.weak_domains
    
def test_curriculum_adjustment():
    controller = CurriculumController()
    weights = controller.adjust_generation_weights(profile)
    assert weights["coding"] > weights["math"]  # More coding tasks
```

---

## Phase 12: Bounded-Generation Autopilot

**Goal:** Implement bounded-generation autopilot with quality gates.

### Tasks

1. **Implement AutopilotController**
   ```python
   # experiments/autopilot/controller.py
   class AutopilotController:
       def run_generation(self, generation_id: int) -> GenerationResult
       def evaluate_quality(self, result) -> bool
       def should_continue(self) -> bool
       def stop_conditions(self) -> List[StopCondition]
   ```

2. **Implement bounded generations**
   - Generate N tasks
   - Execute through multi-agent system
   - Validate results
   - Build dataset
   - Quality gate check
   - Compare with stable model

3. **Add explicit stop conditions**
   - Maximum GPU budget
   - Maximum generation count
   - Maximum wall-clock duration
   - Insufficient disk space
   - Dataset quality below threshold
   - Validation failure rate above threshold
   - Novelty below threshold
   - Benchmark regression
   - No improvement for N generations
   - Excessive duplicate rate
   - Validator disagreement above threshold
   - Catastrophic performance regression
   - Manual emergency stop

### Acceptance Criteria

- [ ] Autopilot runs bounded generations
- [ ] Quality gates prevent bad datasets
- [ ] Stop conditions are respected
- [ ] UI can pause/stop autonomously

### Tests

```python
# tests/test_phase12_autopilot.py
def test_bounded_generation():
    controller = AutopilotController()
    result = controller.run_generation(generation_id=1)
    assert result.dataset_id is not None
    
def test_stop_conditions():
    controller = AutopilotController()
    assert controller.should_continue() is True  # Initially
    # Simulate reaching max generations
    controller._generation_count = controller.max_generations
    assert controller.should_continue() is False
```

---

## Phase 13: Continuous/Indefinite Autopilot Experiments

**Goal:** Implement continuous autopilot for research experiments (NOT production).

### Tasks

1. **Implement continuous mode**
   - Repeated bounded generations
   - Regular quality checks
   - Diversity monitoring
   - Model collapse detection

2. **Add model collapse detection**
   - Track novelty over time
   - Detect distribution drift
   - Alert on self-confirming patterns

3. **Document risks**
   - Plateau
   - Overfit synthetic distributions
   - Lose diversity
   - Amplify systematic errors
   - Exploit validator weaknesses
   - Experience model collapse
   - Produce increasingly self-confirming data

### Acceptance Criteria

- [ ] Continuous mode can run indefinitely (with safeguards)
- [ ] Model collapse is detected and alerted
- [ ] Diversity pressure is maintained

### Tests

```python
# tests/test_phase13_continuous.py
def test_model_collapse_detection():
    controller = AutopilotController()
    # Simulate declining novelty
    controller._novelty_scores = [0.8, 0.7, 0.6, 0.5, 0.4]
    assert controller.detect_collapse() is True
```

---

## Test Strategy

### Unit Tests (Per Phase)

Each phase must have unit tests for:
- Core functionality
- Edge cases
- Error handling
- Rollback scenarios

### Integration Tests

After Phase 3+:
- Full experiment loop
- Mode comparison (A vs B vs C)
- Contamination prevention
- Provenance traceability

### Regression Tests

After each phase:
- Run all existing tests
- Ensure no breaking changes

### Autopilot Tests

After Phase 12+:
- Stop condition verification
- Quality gate enforcement
- Model promotion/rejection logic
- Diversity maintenance

---

## Timeline Estimate

|| Phase | Estimated Effort | Description |
||-------|------------------|-------------|
|| 0 | 2-3 hours | Config + mapping |
|| 1 | 4-6 hours | Task generator + schemas |
|| 2 | 3-4 hours | Diversifier + novelty |
|| 3 | 4-6 hours | Pipeline integration |
|| 4 | 3-4 hours | Validation + failure bank |
|| 5 | 3-4 hours | Dataset builder + versioning |
|| 6 | 8-12 hours | Lab generation UI |
|| 7 | 4-6 hours | Benchmark infrastructure |
|| 8 | 6-8 hours | Trainer integration |
|| 9 | 4-6 hours | Model registry + promotion |
|| 10 | 6-8 hours | Weakness analyzer + curriculum |
|| 11 | 6-8 hours | Bounded-generation autopilot |
|| 12 | 8-12 hours | Continuous autopilot experiments |

**Total V1 (Phases 0-5):** ~24-32 hours  
**Total V2 (Phases 6-9):** ~22-32 hours  
**Total V3 (Phases 10-12):** ~20-24 hours

**Grand Total:** ~66-88 hours

---

## Next Steps

1. **Start with Phase 0** — Document existing components ✅ COMPLETE
2. **Create ExperimentConfig** — Foundation for all experiments ✅ COMPLETE
3. **Implement Phase 1** — Task generator with templates
4. **Iterate** — Test, refine, extend

---

*Plan created: 2026-10-07*  
*Last updated: 2026-10-07*  
*Status: READY FOR IMPLEMENTATION*

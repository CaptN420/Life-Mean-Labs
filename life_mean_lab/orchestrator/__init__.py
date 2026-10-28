"""Orchestration layer — adaptive multi-agent cognitive system.

This package provides the abstractions and engines for three orchestration
modes (A/B/C) plus divergence/convergence and benchmarking. It COMPOSES
with the existing stable core (code_lab, philosophical_council, compare)
without modifying it.

Public API:
  - models.AgentSpec, Task, AgentResult, Branch, ConvergenceResult, OrchestrationTrace
  - router.StrategyRouter      (Mode C: hybrid adaptive selection)
  - memory.CognitiveMemory     (4-level structured memory)
  - benchmark.BenchmarkRunner  (A/B/C/D/E experimental comparison)
"""

from .models import (
    AgentResult,
    AgentType,
    Branch,
    BranchStatus,
    ConvergenceResult,
    OrchestrationTrace,
    Strategy,
    Task,
    ValidationResult,
)
from .router import StrategyRouter
from .memory import CognitiveMemory
from .benchmark import BenchmarkRunner, ConditionMetrics, BenchmarkResult
from .multi_role import MultiRoleOrchestrator, build_from_code_lab_engine
from .model_registry import ModelRegistry, ModelSpec, ModelHealth, ModelProvider
from .scheduler import ParallelScheduler, TaskDependency, TaskResult
from .multi_model import MultiModelOrchestrator, CollaborationMessage, MessageKind
from .workspace_manager import WorkspaceManager, BranchInfo, WorkspaceBranchStatus, TestResult
from .task_analyzer import TaskAnalyzer, TaskAnalysis, UncertaintyLevel, RiskLevel, CorrectionRecord
from .adaptive_controller import AdaptiveStrategyController, StrategyDecision, ControllerDecision
from .divergence_engine import DivergenceEngine, DivergenceStrategy, BranchConfig, DivergenceResult
from .convergence_engine import ConvergenceEngine, ConvergenceOutcome, BranchEvidence, ConvergenceAnalysis
from .budget_controller import MetacognitiveBudgetController, BudgetAllocation, AllocationStage, TransferRecord, ProgressSignal
from .real_llm_executor import RealLLMExecutor, ExecutionStatus, LLMCallMetrics, ExecutionMetrics
from .debate_ledger import ArgumentLedger, DebateEvent, DebateEventType, RepetitionDetector
from .debate_experiment import DebateExperimentRunner, DebateConfig, DebateCondition, DebateResult, AgentState, EmergenceMeasures
from .strategy_learning import StrategyLearning, TaskType, StrategyRecord
from .benchmark_real import RealBenchmarkRunner, ExperimentConfig, RealExperimentResult, MetricProvenance, MeasureType

__all__ = [
    # Models
    "AgentResult",
    "AgentType",
    "Branch",
    "BranchStatus",
    "ConvergenceResult",
    "OrchestrationTrace",
    "Strategy",
    "Task",
    "ValidationResult",
    # Router
    "StrategyRouter",
    # Memory
    "CognitiveMemory",
    # Benchmark
    "BenchmarkRunner",
    "ConditionMetrics",
    "BenchmarkResult",
    # MultiRole (Mode A)
    "MultiRoleOrchestrator",
    "build_from_code_lab_engine",
    # Model Registry (Mode B)
    "ModelRegistry",
    "ModelSpec",
    "ModelHealth",
    "ModelProvider",
    # Scheduler (Mode B)
    "ParallelScheduler",
    "TaskDependency",
    "TaskResult",
    # MultiModel (Mode B)
    "MultiModelOrchestrator",
    "CollaborationMessage",
    "MessageKind",
    # Workspace Manager (Phase 3.5)
    "WorkspaceManager",
    "BranchInfo",
    "WorkspaceBranchStatus",
    "TestResult",
    # Task Analyzer (Phase 4A)
    "TaskAnalyzer",
    "TaskAnalysis",
    "UncertaintyLevel",
    "RiskLevel",
    "CorrectionRecord",
    # Adaptive Strategy Controller (Phase 4A)
    "AdaptiveStrategyController",
    "StrategyDecision",
    "ControllerDecision",
    # Divergence Engine (Phase 4B)
    "DivergenceEngine",
    "DivergenceStrategy",
    "BranchConfig",
    "DivergenceResult",
    # Convergence Engine (Phase 4B)
    "ConvergenceEngine",
    "ConvergenceOutcome",
    "BranchEvidence",
    "ConvergenceAnalysis",
    # Metacognitive Budget Controller (Phase 4C)
    "MetacognitiveBudgetController",
    "BudgetAllocation",
    "AllocationStage",
    "TransferRecord",
    "ProgressSignal",
    # Real LLM Executor (Phase 4C.5)
    "RealLLMExecutor",
    "ExecutionStatus",
    "LLMCallMetrics",
    "ExecutionMetrics",
    # Debate System (Phase 4D)
    "ArgumentLedger",
    "DebateEvent",
    "DebateEventType",
    "RepetitionDetector",
    "DebateExperimentRunner",
    "DebateConfig",
    "DebateCondition",
    "DebateResult",
    "AgentState",
    "EmergenceMeasures",
    # Strategy Learning (Phase 4D)
    "StrategyLearning",
    "TaskType",
    "StrategyRecord",
    # Real Benchmark (Phase 4D)
    "RealBenchmarkRunner",
    "ExperimentConfig",
    "RealExperimentResult",
    "MetricProvenance",
    "MeasureType",
]

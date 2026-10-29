"""Comprehensive tests for Failure-to-Knowledge Pipeline."""

import pytest
import time
from core.debate.failure_analyzer import (
    FailureAnalyzer,
    FailureCategory,
    ObservedError,
    CandidateCause,
    FailureDiagnostic,
)
from core.debate.comparable_run_finder import (
    ComparableRunFinder,
    RunConfiguration,
    RunMetrics,
    RunStatus,
    ComparableRun,
)
from core.debate.causal_hypothesis_engine import (
    CausalHypothesisEngine,
    HypothesisStatus,
    CausalHypothesis,
)
from core.debate.experiment_designer import (
    ControlledExperimentDesigner,
    ExperimentStatus,
    VariableType,
    ControlledExperiment,
    ExperimentVariable,
)
from core.debate.experiment_gate import (
    ExperimentExecutionGate,
    GateStatus,
    ResourceLimits,
    ApprovalResult,
)
from core.debate.knowledge_extractor import (
    ExperimentalKnowledgeExtractor,
    KnowledgeStatus,
    KnowledgeRecord,
)
from core.debate.false_success_detector import (
    FalseSuccessDetector,
    FalseSuccessStatus,
    FalseSuccessFinding,
)


# ── 1. Failure Analyzer Tests ───────────────────────────────────────────────


class TestFailureAnalyzer:
    """Test failure analysis and classification."""

    def test_analyze_syntax_error(self):
        analyzer = FailureAnalyzer()
        diagnostic = analyzer.analyze_failure(
            run_id="codelab_e793c7bd05",
            status="FAILED",
            error_output="SyntaxError: invalid syntax\n  File 'test.py', line 10",
        )
        assert diagnostic.failure_category == FailureCategory.SYNTAX_ERROR
        assert len(diagnostic.observed_errors) > 0

    def test_analyze_runtime_error(self):
        analyzer = FailureAnalyzer()
        diagnostic = analyzer.analyze_failure(
            run_id="codelab_e793c7bd05",
            status="FAILED",
            error_output="TypeError: unhashable type: 'list'",
        )
        assert diagnostic.failure_category == FailureCategory.RUNTIME_ERROR

    def test_analyze_test_failure(self):
        analyzer = FailureAnalyzer()
        diagnostic = analyzer.analyze_failure(
            run_id="codelab_e793c7bd05",
            status="FAILED",
            error_output="FAILED tests/test_foo.py::test_bar - AssertionError",
        )
        assert diagnostic.failure_category == FailureCategory.TEST_FAILURE

    def test_analyze_missing_evidence(self):
        analyzer = FailureAnalyzer()
        diagnostic = analyzer.analyze_failure(
            run_id="codelab_e793c7bd05",
            status="FAILED",
            error_output="",
        )
        assert "No error output or trace available" in diagnostic.missing_evidence

    def test_candidate_causes_generated(self):
        analyzer = FailureAnalyzer()
        diagnostic = analyzer.analyze_failure(
            run_id="codelab_e793c7bd05",
            status="FAILED",
            error_output="TypeError: unhashable type: 'list'",
            code="def _ngrams(words, n):\n    return {words[i : i + n] for i in range(len(words) - n + 1)}",
        )
        assert len(diagnostic.candidate_causes) > 0

    def test_verify_root_cause(self):
        analyzer = FailureAnalyzer()
        diagnostic = analyzer.analyze_failure(
            run_id="codelab_e793c7bd05",
            status="FAILED",
            error_output="TypeError: unhashable type: 'list'",
        )
        if diagnostic.candidate_causes:
            result = analyzer.verify_root_cause(
                "codelab_e793c7bd05",
                diagnostic.candidate_causes[0].cause_id,
            )
            assert result is True

    def test_get_diagnostic(self):
        analyzer = FailureAnalyzer()
        analyzer.analyze_failure("run-1", "FAILED", "Error: something broke")
        diagnostic = analyzer.get_diagnostic("run-1")
        assert diagnostic is not None
        assert diagnostic.run_id == "run-1"

    def test_get_all_diagnostics(self):
        analyzer = FailureAnalyzer()
        analyzer.analyze_failure("run-1", "FAILED", "Error 1")
        analyzer.analyze_failure("run-2", "FAILED", "Error 2")
        diagnostics = analyzer.get_all_diagnostics()
        assert len(diagnostics) == 2


# ── 2. Comparable Run Finder Tests ──────────────────────────────────────────


class TestComparableRunFinder:
    """Test run comparison and similarity scoring."""

    def test_find_comparable_runs(self):
        finder = ComparableRunFinder()
        finder.register_run("run-1", RunConfiguration(
            run_id="run-1",
            task_type="codelab",
            prompt="Implement _ngrams function",
            template="python_coder",
            roles=["coder"],
            models=["gpt-4"],
            versions={"engine": "1.0.0"},
        ))
        finder.register_run("run-2", RunConfiguration(
            run_id="run-2",
            task_type="codelab",
            prompt="Implement _ngrams function",
            template="python_coder",
            roles=["coder"],
            models=["gpt-4"],
            versions={"engine": "1.0.0"},
        ))

        results = finder.find_comparable_runs("run-1")
        assert len(results) == 1
        assert results[0].run_id == "run-2"

    def test_score_breakdown(self):
        finder = ComparableRunFinder()
        finder.register_run("run-1", RunConfiguration(
            run_id="run-1",
            task_type="codelab",
            prompt="Test A",
        ))
        finder.register_run("run-2", RunConfiguration(
            run_id="run-2",
            task_type="codelab",
            prompt="Test A",
        ))

        results = finder.find_comparable_runs("run-1")
        assert len(results) > 0
        assert "task_type" in results[0].score_breakdown

    def test_no_comparison_for_same_run(self):
        finder = ComparableRunFinder()
        finder.register_run("run-1", RunConfiguration(run_id="run-1"))
        results = finder.find_comparable_runs("run-1")
        assert len(results) == 0

    def test_metrics_tracking(self):
        finder = ComparableRunFinder()
        finder.register_run("run-1", RunConfiguration(run_id="run-1"), RunMetrics(
            run_id="run-1",
            completion_rate=1.0,
            validator_pass_rate=1.0,
            status=RunStatus.COMPLETED,
        ))
        metrics = finder.get_run_metrics("run-1")
        assert metrics is not None
        assert metrics.completion_rate == 1.0


# ── 3. Causal Hypothesis Engine Tests ───────────────────────────────────────


class TestCausalHypothesisEngine:
    """Test hypothesis generation and status tracking."""

    def test_generate_hypothesis(self):
        engine = CausalHypothesisEngine()
        hyp = engine.generate_hypothesis(
            run_id="codelab_e793c7bd05",
            difference_description="Non-hashable list in set comprehension",
        )
        assert hyp.hypothesis_id.startswith("HYP-")
        assert hyp.status == HypothesisStatus.UNTESTED

    def test_update_hypothesis_status(self):
        engine = CausalHypothesisEngine()
        hyp = engine.generate_hypothesis("run-1", "Test diff")
        result = engine.update_hypothesis_status(
            hyp.hypothesis_id,
            HypothesisStatus.SUPPORTED,
            evidence_added=["New evidence"],
        )
        assert result is True
        assert hyp.status == HypothesisStatus.SUPPORTED

    def test_verify_causal(self):
        engine = CausalHypothesisEngine()
        hyp = engine.generate_hypothesis("run-1", "Test diff")
        # Add supporting evidence before verifying
        engine.update_hypothesis_status(hyp.hypothesis_id, HypothesisStatus.SUPPORTED, evidence_added=["Experimental result confirms"])
        result = engine.verify_causal(hyp.hypothesis_id, {"results": ["Experiment passed"]})
        assert result is True
        assert hyp.status == HypothesisStatus.VERIFIED_CAUSAL

    def test_get_untested_hypotheses(self):
        engine = CausalHypothesisEngine()
        engine.generate_hypothesis("run-1", "Diff 1")
        engine.generate_hypothesis("run-2", "Diff 2")
        untested = engine.get_untested_hypotheses("run-1")
        assert len(untested) == 1

    def test_get_hypotheses_for_run(self):
        engine = CausalHypothesisEngine()
        engine.generate_hypothesis("run-1", "Diff 1")
        engine.generate_hypothesis("run-1", "Diff 2")
        hypotheses = engine.get_hypotheses_for_run("run-1")
        assert len(hypotheses) == 2


# ── 4. Controlled Experiment Designer Tests ─────────────────────────────────


class TestControlledExperimentDesigner:
    """Test experiment design."""

    def test_design_experiment(self):
        designer = ControlledExperimentDesigner()
        exp = designer.design_experiment(
            hypothesis_id="HYP-001",
            description="Test _ngrams fix",
            independent_variable_name="implementation",
            independent_variable_value="tuple-based",
            controlled_variables=[
                {"name": "input", "type": "CONTROLLED", "value": "['a', 'b', 'c']"},
            ],
            success_criteria="No TypeError raised",
        )
        assert exp.experiment_id.startswith("EXP-")
        assert exp.status == ExperimentStatus.PROPOSED

    def test_multiple_variable_warning(self):
        designer = ControlledExperimentDesigner()
        warning = designer.propose_multiple_variable_change([
            {"name": "var1", "value": "a"},
            {"name": "var2", "value": "b"},
        ])
        assert "warning" in warning
        assert "Cannot isolate cause" in warning["message"]


# ── 5. Experiment Execution Gate Tests ──────────────────────────────────────


class TestExperimentExecutionGate:
    """Test experiment approval and execution control."""

    def test_propose_experiment(self):
        gate = ExperimentExecutionGate()
        request = gate.propose_experiment("EXP-001")
        assert request.status == GateStatus.PROPOSED

    def test_approve_experiment(self):
        gate = ExperimentExecutionGate()
        request = gate.propose_experiment("EXP-001")
        result = gate.approve_experiment(request.request_id, "admin")
        assert result is True
        assert request.status == GateStatus.APPROVED

    def test_deny_experiment(self):
        gate = ExperimentExecutionGate()
        request = gate.propose_experiment("EXP-001")
        result = gate.deny_experiment(request.request_id, "Insufficient evidence")
        assert result is True
        assert request.status == GateStatus.CANCELLED

    def test_start_requires_approval(self):
        gate = ExperimentExecutionGate()
        request = gate.propose_experiment("EXP-001")
        # Try to start without approval
        result = gate.start_experiment(request.request_id)
        assert result is False

    def test_complete_experiment(self):
        gate = ExperimentExecutionGate()
        request = gate.propose_experiment("EXP-001")
        gate.approve_experiment(request.request_id, "admin")
        gate.start_experiment(request.request_id)
        result = gate.complete_experiment(request.request_id, success=True)
        assert result is True
        assert request.status == GateStatus.COMPLETED

    def test_no_double_approval(self):
        gate = ExperimentExecutionGate()
        request = gate.propose_experiment("EXP-001")
        gate.approve_experiment(request.request_id, "admin")
        # Try to approve again
        result = gate.approve_experiment(request.request_id, "admin2")
        assert result is False


# ── 6. Knowledge Extractor Tests ────────────────────────────────────────────


class TestKnowledgeExtractor:
    """Test knowledge extraction."""

    def test_extract_knowledge(self):
        extractor = ExperimentalKnowledgeExtractor()
        record = extractor.extract_knowledge(
            hypothesis_id="HYP-001",
            experiment_ids=["EXP-001"],
            observation="Tuple-based _ngrams completes without TypeError",
            conclusion="Fix eliminates the error for tested inputs",
            status=KnowledgeStatus.SUPPORTED,
        )
        assert record.knowledge_id.startswith("KNOW-")
        assert record.status == KnowledgeStatus.SUPPORTED

    def test_get_knowledge_for_hypothesis(self):
        extractor = ExperimentalKnowledgeExtractor()
        extractor.extract_knowledge("HYP-001", ["EXP-001"], "Obs 1", "Concl 1")
        extractor.extract_knowledge("HYP-001", ["EXP-002"], "Obs 2", "Concl 2")
        records = extractor.get_knowledge_for_hypothesis("HYP-001")
        assert len(records) == 2

    def test_get_verified_knowledge(self):
        extractor = ExperimentalKnowledgeExtractor()
        extractor.extract_knowledge("HYP-001", [], "Obs", "Concl", KnowledgeStatus.SUPPORTED)
        extractor.extract_knowledge("HYP-002", [], "Obs", "Concl", KnowledgeStatus.INCONCLUSIVE)
        verified = extractor.get_verified_knowledge()
        assert len(verified) == 1
        assert verified[0].knowledge_id.startswith("KNOW")


# ── 7. False Success Detector Tests ─────────────────────────────────────────


class TestFalseSuccessDetector:
    """Test false success detection."""

    def test_confirmed_pass(self):
        detector = FalseSuccessDetector()
        finding = detector.analyze_run(
            run_id="run-1",
            validator_output="All tests passed",
            code_executed=True,
            tests_run=10,
            tests_passed=10,
        )
        assert finding.status == FalseSuccessStatus.CONFIRMED_PASS

    def test_suspected_false_pass_no_execution(self):
        detector = FalseSuccessDetector()
        finding = detector.analyze_run(
            run_id="run-2",
            validator_output="PASS",
            code_executed=False,
            tests_run=0,
            tests_passed=1,  # Small number to keep confidence lower
        )
        assert finding.status in (FalseSuccessStatus.SUSPECTED_FALSE_PASS, FalseSuccessStatus.CONFIRMED_FALSE_PASS)

    def test_suspected_false_pass_no_tests(self):
        detector = FalseSuccessDetector()
        finding = detector.analyze_run(
            run_id="run-3",
            validator_output="PASS",
            code_executed=True,
            tests_run=0,
            tests_passed=1,  # Small number to keep confidence lower
        )
        assert finding.status in (FalseSuccessStatus.SUSPECTED_FALSE_PASS, FalseSuccessStatus.CONFIRMED_FALSE_PASS)

    def test_get_suspected_runs(self):
        detector = FalseSuccessDetector()
        detector.analyze_run("run-1", "PASS", code_executed=False, tests_run=0, tests_passed=5)
        detector.analyze_run("run-2", "PASS", code_executed=True, tests_run=10, tests_passed=10)
        suspected = detector.get_suspected_runs()
        assert "run-1" in suspected
        assert "run-2" not in suspected


# ── Integration Tests ────────────────────────────────────────────────────────


class TestIntegration:
    """Integration tests for the Failure-to-Knowledge pipeline."""

    def test_full_pipeline(self):
        """Test complete failure analysis to knowledge extraction."""
        # Phase 1: Analyze failure
        analyzer = FailureAnalyzer()
        diagnostic = analyzer.analyze_failure(
            run_id="codelab_e793c7bd05",
            status="FAILED",
            error_output="TypeError: unhashable type: 'list'",
            code="def _ngrams(words, n):\n    return {words[i : i + n] for i in range(len(words) - n + 1)}",
        )

        # Phase 2: Generate hypothesis
        engine = CausalHypothesisEngine()
        hyp = engine.generate_hypothesis(
            run_id="codelab_e793c7bd05",
            difference_description="Non-hashable list in set comprehension",
        )

        # Phase 3: Design experiment
        designer = ControlledExperimentDesigner()
        exp = designer.design_experiment(
            hypothesis_id=hyp.hypothesis_id,
            description="Test tuple-based fix",
            independent_variable_name="implementation",
            independent_variable_value="tuple-based",
        )

        # Phase 4: Gate approval and execution
        gate = ExperimentExecutionGate()
        request = gate.propose_experiment(exp.experiment_id)
        gate.approve_experiment(request.request_id, "researcher")
        gate.start_experiment(request.request_id)
        gate.complete_experiment(request.request_id, success=True)

        # Phase 5: Extract knowledge
        extractor = ExperimentalKnowledgeExtractor()
        record = extractor.extract_knowledge(
            hypothesis_id=hyp.hypothesis_id,
            experiment_ids=[exp.experiment_id],
            observation="Tuple-based implementation completes without TypeError",
            conclusion="Fix eliminates TypeError for tested inputs",
            status=KnowledgeStatus.SUPPORTED,
        )

        # Verify pipeline completed
        assert diagnostic.failure_category == FailureCategory.RUNTIME_ERROR
        assert exp.experiment_id in record.experiment_ids
        assert record.status == KnowledgeStatus.SUPPORTED

    def test_false_success_detection(self):
        """Test false success detection integrated with analysis."""
        detector = FalseSuccessDetector()
        finding = detector.analyze_run(
            run_id="codelab_ebc8cbaca5",
            validator_output="PASS - All checks passed",
            code_executed=False,
            tests_run=0,
            tests_passed=1,
        )
        assert finding.status in (FalseSuccessStatus.SUSPECTED_FALSE_PASS, FalseSuccessStatus.CONFIRMED_FALSE_PASS)


# ── Edge Case Tests ──────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_evidence_handling(self):
        analyzer = FailureAnalyzer()
        diagnostic = analyzer.analyze_failure("run-1", "FAILED")
        assert "No error output or trace available" in diagnostic.missing_evidence

    def test_nonexistent_hypothesis(self):
        engine = CausalHypothesisEngine()
        result = engine.update_hypothesis_status("HYP-NONEXISTENT", HypothesisStatus.SUPPORTED)
        assert result is False

    def test_nonexistent_experiment(self):
        designer = ControlledExperimentDesigner()
        exp = designer.get_experiment("EXP-NONEXISTENT")
        assert exp is None

    def test_data_corruption_resilience(self):
        """Test resilience to corrupted or missing data."""
        analyzer = FailureAnalyzer()
        diagnostic = analyzer.analyze_failure(
            run_id="run-1",
            status="FAILED",
            error_output="",
            trace=None,
            code=None,
            config=None,
        )
        assert diagnostic is not None
        assert len(diagnostic.observed_errors) == 0

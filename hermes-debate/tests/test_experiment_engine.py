"""
Tests for Experiment Engine and Domain Model.

Tests cover:
- Core domain entities (Question, Persona, Role, Model, Protocol, Experiment, Run)
- Assignment strategies (Fixed, Random, Round-Robin)
- Experiment engine execution
- RAW artifact management
- Provenance tracking
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from core.domain import (
    Question, Persona, Role, ModelConfig, Protocol, Experiment, Run,
    PersonaType, RoleType, ProtocolType, ModelType,
    AssignmentResult, FixedAssignment, RandomAssignment, RoundRobinAssignment,
)
from core.experiment_engine import ExperimentEngine, ExperimentPlanner, AutoPilot
from core.raw import RAWArtifact, RAWArchive, ProvenanceTracker


class TestQuestion:
    """Tests for Question entity."""
    
    def test_create_question(self):
        question = Question(
            id="Q001",
            text="What is the meaning of life?",
        )
        
        assert question.id == "Q001"
        assert question.text == "What is the meaning of life?"
        assert question.version == "1.0"
    
    def test_to_dict(self):
        question = Question(id="Q001", text="Test question")
        d = question.to_dict()
        
        assert d['id'] == "Q001"
        assert 'text' in d
        assert 'created_at' in d


class TestPersona:
    """Tests for Persona entity."""
    
    def test_create_persona(self):
        persona = Persona(
            id="P001",
            name="Skeptic",
            persona_type=PersonaType.SKEPTIC,
            description="Critical thinker",
        )
        
        assert persona.id == "P001"
        assert persona.name == "Skeptic"
        assert persona.persona_type == PersonaType.SKEPTIC
    
    def test_to_dict(self):
        persona = Persona(id="P001", name="Test", persona_type=PersonaType.SKEPTIC, description="Desc")
        d = persona.to_dict()
        
        assert d['id'] == "P001"
        assert d['type'] == "skeptic"


class TestRole:
    """Tests for Role entity."""
    
    def test_create_role(self):
        role = Role(
            id="R001",
            name="Critic",
            role_type=RoleType.CRITIC,
            description="Critical evaluator",
        )
        
        assert role.id == "R001"
        assert role.role_type == RoleType.CRITIC


class TestModelConfig:
    """Tests for ModelConfig entity."""
    
    def test_create_model(self):
        model = ModelConfig(
            id="M001",
            name="Mock Model",
            model_type=ModelType.GENERATIVE,
            provider="mock",
        )
        
        assert model.id == "M001"
        assert model.model_type == ModelType.GENERATIVE
    
    def test_to_dict(self):
        model = ModelConfig(id="M001", name="Test", model_type=ModelType.GENERATIVE, provider="mock")
        d = model.to_dict()
        
        assert d['id'] == "M001"
        assert d['type'] == "generative"


class TestProtocol:
    """Tests for Protocol entity."""
    
    def test_create_protocol(self):
        protocol = Protocol(
            id="PROT001",
            name="Cross Examination",
            protocol_type=ProtocolType.CROSS_EXAMINATION,
            description="Structured cross-examination",
            phases=[
                {'name': 'opening', 'duration': 60},
                {'name': 'examination', 'duration': 120},
            ],
        )
        
        assert protocol.id == "PROT001"
        assert protocol.protocol_type == ProtocolType.CROSS_EXAMINATION
        assert len(protocol.phases) == 2


class TestExperiment:
    """Tests for Experiment entity."""
    
    def test_create_experiment(self):
        experiment = Experiment(
            id="EXP001",
            question_id="Q001",
            personas=["skeptic", "advocate"],
            roles=["critic", "advocate"],
            model_pool=["model_a", "model_b"],
            protocol_id="PROT001",
            orchestrator_id="custom",
            repetitions=5,
        )
        
        assert experiment.id == "EXP001"
        assert len(experiment.personas) == 2
        assert experiment.repetitions == 5
    
    def test_to_dict(self):
        experiment = Experiment(
            id="EXP001",
            question_id="Q001",
            personas=["skeptic"],
            roles=["critic"],
            model_pool=["model_a"],
            protocol_id="PROT001",
            orchestrator_id="custom",
        )
        d = experiment.to_dict()
        
        assert d['id'] == "EXP001"
        assert d['repetitions'] == 5


class TestRun:
    """Tests for Run entity."""
    
    def test_create_run(self):
        run = Run(
            id="RUN001",
            experiment_id="EXP001",
            run_number=1,
            status="pending",
        )
        
        assert run.id == "RUN001"
        assert run.experiment_id == "EXP001"
        assert run.run_number == 1
    
    def test_to_dict(self):
        run = Run(id="RUN001", experiment_id="EXP001", run_number=1, status="completed")
        d = run.to_dict()
        
        assert d['status'] == "completed"
        assert d['transcript_length'] == 0


class TestAssignmentStrategies:
    """Tests for assignment strategies."""
    
    @pytest.mark.asyncio
    async def test_fixed_assignment(self):
        strategy = FixedAssignment({"skeptic": "model_a", "advocate": "model_b"})
        
        result = await strategy.assign(
            persona="skeptic",
            role="critic",
            phase="opening",
            candidates=["model_a", "model_b"],
            context={},
        )
        
        assert result.selected_model == "model_a"
        assert result.strategy == "fixed"
        assert result.confidence == 1.0
    
    @pytest.mark.asyncio
    async def test_random_assignment(self):
        strategy = RandomAssignment(seed=42)
        
        # Run multiple times to verify randomness
        results = []
        for _ in range(10):
            result = await strategy.assign(
                persona="skeptic",
                role="critic",
                phase="opening",
                candidates=["model_a", "model_b"],
                context={},
            )
            results.append(result.selected_model)
        
        # Should have some variation (though seed makes it deterministic)
        assert len(set(results)) > 0
    
    @pytest.mark.asyncio
    async def test_round_robin_assignment(self):
        strategy = RoundRobinAssignment()
        
        # First call should return first candidate
        result1 = await strategy.assign(
            persona="skeptic",
            role="critic",
            phase="opening",
            candidates=["model_a", "model_b"],
            context={},
        )
        
        # Second call should return second candidate
        result2 = await strategy.assign(
            persona="skeptic",
            role="critic",
            phase="opening",
            candidates=["model_a", "model_b"],
            context={},
        )
        
        assert result1.selected_model == "model_a"
        assert result2.selected_model == "model_b"
    
    @pytest.mark.asyncio
    async def test_random_assignment_no_candidates(self):
        strategy = RandomAssignment()
        
        with pytest.raises(ValueError, match="No candidates"):
            await strategy.assign(
                persona="skeptic",
                role="critic",
                phase="opening",
                candidates=[],
                context={},
            )


class TestExperimentEngine:
    """Tests for ExperimentEngine."""
    
    @pytest.mark.asyncio
    async def test_create_experiment(self):
        engine = ExperimentEngine()
        
        experiment = await engine.create_experiment(
            question_id="Q001",
            personas=["skeptic", "advocate"],
            roles=["critic", "advocate"],
            model_pool=["model_a", "model_b"],
            protocol_id="PROT001",
            orchestrator_id="custom",
            repetitions=5,
        )
        
        assert experiment.id.startswith("EXP_")
        assert experiment.question_id == "Q001"
    
    @pytest.mark.asyncio
    async def test_create_run(self):
        engine = ExperimentEngine()
        
        experiment = await engine.create_experiment(
            question_id="Q001",
            personas=["skeptic"],
            roles=["critic"],
            model_pool=["model_a"],
            protocol_id="PROT001",
            orchestrator_id="custom",
            repetitions=3,
        )
        
        run = await engine.create_run(experiment.id, 1)
        
        assert run.experiment_id == experiment.id
        assert run.run_number == 1
    
    @pytest.mark.asyncio
    async def test_execute_experiment(self):
        engine = ExperimentEngine()
        
        experiment = await engine.create_experiment(
            question_id="Q001",
            personas=["skeptic"],
            roles=["critic"],
            model_pool=["model_a"],
            protocol_id="PROT001",
            orchestrator_id="custom",
            repetitions=3,
            max_turns=5,
        )
        
        runs = await engine.execute_experiment(experiment)
        
        assert len(runs) == 3
        assert all(r.status == 'completed' for r in runs)
    
    @pytest.mark.asyncio
    async def test_get_run(self):
        engine = ExperimentEngine()
        
        experiment = await engine.create_experiment(
            question_id="Q001",
            personas=["skeptic"],
            roles=["critic"],
            model_pool=["model_a"],
            protocol_id="PROT001",
            orchestrator_id="custom",
            repetitions=2,
        )
        
        runs = await engine.execute_experiment(experiment)
        run = engine.get_run(runs[0].id)
        
        assert run is not None
        assert run.id == runs[0].id
    
    @pytest.mark.asyncio
    async def test_list_experiments(self):
        engine = ExperimentEngine()
        
        exp1 = await engine.create_experiment(
            question_id="Q001",
            personas=["skeptic"],
            roles=["critic"],
            model_pool=["model_a"],
            protocol_id="PROT001",
            orchestrator_id="custom",
        )
        
        exp2 = await engine.create_experiment(
            question_id="Q002",
            personas=["skeptic"],
            roles=["critic"],
            model_pool=["model_a"],
            protocol_id="PROT001",
            orchestrator_id="custom",
        )
        
        experiments = engine.list_experiments()
        assert len(experiments) == 2


class TestExperimentPlanner:
    """Tests for ExperimentPlanner."""
    
    @pytest.mark.asyncio
    async def test_plan_ablation(self):
        engine = ExperimentEngine()
        
        base_experiment = await engine.create_experiment(
            question_id="Q001",
            personas=["skeptic", "advocate", "scientist"],
            roles=["critic", "advocate"],
            model_pool=["model_a", "model_b"],
            protocol_id="PROT001",
            orchestrator_id="custom",
        )
        
        planner = ExperimentPlanner(engine)
        ablation = await planner.plan_ablation(base_experiment, "persona", "skeptic")
        
        assert "skeptic" not in ablation.personas
        assert len(ablation.personas) == 2
    
    @pytest.mark.asyncio
    async def test_plan_parametric(self):
        engine = ExperimentEngine()
        
        base_experiment = await engine.create_experiment(
            question_id="Q001",
            personas=["skeptic"],
            roles=["critic"],
            model_pool=["model_a"],
            protocol_id="PROT001",
            orchestrator_id="custom",
        )
        
        planner = ExperimentPlanner(engine)
        experiments = await planner.plan_parametric(
            base_experiment,
            "model_pool",
            [["model_a"], ["model_b"], ["model_c"]]
        )
        
        assert len(experiments) == 3


class TestRAwarehouse:
    """Tests for RAW artifact management."""
    
    def test_store_and_retrieve(self):
        archive = RAWArchive()
        
        artifact = RAWArtifact(
            run_id="RUN001",
            experiment_id="EXP001",
            data={'turns': 5, 'tokens': 1000},
        )
        
        artifact_id = archive.store(artifact)
        retrieved = archive.get(artifact_id)
        
        assert retrieved is not None
        assert retrieved.run_id == "RUN001"
    
    def test_list_artifacts(self):
        archive = RAWArchive()
        
        artifact1 = RAWArtifact(run_id="RUN001", experiment_id="EXP001", data={})
        artifact2 = RAWArtifact(run_id="RUN002", experiment_id="EXP001", data={})
        
        archive.store(artifact1)
        archive.store(artifact2)
        
        artifacts = archive.list_artifacts(experiment_id="EXP001")
        assert len(artifacts) == 2


class TestProvenanceTracker:
    """Tests for provenance tracking."""
    
    def test_add_event(self):
        tracker = ProvenanceTracker()
        
        tracker.add_event("study", {'id': 'STUDY001'})
        tracker.add_event("experiment", {'id': 'EXP001'})
        tracker.add_event("run", {'id': 'RUN001'})
        
        chain = tracker.get_chain()
        assert len(chain) == 3
    
    def test_to_dict(self):
        tracker = ProvenanceTracker()
        tracker.add_event("experiment", {'id': 'EXP001'})
        
        d = tracker.to_dict()
        assert 'provenance_chain' in d
        assert len(d['provenance_chain']) == 1


class TestAutoPilot:
    """Tests for AutoPilot."""
    
    @pytest.mark.asyncio
    async def test_run_campaign(self):
        engine = ExperimentEngine()
        pilot = AutoPilot(engine)
        
        experiment = await engine.create_experiment(
            question_id="Q001",
            personas=["skeptic"],
            roles=["critic"],
            model_pool=["model_a"],
            protocol_id="PROT001",
            orchestrator_id="custom",
            repetitions=2,
        )
        
        result = await pilot.run_campaign([experiment])
        
        assert 'campaign_id' in result
        assert result['experiments_count'] == 1
        assert result['runs_count'] == 2
    
    @pytest.mark.asyncio
    async def test_generate_report(self):
        engine = ExperimentEngine()
        pilot = AutoPilot(engine)
        
        experiment = await engine.create_experiment(
            question_id="Q001",
            personas=["skeptic"],
            roles=["critic"],
            model_pool=["model_a"],
            protocol_id="PROT001",
            orchestrator_id="custom",
            repetitions=2,
        )
        
        await pilot.run_campaign([experiment])
        report = await pilot.generate_report("CAMP_TEST")
        
        assert 'campaign_id' in report
        assert 'summary' in report


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

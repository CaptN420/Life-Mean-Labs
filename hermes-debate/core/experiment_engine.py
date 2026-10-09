"""
Experiment Engine.

Manages the execution of experiments with repetitions,
parametric variations, and ablation studies.
"""

import logging
from typing import Any, Optional
from datetime import datetime

from .domain import Experiment, Run, AssignmentStrategy, FixedAssignment

logger = logging.getLogger(__name__)


class ExperimentEngine:
    """
    Engine for executing experiments.
    
    Manages the lifecycle of experiments including:
    - Creating runs
    - Executing repetitions
    - Collecting results
    - Computing metrics
    """
    
    def __init__(self, orchestrator_factory=None, assignment_strategy: Optional[AssignmentStrategy] = None):
        """
        Initialize the experiment engine.
        
        Args:
            orchestrator_factory: Factory function to create orchestrators
            assignment_strategy: Strategy for assigning models to personas
        """
        self.orchestrator_factory = orchestrator_factory
        self.assignment_strategy = assignment_strategy or FixedAssignment({})
        self._runs: dict[str, Run] = {}
        self._experiments: dict[str, Experiment] = {}
        self._experiment_counter = 0
        
    async def _generate_experiment_id(self) -> str:
        """Generate a unique experiment ID."""
        self._experiment_counter += 1
        return f"EXP_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{self._experiment_counter:03d}"
        
    async def create_experiment(
        self,
        question_id: str,
        personas: list[str],
        roles: list[str],
        model_pool: list[str],
        protocol_id: str,
        orchestrator_id: str,
        repetitions: int = 5,
        max_turns: int = 8,
        decision_model_id: Optional[str] = None,
        constraints: Optional[dict] = None,
    ) -> Experiment:
        """
        Create a new experiment configuration.
        
        Args:
            question_id: ID of the research question
            personas: List of persona IDs
            roles: List of role IDs
            model_pool: List of available model IDs
            protocol_id: ID of the debate protocol
            orchestrator_id: ID of the orchestrator to use
            repetitions: Number of repetitions
            max_turns: Maximum number of turns per run
            decision_model_id: Optional decision model ID
            constraints: Experimental constraints
            
        Returns:
            Created Experiment
        """
        experiment = Experiment(
            id=await self._generate_experiment_id(),
            question_id=question_id,
            personas=personas,
            roles=roles,
            model_pool=model_pool,
            protocol_id=protocol_id,
            orchestrator_id=orchestrator_id,
            decision_model_id=decision_model_id,
            repetitions=repetitions,
            max_turns=max_turns,
            constraints=constraints or {},
        )
        
        self._experiments[experiment.id] = experiment
        logger.info(f"Created experiment {experiment.id}")
        
        return experiment
    
    async def create_run(
        self,
        experiment_id: str,
        run_number: int,
    ) -> Run:
        """
        Create a new run for an experiment.
        
        Args:
            experiment_id: ID of the parent experiment
            run_number: Run number (1-based)
            
        Returns:
            Created Run
        """
        if experiment_id not in self._experiments:
            raise ValueError(f"Experiment {experiment_id} not found")
        
        run = Run(
            id=f"RUN_{experiment_id}_{run_number:03d}",
            experiment_id=experiment_id,
            run_number=run_number,
            status="pending",
            started_at=datetime.utcnow(),
        )
        
        self._runs[run.id] = run
        logger.info(f"Created run {run.id} for experiment {experiment_id}")
        
        return run
    
    async def execute_experiment(
        self,
        experiment: Experiment,
        assignment_strategy: Optional[AssignmentStrategy] = None,
    ) -> list[Run]:
        """
        Execute all repetitions of an experiment.
        
        Args:
            experiment: The experiment to execute
            assignment_strategy: Override assignment strategy
            
        Returns:
            List of executed runs
        """
        strategy = assignment_strategy or self.assignment_strategy
        
        runs = []
        
        for run_num in range(1, experiment.repetitions + 1):
            run = await self.create_run(experiment.id, run_num)
            runs.append(run)
            
            # Execute the run (this would call the orchestrator in production)
            result = await self._execute_run(run, experiment, strategy)
            run.status = result['status']
            run.metrics = result.get('metrics', {})
            run.errors = result.get('errors', [])
            run.completed_at = datetime.utcnow()
        
        logger.info(f"Executed {len(runs)} runs for experiment {experiment.id}")
        
        return runs
    
    async def _execute_run(
        self,
        run: Run,
        experiment: Experiment,
        strategy: AssignmentStrategy,
    ) -> dict[str, Any]:
        """
        Execute a single run.
        
        Args:
            run: The run to execute
            experiment: Parent experiment
            strategy: Assignment strategy
            
        Returns:
            Result dictionary with status, metrics, errors
        """
        # In production, this would:
        # 1. Create an orchestrator
        # 2. Assign models using the strategy
        # 3. Run the debate
        # 4. Collect results
        
        # Simulated execution for testing
        return {
            'status': 'completed',
            'metrics': {
                'turns_completed': experiment.max_turns,
                'model_calls': len(experiment.personas) * experiment.max_turns,
                'assignment_strategy': strategy.__class__.__name__,
            },
            'errors': [],
        }
    
    def get_run(self, run_id: str) -> Optional[Run]:
        """Get a run by ID."""
        return self._runs.get(run_id)
    
    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Get an experiment by ID."""
        return self._experiments.get(experiment_id)
    
    def list_experiments(self) -> list[Experiment]:
        """List all experiments."""
        return list(self._experiments.values())
    
    def list_runs(self, experiment_id: Optional[str] = None) -> list[Run]:
        """List runs, optionally filtered by experiment."""
        if experiment_id:
            return [r for r in self._runs.values() if r.experiment_id == experiment_id]
        return list(self._runs.values())


class ExperimentPlanner:
    """
    Planner for parametric experiments.
    
    Generates multiple experiments by varying parameters.
    """
    
    def __init__(self, engine: ExperimentEngine):
        self.engine = engine
    
    async def plan_ablation(
        self,
        base_experiment: Experiment,
        ablation_type: str,
        ablation_value: Any,
    ) -> Experiment:
        """
        Plan an ablation experiment.
        
        Args:
            base_experiment: Base experiment to ablate
            ablation_type: Type of ablation (e.g., "persona", "model", "protocol")
            ablation_value: Value to ablate (e.g., "skeptic" for persona ablation)
            
        Returns:
            New ablation experiment
        """
        # Create modified experiment based on ablation type
        personas = base_experiment.personas.copy()
        model_pool = base_experiment.model_pool.copy()
        
        if ablation_type == "persona":
            personas = [p for p in personas if p != ablation_value]
        elif ablation_type == "model":
            model_pool = [m for m in model_pool if m != ablation_value]
        else:
            raise ValueError(f"Unknown ablation type: {ablation_type}")
        
        return await self.engine.create_experiment(
            question_id=base_experiment.question_id,
            personas=personas,
            roles=base_experiment.roles,
            model_pool=model_pool,
            protocol_id=base_experiment.protocol_id,
            orchestrator_id=base_experiment.orchestrator_id,
            repetitions=base_experiment.repetitions,
            max_turns=base_experiment.max_turns,
            decision_model_id=base_experiment.decision_model_id,
        )
    
    async def plan_parametric(
        self,
        base_experiment: Experiment,
        param_name: str,
        param_values: list[Any],
    ) -> list[Experiment]:
        """
        Plan parametric experiments by varying a parameter.
        
        Args:
            base_experiment: Base experiment
            param_name: Parameter name to vary
            param_values: List of values to test
            
        Returns:
            List of parametric experiments
        """
        experiments = []
        
        for value in param_values:
            # Modify experiment based on parameter
            personas = base_experiment.personas.copy()
            model_pool = base_experiment.model_pool.copy()
            
            if param_name == "personas":
                personas = value
            elif param_name == "model_pool":
                model_pool = value
            else:
                raise ValueError(f"Unknown parameter: {param_name}")
            
            exp = await self.engine.create_experiment(
                question_id=base_experiment.question_id,
                personas=personas,
                roles=base_experiment.roles,
                model_pool=model_pool,
                protocol_id=base_experiment.protocol_id,
                orchestrator_id=base_experiment.orchestrator_id,
                repetitions=base_experiment.repetitions,
                max_turns=base_experiment.max_turns,
            )
            experiments.append(exp)
        
        return experiments


class AutoPilot:
    """
    Automated experiment execution.
    
    Manages large-scale experimental campaigns with:
    - Parallel execution
    - Budget controls
    - Error handling
    - Auto-analysis
    """
    
    def __init__(self, engine: ExperimentEngine):
        self.engine = engine
        self._budget: dict[str, float] = {
            'max_cost': 100.0,
            'max_tokens': 10000000,
            'max_runtime_minutes': 1440,  # 24 hours
            'max_runs': 500,
        }
        self._stats: dict[str, Any] = {
            'runs_completed': 0,
            'runs_failed': 0,
            'total_tokens': 0,
            'total_cost': 0.0,
            'start_time': None,
            'end_time': None,
        }
    
    async def run_campaign(
        self,
        experiments: list[Experiment],
        parallelism: int = 4,
    ) -> dict[str, Any]:
        """
        Run an experimental campaign.
        
        Args:
            experiments: List of experiments to execute
            parallelism: Number of parallel runs
            
        Returns:
            Campaign results summary
        """
        self._stats['start_time'] = datetime.utcnow()
        all_runs = []
        
        for experiment in experiments:
            # Check budget constraints
            if not self._check_budget():
                logger.warning("Budget constraint reached, stopping campaign")
                break
            
            runs = await self.engine.execute_experiment(experiment)
            all_runs.extend(runs)
            
            # Update stats
            self._stats['runs_completed'] += len([r for r in runs if r.status == 'completed'])
            self._stats['runs_failed'] += len([r for r in runs if r.status == 'failed'])
        
        self._stats['end_time'] = datetime.utcnow()
        
        return {
            'campaign_id': f"CAMP_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            'experiments_count': len(experiments),
            'runs_count': len(all_runs),
            'stats': self._stats,
        }
    
    def _check_budget(self) -> bool:
        """Check if budget constraints are met."""
        # In production, check actual usage
        return True
    
    async def generate_report(self, campaign_id: str) -> dict[str, Any]:
        """Generate a campaign report."""
        return {
            'campaign_id': campaign_id,
            'generated_at': datetime.utcnow().isoformat(),
            'summary': self._stats,
        }

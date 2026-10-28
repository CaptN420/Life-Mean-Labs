"""
Workflows module — Workflow schemas and validation.

Defines the structure for workflows used by Life_mean Studio.
Workflows are configurations, NOT authorizations.
A saved workflow does not grant any execution permissions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """Configuration for a single agent in a workflow."""
    role: str = ""  # planner, coder, reviewer, tester, security_reviewer
    model: Optional[str] = None
    prompt_template: Optional[str] = None
    max_tokens: int = 1200
    temperature: float = 0.4
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "model": self.model,
            "prompt_template": self.prompt_template,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }


@dataclass
class WorkflowConfig:
    """
    Configuration for a workflow.
    
    This is a configuration schema ONLY. It does not grant any permissions.
    The actual execution permissions are enforced by the Security Gate.
    """
    name: str = ""
    description: str = ""
    version: str = "1.0"
    mode: str = "single"  # single or multi
    
    # Synthetic-data generation settings (used by the real engine on RUN)
    domain: str = "math"
    num_tasks: int = 10
    seed: int = 42
    
    # Agent configuration
    agents: List[AgentConfig] = field(default_factory=list)
    
    # LLM settings
    llm_base_url: Optional[str] = None
    llm_model: Optional[str] = None
    
    # Context compression (reuses code_lab.compression)
    compression_enabled: bool = False
    compression_budget: int = 4000
    
    # Execution settings
    max_iterations: int = 10
    timeout_seconds: int = 60
    run_tests: bool = True
    
    # Logging
    log_level: str = "INFO"
    
    # Associated prompts (by ID)
    prompt_ids: List[str] = field(default_factory=list)
    
    # Security references (permissions to check)
    security_policy_id: Optional[str] = None
    
    def validate(self) -> List[str]:
        """Validate the workflow configuration. Returns list of errors."""
        errors = []
        
        if not self.name:
            errors.append("Workflow name is required")
        
        if self.mode not in ("single", "multi"):
            errors.append("Mode must be 'single' or 'multi'")
        
        if self.mode == "multi" and not self.agents:
            errors.append("Multi-agent mode requires at least one agent")
        
        if self.compression_budget < 0:
            errors.append("Compression budget must be non-negative")
        
        if self.max_iterations < 1:
            errors.append("Max iterations must be at least 1")
        
        if self.timeout_seconds < 1:
            errors.append("Timeout must be at least 1 second")
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "mode": self.mode,
            "domain": self.domain,
            "num_tasks": self.num_tasks,
            "seed": self.seed,
            "agents": [agent.to_dict() for agent in self.agents],
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "compression_enabled": self.compression_enabled,
            "compression_budget": self.compression_budget,
            "max_iterations": self.max_iterations,
            "timeout_seconds": self.timeout_seconds,
            "run_tests": self.run_tests,
            "log_level": self.log_level,
            "prompt_ids": self.prompt_ids,
            "security_policy_id": self.security_policy_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowConfig":
        agents = []
        for agent_data in data.get("agents", []):
            agents.append(AgentConfig(**agent_data))
        
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            mode=data.get("mode", "single"),
            domain=data.get("domain", "math"),
            num_tasks=data.get("num_tasks", 10),
            seed=data.get("seed", 42),
            agents=agents,
            llm_base_url=data.get("llm_base_url"),
            llm_model=data.get("llm_model"),
            compression_enabled=data.get("compression_enabled", False),
            compression_budget=data.get("compression_budget", 4000),
            max_iterations=data.get("max_iterations", 10),
            timeout_seconds=data.get("timeout_seconds", 60),
            run_tests=data.get("run_tests", True),
            log_level=data.get("log_level", "INFO"),
            prompt_ids=data.get("prompt_ids", []),
            security_policy_id=data.get("security_policy_id"),
        )


# Default workflow templates
DEFAULT_WORKFLOWS = {
    "single-agent-quick-coding": WorkflowConfig(
        name="Single-Agent Quick Coding",
        description="Fast single-agent coding workflow",
        mode="single",
        agents=[AgentConfig(role="coder")],
        max_iterations=5,
        run_tests=True,
    ),
    "multi-agent-coding": WorkflowConfig(
        name="Multi-Agent Coding",
        description="Multi-agent coding with planner, coder, and reviewer",
        mode="multi",
        agents=[
            AgentConfig(role="planner"),
            AgentConfig(role="coder"),
            AgentConfig(role="reviewer"),
        ],
        max_iterations=10,
        run_tests=True,
    ),
    "security-audit": WorkflowConfig(
        name="Security Audit",
        description="Security-focused audit workflow",
        mode="multi",
        agents=[
            AgentConfig(role="planner"),
            AgentConfig(role="security_reviewer"),
        ],
        run_tests=False,
    ),
    "debug": WorkflowConfig(
        name="Debug",
        description="Debug and fix workflow",
        mode="single",
        agents=[AgentConfig(role="coder")],
        max_iterations=15,
        run_tests=True,
    ),
    "refactoring": WorkflowConfig(
        name="Refactoring",
        description="Code refactoring workflow",
        mode="multi",
        agents=[
            AgentConfig(role="planner"),
            AgentConfig(role="coder"),
        ],
        run_tests=True,
    ),
    "test-review": WorkflowConfig(
        name="Test Review",
        description="Test review and improvement workflow",
        mode="single",
        agents=[AgentConfig(role="reviewer")],
        run_tests=True,
    ),
}

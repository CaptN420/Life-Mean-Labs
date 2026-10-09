"""
Configuration for Hermes Multi-Agent Debate Orchestrator.
All settings are configurable via environment variables or config.yaml.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelConfig:
    """Configuration for a single model."""
    model_id: str
    role: str  # "decision_model", "philosopher", "critic", "judge"
    vram_class: str  # "decision", "reasoning"
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    unload_after_call: bool = True
    max_tokens: int = 2048
    temperature: float = 0.7


@dataclass
class DecisionModelConfig:
    """Configuration for a decision model."""
    model_id: str
    name: str
    type: str = "decision_model"
    provider: str = "lm_studio"  # "lm_studio", "mock", "custom"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout_seconds: int = 60
    capabilities: list[str] = field(default_factory=lambda: [
        "routing", "classification", "tool_selection", "agent_selection"
    ])
    metadata: dict = field(default_factory=dict)


@dataclass
class RoutingConfig:
    """Routing configuration."""
    min_confidence: float = 0.70
    loop_threshold: int = 3
    consensus_threshold: float = 0.85


@dataclass
class GenerationConfig:
    """Generation parameters."""
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 1.0


@dataclass
class RuntimeConfig:
    """Runtime configuration."""
    mode: str = "strict"  # "strict" or "performance"
    max_turns: int = 8
    request_timeout_seconds: int = 600
    
    clef_load_timeout_ms: int = 30000
    clef_inference_timeout_ms: int = 10000
    model_load_timeout_ms: int = 120000
    model_inference_timeout_ms: int = 120000
    
    max_vram_gb: float = 24.0
    vram_reserve_mb: int = 1024
    
    # Clef-flash residency settings
    keep_clef_resident: bool = True  # Keep Clef-flash resident if VRAM allows
    clef_estimated_size_mb: int = 3072  # IQ4_XS ~3GB


@dataclass
class HermesConfig:
    """Main configuration."""
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    
    models: dict[str, ModelConfig] = field(default_factory=dict)
    decision_models: dict[str, DecisionModelConfig] = field(default_factory=dict)
    
    # Cloudflare Clef configuration
    clef_account_id: Optional[str] = None
    clef_api_key: Optional[str] = None
    clef_endpoint: str = "https://api.cloudflare.com/client/v4"
    
    # Simulation mode
    simulation: bool = False


def load_config() -> HermesConfig:
    """Load configuration from environment and config.yaml."""
    import os
    import yaml
    
    config = HermesConfig()
    
    # Load from config.yaml if exists
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            yaml_config = yaml.safe_load(f) or {}
        
        # Merge runtime config
        if 'runtime' in yaml_config:
            runtime_data = yaml_config['runtime']
            for key in ['mode', 'max_turns', 'request_timeout_seconds']:
                if key in runtime_data:
                    setattr(config.runtime, key, runtime_data[key])
        
        # Merge routing config
        if 'routing' in yaml_config:
            routing_data = yaml_config['routing']
            for key in ['min_confidence', 'loop_threshold', 'consensus_threshold']:
                if key in routing_data:
                    setattr(config.routing, key, routing_data[key])
        
        # Load models
        if 'models' in yaml_config:
            for model_name, model_data in yaml_config['models'].items():
                config.models[model_name] = ModelConfig(
                    model_id=model_data.get('model_id', model_name),
                    role=model_data.get('role', 'philosopher'),
                    vram_class=model_data.get('vram_class', 'reasoning'),
                    endpoint=model_data.get('endpoint'),
                    api_key=model_data.get('api_key'),
                    unload_after_call=model_data.get('unload_after_call', True),
                    max_tokens=model_data.get('max_tokens', 2048),
                    temperature=model_data.get('temperature', 0.7)
                )
    
    # Environment variables override
    if os.getenv('SIMULATION'):
        config.simulation = True
    
    if os.getenv('CLEF_ACCOUNT_ID'):
        config.clef_account_id = os.getenv('CLEF_ACCOUNT_ID')
    
    if os.getenv('CLEF_API_KEY'):
        config.clef_api_key = os.getenv('CLEF_API_KEY')
    
    return config

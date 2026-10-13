# Architect: Célestin Martin
# Project: Captn - Deterministic Agent Runtime

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class RuntimeConfig:
    base_dir: Path
    session_dir: Path | None = None
    
    # OpenAI/LM Studio API configuration
    api_url: str = "http://localhost:1234/v1/chat/completions"
    request_timeout: int = 60
    max_api_retries: int = 1
    retry_backoff_seconds: float = 0.7
    api_key: str | None = "sk-lm-XVdni9Sy:REDACTED"  # Set to None; if LM Studio requires authentication, configure it in LM Studio settings
    
    # GPU configuration - GPU 1 (3080 12GB) first, then GPU 0 (3070 Ti 8GB)
    # EXCLUSIVE VRAM USAGE: No RAM offloading. All model layers and discussion context fit in VRAM.
    gpu_devices: str = "1,0"

    # Model configurations - ALL AGENTS USE 3B MODEL FOR EXCLUSIVE VRAM USAGE (NO RAM OFFLOAD)
    # This maximizes context window capacity for 12-agent discussions in VRAM
    # qwen2.5:3b (Q4 quantization) uses ~2.2 GB VRAM for weights, leaving ~17.8 GB for 12-agent context
    model_aurelius: str = "qwen2.5:3b"
    model_basilide: str = "qwen2.5:3b"
    model_chymicus: str = "qwen2.5:3b"
    model_archiviste: str = "qwen2.5:3b"
    model_sentinelle: str = "qwen2.5:3b"
    model_hermes: str = "qwen2.5:3b"
    model_hermetica: str = "qwen2.5:3b"
    model_synthetiseur: str = "qwen2.5:3b"
    model_reviseur: str = "qwen2.5:3b"
    model_variable_validator: str = "qwen2.5:3b"
    model_equation_validator: str = "qwen2.5:3b"
    model_final_validator: str = "qwen2.5:3b"
    
    # Prediction configurations
    num_predict_debate: int = 150
    num_predict_validation: int = 80
    num_predict_archive: int = 200
    num_predict_sentinelle: int = 120
    num_predict_support: int = 100
    num_predict_synth: int = 180
    num_predict_hermes: int = 200
    
    # Temperature configurations
    temperature_debate: float = 0.7
    temperature_support: float = 0.3
    temperature_hermes: float = 0.5
    
    # History configuration
    max_history_messages: int = 16
    
    # Agent model routing function (optional)
    model_for_agent: Callable[[str], str] | None = None

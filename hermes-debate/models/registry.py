"""
Model Registry - manages model configurations and metadata.
"""

from typing import Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from config import ModelConfig


@dataclass
class ModelEntry:
    """Registry entry for a single model."""
    model_id: str
    config: ModelConfig
    status: str = "UNLOADED"
    last_loaded: Optional[float] = None
    load_attempts: int = 0
    
    def mark_loading(self) -> None:
        self.status = "LOADING"
    
    def mark_ready(self) -> None:
        self.status = "READY"
        self.last_loaded = datetime.utcnow().timestamp()
    
    def mark_error(self) -> None:
        self.status = "ERROR"
    
    def to_dict(self) -> dict:
        return {
            'model_id': self.model_id,
            'role': self.config.role,
            'vram_class': self.config.vram_class,
            'status': self.status,
            'last_loaded': self.last_loaded,
            'load_attempts': self.load_attempts
        }


class ModelRegistry:
    """Registry of all available models."""
    
    def __init__(self):
        self._models: dict[str, ModelEntry] = {}
    
    def register(self, name: str, config: ModelConfig) -> None:
        """Register a new model."""
        self._models[name] = ModelEntry(model_id=name, config=config)
    
    def get(self, name: str) -> Optional[ModelEntry]:
        """Get model entry by name."""
        return self._models.get(name)
    
    def list_models(self) -> dict[str, ModelConfig]:
        """List all registered models."""
        return {name: entry.config for name, entry in self._models.items()}
    
    def has_model(self, name: str) -> bool:
        """Check if a model is registered."""
        return name in self._models
    
    def get_by_role(self, role: str) -> list[ModelEntry]:
        """Get all models with a specific role."""
        return [
            entry for entry in self._models.values()
            if entry.config.role == role
        ]
    
    def get_available_models(self) -> dict[str, str]:
        """Get mapping of model_id to status."""
        return {m.model_id: m.status for m in self._models.values()}
    
    def remove(self, model_id: str) -> bool:
        """Remove a model from the registry."""
        if model_id in self._models:
            del self._models[model_id]
            return True
        return False

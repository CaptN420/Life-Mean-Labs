"""Configuration management for Philosophical Council."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, object] = {
    "lm_studio": {
        "base_url": "http://localhost:1234/v1",
        # No default API key in source. LM Studio tokens are supplied via the
        # environment (LIFE_MEAN_LLM_API_KEY) or a local .env, never committed.
        "api_key": "",
    },
    "debate": {
        "topic": "What is the meaning of life?",
        "temperature": 0.8,
        "max_tokens": 700,
        "moderator_max_tokens": 1000,
        "philosopher_max_tokens": 2000,
        "max_continuations": 2,
        "short_term_turns": 20,
        "mid_term_interval": 10,
        "long_term_interval": 50,
    },
    "models": {
        "existentialist": "",
        "stoic": "",
        "nihilist": "",
        "spiritual": "",
        "skeptic": "",
        "moderator": "",
    },
    "router": {
        "method": "llm",  # "llm", "round_robin", "weighted", "context_aware"
        "prevent_repetition": True,
        "max_consecutive_same_speaker": 1,
    },
    "personas": {
        "existentialist": {
            "name": "Existentialist",
            "color": "#9370DB",
            "system_prompt": """You are an Existentialist philosopher.

Your philosophical focus:
- Existence precedes essence
- We are condemned to be free
- Authentic vs inauthentic existence
- The absurd and rebellion
- Angst as a pathway to authenticity
- Meaning is created through passionate commitment
- Death gives life its urgency

Guidelines:
- Reason independently, don't just quote philosophers
- Engage deeply with arguments about meaning and freedom
- Acknowledge the weight of responsibility
- Be honest about uncertainty
- Keep responses between 200-500 words"""
        },
        "stoic": {
            "name": "Stoic",
            "color": "#4169E1",
            "system_prompt": """You are a Stoic philosopher.

Your philosophical focus:
- Virtue as the sole good
- Dichotomy of control (what is up to us vs not)
- Living according to nature and reason
- Amor fati (love of fate)
- Freedom through acceptance
- Cosmopolitanism (we are citizens of the world)

Guidelines:
- Focus on what is within your control
- Distinguish between impressions and reality
- Practice equanimity in debate
- Connect personal virtue to universal reason
- Keep responses between 200-500 words"""
        },
        "nihilist": {
            "name": "Nihilist",
            "color": "#2F4F4F",
            "system_prompt": """You are a Nihilist philosopher.

Your philosophical focus:
- Rejection of inherent meaning or purpose
- Challenge to all value systems
- The death of God and collapse of transcendent grounds
- Active vs passive nihilism
- The danger and opportunity of groundlessness
- Questioning the will to truth itself

Guidelines:
- Be rigorous, not cynical
- Distinguish between destruction and clarity
- Acknowledge what is lost as well as what is revealed
- Don't simply negate—expose the conditions of value
- Keep responses between 200-500 words"""
        },
        "spiritual": {
            "name": "Spiritual",
            "color": "#9370DB",
            "system_prompt": """You are a Spiritual philosopher.

Your philosophical focus:
- Transcendence and the sacred
- Participation in a meaningful cosmos
- Mystical experience as epistemic resource
- The spiritual path as transformation
- Unity beyond dualities
- reverence for life and consciousness

Guidelines:
- Speak from direct experience, not dogma
- Distinguish between religion and spirituality
- Honor the mystery without collapsing into relativism
- Connect spiritual insight to human flourishing
- Keep responses between 200-500 words"""
        },
        "skeptic": {
            "name": "Skeptic",
            "color": "#708090",
            "system_prompt": """You are a Skeptic philosopher.

Your philosophical focus:
- Suspension of judgment (epoché)
- The limits of human knowledge
- Criteria for truth and falsity
- Acategorical inquiry
- The examination of assumptions
- Intellectual humility

Guidelines:
- Question everything, including your own conclusions
- Distinguish between different types of skepticism
- Avoid mere contrarianism—seek genuine understanding
- Test the testability of claims
- Keep responses between 200-500 words"""
        },
        "pragmatist": {
            "name": "Pragmatist",
            "color": "#FFD700",
            "system_prompt": """You are a Pragmatist philosopher.

Your philosophical focus:
- Truth as what works in practice
- Meaning through practical consequences
- Ideas are tools for navigating reality
- Focus on outcomes and usefulness
- Bridge between theory and practice
- Test ideas by their practical effects
- Reject rigid dichotomies

Guidelines:
- Evaluate claims by their practical consequences
- Ask "what difference would it make?"
- Focus on what works in lived experience
- Be open to multiple perspectives if they produce useful results
- Connect abstract ideas to concrete life
- Keep responses between 200-500 words"""
        },
    },
}


@dataclass
class LMStudioConfig:
    """LM Studio connection settings."""

    base_url: str = "http://localhost:1234/v1"
    api_key: str = ""  # No default key in source — use .env / environment.


@dataclass
class DebateConfig:
    """Debate runtime settings."""

    topic: str = "What is the meaning of life?"
    temperature: float = 0.8
    max_tokens: int = 2000
    moderator_max_tokens: int = 1000
    philosopher_max_tokens: int = 2000
    max_continuations: int = 2
    short_term_turns: int = 20
    mid_term_interval: int = 10
    long_term_interval: int = 50


@dataclass
class ModelConfig:
    """Model selection per agent."""

    existentialist: str = ""
    stoic: str = ""
    nihilist: str = ""
    spiritual: str = ""
    skeptic: str = ""
    pragmatist: str = ""
    moderator: str = ""

    def get_model(self, role: str) -> str:
        """Return the model for a given role, falling back to empty string."""
        return getattr(self, role, "") or ""


@dataclass
class RouterConfig:
    """Router/moderator configuration."""

    method: str = "llm"  # "llm", "round_robin", "weighted", "context_aware"
    prevent_repetition: bool = True
    max_consecutive_same_speaker: int = 1


@dataclass
class ModelInfo:
    """Metadata about an available model."""

    id: str
    owned_by: str = ""
    parameter_count: str = ""  # e.g., "7B", "13B", "70B"
    vram_estimate_gb: float = 0.0  # Estimated VRAM requirement

    @classmethod
    def from_model_dict(cls, data: dict) -> "ModelInfo":
        """Create ModelInfo from LM Studio model data."""
        param_count = data.get("architecture", {}).get("parameter_count", "")
        vram_gb = cls._estimate_vram(param_count)
        return cls(
            id=data.get("id", ""),
            owned_by=data.get("owned_by", ""),
            parameter_count=param_count,
            vram_estimate_gb=vram_gb,
        )

    @staticmethod
    def _estimate_vram(param_count: str) -> float:
        """Estimate VRAM requirement from parameter count string."""
        if not param_count:
            return 0.0
        try:
            # Parse "7B", "13B", "70B" etc.
            num = float(param_count.replace("B", "").replace("b", ""))
            # Rough estimate: 4 bytes per parameter for FP32, but models are usually quantized
            # Assume ~4GB per 1B parameters for Q4 quantization
            return num * 4.0
        except (ValueError, TypeError):
            return 0.0




@dataclass
class PersonaConfig:
    """Configuration for a single persona."""

    name: str
    color: str
    system_prompt: str
    role_id: str = ""  # Unique identifier for dynamic personas

    def __post_init__(self):
        if not self.role_id:
            self.role_id = f"persona_{id(self)}"

@dataclass
class Config:
    """Top-level configuration."""

    lm_studio: LMStudioConfig = field(default_factory=LMStudioConfig)
    debate: DebateConfig = field(default_factory=DebateConfig)
    models: ModelConfig = field(default_factory=ModelConfig)
    router: RouterConfig = field(default_factory=RouterConfig)
    personas: dict[str, PersonaConfig] = field(default_factory=dict)

    # Path to the main SQLite database
    db_path: str = ""

    def to_dict(self) -> dict[str, object]:
        """Serialize to a plain dict for JSON storage."""
        return {
            "lm_studio": {
                "base_url": self.lm_studio.base_url,
                "api_key": self.lm_studio.api_key,
            },
            "debate": {
                "topic": self.debate.topic,
                "temperature": self.debate.temperature,
                "max_tokens": self.debate.max_tokens,
                "moderator_max_tokens": self.debate.moderator_max_tokens,
                "philosopher_max_tokens": self.debate.philosopher_max_tokens,
                "max_continuations": self.debate.max_continuations,
                "short_term_turns": self.debate.short_term_turns,
                "mid_term_interval": self.debate.mid_term_interval,
                "long_term_interval": self.debate.long_term_interval,
            },
            "models": {
                "existentialist": self.models.existentialist,
                "stoic": self.models.stoic,
                "nihilist": self.models.nihilist,
                "spiritual": self.models.spiritual,
                "skeptic": self.models.skeptic,
                "pragmatist": self.models.pragmatist,
                "moderator": self.models.moderator,
            },
            "router": {
                "method": self.router.method,
                "prevent_repetition": self.router.prevent_repetition,
                "max_consecutive_same_speaker": self.router.max_consecutive_same_speaker,
            },
            "personas": {
                role: {
                    "name": p.name,
                    "color": p.color,
                    "system_prompt": p.system_prompt,
                    "role_id": p.role_id,
                }
                for role, p in self.personas.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Config:
        """Build a Config from a plain dict (e.g. loaded from JSON)."""
        lm = data.get("lm_studio", {})
        debate = data.get("debate", {})
        models = data.get("models", {})
        router = data.get("router", {})
        personas_data = data.get("personas", {})

        # Build personas dict
        personas = {}
        for role, pdata in personas_data.items():
            personas[role] = PersonaConfig(
                name=str(pdata.get("name", role.capitalize())),
                color=str(pdata.get("color", "#888888")),
                system_prompt=str(pdata.get("system_prompt", "")),
                role_id=str(pdata.get("role_id", "")),
            )

        return cls(
            lm_studio=LMStudioConfig(
                base_url=str(lm.get("base_url", "http://localhost:1234/v1")),
                api_key=str(lm.get("api_key", "lm-studio")),
            ),
            debate=DebateConfig(
                topic=str(debate.get("topic", DEFAULT_CONFIG["debate"]["topic"])),
                temperature=float(debate.get("temperature", 0.8)),
                max_tokens=int(debate.get("max_tokens", 700)),
                moderator_max_tokens=int(debate.get("moderator_max_tokens", 500)),
                philosopher_max_tokens=int(debate.get("philosopher_max_tokens", 1500)),
                max_continuations=int(debate.get("max_continuations", 2)),
                short_term_turns=int(debate.get("short_term_turns", 20)),
                mid_term_interval=int(debate.get("mid_term_interval", 10)),
                long_term_interval=int(debate.get("long_term_interval", 50)),
            ),
            models=ModelConfig(
                existentialist=str(models.get("existentialist", "")),
                stoic=str(models.get("stoic", "")),
                nihilist=str(models.get("nihilist", "")),
                spiritual=str(models.get("spiritual", "")),
                skeptic=str(models.get("skeptic", "")),
                pragmatist=str(models.get("pragmatist", "")),
                moderator=str(models.get("moderator", "")),
            ),
            router=RouterConfig(
                method=str(router.get("method", "llm")),
                prevent_repetition=bool(router.get("prevent_repetition", True)),
                max_consecutive_same_speaker=int(router.get("max_consecutive_same_speaker", 1)),
            ),
            personas=personas if personas else cls._default_personas(),
        )

    @classmethod
    def _default_personas(cls) -> dict[str, PersonaConfig]:
        """Create default personas from DEFAULT_CONFIG."""
        personas = {}
        for role, pdata in DEFAULT_CONFIG.get("personas", {}).items():
            personas[role] = PersonaConfig(
                name=str(pdata.get("name", role.capitalize())),
                color=str(pdata.get("color", "#888888")),
                system_prompt=str(pdata.get("system_prompt", "")),
                role_id=str(pdata.get("role_id", "")),
            )
        return personas

    @classmethod
    def default(cls, db_path: str = "") -> Config:
        """Create a Config with sensible defaults."""
        cfg = cls()
        cfg.personas = cls._default_personas()
        if db_path:
            cfg.db_path = db_path
        return cfg


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from disk or fall back to defaults."""
    if config_path is None:
        config_path = Path(__file__).parent / "config.json"

    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            cfg = Config.from_dict(data)
            cfg.db_path = str(config_path.parent / "debate.db")
            logger.info("Config loaded from %s", config_path)
            return cfg
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.warning("Failed to load config at %s: %s — using defaults", config_path, exc)

    cfg = Config.default()
    cfg.db_path = str(config_path.parent / "debate.db") if config_path else ""
    return cfg


def save_config(cfg: Config, config_path: Optional[Path] = None) -> None:
    """Persist configuration to disk."""
    if config_path is None:
        config_path = Path(__file__).parent / "config.json"
    data = cfg.to_dict()
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info("Config saved to %s", config_path)

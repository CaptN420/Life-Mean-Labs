"""Unified Persona Manager — CRUD, validation, and template inheritance.

This module provides a centralized registry for managing personas across the
Life-Mean system. It supports:

- Creating, reading, updating, and deleting personas
- Template inheritance (child personas inherit from parent)
- Prompt validation (schema enforcement)
- Hot-reload from disk
- Deterministic content hashing for reproducibility
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import PersonaConfig, PersonaType

logger = logging.getLogger("core.personas.manager")


# ── Validation Rules ────────────────────────────────────────────────────────


class PersonaValidationError(ValueError):
    """Raised when a persona fails validation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# Controlled error codes.
INVALID_ROLE_ID = "INVALID_ROLE_ID"
EMPTY_SYSTEM_PROMPT = "EMPTY_SYSTEM_PROMPT"
INVALID_PERSONA_TYPE = "INVALID_PERSONA_TYPE"
PROMPT_TOO_LONG = "PROMPT_TOO_LONG"
DUPLICATE_ROLE_ID = "DUPLICATE_ROLE_ID"
PARENT_NOT_FOUND = "PARENT_NOT_FOUND"


class PersonaManager:
    """Centralized registry for persona management."""

    MAX_PROMPT_LENGTH = 10000  # characters
    MAX_NAME_LENGTH = 200
    ROLE_ID_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self._personas: Dict[str, PersonaConfig] = {}
        self._storage_path = storage_path or Path.cwd() / "data" / "personas.json"
        self._load_on_init()

    def _load_on_init(self) -> None:
        """Load personas from disk on initialization."""
        if self._storage_path.exists():
            try:
                with open(self._storage_path, encoding="utf-8") as f:
                    data = json.load(f)
                for role_id, pdata in data.items():
                    try:
                        self._personas[role_id] = PersonaConfig.from_dict(pdata)
                    except Exception as e:
                        logger.warning("Failed to load persona '%s': %s", role_id, e)
                logger.info("Loaded %d personas from %s", len(self._personas), self._storage_path)
            except Exception as e:
                logger.warning("Failed to load personas from %s: %s", self._storage_path, e)

    def _save(self) -> None:
        """Persist personas to disk atomically (write to .tmp then rename)."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._storage_path.with_suffix(".json.tmp")
        data = {rid: p.to_dict() for rid, p in self._personas.items()}
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                import os
                os.fsync(f.fileno())
            import shutil
            shutil.move(str(tmp_path), str(self._storage_path))
        except Exception as e:
            # Clean up tmp file on failure
            if tmp_path.exists():
                tmp_path.unlink()
            logger.error("Failed to save personas: %s", e)
            raise
        logger.debug("Saved %d personas to %s", len(self._personas), self._storage_path)

    # ── CRUD Operations ────────────────────────────────────────────────────

    def create_persona(
        self,
        role_id: str,
        name: str,
        persona_type: PersonaType,
        description: str,
        system_prompt: str,
        color: str = "#888888",
        parent_id: Optional[str] = None,
    ) -> PersonaConfig:
        """Create a new persona with validation."""
        self._validate_role_id(role_id)
        self._check_duplicate(role_id)

        if len(system_prompt) > self.MAX_PROMPT_LENGTH:
            raise PersonaValidationError(
                PROMPT_TOO_LONG,
                f"system_prompt exceeds {self.MAX_PROMPT_LENGTH} characters",
            )

        if parent_id and parent_id not in self._personas:
            raise PersonaValidationError(
                PARENT_NOT_FOUND,
                f"parent persona '{parent_id}' not found",
            )

        persona = PersonaConfig(
            role_id=role_id,
            name=name,
            persona_type=persona_type,
            description=description,
            system_prompt=system_prompt,
            color=color,
            parent_persona_id=parent_id,
        )

        self._personas[role_id] = persona
        self._save()
        logger.info("Created persona '%s' (type=%s)", role_id, persona_type.value)
        return persona

    def get_persona(self, role_id: str) -> Optional[PersonaConfig]:
        """Get a persona by role_id."""
        return self._personas.get(role_id)

    def list_personas(self) -> List[PersonaConfig]:
        """List all personas."""
        return list(self._personas.values())

    def update_persona(
        self,
        role_id: str,
        name: Optional[str] = None,
        persona_type: Optional[PersonaType] = None,
        description: Optional[str] = None,
        system_prompt: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Optional[PersonaConfig]:
        """Update an existing persona."""
        persona = self._personas.get(role_id)
        if persona is None:
            return None

        if name is not None:
            if len(name) > self.MAX_NAME_LENGTH:
                raise PersonaValidationError("INVALID_NAME", "name too long")
            persona.name = name

        if persona_type is not None:
            persona.persona_type = persona_type

        if description is not None:
            persona.description = description

        if system_prompt is not None:
            if len(system_prompt) > self.MAX_PROMPT_LENGTH:
                raise PersonaValidationError(PROMPT_TOO_LONG, "system_prompt too long")
            persona.system_prompt = system_prompt

        if color is not None:
            persona.color = color

        self._save()
        logger.info("Updated persona '%s'", role_id)
        return persona

    def delete_persona(self, role_id: str) -> bool:
        """Delete a persona. Returns False if not found."""
        if role_id not in self._personas:
            return False

        # Check for children before deleting
        children = [rid for rid, p in self._personas.items() if p.parent_persona_id == role_id]
        if children:
            raise PersonaValidationError(
                "CANNOT_DELETE_WITH_CHILDREN",
                f"persona '{role_id}' has {len(children)} child persona(s)",
            )

        del self._personas[role_id]
        self._save()
        logger.info("Deleted persona '%s'", role_id)
        return True

    # ── Template Operations ────────────────────────────────────────────────

    def create_template(
        self,
        template_id: str,
        name: str,
        description: str,
        base_persona_id: Optional[str] = None,
    ) -> PersonaConfig:
        """Create a persona template (parent for inheritance).

        A template is a special persona with an empty system_prompt that serves
        as a parent for instantiation. It is marked with metadata
        ``is_template=True`` to distinguish it from executable personas.
        """
        if base_persona_id and base_persona_id not in self._personas:
            raise PersonaValidationError(
                PARENT_NOT_FOUND,
                f"base persona '{base_persona_id}' not found",
            )

        # Templates use a placeholder prompt that satisfies validation but
        # signals to consumers that this is NOT executable.
        template_prompt = (
            f"[TEMPLATE — {name}]\n"
            "This persona is a template and must be instantiated before use.\n"
            f"Inherit from '{base_persona_id}' if available."
        )

        return self.create_persona(
            role_id=template_id,
            name=name,
            persona_type=PersonaType.ANALYTICAL_PHILOSOPHER,  # default
            description=description,
            system_prompt=template_prompt,
            parent_id=base_persona_id,
        )

    def instantiate_template(
        self,
        template_id: str,
        new_role_id: str,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> PersonaConfig:
        """Create a new persona from a template with optional overrides.

        The template's system_prompt is NOT inherited (templates have placeholder
        prompts). Overrides must supply a valid system_prompt unless the template
        has a real prompt (rare edge case).
        """
        template = self._personas.get(template_id)
        if template is None:
            raise PersonaValidationError(
                "TEMPLATE_NOT_FOUND",
                f"template '{template_id}' not found",
            )

        # Normalise overrides — avoid .get() on None
        overrides = overrides or {}

        # Resolve name: explicit override > template name
        name = overrides.get("name") or template.name

        # Resolve persona_type: explicit override > template type
        ptype_str = overrides.get("persona_type") or template.persona_type.value
        try:
            persona_type = PersonaType(str(ptype_str))
        except ValueError:
            persona_type = PersonaType.ANALYTICAL_PHILOSOPHER

        # Resolve description
        description = overrides.get("description") or template.description

        # system_prompt: MUST be provided by caller — templates have placeholder prompts
        system_prompt = overrides.get("system_prompt")
        if not system_prompt or not system_prompt.strip():
            raise PersonaValidationError(
                "EMPTY_SYSTEM_PROMPT",
                f"instantiation of template '{template_id}' requires a non-empty system_prompt",
            )

        # color: override > template > default
        color = overrides.get("color") or template.color

        persona = PersonaConfig(
            role_id=new_role_id,
            name=name,
            persona_type=persona_type,
            description=description,
            system_prompt=system_prompt,
            color=color,
            parent_persona_id=template_id,  # correct field name
        )

        self._personas[new_role_id] = persona
        self._save()
        logger.info("Instantiated template '%s' as '%s'", template_id, new_role_id)
        return persona

    # ── Validation ─────────────────────────────────────────────────────────

    def validate_persona(self, role_id: str) -> Dict[str, Any]:
        """Validate a persona and return results."""
        persona = self._personas.get(role_id)
        if persona is None:
            return {"valid": False, "error": "persona not found"}

        errors = []
        warnings = []

        # Check prompt length
        if len(persona.system_prompt) > self.MAX_PROMPT_LENGTH:
            errors.append(PROMPT_TOO_LONG)

        # Check for empty sections
        if not persona.description.strip():
            warnings.append("description is empty")

        # Check for placeholder text
        if "{{" in persona.system_prompt or "TEMPLATE" in persona.system_prompt:
            warnings.append("system_prompt may contain unresolved template variables")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "persona_id": role_id,
            "content_hash": persona.content_hash(),
        }

    # ── Helpers ────────────────────────────────────────────────────────────

    def _validate_role_id(self, role_id: str) -> None:
        """Validate role_id format."""
        if not self.ROLE_ID_PATTERN.match(role_id):
            raise PersonaValidationError(
                INVALID_ROLE_ID,
                f"role_id '{role_id}' must match pattern {self.ROLE_ID_PATTERN.pattern}",
            )

    def _check_duplicate(self, role_id: str) -> None:
        """Check for duplicate role_id."""
        if role_id in self._personas:
            raise PersonaValidationError(
                DUPLICATE_ROLE_ID,
                f"persona '{role_id}' already exists",
            )

    # ── Presets ────────────────────────────────────────────────────────────

    @classmethod
    def load_default_personas(cls) -> Dict[str, PersonaConfig]:
        """Load the default philosophical personas."""
        manager = cls()

        defaults = [
            {
                "role_id": "existentialist",
                "name": "Existentialist",
                "type": "analytical_philosopher",
                "description": "Focuses on existence, freedom, and meaning creation",
                "prompt": """You are an Existentialist philosopher.

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
- Keep responses between 200-500 words""",
                "color": "#9370DB",
            },
            {
                "role_id": "stoic",
                "name": "Stoic",
                "type": "analytical_philosopher",
                "description": "Focuses on virtue, control, and acceptance",
                "prompt": """You are a Stoic philosopher.

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
- Keep responses between 200-500 words""",
                "color": "#4169E1",
            },
            {
                "role_id": "nihilist",
                "name": "Nihilist",
                "type": "skeptic",
                "description": "Challenges value systems and questions meaning",
                "prompt": """You are a Nihilist philosopher.

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
- Keep responses between 200-500 words""",
                "color": "#2F4F4F",
            },
            {
                "role_id": "skeptic",
                "name": "Skeptic",
                "type": "skeptic",
                "description": "Questions assumptions and suspends judgment",
                "prompt": """You are a Skeptic philosopher.

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
- Keep responses between 200-500 words""",
                "color": "#708090",
            },
        ]

        for data in defaults:
            try:
                manager.create_persona(
                    role_id=data["role_id"],
                    name=data["name"],
                    persona_type=PersonaType(data["type"]),
                    description=data["description"],
                    system_prompt=data["prompt"],
                    color=data["color"],
                )
            except Exception as e:
                logger.warning("Failed to load default persona '%s': %s", data["role_id"], e)

        return manager._personas

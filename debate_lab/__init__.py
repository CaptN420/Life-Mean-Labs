"""Debate Lab — first-class, template-driven debate execution surface.

DEBATE LAB CONFIGURES THE EXISTING DebateEngine. It does NOT replace it.

- ``DebateLabConfig``      — reproducible per-run configuration
- ``DebateLabController``  — run ownership / lifecycle / events / stop / list / inspect
- ``DebateSessionFactory`` — converts a RoleTemplate + run config into the EXISTING
  ``philosophical_council.core.debate_engine.DebateEngine``

There is intentionally NO ``DebateLabEngine`` / ``NewDebateEngine`` here: the
engine stays ``DebateEngine``, the team is a ``RoleTemplate``, model assignment
is run configuration, and actual models are runtime provenance.
"""

from .config import DebateLabConfig
from .validation import (
    TEMPLATE_INVALID_FOR_DEBATE,
    TemplateInvalidForDebate,
    validate_debate_template,
)

__all__ = [
    "DebateLabConfig",
    "TemplateInvalidForDebate",
    "TEMPLATE_INVALID_FOR_DEBATE",
    "validate_debate_template",
]

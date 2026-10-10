"""Visible response-section parsing (§65/§78/§79).

Debate-compatible templates may define a *visible response presentation
contract* (e.g. ARGUMENT / RATIONALE / EVIDENCE / HYPOTHESIS / UNCERTAINTY /
NEXT). This module parses those labeled sections from the ACTUAL text the agent
produced — it is an explicit public response artifact, never hidden
chain-of-thought (§66).

The parser is honest and lossless: if the agent did not emit a labeled
section, no value is fabricated. Section content is whatever natural language
followed the label (same line or the following lines) until the next recognized
label (or the end). Both ``LABEL: body`` and ``LABEL:\\n body`` forms are
supported. A line beginning with a recognized label is a hard boundary — a
label can never be swallowed as another section's body.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

_LABEL_RE = re.compile(r"^\s*([A-Z][A-Z_ ]{2,40}?):\s*(.*)$")


def parse_response_sections(
    text: str,
    contract: Optional[List[str]],
) -> Dict[str, str]:
    """Extract labeled sections from ``text`` according to ``contract``.

    Returns a dict of found sections (label -> trimmed body). Labels are
    matched case-insensitively against the contract (e.g. ``hypothesis:`` →
    ``HYPOTHESIS``). Content before the first recognized label is preserved as
    the ``INTRO`` pseudo-section when non-empty.
    """
    if not text:
        return {}
    contract_labels = {str(x).strip().upper() for x in (contract or [])}
    if not contract_labels:
        return {}

    sections: Dict[str, str] = {}
    intro: List[str] = []
    current_label: Optional[str] = None
    current_body: List[str] = []

    for line in text.split("\n"):
        m = _LABEL_RE.match(line)
        if m and m.group(1).strip().upper().replace(" ", "_") in contract_labels:
            # flush the previous section
            if current_label is not None:
                body = "\n".join(current_body).strip()
                if body:
                    sections[current_label] = body
            current_label = m.group(1).strip().upper().replace(" ", "_")
            current_body = [m.group(2)] if m.group(2).strip() else []
            continue
        if current_label is None:
            intro.append(line)
        else:
            current_body.append(line)

    if current_label is not None:
        body = "\n".join(current_body).strip()
        if body:
            sections[current_label] = body

    if not sections:
        return {}
    intro_text = "\n".join(intro).strip()
    if intro_text:
        sections["INTRO"] = intro_text
    return sections


def infer_message_type(sections: Dict[str, str], role_id: str) -> str:
    """Derive a coarse conversational message type from real parsed sections
    (§68). Defaults to AGENT_ARGUMENT; a genuine HYPOTHESIS/OBJECTION section
    upgrades the label. Never inferred from templates or expected workflows —
    only from what the agent actually wrote.
    """
    if role_id == "moderator":
        return "MODERATOR"
    if "OBJECTION" in sections or "CRITIQUE" in sections:
        return "AGENT_CRITIQUE"
    if "HYPOTHESIS" in sections:
        return "AGENT_HYPOTHESIS"
    if "REVISION" in sections:
        return "AGENT_REVISION"
    return "AGENT_ARGUMENT"
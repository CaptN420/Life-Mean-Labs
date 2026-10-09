"""
Pydantic schemas for structured outputs.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ClefDecision(BaseModel):
    """Structured decision from CLEF."""
    next_agent: str = Field(..., description="Name of the next agent to call")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the decision")
    reason: str = Field(..., description="Reason for the decision")
    continue_debate: bool = Field(False, description="Whether to continue the debate")
    consensus_reached: bool = Field(False, description="Whether consensus has been reached")
    loop_detected: bool = Field(False, description="Whether a loop has been detected")
    escalation_required: bool = Field(False, description="Whether escalation is needed")
    escalation_level: int = Field(0, ge=0, le=3, description="Escalation level (0-3)")


class AgentResponse(BaseModel):
    """Response from a reasoning agent."""
    agent_id: str
    role: str
    content: str
    turn_number: int
    metadata: Dict[str, Any] = Field(default_factory=dict)


class JudgeResult(BaseModel):
    """Result from the Judge agent."""
    synthesis: str
    strongest_arguments: List[str] = Field(default_factory=list)
    disagreement_type: str = Field("philosophical", description="factual or philosophical")
    escalation_needed: bool = False
    recommendation: str = ""


class MemoryResult(BaseModel):
    """Result from memory reranking."""
    results: List[Dict[str, Any]] = Field(default_factory=list)
    query: str = ""


class EscalationDecision(BaseModel):
    """Decision to escalate to a higher-level model."""
    current_level: int
    next_level: int
    reason: str
    agent_to_call: str

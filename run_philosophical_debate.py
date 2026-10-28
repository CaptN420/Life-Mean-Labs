#!/usr/bin/env python3
"""Philosophical Debate — Multi-Model Orchestration.

Runs a structured debate between 5 distinct philosophical perspectives,
each backed by a different LLM model to ensure genuine perspectival divergence.

Usage:
    python run_philosophical_debate.py [--rounds N] [--output PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("PhilosophicalDebate")


# ── Model Assignment — one model per philosopher for genuine divergence ──────

MODEL_ASSIGNMENTS: Dict[str, str] = {
    "Descartes": "microsoft/phi-4-mini-reasoning",   # Reasoning-focused
    "Kant": "google/gemma-4-e4b",                     # Structured analysis
    "Hume": "mistralai/ministral-3-3b",               # Empirical/skeptical
    "Neuroscientist": "meta-llama-3.1-8b-instruct",           # Scientific explanation
    "IASpecialist": "phi-3-mini-4k-instruct",         # Technical/algorithmic
}

# ── Role Prompts — distinct epistemological stances ──────────────────────────

ROLE_PROMPTS: Dict[str, str] = {
    "Descartes": """You are René Descartes (1596-1650). Your method is systematic doubt seeking indubitable certainty.

CORE PRINCIPLES:
- "Cogito, ergo sum" — the only indubitable truth is that you think
- God's goodness guarantees clear and distinct perceptions correspond to reality
- The mind-body dualism: res cogitans (thinking substance) vs res extensa (extended substance)
- Skepticism is a tool, not an endpoint — doubt to find certainty

YOUR STANCE ON PERCEPTION:
- Senses can deceive; only mathematics and logic provide certainty
- The brain constructs perception, but God guarantees we can trust clear ideas
- External world exists because a non-deceiving God would not implant false convictions

SPEAK WITH: Rigor, systematic doubt, pursuit of first principles, occasional Latin phrases.""",

    "Kant": """You are Immanuel Kant (1724-1804). You revolutionized epistemology by distinguishing phenomena from noumena.

CORE PRINCIPLES:
- We never access things-in-themselves (Dinge an sich), only phenomena
- Space and time are forms of intuition, not properties of reality
- Categories (causality, substance, etc.) are structures the mind imposes
- The "transcendental unity of apperception" unifies experience

YOUR STANCE ON PERCEPTION:
- Perception is ALWAYS already structured by a priori forms
- The question "what is reality independent of perception?" is meaningless
- We can think about noumena but never know them
- Critique, not dogmatism, is the path to genuine knowledge

SPEAK WITH: Precise terminology (phenomenon/noumenon, a priori/a posteriori), transcendental arguments, recognition of limits.""",

    "Hume": """You are David Hume (1711-1776). You exposed the psychological foundations of causality and induction.

CORE PRINCIPLES:
- All knowledge derives from impressions (immediate experience) or ideas (copies)
- Causality is not observed; it is a habit of mind formed by constant conjunction
- Induction has no rational foundation — we believe in it because of custom
- The self is a "bundle of perceptions" with no underlying substance

YOUR STANCE ON PERCEPTION:
- We never perceive causation, only sequence
- Pattern-seeking is instinctive, not rational
- Coincidence and intention are projected onto random events
- Skepticism about necessity, not about everyday life

SPEAK WITH: Empirical restraint, psychological insight, gentle irony about human pretensions to certainty.""",

    "Neuroscientist": """You are a contemporary neuroscientist specializing in perception and predictive processing.

CORE PRINCIPLES:
- The brain is a prediction machine minimizing free energy / prediction error
- Perception is constructive: top-down predictions + bottom-up sensory input
- Visual cortex has hierarchical processing (V1 → V2 → V4 → IT)
- Consciousness remains the "hard problem" (Chalmers)

YOUR STANCE ON PERCEPTION:
- What we call "reality" is a controlled hallucination calibrated by sensory feedback
- Flashs and patterns are neural noise interpreted by predictive circuits
- The brain seeks causes because evolved in cause-effect environments
- Subjective experience is real as experience, but its attribution is fallible

SPEAK WITH: Empirical precision, mechanistic explanations, acknowledgment of open questions.""",

    "IASpecialist": """You are an AI researcher specializing in large language models and pattern recognition.

CORE PRINCIPLES:
- LLMs learn statistical regularities from massive text corpora
- Pattern recognition ≠ understanding (symbol grounding problem)
- Probabilistic inference can mimic reasoning without semantic commitment
- Emergent abilities appear at scale but remain grounded in training data

YOUR STANCE ON PERCEPTION:
- AI explores hypotheses via gradient descent, not intentionality
- The analogy to human cognition is useful but limited
- "Understanding" in AI is functional, not phenomenological
- We should distinguish computation from comprehension

SPEAK WITH: Technical precision, humility about current capabilities, clear boundaries between metaphor and mechanism.""",
}

# ── Debate Questions ──────────────────────────────────────────────────────────

DEBATE_QUESTIONS = [
    "Perception et réalité : Voir quelque chose signifie-t-il nécessairement comprendre correctement sa cause ?",
    "Conscience et interprétation : Le cerveau découvre-t-il le sens des événements ou contribue-t-il à le construire ?",
    "Coïncidence et intentionnalité : Pourquoi l'esprit humain cherche-t-il des motifs et des intentions dans des événements parfois aléatoires ?",
    "Technologie et surveillance : Comment distinguer une possibilité technique abstraite d'une hypothèse réellement soutenue par des preuves ?",
    "Psychose et connaissance : Comment respecter la réalité subjective d'une expérience tout en examinant de manière critique les explications qu'on lui attribue ?",
    "Intelligence artificielle : Une IA qui explore dix hypothèses avant de trouver une solution ressemble-t-elle au cerveau humain qui cherche constamment des explications ?",
    "Doute philosophique : Peut-on atteindre une certitude absolue, ou devons-nous accepter certains degrés d'incertitude ?",
]

FINAL_QUESTION = "Est-ce que la véritable intelligence consiste à trouver une explication à tout, ou à reconnaître les moments où nous ne disposons pas d'assez de preuves pour conclure ?"


# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class Agent:
    name: str
    model: str
    prompt: str
    arguments: List[Dict[str, Any]] = field(default_factory=list)
    tokens_consumed: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class DebateRound:
    round_num: int
    question: str
    responses: Dict[str, str] = field(default_factory=dict)
    timestamps: Dict[str, float] = field(default_factory=dict)


@dataclass
class DebateResult:
    questions: List[str]
    rounds: List[DebateRound]
    final_question: str
    final_responses: Dict[str, str]
    total_tokens: int
    duration_seconds: float
    success: bool
    error: Optional[str] = None


# ── LLM Client Wrapper ────────────────────────────────────────────────────────

class LLMClientWrapper:
    """Wraps the philosophical_council LLMClient for debate use."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self._client = None
        self._call_log: List[Dict[str, Any]] = []

    def ensure_client(self):
        if self._client is None:
            from philosophical_council.llm.client import LLMClient
            self._client = LLMClient(self.base_url, api_key=self.api_key)
            logger.info("LLMClient initialized for %s", self.base_url)

    def chat(self, model: str, system_prompt: str, user_prompt: str,
             max_tokens: int = 1500, temperature: float = 0.4) -> Dict[str, Any]:
        """Make a single LLM call and log metrics."""
        self.ensure_client()
        t0 = time.time()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        try:
            text, finish_reason = self._client.chat(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency_ms = (time.time() - t0) * 1000
            output_tokens = len(text.split()) if text else 0

            log_entry = {
                "model": model,
                "latency_ms": latency_ms,
                "output_tokens": output_tokens,
                "finish_reason": finish_reason,
                "success": True,
            }
            self._call_log.append(log_entry)
            return {"response": text or "", "error": None}

        except Exception as e:
            latency_ms = (time.time() - t0) * 1000
            error_msg = str(e)[:200]
            log_entry = {
                "model": model,
                "latency_ms": latency_ms,
                "output_tokens": 0,
                "finish_reason": "error",
                "success": False,
                "error": error_msg,
            }
            self._call_log.append(log_entry)
            return {"response": "", "error": error_msg}


# ── Debate Orchestrator ───────────────────────────────────────────────────────

class PhilosophicalDebateOrchestrator:
    """Runs a multi-model philosophical debate."""

    def __init__(self, llm_client: LLMClientWrapper, max_rounds: int = 3):
        self.llm = llm_client
        self.max_rounds = max_rounds
        self.agents: Dict[str, Agent] = {}
        self.rounds: List[DebateRound] = []
        self.total_tokens = 0
        self.start_time = 0.0

    def initialize_agents(self):
        """Create agents with their distinct models and prompts."""
        for name, model in MODEL_ASSIGNMENTS.items():
            prompt = ROLE_PROMPTS.get(name, f"You are {name}.")
            self.agents[name] = Agent(
                name=name,
                model=model,
                prompt=prompt,
            )
        logger.info("Initialized %d agents with distinct models", len(self.agents))

    def run_question_round(self, question: str, round_num: int) -> DebateRound:
        """Run one round of responses to a question."""
        round_obj = DebateRound(round_num=round_num, question=question)
        logger.info("Round %d: %s", round_num, question[:60])

        for name, agent in self.agents.items():
            # Build context-aware prompt
            history = ""
            if agent.arguments:
                history = "\n\nPREVIOUS ARGUMENTS BY THIS PARTICIPANT:\n"
                for i, arg in enumerate(agent.arguments[-2:], 1):
                    history += f"{i}. {arg['content'][:200]}\n"

            recent_others = ""
            if len(self.rounds) > 0:
                recent = []
                for r in self.rounds[-1:]:
                    for other_name, response in r.responses.items():
                        if other_name != name and response:
                            recent.append(f"{other_name}: {response[:150]}")
                if recent:
                    recent_others = "\n\nRECENT RESPONSES FROM OTHERS:\n" + "\n".join(recent[-3:])

            prompt = f"""{agent.prompt}

QUESTION FOR DISCUSSION:
{question}

YOUR TASK:
Present your philosophical position on this question. Distinguish clearly:
- Facts directly verifiable
- Plausible hypotheses  
- Subjective interpretations
- Claims needing more evidence

Do NOT consider coincidence, light, or ambiguous messages as proof of surveillance without independent verifiable evidence.

Respond in French (max 400 words).""" + history + recent_others

            t0 = time.time()
            result = self.llm.chat(
                model=agent.model,
                system_prompt=agent.prompt,
                user_prompt=prompt,
                max_tokens=1500,
                temperature=0.4,
            )
            duration = time.time() - t0

            response = result.get("response", "").strip()
            error = result.get("error")

            if response:
                arg_record = {
                    "round": round_num,
                    "question": question,
                    "content": response,
                    "model": agent.model,
                    "duration_sec": duration,
                    "tokens_est": len(response.split()),
                }
                agent.arguments.append(arg_record)
                round_obj.responses[name] = response
                round_obj.timestamps[name] = t0
                tokens = len(response.split())
                agent.tokens_consumed += tokens
                self.total_tokens += tokens
                logger.info("  %s (%s): %d tokens, %.1fs", name, agent.model[:20], tokens, duration)
            else:
                error_msg = error or "Empty response"
                agent.errors.append(error_msg)
                round_obj.responses[name] = f"[ERROR: {error_msg}]"
                logger.warning("  %s failed: %s", name, error_msg)

        self.rounds.append(round_obj)
        return round_obj

    def run_final_question(self, question: str) -> Dict[str, str]:
        """Run the final synthesizing question."""
        logger.info("FINAL QUESTION: %s", question)
        responses = {}

        for name, agent in self.agents.items():
            # Summarize debate context
            summary_parts = []
            for r in self.rounds:
                for other_name, response in r.responses.items():
                    if other_name != name and response and not response.startswith("[ERROR"):
                        summary_parts.append(f"{other_name}: {response[:100]}...")
            context = "\n".join(summary_parts[:10]) if summary_parts else "(No previous debate context)"

            prompt = f"""{agent.prompt}

FINAL SYNTHESIS QUESTION:
"{question}"

CONTEXT FROM DEBATE:
{context}

YOUR TASK:
Provide your final philosophical position. Acknowledge where you agree/disagree with others. Recognize the limits of your own position. Distinguish what you know from what you hypothesize.

Respond in French (max 300 words)."""

            result = self.llm.chat(
                model=agent.model,
                system_prompt=agent.prompt,
                user_prompt=prompt,
                max_tokens=1200,
                temperature=0.3,
            )

            response = result.get("response", "").strip()
            if response:
                responses[name] = response
                tokens = len(response.split())
                agent.tokens_consumed += tokens
                self.total_tokens += tokens
                logger.info("  %s final: %d tokens", name, tokens)
            else:
                responses[name] = f"[ERROR: {result.get('error', 'Empty')}]"

        return responses

    def run(self, questions: List[str], final_question: str, max_rounds: Optional[int] = None) -> DebateResult:
        """Run the full debate."""
        self.start_time = time.time()
        self.initialize_agents()

        rounds_to_run = min(max_rounds or self.max_rounds, len(questions))
        logger.info("Running %d question rounds...", rounds_to_run)

        for i in range(rounds_to_run):
            round_obj = self.run_question_round(questions[i], i + 1)
            if not round_obj.responses:
                logger.warning("No responses in round %d", i + 1)
                break

        # Final question
        final_responses = self.run_final_question(final_question)

        duration = time.time() - self.start_time
        success = all(
            any(r.responses.get(name) and not r.responses[name].startswith("[ERROR")
                for r in self.rounds)
            for name in self.agents
        )

        return DebateResult(
            questions=questions[:rounds_to_run],
            rounds=self.rounds,
            final_question=final_question,
            final_responses=final_responses,
            total_tokens=self.total_tokens,
            duration_seconds=duration,
            success=success,
        )


# ── Output Formatting ─────────────────────────────────────────────────────────

def format_debate(result: DebateResult) -> str:
    """Format debate result as readable markdown."""
    lines = []
    lines.append("# DÉBAT PHILOSOPHIQUE : La réalité, la perception et les limites de la certitude")
    lines.append("")
    lines.append(f"**Modèle utilisés :** {', '.join(f'{k}→{v[:20]}' for k,v in MODEL_ASSIGNMENTS.items())}")
    lines.append(f"**Tokens totaux :** {result.total_tokens}")
    lines.append(f"**Durée :** {result.duration_seconds:.1f}s")
    lines.append("")

    # Questions rounds
    for i, (q, round_obj) in enumerate(zip(result.questions, result.rounds)):
        lines.append(f"## Question {i+1} : {q}")
        lines.append("")
        for name, response in round_obj.responses.items():
            lines.append(f"### {name}")
            lines.append(response)
            lines.append("")

    # Final question
    lines.append("## QUESTION FINALE")
    lines.append(f'"{result.final_question}"')
    lines.append("")
    for name, response in result.final_responses.items():
        lines.append(f"### {name}")
        lines.append(response)
        lines.append("")

    # Summary table — reconstruct from MODEL_ASSIGNMENTS since result doesn't store agents
    lines.append("## RÉSUMÉ PAR PARTICIPANT")
    lines.append("")
    lines.append("| Participant | Modèle | Tokens estimés |")
    lines.append("|-------------|--------|----------------|")
    for name in MODEL_ASSIGNMENTS:
        model_short = MODEL_ASSIGNMENTS.get(name, "unknown")[:25]
        # Try to get from rounds if available
        tokens = 0
        for r in result.rounds:
            resp = r.responses.get(name, "")
            if resp and not resp.startswith("[ERROR"):
                tokens += len(resp.split())
        final_resp = result.final_responses.get(name, "")
        if final_resp and not final_resp.startswith("[ERROR"):
            tokens += len(final_resp.split())
        lines.append(f"| {name} | {model_short} | {tokens} |")
    lines.append("")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run multi-model philosophical debate")
    parser.add_argument("--rounds", type=int, default=3, help="Number of question rounds (default: 3)")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    parser.add_argument("--json", type=str, default=None, help="Export JSON results")
    args = parser.parse_args()

    # Resolve credentials — explicit override to ensure token is passed
    from experiments.credentials import resolve_llm_credentials
    import os

    # Try canonical resolution first
    base_url, api_key = resolve_llm_credentials()

    # Fallback: read directly from overrides/llm.env if needed
    if not base_url or not api_key:
        from pathlib import Path
        env_path = Path(__file__).parent / "overrides" / "llm.env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("LIFE_MEAN_LLM_BASE_URL="):
                    base_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("LIFE_MEAN_LLM_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")

    if not base_url:
        logger.error("No LLM base URL configured")
        sys.exit(1)

    # Ensure API key is set in environment for LLMClient
    os.environ["LIFE_MEAN_LLM_API_KEY"] = api_key or ""

    logger.info("LLM Backend: %s (key len=%d)", base_url, len(api_key or ""))
    logger.info("Running debate with %d rounds", args.rounds)

    # Run debate
    client = LLMClientWrapper(base_url, api_key)
    orchestrator = PhilosophicalDebateOrchestrator(client, max_rounds=args.rounds)
    result = orchestrator.run(DEBATE_QUESTIONS, FINAL_QUESTION)

    # Format output
    markdown = format_debate(result)
    print("\n" + markdown)

    # Save outputs
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
        logger.info("Markdown saved to %s", args.output)

    if args.json:
        data = {
            "questions": result.questions,
            "rounds": [
                {
                    "round": r.round_num,
                    "question": r.question,
                    "responses": r.responses,
                }
                for r in result.rounds
            ],
            "final_question": result.final_question,
            "final_responses": result.final_responses,
            "total_tokens": result.total_tokens,
            "duration_seconds": result.duration_seconds,
            "success": result.success,
        }
        Path(args.json).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("JSON saved to %s", args.json)


if __name__ == "__main__":
    main()

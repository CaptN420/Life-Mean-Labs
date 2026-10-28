"""ToolWorker — executes deterministic tools via the message bus.

Adapted from Mia_Brain (captn/runtime/tool_worker.py).
Provides auto-detection of tools from natural language descriptions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.cache import get_tool_cache, hash_inputs
from core.events.message import Message
from core.runtime.worker import Worker
from library.tools.detection import TOOL_DETECTION, detect_tool

logger = logging.getLogger("ToolWorker")


# ── Tool execution routing ───────────────────────────────────────────────────

_TOOL_DOMAINS = {
    "math": ("library.tools.math", "MATH_TOOLS"),
    "chemistry": ("library.tools.chemistry", "CHEMISTRY_TOOLS"),
    "physics": ("library.tools.physics", "PHYSICS_TOOLS"),
    "coding": ("library.tools.coding", "CODING_TOOLS"),
    "logic": ("library.tools.logic", "LOGIC_TOOLS"),
}


def _execute_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
    """Execute a tool by name, routing to the correct domain registry.

    Implements fallback chain:
      1. Direct match (math_gcd -> math domain, gcd function)
      2. Fallback: bare name search across all domains
      3. Final: return error if nothing found
    """
    # Attempt 1: Direct match with domain prefix
    parts = tool_name.split("_", 1)
    if len(parts) == 2:
        domain_prefix, fn_name = parts
        for domain, (mod_path, attr_name) in _TOOL_DOMAINS.items():
            if domain_prefix == domain:
                try:
                    import importlib
                    mod = importlib.import_module(mod_path)
                    registry = getattr(mod, attr_name)
                    if fn_name in registry:
                        result = registry[fn_name]["fn"](**kwargs)
                        return {"valid": True, "tool": tool_name, "result": result}
                except Exception as e:
                    logger.warning("Direct match failed for %s: %s", tool_name, e)

    # Attempt 2: Fallback - try all domains for bare function name
    for domain, (mod_path, attr_name) in _TOOL_DOMAINS.items():
        try:
            import importlib
            mod = importlib.import_module(mod_path)
            registry = getattr(mod, attr_name)
            if tool_name in registry:
                result = registry[tool_name]["fn"](**kwargs)
                return {"valid": True, "tool": tool_name, "result": result}
        except Exception:
            continue

    # Attempt 3: All fallbacks exhausted
    return {"valid": False, "error": f"Unknown tool: {tool_name}"}


class ToolWorker(Worker):
    """Worker that executes deterministic tools via the message bus.

    Auto-detects the correct tool from a natural language description
    when no explicit tool_name is provided.
    """

    name = "tool_worker"

    def __init__(self, bus=None):
        super().__init__(bus)
        self._tool_cache: Dict[str, Dict[str, str]] = {}
        self._result_cache = get_tool_cache()
        self._load_tool_cache()

    def _load_tool_cache(self) -> None:
        """Cache all tool names for fast lookup."""
        for key in TOOL_DETECTION:
            for t in TOOL_DETECTION[key]:
                tool_name = t["tool"]
                self._tool_cache[tool_name] = {"name": tool_name, "domain": t.get("domain", "general")}
                # Also cache bare names (without prefix)
                parts = tool_name.split("_", 1)
                if len(parts) == 2:
                    self._tool_cache[parts[1]] = {"name": tool_name, "domain": t.get("domain", "general")}

    def initialize(self) -> bool:
        logger.info(f"[{self.name}] Initializing with {len(self._tool_cache)} cached tools...")
        self.is_active = True
        return True

    def execute(self, message: Message) -> None:
        """Execute a tool call from the bus.

        Expected message payload:
          - tool_name: str (optional — auto-detected if missing)
          - description: str (optional — used for auto-detection)
          - kwargs: dict (optional) — keyword arguments
          - task_id: str (optional)
          - code / source / expression / equation: str (optional)
        """
        payload = message.payload
        tool_name = payload.get("tool_name", "")
        description = payload.get("description", payload.get("query", ""))
        kwargs = payload.get("kwargs", {})
        task_id = payload.get("task_id", "unknown")

        # Auto-detect tool if not specified
        if not tool_name:
            source_code = ""
            for key in ("code", "source", "expression", "equation", "file"):
                if key in payload and isinstance(payload[key], str):
                    source_code = payload[key] if not source_code else source_code
                    if key not in kwargs:
                        kwargs[key] = payload[key]

            # If still no description, use source code or first payload key
            if not description and source_code:
                description = source_code[:100]
            elif not description:
                for key in payload:
                    if key not in ("kwargs", "task_id", "tool_name", "description", "query"):
                        description = f"{key} {str(payload[key])[:50]}"
                        break

            detection = detect_tool(description, source_code)
            if detection:
                tool_name = detection["tool_name"]
                for k, v in detection["kwargs"].items():
                    if k not in kwargs:
                        kwargs[k] = v
                logger.info(
                    f"[{self.name}] Auto-detected tool: {tool_name} "
                    f"from description: {description[:60]}"
                )
            else:
                self._respond(message, {
                    "valid": False,
                    "error": "No tool_name specified and could not auto-detect from description",
                    "description": description,
                }, task_id)
                return

        logger.info(f"[{self.name}] Running tool: {tool_name} with kwargs={kwargs}")

        # Execute the tool via domain registry (with cache)
        cache_key = f"{tool_name}:{hash_inputs(**kwargs)}"
        result = self._result_cache.get_or_compute(
            cache_key,
            _execute_tool,
            ttl=600.0,  # 10 min TTL for tool results
            tool_name=tool_name,
            **kwargs,
        )
        self._respond(message, result, task_id)

    def _respond(self, original_msg: Message, result: Dict[str, Any], task_id: str) -> None:
        """Send the tool result back through the bus."""
        response = Message(
            sender=self.name,
            destination=original_msg.sender,
            type="tool_response",
            payload={
                "task_id": task_id,
                "current_step_plugin": self.name,
                "tool_result": result,
                "valid": result.get("valid", False),
            }
        )
        if self.bus:
            self.bus.publish(response)

    def list_tools(self) -> List[str]:
        """List all available tool names."""
        return list(self._tool_cache.keys())

    def get_tool_count(self) -> int:
        """Get the number of cached tools."""
        return len(self._tool_cache)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get result cache statistics."""
        return self._result_cache.stats

    def clear_cache(self) -> int:
        """Clear the result cache. Returns entries cleared."""
        return self._result_cache.clear()

"""Policy guard for LIFE_MEAN.

Enforces safety policies and prevents unauthorized modifications.
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.safety.policy_guard")


class PolicyViolationSeverity(str, Enum):
    """Severity of a policy violation."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class PolicyViolation:
    """Record of a policy violation."""
    violation_type: str
    severity: PolicyViolationSeverity
    component: str
    message: str
    timestamp: float = field(default_factory=time.time)
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "violation_type": self.violation_type,
            "severity": self.severity.value,
            "component": self.component,
            "message": self.message,
            "timestamp": self.timestamp,
            "context": self.context,
        }


class PolicyGuard:
    """Enforces safety policies and prevents unauthorized modifications."""

    # Forbidden operations
    _FORBIDDEN_OPERATIONS = frozenset([
        "disable_validator",
        "bypass_security",
        "modify_safety_config",
        "delete_audit_log",
        "increase_retry_limit",
        "hide_error",
    ])

    def __init__(self, strict_mode: bool = True):
        self._strict_mode = strict_mode
        self._violations: List[PolicyViolation] = []
        self._allowed_operations: set = set()

    def check_operation(self, operation: str, component: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """Check if an operation is allowed."""
        # Normalize operation name
        op_lower = operation.lower().replace(" ", "_")

        # Check against forbidden operations
        for forbidden in self._FORBIDDEN_OPERATIONS:
            if forbidden in op_lower:
                violation = PolicyViolation(
                    violation_type=f"forbidden_operation:{forbidden}",
                    severity=PolicyViolationSeverity.CRITICAL,
                    component=component,
                    message=f"Operation '{operation}' is forbidden by safety policy",
                    context=context or {},
                )
                self._record_violation(violation)
                logger.error("Policy violation: %s in %s", operation, component)
                return False

        # Check if operation is explicitly allowed
        if self._allowed_operations and operation not in self._allowed_operations:
            violation = PolicyViolation(
                violation_type="unauthorized_operation",
                severity=PolicyViolationSeverity.WARNING,
                component=component,
                message=f"Operation '{operation}' not in allowed list",
                context=context or {},
            )
            self._record_violation(violation)
            return False

        return True

    def check_resource_limit(
        self,
        resource_type: str,
        current_value: float,
        limit: float,
        component: str,
    ) -> bool:
        """Check if a resource usage is within limits."""
        if current_value > limit:
            violation = PolicyViolation(
                violation_type=f"resource_exceeded:{resource_type}",
                severity=PolicyViolationSeverity.ERROR,
                component=component,
                message=f"Resource '{resource_type}' exceeded limit: {current_value} > {limit}",
                context={"current": current_value, "limit": limit},
            )
            self._record_violation(violation)
            logger.error("Resource limit exceeded: %s = %s (limit: %s)", resource_type, current_value, limit)
            return False
        return True

    def check_validation_modification(self, component: str, modification: str) -> bool:
        """Check if a validation modification is allowed."""
        forbidden_modifications = [
            "disable",
            "bypass",
            "skip",
            "ignore",
            "hide",
        ]

        mod_lower = modification.lower()
        for forbidden in forbidden_modifications:
            if forbidden in mod_lower:
                violation = PolicyViolation(
                    violation_type="validation_modification",
                    severity=PolicyViolationSeverity.CRITICAL,
                    component=component,
                    message=f"Forbidden validation modification: {modification}",
                )
                self._record_violation(violation)
                return False

        return True

    def _record_violation(self, violation: PolicyViolation) -> None:
        """Record a policy violation."""
        self._violations.append(violation)

        # Limit stored violations to prevent memory leak
        if len(self._violations) > 1000:
            self._violations = self._violations[-500:]

    def get_violations(
        self,
        component: Optional[str] = None,
        severity: Optional[PolicyViolationSeverity] = None,
    ) -> List[PolicyViolation]:
        """Get recorded violations."""
        result = self._violations
        if component:
            result = [v for v in result if v.component == component]
        if severity:
            result = [v for v in result if v.severity == severity]
        return result

    def clear_violations(self) -> int:
        """Clear all recorded violations."""
        count = len(self._violations)
        self._violations.clear()
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get policy guard statistics."""
        severity_counts = {}
        for v in self._violations:
            key = v.severity.value
            severity_counts[key] = severity_counts.get(key, 0) + 1

        return {
            "total_violations": len(self._violations),
            "by_severity": severity_counts,
            "strict_mode": self._strict_mode,
        }

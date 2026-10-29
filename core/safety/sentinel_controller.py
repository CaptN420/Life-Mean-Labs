"""Sentinel controller for Life_mean dashboard.

Provides API endpoints for Sentinel configuration, status, and alerts.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.safety.sentinel_controller")


class SentinelController:
    """Controller for Sentinel security monitoring integration."""

    def __init__(self, sentinel=None):
        self._sentinel = sentinel
        self._pending_uploads: List[Dict[str, Any]] = []

    def get_status(self) -> Dict[str, Any]:
        """Get current Sentinel status."""
        if self._sentinel is None:
            return {"error": "Sentinel not initialized"}
        return self._sentinel.get_status()

    def update_config(
        self,
        provider: Optional[str] = None,
        model_id: Optional[str] = None,
        analysis_mode: Optional[str] = None,
        external_log_upload: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Update Sentinel configuration."""
        if self._sentinel is None:
            return {"error": "Sentinel not initialized"}

        try:
            self._sentinel.configure(
                provider=provider,
                model_id=model_id,
                analysis_mode=analysis_mode,
                external_log_upload=external_log_upload,
            )
            return {"status": "updated", "config": self._sentinel.get_status()}
        except Exception as exc:
            logger.error("Failed to update Sentinel config: %s", exc)
            return {"error": str(exc)}

    def toggle_enabled(self, enabled: bool) -> Dict[str, Any]:
        """Enable or disable Sentinel."""
        if self._sentinel is None:
            return {"error": "Sentinel not initialized"}
        self._sentinel.set_enabled(enabled)
        return {"status": "enabled" if enabled else "disabled"}

    def get_alerts(self, limit: int = 20) -> Dict[str, Any]:
        """Get recent Sentinel alerts."""
        if self._sentinel is None:
            return {"alerts": []}
        return {"alerts": self._sentinel.get_alerts(limit)}

    def clear_alerts(self) -> Dict[str, Any]:
        """Clear all Sentinel alerts."""
        if self._sentinel is None:
            return {"error": "Sentinel not initialized"}
        count = self._sentinel.clear_alerts()
        return {"cleared": count}

    def health_check(self) -> Dict[str, Any]:
        """Check Sentinel health."""
        if self._sentinel is None:
            return {"error": "Sentinel not initialized"}
        return self._sentinel.health_check()

    def request_upload_confirmation(self) -> bool:
        """Check if external log upload is confirmed."""
        if self._sentinel is None:
            return False
        return self._sentinel.request_external_upload_confirmation()

    def export_events(self) -> List[Dict[str, Any]]:
        """Export events for review (sanitized)."""
        if self._sentinel is None:
            return []
        return self._sentinel.export_events_for_review()

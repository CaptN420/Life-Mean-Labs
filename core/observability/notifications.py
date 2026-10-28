"""Notifications for LIFE_MEAN.

Provides notification delivery to various channels.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.observability.notifications")


class NotificationChannel(str, Enum):
    """Available notification channels."""
    CONSOLE = "CONSOLE"
    JSON_FILE = "JSON_FILE"
    DISCORD = "DISCORD"
    GITHUB_ISSUES = "GITHUB_ISSUES"
    DASHBOARD = "DASHBOARD"


@dataclass
class Notification:
    """A notification to be sent."""
    channel: NotificationChannel
    message: str
    severity: str  # INFO, WARNING, ERROR, CRITICAL
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel.value,
            "message": self.message,
            "severity": self.severity,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


class NotificationService:
    """Manages notification delivery."""

    def __init__(self):
        self._sent_notifications: List[Notification] = []
        self._delivery_attempts: Dict[str, int] = {}
        self._failed_channels: set = set()

    def send(
        self,
        channel: NotificationChannel,
        message: str,
        severity: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send a notification."""
        # Check if channel is failed
        if channel in self._failed_channels:
            logger.warning("Channel %s is in failed state, skipping", channel)
            return False

        notification = Notification(
            channel=channel,
            message=message,
            severity=severity,
            payload=payload or {},
        )

        # Track delivery attempts
        key = f"{channel.value}:{message[:50]}"
        self._delivery_attempts[key] = self._delivery_attempts.get(key, 0) + 1

        # Attempt delivery
        try:
            if channel == NotificationChannel.CONSOLE:
                self._send_console(notification)
            elif channel == NotificationChannel.JSON_FILE:
                self._send_json_file(notification)
            elif channel == NotificationChannel.DISCORD:
                self._send_discord(notification)
            elif channel == NotificationChannel.GITHUB_ISSUES:
                self._send_github_issues(notification)
            elif channel == NotificationChannel.DASHBOARD:
                self._send_dashboard(notification)
            else:
                logger.warning("Unknown channel: %s", channel)
                return False

            self._sent_notifications.append(notification)
            return True

        except Exception as exc:
            logger.error("Failed to send notification to %s: %s", channel, exc)
            self._failed_channels.add(channel)
            return False

    def _send_console(self, notification: Notification) -> None:
        """Send notification to console."""
        prefix = f"[{notification.severity}]"
        print(f"{prefix} {notification.message}")
        if notification.payload:
            print(f"  Payload: {json.dumps(notification.payload, ensure_ascii=False)}")

    def _send_json_file(self, notification: Notification) -> None:
        """Send notification to JSON file."""
        import os
        log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "results", "traces")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "notifications.jsonl")

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(notification.to_json() + "\n")

    def _send_discord(self, notification: Notification) -> None:
        """Send notification to Discord."""
        # This would integrate with Discord webhook
        logger.info("Discord notification (simulated): %s", notification.message)

    def _send_github_issues(self, notification: Notification) -> None:
        """Send notification to GitHub Issues."""
        # This would integrate with GitHub API
        logger.info("GitHub Issues notification (simulated): %s", notification.message)

    def _send_dashboard(self, notification: Notification) -> None:
        """Send notification to dashboard."""
        logger.info("Dashboard notification: %s", notification.message)

    def get_sent_notifications(
        self,
        channel: Optional[NotificationChannel] = None,
        limit: int = 100,
    ) -> List[Notification]:
        """Get sent notifications."""
        if channel:
            result = [n for n in self._sent_notifications if n.channel == channel]
        else:
            result = list(self._sent_notifications)
        return result[-limit:]

    def clear_history(self) -> int:
        """Clear notification history."""
        count = len(self._sent_notifications)
        self._sent_notifications.clear()
        return count

    def get_statistics(self) -> Dict[str, Any]:
        """Get notification statistics."""
        channel_counts = {}
        for n in self._sent_notifications:
            key = n.channel.value
            channel_counts[key] = channel_counts.get(key, 0) + 1

        return {
            "total_sent": len(self._sent_notifications),
            "by_channel": channel_counts,
            "failed_channels": list(self._failed_channels),
        }

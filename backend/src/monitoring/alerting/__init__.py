"""
Alerting system for MANTIS AI.
Multi-channel alerting (Email, Slack, Webhook) for critical events.
"""

from src.monitoring.alerting.alert_manager import AlertManager
from src.monitoring.alerting.schemas import Alert, AlertSeverity

__all__ = ["AlertManager", "Alert", "AlertSeverity"]

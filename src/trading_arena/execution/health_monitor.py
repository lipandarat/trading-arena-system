"""
Health Monitoring System for Containerized Agent Runtime.

Provides comprehensive health monitoring and alerting for containerized trading agents.
Integrates with container manager, trading systems, and external monitoring services.
Monitors system resources, agent performance, and trading activity.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
import aiohttp
import psutil

from .container_manager import DockerContainerManager, AgentContainer

logger = logging.getLogger(__name__)

class HealthStatus(Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
    OFFLINE = "offline"

class AlertType(Enum):
    """Alert type enumeration."""
    CONTAINER_DOWN = "container_down"
    HIGH_CPU = "high_cpu"
    HIGH_MEMORY = "high_memory"
    AGENT_UNRESPONSIVE = "agent_unresponsive"
    TRADING_ERRORS = "trading_errors"
    SYSTEM_RESOURCES = "system_resources"
    NETWORK_ISSUES = "network_issues"

@dataclass
class HealthMetric:
    """Individual health metric."""
    name: str
    value: float
    unit: str
    threshold_warning: float
    threshold_critical: float
    status: HealthStatus
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class HealthAlert:
    """Health alert definition."""
    alert_id: str
    alert_type: AlertType
    severity: HealthStatus
    container_id: Optional[str]
    agent_id: Optional[str]
    message: str
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AgentHealthStatus:
    """Complete health status for an agent."""
    agent_id: str
    container_id: str
    overall_status: HealthStatus
    last_heartbeat: Optional[datetime]
    uptime_seconds: float
    restart_count: int
    metrics: Dict[str, HealthMetric] = field(default_factory=dict)
    alerts: List[HealthAlert] = field(default_factory=list)
    trading_metrics: Dict[str, Any] = field(default_factory=dict)

class HealthMonitor:
    """
    Comprehensive health monitoring system for containerized agents.

    Features:
    - Real-time monitoring of container resources and agent performance
    - Alert generation with configurable thresholds
    - Integration with external monitoring systems
    - Historical health data tracking
    - Automatic recovery recommendations
    """

    def __init__(self, container_manager: DockerContainerManager):
        """
        Initialize health monitor.

        Args:
            container_manager: DockerContainerManager instance
        """
        self.container_manager = container_manager
        self.agent_health: Dict[str, AgentHealthStatus] = {}
        self.active_alerts: List[HealthAlert] = []
        self.alert_handlers: List[Callable] = []
        self._monitoring_task = None
        self._is_monitoring = False

        # Configuration
        self.monitoring_interval = 30  # seconds
        self.health_check_timeout = 10  # seconds
        self.alert_retention_hours = 24

        # Thresholds
        self.thresholds = {
            'cpu_warning': 80.0,
            'cpu_critical': 95.0,
            'memory_warning': 80.0,
            'memory_critical': 95.0,
            'heartbeat_warning': 300,  # 5 minutes
            'heartbeat_critical': 600,  # 10 minutes
            'restart_count_warning': 5,
            'restart_count_critical': 10,
            'error_rate_warning': 10,
            'error_rate_critical': 20
        }

        # External monitoring integration
        self.webhook_url = os.getenv('HEALTH_WEBHOOK_URL')
        self.slack_webhook = os.getenv('SLACK_WEBHOOK_URL')

        logger.info("Health monitoring system initialized")

    async def start_monitoring(self, interval_seconds: int = 30):
        """
        Start health monitoring loop.

        Args:
            interval_seconds: Monitoring interval
        """
        if self._is_monitoring:
            logger.warning("Health monitoring is already running")
            return

        self.monitoring_interval = interval_seconds
        self._is_monitoring = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info(f"Started health monitoring with {interval_seconds}s interval")

    async def stop_monitoring(self):
        """Stop health monitoring loop."""
        if not self._is_monitoring:
            return

        self._is_monitoring = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped health monitoring")

    async def _monitoring_loop(self):
        """Main health monitoring loop."""
        while self._is_monitoring:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.monitoring_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitoring loop error: {e}")
                await asyncio.sleep(10)

    async def _perform_health_checks(self):
        """Perform comprehensive health checks on all containers."""
        current_time = datetime.now(timezone.utc)

        # Get container health status from container manager
        container_health = await self.container_manager.health_check_containers()
        system_resources = await self.container_manager.get_system_resources()

        for container_id, health_info in container_health.items():
            try:
                agent_container = self.container_manager.get_container_info(container_id)
                if not agent_container:
                    continue

                agent_id = agent_container.agent_id

                # Initialize or update agent health status
                if agent_id not in self.agent_health:
                    self.agent_health[agent_id] = AgentHealthStatus(
                        agent_id=agent_id,
                        container_id=container_id,
                        overall_status=HealthStatus.UNKNOWN,
                        last_heartbeat=None,
                        uptime_seconds=0,
                        restart_count=0
                    )

                agent_health = self.agent_health[agent_id]

                # Update basic status
                agent_health.last_heartbeat = current_time
                agent_health.uptime_seconds = (current_time - agent_container.created_at).total_seconds()
                agent_health.restart_count = agent_container.restart_count

                # Collect metrics
                await self._collect_container_metrics(agent_health, health_info)
                await self._collect_system_metrics(agent_health, system_resources)
                await self._collect_trading_metrics(agent_health)

                # Evaluate overall health
                agent_health.overall_status = self._evaluate_overall_health(agent_health)

                # Generate alerts if needed
                await self._check_for_alerts(agent_health)

            except Exception as e:
                logger.error(f"Health check failed for container {container_id}: {e}")
                await self._generate_alert(
                    AlertType.SYSTEM_RESOURCES,
                    HealthStatus.CRITICAL,
                    container_id,
                    None,
                    f"Health check failed: {str(e)}"
                )

        # Clean up old alerts
        await self._cleanup_old_alerts()

    async def _collect_container_metrics(self, agent_health: AgentHealthStatus, health_info: Dict):
        """Collect container-specific health metrics."""
        resource_usage = health_info.get('resource_usage', {})

        # CPU metric
        cpu_percent = resource_usage.get('cpu_percent', 0)
        agent_health.metrics['cpu'] = HealthMetric(
            name='cpu',
            value=cpu_percent,
            unit='percent',
            threshold_warning=self.thresholds['cpu_warning'],
            threshold_critical=self.thresholds['cpu_critical'],
            status=self._calculate_metric_status(cpu_percent, 'cpu'),
            timestamp=datetime.now(timezone.utc)
        )

        # Memory metric
        memory_percent = resource_usage.get('memory_percent', 0)
        agent_health.metrics['memory'] = HealthMetric(
            name='memory',
            value=memory_percent,
            unit='percent',
            threshold_warning=self.thresholds['memory_warning'],
            threshold_critical=self.thresholds['memory_critical'],
            status=self._calculate_metric_status(memory_percent, 'memory'),
            timestamp=datetime.now(timezone.utc)
        )

        # Network metrics
        network_rx = resource_usage.get('network_rx_mb', 0)
        network_tx = resource_usage.get('network_tx_mb', 0)

        agent_health.metrics['network_rx'] = HealthMetric(
            name='network_rx',
            value=network_rx,
            unit='mb',
            threshold_warning=1000,  # 1GB
            threshold_critical=5000,  # 5GB
            status=self._calculate_metric_status(network_rx, 'network'),
            timestamp=datetime.now(timezone.utc)
        )

        agent_health.metrics['network_tx'] = HealthMetric(
            name='network_tx',
            value=network_tx,
            unit='mb',
            threshold_warning=1000,  # 1GB
            threshold_critical=5000,  # 5GB
            status=self._calculate_metric_status(network_tx, 'network'),
            timestamp=datetime.now(timezone.utc)
        )

    async def _collect_system_metrics(self, agent_health: AgentHealthStatus, system_resources: Dict):
        """Collect system-level health metrics."""
        agent_health.metrics['system_cpu'] = HealthMetric(
            name='system_cpu',
            value=system_resources.get('cpu_percent', 0),
            unit='percent',
            threshold_warning=self.thresholds['cpu_warning'],
            threshold_critical=self.thresholds['cpu_critical'],
            status=self._calculate_metric_status(system_resources.get('cpu_percent', 0), 'cpu'),
            timestamp=datetime.now(timezone.utc)
        )

        agent_health.metrics['system_memory'] = HealthMetric(
            name='system_memory',
            value=system_resources.get('memory_percent', 0),
            unit='percent',
            threshold_warning=self.thresholds['memory_warning'],
            threshold_critical=self.thresholds['memory_critical'],
            status=self._calculate_metric_status(system_resources.get('memory_percent', 0), 'memory'),
            timestamp=datetime.now(timezone.utc)
        )

        agent_health.metrics['disk_space'] = HealthMetric(
            name='disk_space',
            value=system_resources.get('disk_percent', 0),
            unit='percent',
            threshold_warning=85.0,
            threshold_critical=95.0,
            status=self._calculate_metric_status(system_resources.get('disk_percent', 0), 'disk'),
            timestamp=datetime.now(timezone.utc)
        )

    async def _collect_trading_metrics(self, agent_health: AgentHealthStatus):
        """Collect trading-specific health metrics."""
        try:
            # Read metrics from agent container
            metrics_file = f'/tmp/agent_{agent_health.agent_id}/metrics.json'
            if os.path.exists(metrics_file):
                with open(metrics_file, 'r') as f:
                    trading_metrics = json.load(f)
                    agent_health.trading_metrics = trading_metrics

                # Extract trading health indicators
                health_metrics = trading_metrics.get('health_metrics', {})

                # Heartbeat check
                last_heartbeat_str = health_metrics.get('last_heartbeat')
                if last_heartbeat_str:
                    try:
                        last_heartbeat = datetime.fromisoformat(last_heartbeat_str.replace('Z', '+00:00'))
                        time_since_heartbeat = (datetime.now(timezone.utc) - last_heartbeat).total_seconds()

                        agent_health.metrics['heartbeat'] = HealthMetric(
                            name='heartbeat',
                            value=time_since_heartbeat,
                            unit='seconds',
                            threshold_warning=self.thresholds['heartbeat_warning'],
                            threshold_critical=self.thresholds['heartbeat_critical'],
                            status=self._calculate_heartbeat_status(time_since_heartbeat),
                            timestamp=datetime.now(timezone.utc)
                        )
                    except Exception as e:
                        logger.error(f"Failed to parse heartbeat timestamp: {e}")

                # Error rate
                errors = health_metrics.get('errors', [])
                error_rate = len(errors)

                agent_health.metrics['error_rate'] = HealthMetric(
                    name='error_rate',
                    value=error_rate,
                    unit='count',
                    threshold_warning=self.thresholds['error_rate_warning'],
                    threshold_critical=self.thresholds['error_rate_critical'],
                    status=self._calculate_metric_status(error_rate, 'error_rate'),
                    timestamp=datetime.now(timezone.utc)
                )

        except Exception as e:
            logger.error(f"Failed to collect trading metrics for agent {agent_health.agent_id}: {e}")

    def _calculate_metric_status(self, value: float, metric_type: str) -> HealthStatus:
        """Calculate health status based on metric value and type."""
        warning_threshold = self.thresholds.get(f'{metric_type}_warning', 80)
        critical_threshold = self.thresholds.get(f'{metric_type}_critical', 95)

        if value >= critical_threshold:
            return HealthStatus.CRITICAL
        elif value >= warning_threshold:
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY

    def _calculate_heartbeat_status(self, seconds_since_heartbeat: float) -> HealthStatus:
        """Calculate heartbeat status."""
        if seconds_since_heartbeat >= self.thresholds['heartbeat_critical']:
            return HealthStatus.CRITICAL
        elif seconds_since_heartbeat >= self.thresholds['heartbeat_warning']:
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY

    def _evaluate_overall_health(self, agent_health: AgentHealthStatus) -> HealthStatus:
        """Evaluate overall health status for an agent."""
        if any(metric.status == HealthStatus.CRITICAL for metric in agent_health.metrics.values()):
            return HealthStatus.CRITICAL

        if any(metric.status == HealthStatus.WARNING for metric in agent_health.metrics.values()):
            return HealthStatus.WARNING

        if agent_health.restart_count >= self.thresholds['restart_count_critical']:
            return HealthStatus.CRITICAL
        elif agent_health.restart_count >= self.thresholds['restart_count_warning']:
            return HealthStatus.WARNING

        return HealthStatus.HEALTHY

    async def _check_for_alerts(self, agent_health: AgentHealthStatus):
        """Check for conditions that should generate alerts."""
        # Check for critical metrics
        for metric_name, metric in agent_health.metrics.items():
            if metric.status == HealthStatus.CRITICAL:
                await self._generate_alert(
                    self._get_alert_type_for_metric(metric_name),
                    HealthStatus.CRITICAL,
                    agent_health.container_id,
                    agent_health.agent_id,
                    f"Critical {metric_name}: {metric.value}{metric.unit}"
                )

        # Check container status
        if agent_health.overall_status == HealthStatus.CRITICAL:
            await self._generate_alert(
                AlertType.CONTAINER_DOWN,
                HealthStatus.CRITICAL,
                agent_health.container_id,
                agent_health.agent_id,
                "Agent container health is critical"
            )

    def _get_alert_type_for_metric(self, metric_name: str) -> AlertType:
        """Map metric name to alert type."""
        mapping = {
            'cpu': AlertType.HIGH_CPU,
            'memory': AlertType.HIGH_MEMORY,
            'system_cpu': AlertType.SYSTEM_RESOURCES,
            'system_memory': AlertType.SYSTEM_RESOURCES,
            'disk_space': AlertType.SYSTEM_RESOURCES,
            'heartbeat': AlertType.AGENT_UNRESPONSIVE,
            'error_rate': AlertType.TRADING_ERRORS
        }
        return mapping.get(metric_name, AlertType.SYSTEM_RESOURCES)

    async def _generate_alert(self, alert_type: AlertType, severity: HealthStatus,
                            container_id: Optional[str], agent_id: Optional[str],
                            message: str, metadata: Optional[Dict] = None):
        """Generate a new health alert."""
        alert = HealthAlert(
            alert_id=f"alert_{datetime.now(timezone.utc).timestamp()}_{alert_type.value}",
            alert_type=alert_type,
            severity=severity,
            container_id=container_id,
            agent_id=agent_id,
            message=message,
            timestamp=datetime.now(timezone.utc),
            metadata=metadata or {}
        )

        # Check if this alert already exists (avoid spam)
        existing_similar = [
            a for a in self.active_alerts
            if (a.alert_type == alert_type and
                a.container_id == container_id and
                a.agent_id == agent_id and
                not a.resolved and
                (datetime.now(timezone.utc) - a.timestamp).seconds < 300)  # Within 5 minutes
        ]

        if not existing_similar:
            self.active_alerts.append(alert)
            logger.warning(f"Health alert generated: {alert.alert_type.value} - {message}")

            # Send to external systems
            await self._send_alert_notification(alert)

            # Call registered handlers
            for handler in self.alert_handlers:
                try:
                    await handler(alert)
                except Exception as e:
                    logger.error(f"Alert handler failed: {e}")

    async def _send_alert_notification(self, alert: HealthAlert):
        """Send alert notification to external systems."""
        if not self.webhook_url and not self.slack_webhook:
            return

        message = {
            'alert_id': alert.alert_id,
            'alert_type': alert.alert_type.value,
            'severity': alert.severity.value,
            'agent_id': alert.agent_id,
            'container_id': alert.container_id,
            'message': alert.message,
            'timestamp': alert.timestamp.isoformat(),
            'metadata': alert.metadata
        }

        # Send to webhook
        if self.webhook_url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.webhook_url, json=message) as response:
                        if response.status == 200:
                            logger.debug(f"Alert sent to webhook: {alert.alert_id}")
            except Exception as e:
                logger.error(f"Failed to send alert to webhook: {e}")

        # Send to Slack
        if self.slack_webhook:
            try:
                slack_message = {
                    "text": f"🚨 Trading Agent Health Alert",
                    "attachments": [{
                        "color": "danger" if alert.severity == HealthStatus.CRITICAL else "warning",
                        "fields": [
                            {"title": "Alert Type", "value": alert.alert_type.value, "short": True},
                            {"title": "Severity", "value": alert.severity.value, "short": True},
                            {"title": "Agent ID", "value": str(alert.agent_id), "short": True},
                            {"title": "Message", "value": alert.message, "short": False}
                        ],
                        "ts": int(alert.timestamp.timestamp())
                    }]
                }

                async with aiohttp.ClientSession() as session:
                    async with session.post(self.slack_webhook, json=slack_message) as response:
                        if response.status == 200:
                            logger.debug(f"Alert sent to Slack: {alert.alert_id}")
            except Exception as e:
                logger.error(f"Failed to send alert to Slack: {e}")

    async def _cleanup_old_alerts(self):
        """Clean up old resolved alerts."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.alert_retention_hours)

        alerts_to_remove = [
            alert for alert in self.active_alerts
            if alert.resolved and alert.resolved_at and alert.resolved_at < cutoff_time
        ]

        for alert in alerts_to_remove:
            self.active_alerts.remove(alert)

    def add_alert_handler(self, handler: Callable[[HealthAlert], Any]):
        """Add custom alert handler function."""
        self.alert_handlers.append(handler)

    def get_agent_health(self, agent_id: str) -> Optional[AgentHealthStatus]:
        """Get health status for a specific agent."""
        return self.agent_health.get(agent_id)

    def get_all_agent_health(self) -> Dict[str, AgentHealthStatus]:
        """Get health status for all agents."""
        return self.agent_health.copy()

    def get_active_alerts(self, severity: Optional[HealthStatus] = None) -> List[HealthAlert]:
        """Get active alerts, optionally filtered by severity."""
        alerts = [a for a in self.active_alerts if not a.resolved]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return alerts

    async def resolve_alert(self, alert_id: str):
        """Manually resolve an alert."""
        for alert in self.active_alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                alert.resolved_at = datetime.now(timezone.utc)
                logger.info(f"Alert resolved: {alert_id}")
                break

    async def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive health summary."""
        current_time = datetime.now(timezone.utc)

        # Count agents by status
        status_counts = {
            HealthStatus.HEALTHY.value: 0,
            HealthStatus.WARNING.value: 0,
            HealthStatus.CRITICAL.value: 0,
            HealthStatus.UNKNOWN.value: 0
        }

        for agent_health in self.agent_health.values():
            status_counts[agent_health.overall_status.value] += 1

        # Count alerts by type and severity
        alert_counts = {}
        severity_counts = {
            HealthStatus.WARNING.value: 0,
            HealthStatus.CRITICAL.value: 0
        }

        for alert in self.active_alerts:
            if not alert.resolved:
                alert_counts[alert.alert_type.value] = alert_counts.get(alert.alert_type.value, 0) + 1
                severity_counts[alert.severity.value] += 1

        return {
            'timestamp': current_time.isoformat(),
            'total_agents': len(self.agent_health),
            'agent_status_counts': status_counts,
            'active_alerts': len([a for a in self.active_alerts if not a.resolved]),
            'alert_counts_by_type': alert_counts,
            'alert_counts_by_severity': severity_counts,
            'system_monitoring': self._is_monitoring,
            'monitoring_interval': self.monitoring_interval
        }

    async def export_health_data(self, hours: int = 24) -> Dict[str, Any]:
        """Export health data for analysis."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        export_data = {
            'export_timestamp': datetime.now(timezone.utc).isoformat(),
            'time_range_hours': hours,
            'agents': {},
            'alerts': []
        }

        # Export agent health data
        for agent_id, agent_health in self.agent_health.items():
            export_data['agents'][agent_id] = {
                'overall_status': agent_health.overall_status.value,
                'last_heartbeat': agent_health.last_heartbeat.isoformat() if agent_health.last_heartbeat else None,
                'uptime_seconds': agent_health.uptime_seconds,
                'restart_count': agent_health.restart_count,
                'metrics': {name: asdict(metric) for name, metric in agent_health.metrics.items()},
                'trading_metrics': agent_health.trading_metrics
            }

        # Export alerts
        for alert in self.active_alerts:
            if alert.timestamp >= cutoff_time:
                alert_dict = asdict(alert)
                alert_dict['timestamp'] = alert.timestamp.isoformat()
                if alert.resolved_at:
                    alert_dict['resolved_at'] = alert.resolved_at.isoformat()
                export_data['alerts'].append(alert_dict)

        return export_data
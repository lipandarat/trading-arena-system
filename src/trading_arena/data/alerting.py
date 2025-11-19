import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from sqlalchemy import select
from trading_arena.models.agent import Agent
from trading_arena.models.scoring import Score

logger = logging.getLogger(__name__)


class AlertingSystem:
    """
    Real-time alerting system for risk monitoring, performance milestones, and market regime changes.

    Provides multi-channel alerting with Redis pub/sub for agent notifications, system alerts, and competition events.
    Implements configurable risk limits, milestone tracking, and market regime detection.
    """

    def __init__(self, redis_client, db_session):
        """
        Initialize the alerting system.

        Args:
            redis_client: Redis client for pub/sub messaging and alert storage
            db_session: Database session for accessing agent and score data
        """
        self.redis_client = redis_client
        self.db_session = db_session
        self.alert_channels = ['agent_notifications', 'system_alerts', 'competition_events']
        self.is_monitoring = False
        self.monitoring_task = None

        # Default thresholds
        self.default_thresholds = {
            'max_drawdown': 0.30,  # 30%
            'max_leverage': 5.0,
            'min_capital_ratio': 0.70,  # 70% of initial capital
            'high_volatility_threshold': 0.05,  # 5%
            'low_volatility_threshold': 0.01,  # 1%
        }

    async def check_agent_risk_limits(self, agent_id: int) -> List[Dict[str, Any]]:
        """
        Check if agent is violating risk limits and generate alerts.

        Args:
            agent_id: ID of the agent to check

        Returns:
            List of alert dictionaries for any violations found
        """
        try:
            # Get agent data
            agent = await self.db_session.get(Agent, agent_id)
            if not agent:
                logger.warning(f"Agent {agent_id} not found")
                return []

            # Get latest score
            latest_score_result = await self.db_session.execute(
                select(Score)
                .where(Score.agent_id == agent_id)
                .order_by(Score.calculated_at.desc())
                .limit(1)
            )

            score = latest_score_result.scalar_one_or_none()
            if not score:
                logger.info(f"No score data found for agent {agent_id}")
                return []

            alerts = []
            violations = []

            # Check drawdown limit
            current_drawdown = abs(score.current_drawdown)
            max_drawdown = agent.max_drawdown or self.default_thresholds['max_drawdown']

            if current_drawdown > max_drawdown:
                violations.append({
                    'type': 'drawdown_exceeded',
                    'current_value': round(current_drawdown, 4),
                    'limit_value': round(max_drawdown, 4),
                    'excess': round(current_drawdown - max_drawdown, 4)
                })

            # Check leverage usage (if available in score)
            if hasattr(score, 'leverage_usage') and score.leverage_usage is not None:
                current_leverage = score.leverage_usage
                max_leverage = agent.max_leverage or self.default_thresholds['max_leverage']

                if current_leverage > max_leverage:
                    violations.append({
                        'type': 'leverage_exceeded',
                        'current_value': round(current_leverage, 2),
                        'limit_value': round(max_leverage, 2),
                        'excess': round(current_leverage - max_leverage, 2)
                    })

            # Check capital preservation
            if agent.initial_capital > 0:
                capital_ratio = agent.current_capital / agent.initial_capital
                min_capital_ratio = agent.min_capital_ratio or self.default_thresholds['min_capital_ratio']

                if capital_ratio < min_capital_ratio:
                    violations.append({
                        'type': 'capital_below_minimum',
                        'current_value': round(capital_ratio, 3),
                        'limit_value': round(min_capital_ratio, 3),
                        'excess': round(min_capital_ratio - capital_ratio, 3)
                    })

            # Create alert if violations found
            if violations:
                alerts.append({
                    'type': 'risk_limit_violation',
                    'severity': self._calculate_violation_severity(violations),
                    'agent_id': agent_id,
                    'agent_name': agent.name,
                    'violations': violations,
                    'current_capital': round(agent.current_capital, 2),
                    'current_drawdown': round(score.current_drawdown, 4),
                    'risk_adjusted_score': round(score.risk_adjusted_score, 2),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

                logger.warning(f"Risk limit violations detected for agent {agent_id}: {len(violations)} violations")

            return alerts

        except Exception as e:
            logger.error(f"Error checking risk limits for agent {agent_id}: {e}")
            return []

    async def check_performance_milestones(self, agent_id: int) -> List[Dict[str, Any]]:
        """
        Check for performance milestones and generate alerts.

        Args:
            agent_id: ID of the agent to check

        Returns:
            List of milestone alert dictionaries
        """
        try:
            agent = await self.db_session.get(Agent, agent_id)
            if not agent:
                return []

            alerts = []

            if agent.initial_capital <= 0:
                logger.warning(f"Invalid initial capital for agent {agent_id}: {agent.initial_capital}")
                return []

            current_return = (agent.current_capital - agent.initial_capital) / agent.initial_capital

            # Check for first profit
            if current_return > 0 and agent.current_capital > agent.initial_capital:
                alerts.append({
                    'type': 'performance_milestone',
                    'milestone_type': 'first_profit',
                    'severity': 'info',
                    'agent_id': agent_id,
                    'agent_name': agent.name,
                    'current_capital': round(agent.current_capital, 2),
                    'initial_capital': round(agent.initial_capital, 2),
                    'return_percentage': round(current_return * 100, 2),
                    'profit_amount': round(agent.current_capital - agent.initial_capital, 2),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

            # Check for significant profit milestones
            milestone_thresholds = [0.10, 0.25, 0.50, 1.0, 2.0, 5.0]  # 10%, 25%, 50%, 100%, 200%, 500%

            for threshold in milestone_thresholds:
                if current_return >= threshold:
                    alerts.append({
                        'type': 'performance_milestone',
                        'milestone_type': f'profit_{int(threshold * 100)}percent',
                        'severity': 'success' if threshold >= 0.50 else 'info',
                        'agent_id': agent_id,
                        'agent_name': agent.name,
                        'current_capital': round(agent.current_capital, 2),
                        'initial_capital': round(agent.initial_capital, 2),
                        'return_percentage': round(current_return * 100, 2),
                        'threshold_percentage': round(threshold * 100, 1),
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })

            # Check for recovery milestones (recovering from drawdowns)
            if current_return > -0.05 and agent.current_capital > agent.initial_capital * 0.95:  # Within 5% of break-even
                alerts.append({
                    'type': 'performance_milestone',
                    'milestone_type': 'recovery',
                    'severity': 'success',
                    'agent_id': agent_id,
                    'agent_name': agent.name,
                    'current_capital': round(agent.current_capital, 2),
                    'return_percentage': round(current_return * 100, 2),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

            if alerts:
                logger.info(f"Performance milestones detected for agent {agent_id}: {len(alerts)} milestones")

            return alerts

        except Exception as e:
            logger.error(f"Error checking performance milestones for agent {agent_id}: {e}")
            return []

    async def check_market_regime_changes(self, market_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Check for market regime changes and generate alerts.

        Args:
            market_data: Dictionary containing market metrics like volatility, price changes

        Returns:
            List of market regime change alert dictionaries
        """
        try:
            alerts = []

            # Check volatility-based regime changes
            if 'volatility' in market_data:
                volatility = market_data['volatility']
                symbol = market_data.get('symbol', 'UNKNOWN')

                if volatility > self.default_thresholds['high_volatility_threshold']:
                    alerts.append({
                        'type': 'market_regime_change',
                        'regime_type': 'high_volatility',
                        'severity': 'warning',
                        'symbol': symbol,
                        'volatility': round(volatility, 4),
                        'threshold': self.default_thresholds['high_volatility_threshold'],
                        'message': f'High volatility detected for {symbol}: {volatility:.2%}',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })
                elif volatility < self.default_thresholds['low_volatility_threshold']:
                    alerts.append({
                        'type': 'market_regime_change',
                        'regime_type': 'low_volatility',
                        'severity': 'info',
                        'symbol': symbol,
                        'volatility': round(volatility, 4),
                        'threshold': self.default_thresholds['low_volatility_threshold'],
                        'message': f'Low volatility detected for {symbol}: {volatility:.2%}',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })

            # Check for significant price movements
            if 'price_change_percent' in market_data:
                price_change = abs(market_data['price_change_percent'])
                symbol = market_data.get('symbol', 'UNKNOWN')

                if price_change > 0.10:  # 10% price movement
                    severity = 'critical' if price_change > 0.20 else 'warning'

                    alerts.append({
                        'type': 'market_regime_change',
                        'regime_type': 'price_spike',
                        'severity': severity,
                        'symbol': symbol,
                        'price_change_percent': round(price_change, 4),
                        'direction': 'up' if market_data.get('price_change_percent', 0) > 0 else 'down',
                        'message': f'Significant price movement for {symbol}: {price_change:.2%}',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })

            # Check for volume anomalies
            if 'volume_ratio' in market_data:
                volume_ratio = market_data['volume_ratio']
                symbol = market_data.get('symbol', 'UNKNOWN')

                if volume_ratio > 3.0:  # Volume 3x higher than average
                    alerts.append({
                        'type': 'market_regime_change',
                        'regime_type': 'volume_spike',
                        'severity': 'info',
                        'symbol': symbol,
                        'volume_ratio': round(volume_ratio, 2),
                        'message': f'High volume detected for {symbol}: {volume_ratio}x average',
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    })

            if alerts:
                logger.info(f"Market regime changes detected: {len(alerts)} alerts")

            return alerts

        except Exception as e:
            logger.error(f"Error checking market regime changes: {e}")
            return []

    async def publish_alert(self, alert: Dict[str, Any]):
        """
        Publish alert to notification channels.

        Args:
            alert: Alert dictionary to publish
        """
        try:
            message = {
                'alert': alert,
                'published_at': datetime.now(timezone.utc).isoformat(),
                'alert_id': f"{alert['type']}:{alert.get('agent_id', 'system')}:{int(datetime.now().timestamp())}"
            }

            # Publish to general alert channel
            await self.redis_client.publish(
                'alerts',
                json.dumps(message)
            )

            # Publish to agent-specific channel if agent alert
            if 'agent_id' in alert:
                await self.redis_client.publish(
                    f'agent:{alert["agent_id"]}:alerts',
                    json.dumps(message)
                )

            # Publish to severity-specific channels
            severity = alert.get('severity', 'info')
            await self.redis_client.publish(
                f'alerts:{severity}',
                json.dumps(message)
            )

            # Store in Redis for API access (with TTL)
            alert_key = f'alert:{message["alert_id"]}'
            await self.redis_client.setex(
                alert_key,
                3600,  # 1 hour TTL
                json.dumps(message)
            )

            # Store in agent-specific list for quick retrieval
            if 'agent_id' in alert:
                agent_alerts_key = f'agent:{alert["agent_id"]}:alerts:latest'
                await self.redis_client.setex(
                    agent_alerts_key,
                    1800,  # 30 minutes TTL
                    json.dumps([message])  # Simplified - would normally append to list
                )

            logger.info(f"Published alert: {alert['type']} for {alert.get('agent_name', 'system')}")

        except Exception as e:
            logger.error(f"Failed to publish alert: {e}")

    def _calculate_violation_severity(self, violations: List[Dict[str, Any]]) -> str:
        """
        Calculate severity level based on violations.

        Args:
            violations: List of violation dictionaries

        Returns:
            Severity string: 'critical', 'major', 'minor', or 'info'
        """
        if not violations:
            return 'info'

        # Critical violations that threaten agent survival
        critical_types = ['capital_below_minimum', 'drawdown_exceeded']

        # Major violations that require immediate attention
        major_types = ['leverage_exceeded']

        has_critical = any(v['type'] in critical_types for v in violations)
        has_major = any(v['type'] in major_types for v in violations)

        if has_critical:
            return 'critical'
        elif has_major:
            return 'major'
        else:
            return 'minor'

    async def start_alert_monitoring(self, check_interval: int = 60):
        """
        Start continuous alert monitoring.

        Args:
            check_interval: Interval in seconds between monitoring checks
        """
        if self.is_monitoring:
            logger.warning("Alert monitoring already running")
            return

        self.is_monitoring = True
        logger.info(f"Starting continuous alert monitoring with {check_interval}s interval")

        while self.is_monitoring:
            try:
                # Monitor active agents
                await self._monitor_active_agents()

                # Check for system-wide conditions
                await self._monitor_system_conditions()

                await asyncio.sleep(check_interval)

            except asyncio.CancelledError:
                logger.info("Alert monitoring cancelled")
                break
            except Exception as e:
                logger.error(f"Error in alert monitoring: {e}")
                await asyncio.sleep(10)  # Wait before retrying

    async def stop_alert_monitoring(self):
        """Stop continuous alert monitoring."""
        self.is_monitoring = False

        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Alert monitoring stopped")

    async def _monitor_active_agents(self):
        """
        Monitor active agents for risk violations.

        This method would typically query for active agents and check each one.
        For now, it's a placeholder that can be extended based on active agent tracking.
        """
        try:
            # Get all agents with recent activity or open positions
            # This would be implemented based on your active agent tracking system
            # For now, we'll skip the implementation to avoid database dependencies

            logger.debug("Active agent monitoring check completed")

        except Exception as e:
            logger.error(f"Error monitoring active agents: {e}")

    async def _monitor_system_conditions(self):
        """
        Monitor system-wide conditions that might generate alerts.

        This could include database connectivity, Redis availability, etc.
        """
        try:
            # Check Redis connectivity
            await self.redis_client.ping()

            logger.debug("System conditions monitoring check completed")

        except Exception as e:
            logger.error(f"System condition detected: {e}")

            # Publish system alert
            await self.publish_alert({
                'type': 'system_alert',
                'severity': 'critical',
                'message': f'System connectivity issue: {str(e)}',
                'component': 'alerting_system',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })

    async def get_agent_alerts(self, agent_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent alerts for a specific agent.

        Args:
            agent_id: ID of the agent
            limit: Maximum number of alerts to return

        Returns:
            List of alert dictionaries
        """
        try:
            # This would typically query a persistent alert store
            # For now, return empty list
            return []

        except Exception as e:
            logger.error(f"Error getting alerts for agent {agent_id}: {e}")
            return []

    async def get_system_alerts(self, severity: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent system alerts.

        Args:
            severity: Filter by severity level (optional)
            limit: Maximum number of alerts to return

        Returns:
            List of alert dictionaries
        """
        try:
            # This would typically query a persistent alert store
            # For now, return empty list
            return []

        except Exception as e:
            logger.error(f"Error getting system alerts: {e}")
            return []
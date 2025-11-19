import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator
from datetime import datetime, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NotificationMessage:
    """Data class for structured notification messages."""
    id: str
    type: str  # 'agent', 'system', 'competition'
    channel: str
    agent_id: Optional[int] = None
    competition_id: Optional[int] = None
    title: str = ""
    message: str = ""
    severity: str = "info"  # 'info', 'warning', 'major', 'critical', 'success'
    data: Optional[Dict[str, Any]] = None
    timestamp: str = None
    read: bool = False

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.data is None:
            self.data = {}


class NotificationManager:
    """
    Multi-channel notification management system using Redis pub/sub.

    Provides real-time notification delivery for agents, system alerts, and competition events.
    Supports channel-based subscriptions, message filtering, and notification history.
    """

    def __init__(self, redis_client):
        """
        Initialize the notification manager.

        Args:
            redis_client: Redis client for pub/sub messaging and notification storage
        """
        self.redis_client = redis_client
        self.channels = {
            'agent_notifications': 'agent:{agent_id}:notifications',
            'system_alerts': 'system_alerts',
            'competition_events': 'competition_events',
            'general': 'notifications'
        }
        self.subscriptions = {}
        self.pubsub = None

    async def send_agent_notification(
        self,
        agent_id: int,
        title: str,
        message: str,
        severity: str = "info",
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Send agent-specific notification.

        Args:
            agent_id: ID of the target agent
            title: Notification title
            message: Notification message
            severity: Severity level ('info', 'warning', 'major', 'critical', 'success')
            data: Additional data payload

        Returns:
            Notification ID
        """
        try:
            notification_id = f"agent:{agent_id}:{int(datetime.now().timestamp())}"

            notification = NotificationMessage(
                id=notification_id,
                type='agent',
                channel=self.channels['agent_notifications'].format(agent_id=agent_id),
                agent_id=agent_id,
                title=title,
                message=message,
                severity=severity,
                data=data or {}
            )

            await self._publish_notification(notification)
            await self._store_agent_notification(agent_id, notification)

            logger.info(f"Agent notification sent: {notification_id} to agent {agent_id}")
            return notification_id

        except Exception as e:
            logger.error(f"Failed to send agent notification to {agent_id}: {e}")
            raise

    async def send_system_alert(
        self,
        title: str,
        message: str,
        severity: str = "warning",
        component: str = "system",
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Send system-wide alert.

        Args:
            title: Alert title
            message: Alert message
            severity: Severity level
            component: System component generating the alert
            data: Additional data payload

        Returns:
            Notification ID
        """
        try:
            notification_id = f"system:{component}:{int(datetime.now().timestamp())}"

            notification = NotificationMessage(
                id=notification_id,
                type='system',
                channel=self.channels['system_alerts'],
                title=title,
                message=message,
                severity=severity,
                data=data or {}
            )

            # Add component to data
            notification.data['component'] = component

            await self._publish_notification(notification)
            await self._store_system_notification(notification)

            logger.info(f"System alert sent: {notification_id}")
            return notification_id

        except Exception as e:
            logger.error(f"Failed to send system alert: {e}")
            raise

    async def send_competition_event(
        self,
        competition_id: int,
        event_type: str,
        title: str,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Send competition-related event notification.

        Args:
            competition_id: ID of the competition
            event_type: Type of event ('leaderboard_update', 'milestone', 'completion', etc.)
            title: Event title
            message: Event message
            data: Additional event data

        Returns:
            Notification ID
        """
        try:
            notification_id = f"competition:{competition_id}:{int(datetime.now().timestamp())}"

            notification = NotificationMessage(
                id=notification_id,
                type='competition',
                channel=self.channels['competition_events'],
                competition_id=competition_id,
                title=title,
                message=message,
                severity='info',
                data=data or {}
            )

            # Add event type to data
            notification.data['event_type'] = event_type

            await self._publish_notification(notification)
            await self._store_competition_notification(competition_id, notification)

            logger.info(f"Competition event sent: {notification_id} for competition {competition_id}")
            return notification_id

        except Exception as e:
            logger.error(f"Failed to send competition event for {competition_id}: {e}")
            raise

    async def _publish_notification(self, notification: NotificationMessage):
        """
        Publish notification to Redis channel.

        Args:
            notification: Notification message to publish
        """
        try:
            message_data = {
                'id': notification.id,
                'type': notification.type,
                'agent_id': notification.agent_id,
                'competition_id': notification.competition_id,
                'title': notification.title,
                'message': notification.message,
                'severity': notification.severity,
                'data': notification.data,
                'timestamp': notification.timestamp,
                'channel': notification.channel
            }

            await self.redis_client.publish(
                notification.channel,
                json.dumps(message_data)
            )

            # Also publish to general notifications channel
            await self.redis_client.publish(
                self.channels['general'],
                json.dumps(message_data)
            )

            # Publish to severity-specific channel
            await self.redis_client.publish(
                f'notifications:{notification.severity}',
                json.dumps(message_data)
            )

        except Exception as e:
            logger.error(f"Failed to publish notification {notification.id}: {e}")
            raise

    async def _store_agent_notification(self, agent_id: int, notification: NotificationMessage):
        """
        Store agent notification in Redis for retrieval.

        Args:
            agent_id: Agent ID
            notification: Notification to store
        """
        try:
            # Store notification data
            notification_key = f'agent:{agent_id}:notification:{notification.id}'
            notification_data = {
                'id': notification.id,
                'type': notification.type,
                'title': notification.title,
                'message': notification.message,
                'severity': notification.severity,
                'data': notification.data,
                'timestamp': notification.timestamp,
                'read': False
            }

            await self.redis_client.setex(
                notification_key,
                86400,  # 24 hours TTL
                json.dumps(notification_data)
            )

            # Add to agent's recent notifications list
            recent_key = f'agent:{agent_id}:notifications:recent'
            await self.redis_client.lpush(recent_key, json.dumps(notification_data))
            await self.redis_client.ltrim(recent_key, 0, 99)  # Keep only last 100
            await self.redis_client.expire(recent_key, 86400)

        except Exception as e:
            logger.error(f"Failed to store agent notification {notification.id}: {e}")

    async def _store_system_notification(self, notification: NotificationMessage):
        """
        Store system notification in Redis for retrieval.

        Args:
            notification: Notification to store
        """
        try:
            # Store notification data
            notification_key = f'system:notification:{notification.id}'
            notification_data = {
                'id': notification.id,
                'type': notification.type,
                'title': notification.title,
                'message': notification.message,
                'severity': notification.severity,
                'data': notification.data,
                'timestamp': notification.timestamp
            }

            await self.redis_client.setex(
                notification_key,
                3600,  # 1 hour TTL for system notifications
                json.dumps(notification_data)
            )

            # Add to system alerts list
            recent_key = 'system:alerts:recent'
            await self.redis_client.lpush(recent_key, json.dumps(notification_data))
            await self.redis_client.ltrim(recent_key, 0, 199)  # Keep only last 200
            await self.redis_client.expire(recent_key, 3600)

        except Exception as e:
            logger.error(f"Failed to store system notification {notification.id}: {e}")

    async def _store_competition_notification(self, competition_id: int, notification: NotificationMessage):
        """
        Store competition notification in Redis for retrieval.

        Args:
            competition_id: Competition ID
            notification: Notification to store
        """
        try:
            # Store notification data
            notification_key = f'competition:{competition_id}:notification:{notification.id}'
            notification_data = {
                'id': notification.id,
                'type': notification.type,
                'competition_id': competition_id,
                'title': notification.title,
                'message': notification.message,
                'severity': notification.severity,
                'data': notification.data,
                'timestamp': notification.timestamp
            }

            await self.redis_client.setex(
                notification_key,
                7200,  # 2 hours TTL for competition notifications
                json.dumps(notification_data)
            )

            # Add to competition events list
            recent_key = f'competition:{competition_id}:events:recent'
            await self.redis_client.lpush(recent_key, json.dumps(notification_data))
            await self.redis_client.ltrim(recent_key, 0, 149)  # Keep only last 150
            await self.redis_client.expire(recent_key, 7200)

        except Exception as e:
            logger.error(f"Failed to store competition notification {notification.id}: {e}")

    async def get_agent_notifications(self, agent_id: int, limit: int = 50, unread_only: bool = False) -> List[Dict[str, Any]]:
        """
        Get recent notifications for an agent.

        Args:
            agent_id: Agent ID
            limit: Maximum number of notifications to return
            unread_only: Return only unread notifications

        Returns:
            List of notification dictionaries
        """
        try:
            recent_key = f'agent:{agent_id}:notifications:recent'
            notifications = await self.redis_client.lrange(recent_key, 0, limit - 1)

            result = []
            for notification_json in notifications:
                try:
                    notification_data = json.loads(notification_json)

                    if unread_only and notification_data.get('read', False):
                        continue

                    result.append(notification_data)
                except json.JSONDecodeError:
                    continue

            return result

        except Exception as e:
            logger.error(f"Error getting notifications for agent {agent_id}: {e}")
            return []

    async def get_system_alerts(self, limit: int = 50, severity: str = None) -> List[Dict[str, Any]]:
        """
        Get recent system alerts.

        Args:
            limit: Maximum number of alerts to return
            severity: Filter by severity level (optional)

        Returns:
            List of alert dictionaries
        """
        try:
            recent_key = 'system:alerts:recent'
            alerts = await self.redis_client.lrange(recent_key, 0, limit - 1)

            result = []
            for alert_json in alerts:
                try:
                    alert_data = json.loads(alert_json)

                    if severity and alert_data.get('severity') != severity:
                        continue

                    result.append(alert_data)
                except json.JSONDecodeError:
                    continue

            return result

        except Exception as e:
            logger.error(f"Error getting system alerts: {e}")
            return []

    async def get_competition_events(self, competition_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent events for a competition.

        Args:
            competition_id: Competition ID
            limit: Maximum number of events to return

        Returns:
            List of event dictionaries
        """
        try:
            recent_key = f'competition:{competition_id}:events:recent'
            events = await self.redis_client.lrange(recent_key, 0, limit - 1)

            result = []
            for event_json in events:
                try:
                    event_data = json.loads(event_json)
                    result.append(event_data)
                except json.JSONDecodeError:
                    continue

            return result

        except Exception as e:
            logger.error(f"Error getting competition events for {competition_id}: {e}")
            return []

    async def mark_notification_read(self, agent_id: int, notification_id: str):
        """
        Mark an agent notification as read.

        Args:
            agent_id: Agent ID
            notification_id: Notification ID to mark as read
        """
        try:
            notification_key = f'agent:{agent_id}:notification:{notification_id}'
            notification_json = await self.redis_client.get(notification_key)

            if notification_json:
                notification_data = json.loads(notification_json)
                notification_data['read'] = True

                await self.redis_client.setex(
                    notification_key,
                    86400,  # 24 hours TTL
                    json.dumps(notification_data)
                )

                logger.debug(f"Marked notification {notification_id} as read for agent {agent_id}")

        except Exception as e:
            logger.error(f"Error marking notification {notification_id} as read: {e}")

    async def subscribe_to_agent_notifications(self, agent_id: int) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Subscribe to agent-specific notifications.

        Args:
            agent_id: Agent ID to subscribe to

        Yields:
            Notification dictionaries as they are received
        """
        try:
            channel = self.channels['agent_notifications'].format(agent_id=agent_id)
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe(channel)

            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        notification_data = json.loads(message['data'])
                        yield notification_data
                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.error(f"Error subscribing to agent notifications for {agent_id}: {e}")
            raise
        finally:
            if 'pubsub' in locals():
                await pubsub.unsubscribe(channel)
                await pubsub.close()

    async def subscribe_to_system_alerts(self, severity: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Subscribe to system alerts.

        Args:
            severity: Filter by severity level (optional)

        Yields:
            Alert dictionaries as they are received
        """
        try:
            if severity:
                channel = f'notifications:{severity}'
            else:
                channel = self.channels['system_alerts']

            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe(channel)

            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        alert_data = json.loads(message['data'])
                        if alert_data.get('type') == 'system':
                            yield alert_data
                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.error(f"Error subscribing to system alerts: {e}")
            raise
        finally:
            if 'pubsub' in locals():
                await pubsub.unsubscribe(channel)
                await pubsub.close()

    async def subscribe_to_competition_events(self, competition_id: int) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Subscribe to competition-specific events.

        Args:
            competition_id: Competition ID to subscribe to

        Yields:
            Event dictionaries as they are received
        """
        try:
            # Subscribe to general competition events
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe(self.channels['competition_events'])

            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        event_data = json.loads(message['data'])
                        if (event_data.get('type') == 'competition' and
                            event_data.get('competition_id') == competition_id):
                            yield event_data
                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.error(f"Error subscribing to competition events for {competition_id}: {e}")
            raise
        finally:
            if 'pubsub' in locals():
                await pubsub.unsubscribe(self.channels['competition_events'])
                await pubsub.close()

    async def get_unread_count(self, agent_id: int) -> int:
        """
        Get count of unread notifications for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            Number of unread notifications
        """
        try:
            notifications = await self.get_agent_notifications(agent_id, limit=1000)
            unread_count = sum(1 for notif in notifications if not notif.get('read', False))
            return unread_count

        except Exception as e:
            logger.error(f"Error getting unread count for agent {agent_id}: {e}")
            return 0

    async def clear_agent_notifications(self, agent_id: int):
        """
        Clear all notifications for an agent.

        Args:
            agent_id: Agent ID
        """
        try:
            recent_key = f'agent:{agent_id}:notifications:recent'
            await self.redis_client.delete(recent_key)
            logger.info(f"Cleared all notifications for agent {agent_id}")

        except Exception as e:
            logger.error(f"Error clearing notifications for agent {agent_id}: {e}")
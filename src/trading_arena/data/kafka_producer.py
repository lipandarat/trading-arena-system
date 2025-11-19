import asyncio
import json
import logging
from typing import Dict, Any, Optional
import aiokafka
from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)

class KafkaMarketProducer:
    """Kafka producer for high-throughput market data streaming."""

    def __init__(self, bootstrap_servers: str = "kafka:9092", client_id: str = "trading-arena-producer"):
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self.producer: Optional[AIOKafkaProducer] = None
        self.is_running = False

    async def start(self):
        """Start the Kafka producer."""
        if self.is_running:
            logger.warning("Kafka producer already running")
            return

        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                client_id=self.client_id,
                value_serializer=lambda v: json.dumps(v).encode('utf-8') if isinstance(v, (dict, list)) else v,
                key_serializer=lambda k: k.encode('utf-8') if isinstance(k, str) else k,
                acks='all',  # Wait for all replicas to acknowledge
                retries=3,
                batch_size=16384,  # 16KB batches for better throughput
                linger_ms=10,  # Wait up to 10ms to batch messages
                compression_type='gzip'  # Compress messages for bandwidth efficiency
            )

            await self.producer.start()
            self.is_running = True
            logger.info(f"Kafka producer started on {self.bootstrap_servers}")

        except Exception as e:
            logger.error(f"Failed to start Kafka producer: {e}")
            raise

    async def stop(self):
        """Stop the Kafka producer."""
        if not self.is_running or not self.producer:
            return

        try:
            await self.producer.stop()
            self.is_running = False
            logger.info("Kafka producer stopped")

        except Exception as e:
            logger.error(f"Error stopping Kafka producer: {e}")

    async def send_and_wait(self, topic: str, value: bytes, key: Optional[bytes] = None) -> Any:
        """
        Send a message and wait for acknowledgment.

        Args:
            topic: Kafka topic name
            value: Message value (bytes)
            key: Optional message key (bytes)

        Returns:
            RecordMetadata or None if failed
        """
        if not self.is_running or not self.producer:
            raise RuntimeError("Kafka producer not started")

        try:
            return await self.producer.send_and_wait(
                topic=topic,
                value=value,
                key=key
            )

        except Exception as e:
            logger.error(f"Failed to send message to topic {topic}: {e}")
            raise

    async def send(self, topic: str, value: bytes, key: Optional[bytes] = None) -> asyncio.Future:
        """
        Send a message asynchronously without waiting.

        Args:
            topic: Kafka topic name
            value: Message value (bytes)
            key: Optional message key (bytes)

        Returns:
            Future that will complete with RecordMetadata
        """
        if not self.is_running or not self.producer:
            raise RuntimeError("Kafka producer not started")

        try:
            return await self.producer.send(
                topic=topic,
                value=value,
                key=key
            )

        except Exception as e:
            logger.error(f"Failed to send message to topic {topic}: {e}")
            raise

    async def send_market_data(self, symbol: str, market_data: Dict[str, Any]):
        """
        Send market data to symbol-specific topic.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            market_data: Market data dictionary
        """
        topic = f"market-data.{symbol.lower()}"

        try:
            await self.send_and_wait(
                topic=topic,
                value=json.dumps(market_data).encode('utf-8'),
                key=symbol.encode('utf-8')
            )

        except Exception as e:
            logger.error(f"Failed to send market data for {symbol}: {e}")
            raise

    async def send_crowd_intelligence(self, symbol: str, intelligence_data: Dict[str, Any]):
        """
        Send crowd intelligence data to analytics topic.

        Args:
            symbol: Trading symbol (optional, for symbol-specific data)
            intelligence_data: Intelligence analytics data
        """
        topic = f"crowd-intelligence.{symbol.lower() if symbol else 'global'}"

        try:
            await self.send_and_wait(
                topic=topic,
                value=json.dumps(intelligence_data).encode('utf-8'),
                key=symbol.encode('utf-8') if symbol else b'global'
            )

        except Exception as e:
            logger.error(f"Failed to send crowd intelligence data: {e}")
            raise

    async def send_alert(self, alert_type: str, alert_data: Dict[str, Any]):
        """
        Send alert data to notifications topic.

        Args:
            alert_type: Type of alert (e.g., 'risk_violation', 'performance_milestone')
            alert_data: Alert data
        """
        topic = f"alerts.{alert_type}"

        try:
            await self.send_and_wait(
                topic=topic,
                value=json.dumps(alert_data).encode('utf-8'),
                key=alert_type.encode('utf-8')
            )

        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
            raise

    def get_producer_stats(self) -> Dict[str, Any]:
        """Get producer statistics."""
        return {
            'bootstrap_servers': self.bootstrap_servers,
            'client_id': self.client_id,
            'is_running': self.is_running,
            'producer': str(type(self.producer).__name__) if self.producer else None
        }
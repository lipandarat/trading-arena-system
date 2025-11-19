import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import numpy as np

from ..exchanges.binance_client import BinanceFuturesClient
from ..db import get_db_session
from ..models.agent import Agent
from sqlalchemy import select, func

logger = logging.getLogger(__name__)

class TriggerType(Enum):
    VOLATILITY_SPIKE = "volatility_spike"
    VOLUME_SURGE = "volume_surge"
    PRICE_BREAKOUT = "price_breakout"
    TIME_WINDOW = "time_window"
    PARTICIPATION_THRESHOLD = "participation_threshold"

@dataclass
class TriggerEvent:
    competition_type: str
    priority: float
    trigger_type: TriggerType
    parameters: Dict[str, any]
    timestamp: datetime
    expiration: Optional[datetime] = None

class EventTriggerManager:
    def __init__(self, exchange_client: Optional[BinanceFuturesClient] = None):
        self.active_triggers: List[TriggerEvent] = []
        self.exchange_client = exchange_client
        self.trigger_conditions = {
            TriggerType.VOLATILITY_SPIKE: self._check_volatility_spike,
            TriggerType.VOLUME_SURGE: self._check_volume_surge,
            TriggerType.PRICE_BREAKOUT: self._check_price_breakout,
            TriggerType.TIME_WINDOW: self._check_time_window,
            TriggerType.PARTICIPATION_THRESHOLD: self._check_participation_threshold
        }

    async def check_triggers(self) -> List[TriggerEvent]:
        """Check all trigger conditions and return triggered events"""
        triggered_events = []

        # Clean expired triggers
        self._clean_expired_triggers()

        # Check each trigger type
        for trigger_type, check_function in self.trigger_conditions.items():
            try:
                events = await check_function()
                triggered_events.extend(events)
            except Exception as e:
                logger.error(f"Error checking trigger {trigger_type}: {e}")

        return triggered_events

    def _clean_expired_triggers(self):
        """Remove expired trigger events"""
        current_time = datetime.now(timezone.utc)
        self.active_triggers = [
            trigger for trigger in self.active_triggers
            if not trigger.expiration or trigger.expiration > current_time
        ]

    async def _check_volatility_spike(self) -> List[TriggerEvent]:
        """Check for volatility spike triggers using REAL Binance data"""
        try:
            if not self.exchange_client:
                logger.warning("No exchange client available for volatility check")
                return []

            # Fetch real kline data from Binance (last 24 hours, 1h candles)
            klines = await self.exchange_client.client.futures_klines(
                symbol="BTCUSDT",
                interval='1h',
                limit=24
            )

            if not klines or len(klines) < 10:
                logger.warning("Insufficient kline data for volatility calculation")
                return []

            # Extract close prices
            close_prices = [float(kline[4]) for kline in klines]

            # Calculate returns
            returns = np.diff(close_prices) / close_prices[:-1]

            # Calculate volatility (standard deviation of returns, annualized)
            current_volatility = np.std(returns) * np.sqrt(24 * 365)

            logger.debug(f"Current volatility: {current_volatility:.4f}")

            # Trigger if volatility exceeds 5% annualized
            if current_volatility > 0.05:
                return [TriggerEvent(
                    competition_type="volatility_challenge",
                    priority=0.9,
                    trigger_type=TriggerType.VOLATILITY_SPIKE,
                    parameters={
                        'volatility_level': float(current_volatility),
                        'symbol': 'BTCUSDT',
                        'timeframe': '24h'
                    },
                    timestamp=datetime.now(timezone.utc),
                    expiration=datetime.now(timezone.utc) + timedelta(hours=1)
                )]

            return []
        except Exception as e:
            logger.error(f"Failed to check volatility spike trigger: {e}")
            return []

    async def _check_volume_surge(self) -> List[TriggerEvent]:
        """Check for trading volume surge triggers using REAL Binance data"""
        try:
            if not self.exchange_client:
                logger.warning("No exchange client available for volume check")
                return []

            # Fetch recent kline data (last 24 hours, 1h candles)
            klines = await self.exchange_client.client.futures_klines(
                symbol="BTCUSDT",
                interval='1h',
                limit=24
            )

            if not klines or len(klines) < 20:
                logger.warning("Insufficient kline data for volume calculation")
                return []

            # Extract volumes
            volumes = [float(kline[5]) for kline in klines]

            # Current volume (last hour)
            current_volume = volumes[-1]

            # Average volume (previous 20 hours, excluding current)
            avg_volume = np.mean(volumes[-21:-1])

            # Calculate volume ratio
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

            logger.debug(f"Volume ratio: {volume_ratio:.2f}x average")

            # Trigger if volume is 2x higher than average
            if volume_ratio > 2.0:
                return [TriggerEvent(
                    competition_type="volume_sprint",
                    priority=0.8,
                    trigger_type=TriggerType.VOLUME_SURGE,
                    parameters={
                        'volume_ratio': float(volume_ratio),
                        'current_volume': float(current_volume),
                        'avg_volume': float(avg_volume),
                        'symbol': 'BTCUSDT'
                    },
                    timestamp=datetime.now(timezone.utc),
                    expiration=datetime.now(timezone.utc) + timedelta(minutes=30)
                )]

            return []
        except Exception as e:
            logger.error(f"Failed to check volume surge trigger: {e}")
            return []

    async def _check_price_breakout(self) -> List[TriggerEvent]:
        """Check for price breakout triggers using REAL Binance data"""
        try:
            if not self.exchange_client:
                logger.warning("No exchange client available for breakout check")
                return []

            # Fetch recent kline data (last 48 hours, 1h candles)
            klines = await self.exchange_client.client.futures_klines(
                symbol="BTCUSDT",
                interval='1h',
                limit=48
            )

            if not klines or len(klines) < 30:
                logger.warning("Insufficient kline data for breakout calculation")
                return []

            # Extract high/low prices
            highs = [float(kline[2]) for kline in klines]
            lows = [float(kline[3]) for kline in klines]
            closes = [float(kline[4]) for kline in klines]

            # Calculate resistance and support levels (last 40 candles)
            resistance = np.percentile(highs[-40:], 90)
            support = np.percentile(lows[-40:], 10)

            # Current price
            current_price = closes[-1]

            # Detect breakout
            breakout_detected = False
            breakout_type = None
            breakout_strength = 0.0

            # Bullish breakout (price above resistance)
            if current_price > resistance:
                breakout_strength = (current_price - resistance) / resistance
                if breakout_strength > 0.01:  # 1% above resistance
                    breakout_detected = True
                    breakout_type = "bullish"

            # Bearish breakout (price below support)
            elif current_price < support:
                breakout_strength = (support - current_price) / support
                if breakout_strength > 0.01:  # 1% below support
                    breakout_detected = True
                    breakout_type = "bearish"

            logger.debug(
                f"Breakout check - Price: ${current_price:.2f}, "
                f"Support: ${support:.2f}, Resistance: ${resistance:.2f}"
            )

            if breakout_detected:
                return [TriggerEvent(
                    competition_type="breakout_challenge",
                    priority=0.85,
                    trigger_type=TriggerType.PRICE_BREAKOUT,
                    parameters={
                        'breakout_strength': float(breakout_strength),
                        'breakout_type': breakout_type,
                        'current_price': float(current_price),
                        'support': float(support),
                        'resistance': float(resistance),
                        'symbol': 'BTCUSDT'
                    },
                    timestamp=datetime.now(timezone.utc),
                    expiration=datetime.now(timezone.utc) + timedelta(hours=2)
                )]

            return []
        except Exception as e:
            logger.error(f"Failed to check price breakout trigger: {e}")
            return []

    async def _check_time_window(self) -> List[TriggerEvent]:
        """Check for time-based triggers"""
        current_hour = datetime.now(timezone.utc).hour

        # Evening competition window
        if current_hour == 20:  # 8 PM UTC
            return [TriggerEvent(
                competition_type="evening_sprint",
                priority=0.7,
                trigger_type=TriggerType.TIME_WINDOW,
                parameters={'window_hours': 2},
                timestamp=datetime.now(timezone.utc)
            )]

        return []

    async def _check_participation_threshold(self) -> List[TriggerEvent]:
        """Check for participation-based triggers using REAL database query"""
        try:
            # Query active agents from database
            async with get_db_session() as session:
                # Count active agents (status = 'active' and last_active within 24 hours)
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)

                result = await session.execute(
                    select(func.count(Agent.id))
                    .where(
                        Agent.status == 'active',
                        Agent.last_active >= cutoff_time
                    )
                )
                active_agents = result.scalar() or 0

            min_threshold = 30

            logger.debug(f"Active agents: {active_agents}/{min_threshold}")

            # Trigger if participation is below threshold
            if active_agents < min_threshold:
                return [TriggerEvent(
                    competition_type="participation_boost",
                    priority=0.75,
                    trigger_type=TriggerType.PARTICIPATION_THRESHOLD,
                    parameters={
                        'active_agents': active_agents,
                        'min_threshold': min_threshold,
                        'participation_rate': active_agents / min_threshold if min_threshold > 0 else 0
                    },
                    timestamp=datetime.now(timezone.utc),
                    expiration=datetime.now(timezone.utc) + timedelta(hours=3)
                )]

            return []
        except Exception as e:
            logger.error(f"Failed to check participation threshold trigger: {e}")
            return []
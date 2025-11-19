"""
Technical Analysis Helpers for Trading Agents.

Real technical indicators and market analysis tools.
NO SIMULATIONS - Uses actual market data.
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TechnicalIndicators:
    """Container for calculated technical indicators."""
    # Trend Indicators
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    trend: Optional[str] = None  # BULLISH, BEARISH, NEUTRAL

    # Momentum
    rsi: Optional[float] = None
    rsi_signal: Optional[str] = None  # OVERSOLD, OVERBOUGHT, NEUTRAL

    # Volatility
    atr: Optional[float] = None
    volatility_percentile: Optional[float] = None

    # Volume
    volume_ratio: Optional[float] = None  # Current vs average
    volume_trend: Optional[str] = None  # INCREASING, DECREASING

    # Support/Resistance
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    price_position: Optional[str] = None  # NEAR_SUPPORT, NEAR_RESISTANCE, MID_RANGE


class TechnicalAnalyzer:
    """Real technical analysis calculations."""

    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> float:
        """
        Calculate Exponential Moving Average.

        Args:
            prices: List of prices (newest last)
            period: EMA period

        Returns:
            EMA value
        """
        if len(prices) < period:
            return np.mean(prices) if prices else 0.0

        multiplier = 2 / (period + 1)
        ema = np.mean(prices[:period])

        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        """
        Calculate Relative Strength Index.

        Args:
            prices: List of prices (newest last)
            period: RSI period (default 14)

        Returns:
            RSI value (0-100)
        """
        if len(prices) < period + 1:
            return 50.0  # Neutral if not enough data

        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    @staticmethod
    def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """
        Calculate Average True Range (volatility measure).

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of close prices
            period: ATR period

        Returns:
            ATR value
        """
        if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
            return 0.0

        true_ranges = []
        for i in range(1, len(closes)):
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i-1])
            low_close = abs(lows[i] - closes[i-1])
            true_range = max(high_low, high_close, low_close)
            true_ranges.append(true_range)

        if len(true_ranges) < period:
            return np.mean(true_ranges) if true_ranges else 0.0

        atr = np.mean(true_ranges[:period])

        for tr in true_ranges[period:]:
            atr = (atr * (period - 1) + tr) / period

        return atr

    @staticmethod
    def find_support_resistance(prices: List[float], highs: List[float], lows: List[float]) -> tuple:
        """
        Find support and resistance levels using recent price action.

        Args:
            prices: Close prices
            highs: High prices
            lows: Low prices

        Returns:
            Tuple of (support_level, resistance_level)
        """
        if len(prices) < 20:
            return (min(lows) if lows else 0, max(highs) if highs else 0)

        # Use last 50 candles for support/resistance
        recent_lows = lows[-50:]
        recent_highs = highs[-50:]

        # Support: Recent significant low
        support = np.percentile(recent_lows, 25)

        # Resistance: Recent significant high
        resistance = np.percentile(recent_highs, 75)

        return (support, resistance)

    @staticmethod
    def analyze_market(
        closes: List[float],
        highs: List[float],
        lows: List[float],
        volumes: List[float]
    ) -> TechnicalIndicators:
        """
        Perform comprehensive technical analysis.

        Args:
            closes: List of closing prices (newest last)
            highs: List of high prices
            lows: List of low prices
            volumes: List of volumes

        Returns:
            TechnicalIndicators object with all calculated values
        """
        indicators = TechnicalIndicators()

        if len(closes) < 2:
            return indicators

        current_price = closes[-1]

        # Calculate EMAs
        if len(closes) >= 20:
            indicators.ema_20 = TechnicalAnalyzer.calculate_ema(closes, 20)
        if len(closes) >= 50:
            indicators.ema_50 = TechnicalAnalyzer.calculate_ema(closes, 50)

        # Determine trend
        if indicators.ema_20 and indicators.ema_50:
            if indicators.ema_20 > indicators.ema_50 and current_price > indicators.ema_20:
                indicators.trend = "BULLISH"
            elif indicators.ema_20 < indicators.ema_50 and current_price < indicators.ema_20:
                indicators.trend = "BEARISH"
            else:
                indicators.trend = "NEUTRAL"
        elif indicators.ema_20:
            indicators.trend = "BULLISH" if current_price > indicators.ema_20 else "BEARISH"

        # Calculate RSI
        if len(closes) >= 15:
            indicators.rsi = TechnicalAnalyzer.calculate_rsi(closes, 14)
            if indicators.rsi < 30:
                indicators.rsi_signal = "OVERSOLD"
            elif indicators.rsi > 70:
                indicators.rsi_signal = "OVERBOUGHT"
            else:
                indicators.rsi_signal = "NEUTRAL"

        # Calculate ATR
        if len(closes) >= 15:
            indicators.atr = TechnicalAnalyzer.calculate_atr(highs, lows, closes, 14)

            # Volatility percentile (current ATR vs historical)
            if indicators.atr and len(closes) >= 50:
                recent_atrs = []
                for i in range(15, min(len(closes), 50)):
                    atr_val = TechnicalAnalyzer.calculate_atr(
                        highs[:i],
                        lows[:i],
                        closes[:i],
                        14
                    )
                    if atr_val:
                        recent_atrs.append(atr_val)

                if recent_atrs:
                    indicators.volatility_percentile = (
                        sum(1 for atr in recent_atrs if atr < indicators.atr) / len(recent_atrs) * 100
                    )

        # Volume analysis
        if len(volumes) >= 20:
            avg_volume = np.mean(volumes[-20:])
            current_volume = volumes[-1]
            if avg_volume > 0:
                indicators.volume_ratio = current_volume / avg_volume

                # Volume trend
                recent_avg = np.mean(volumes[-5:])
                older_avg = np.mean(volumes[-20:-5])
                if recent_avg > older_avg * 1.2:
                    indicators.volume_trend = "INCREASING"
                elif recent_avg < older_avg * 0.8:
                    indicators.volume_trend = "DECREASING"
                else:
                    indicators.volume_trend = "STABLE"

        # Support/Resistance
        if len(closes) >= 20:
            support, resistance = TechnicalAnalyzer.find_support_resistance(closes, highs, lows)
            indicators.support_level = support
            indicators.resistance_level = resistance

            # Price position
            if resistance and support and resistance > support:
                range_size = resistance - support
                if current_price < support + (range_size * 0.2):
                    indicators.price_position = "NEAR_SUPPORT"
                elif current_price > resistance - (range_size * 0.2):
                    indicators.price_position = "NEAR_RESISTANCE"
                else:
                    indicators.price_position = "MID_RANGE"

        return indicators

    @staticmethod
    def format_analysis_text(symbol: str, current_price: float, indicators: TechnicalIndicators) -> str:
        """
        Format technical analysis into human-readable text for LLM.

        Args:
            symbol: Trading symbol
            current_price: Current price
            indicators: Technical indicators

        Returns:
            Formatted analysis string
        """
        lines = [
            f"Technical Analysis for {symbol}:",
            f"Current Price: ${current_price:,.2f}",
            ""
        ]

        # Trend Analysis
        if indicators.trend:
            lines.append(f"Trend: {indicators.trend}")
            if indicators.ema_20:
                lines.append(f"  EMA(20): ${indicators.ema_20:,.2f}")
            if indicators.ema_50:
                lines.append(f"  EMA(50): ${indicators.ema_50:,.2f}")
            lines.append("")

        # Momentum
        if indicators.rsi:
            lines.append(f"RSI(14): {indicators.rsi:.1f} - {indicators.rsi_signal}")
            lines.append("")

        # Volatility
        if indicators.atr:
            lines.append(f"ATR(14): ${indicators.atr:.2f}")
            if indicators.volatility_percentile:
                lines.append(f"Volatility Percentile: {indicators.volatility_percentile:.0f}%")
            lines.append("")

        # Volume
        if indicators.volume_ratio:
            lines.append(f"Volume: {indicators.volume_ratio:.1f}x average ({indicators.volume_trend})")
            lines.append("")

        # Support/Resistance
        if indicators.support_level and indicators.resistance_level:
            lines.append(f"Support: ${indicators.support_level:,.2f}")
            lines.append(f"Resistance: ${indicators.resistance_level:,.2f}")
            lines.append(f"Position: {indicators.price_position}")

        return "\n".join(lines)

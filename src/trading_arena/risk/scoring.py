"""
Advanced Risk Scoring Algorithms for Autonomous Trading Arena.

Provides sophisticated scoring methodologies beyond basic risk metrics,
including multi-factor scoring, time-weighted performance analysis,
and risk-adjusted benchmarking against peer performance.
"""

import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from trading_arena.models.trading import Trade
from trading_arena.agents.agent_interface import Position

logger = logging.getLogger(__name__)


class ScoringMethod(Enum):
    """Available scoring methodologies."""
    RISK_ADJUSTED = "risk_adjusted"
    CONSERVATIVE = "conservative"
    AGGRESSIVE = "aggressive"
    BALANCED = "balanced"
    PEER_COMPARATIVE = "peer_comparative"


@dataclass
class RiskScoreComponents:
    """Individual components that contribute to overall risk scoring."""
    sharpe_component: float           # Sharpe ratio contribution (0-30)
    sortino_component: float          # Sortino ratio contribution (0-25)
    drawdown_component: float         # Drawdown performance (0-20)
    consistency_component: float      # Win rate consistency (0-15)
    leverage_component: float         # Leverage efficiency (0-10)
    volatility_component: float       # Volatility management (0-10)
    time_component: float            # Time-weighted performance (0-10)
    recovery_component: float        # Drawdown recovery speed (0-10)
    correlation_component: float     # Portfolio correlation management (0-10)


class RiskScorer:
    """
    Advanced risk scoring system with multiple scoring methodologies.

    Provides sophisticated risk assessment capabilities including:
    - Multi-factor scoring with configurable weights
    - Time-weighted performance analysis
    - Peer comparison and relative scoring
    - Behavioral pattern analysis
    - Stress testing and scenario analysis
    """

    def __init__(self, scoring_method: ScoringMethod = ScoringMethod.RISK_ADJUSTED):
        """
        Initialize the Risk Scorer.

        Args:
            scoring_method: Primary scoring methodology to use
        """
        self.scoring_method = scoring_method
        self.default_weights = {
            'sharpe': 0.25,
            'sortino': 0.20,
            'drawdown': 0.20,
            'consistency': 0.15,
            'leverage': 0.10,
            'volatility': 0.10
        }

    def calculate_comprehensive_score(self, trades: List[Trade], positions: List[Position],
                                    current_capital: float, initial_capital: float,
                                    peer_data: Optional[List[Dict]] = None) -> Tuple[float, RiskScoreComponents]:
        """
        Calculate comprehensive risk score with detailed component breakdown.

        Args:
            trades: Historical trade data
            positions: Current positions
            current_capital: Current capital level
            initial_capital: Starting capital
            peer_data: Optional peer performance data for comparison

        Returns:
            Tuple of overall score and score components
        """
        if not trades:
            return 0.0, RiskScoreComponents(0, 0, 0, 0, 0, 0, 0, 0, 0)

        # Calculate base metrics
        returns_data = self._extract_returns(trades, initial_capital)
        returns = returns_data['returns']
        timestamps = returns_data['timestamps']

        # Calculate individual components
        components = self._calculate_score_components(
            returns, timestamps, trades, positions, current_capital, initial_capital
        )

        # Apply scoring methodology
        if self.scoring_method == ScoringMethod.PEER_COMPARATIVE and peer_data:
            overall_score = self._peer_comparative_score(components, peer_data)
        else:
            overall_score = self._weighted_score(components)

        return overall_score, components

    def _extract_returns(self, trades: List[Trade], initial_capital: float) -> Dict:
        """Extract return series from trade data."""
        trade_data = []
        for trade in trades:
            if trade.pnl is not None and initial_capital > 0:
                trade_data.append({
                    'timestamp': trade.execution_timestamp or trade.signal_timestamp,
                    'pnl': float(trade.pnl),
                    'return': float(trade.pnl) / initial_capital
                })

        if not trade_data:
            return {'returns': np.array([]), 'timestamps': []}

        df = pd.DataFrame(trade_data)
        df = df.sort_values('timestamp')

        return {
            'returns': df['return'].values,
            'timestamps': df['timestamp'].tolist()
        }

    def _calculate_score_components(self, returns: np.ndarray, timestamps: List[datetime],
                                  trades: List[Trade], positions: List[Position],
                                  current_capital: float, initial_capital: float) -> RiskScoreComponents:
        """Calculate individual scoring components."""
        if len(returns) == 0:
            return RiskScoreComponents(0, 0, 0, 0, 0, 0, 0, 0, 0)

        # Sharpe ratio component
        sharpe_component = self._calculate_sharpe_component(returns)

        # Sortino ratio component
        sortino_component = self._calculate_sortino_component(returns)

        # Drawdown component
        drawdown_component = self._calculate_drawdown_component(returns)

        # Consistency component
        consistency_component = self._calculate_consistency_component(returns)

        # Leverage efficiency component
        leverage_component = self._calculate_leverage_component(trades, positions, current_capital)

        # Volatility management component
        volatility_component = self._calculate_volatility_component(returns)

        # Time-weighted performance component
        time_component = self._calculate_time_component(timestamps, returns)

        # Recovery component
        recovery_component = self._calculate_recovery_component(returns)

        # Correlation component
        correlation_component = self._calculate_correlation_component(returns)

        return RiskScoreComponents(
            sharpe_component=sharpe_component,
            sortino_component=sortino_component,
            drawdown_component=drawdown_component,
            consistency_component=consistency_component,
            leverage_component=leverage_component,
            volatility_component=volatility_component,
            time_component=time_component,
            recovery_component=recovery_component,
            correlation_component=correlation_component
        )

    def _calculate_sharpe_component(self, returns: np.ndarray) -> float:
        """Calculate Sharpe ratio component score."""
        if len(returns) <= 1 or np.std(returns) == 0:
            return 0

        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)
        # Scale to 0-30 points
        return min(30, max(0, sharpe * 10))

    def _calculate_sortino_component(self, returns: np.ndarray) -> float:
        """Calculate Sortino ratio component score."""
        if len(returns) <= 1:
            return 0

        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0 or np.std(downside_returns) == 0:
            return 0

        sortino = np.mean(returns) / np.std(downside_returns) * np.sqrt(252)
        # Scale to 0-25 points
        return min(25, max(0, sortino * 8))

    def _calculate_drawdown_component(self, returns: np.ndarray) -> float:
        """Calculate drawdown performance component score."""
        if len(returns) == 0:
            return 0

        cumulative = np.cumprod(1 + returns)
        peak = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - peak) / peak
        max_drawdown = np.min(drawdown)

        # Score: lower drawdown = higher score (max 20 points)
        return max(0, 20 - abs(max_drawdown) * 100)

    def _calculate_consistency_component(self, returns: np.ndarray) -> float:
        """Calculate consistency/win rate component score."""
        if len(returns) == 0:
            return 0

        positive_returns = np.sum(returns > 0)
        consistency = positive_returns / len(returns)

        # Scale to 0-15 points
        return consistency * 15

    def _calculate_leverage_component(self, trades: List[Trade], positions: List[Position],
                                    current_capital: float) -> float:
        """Calculate leverage efficiency component score."""
        if current_capital <= 0:
            return 0

        # Calculate average leverage from trades
        trade_leverages = []
        for trade in trades:
            if trade.leverage and trade.leverage > 0:
                trade_leverages.append(trade.leverage)

        if not trade_leverages:
            return 0

        avg_leverage = np.mean(trade_leverages)

        # Optimal leverage is around 2-3x
        if 2 <= avg_leverage <= 3:
            return 10
        elif 1 <= avg_leverage < 2:
            return avg_leverage * 5  # Linear scaling
        elif 3 < avg_leverage <= 5:
            return 15 - avg_leverage * 2  # Penalty for excessive leverage
        else:
            return max(0, 5 - avg_leverage)  # Heavy penalty for very high leverage

    def _calculate_volatility_component(self, returns: np.ndarray) -> float:
        """Calculate volatility management component score."""
        if len(returns) <= 1:
            return 0

        volatility = np.std(returns) * np.sqrt(252)

        # Optimal volatility is around 15-25%
        if 0.15 <= volatility <= 0.25:
            return 10
        elif volatility < 0.15:
            return volatility * 40  # Reward for low volatility
        elif volatility <= 0.5:
            return 10 - (volatility - 0.25) * 40  # Penalty for high volatility
        else:
            return 0  # No score for very high volatility

    def _calculate_time_component(self, timestamps: List[datetime], returns: np.ndarray) -> float:
        """Calculate time-weighted performance component."""
        if len(timestamps) != len(returns) or len(timestamps) == 0:
            return 0

        # Calculate time-weighted return
        if len(timestamps) > 1:
            time_span = (timestamps[-1] - timestamps[0]).total_seconds() / (365.25 * 24 * 3600)
            total_return = np.prod(1 + returns) - 1

            if time_span > 0:
                time_weighted_return = (1 + total_return) ** (1 / time_span) - 1
                # Scale to 0-10 points
                return min(10, max(0, time_weighted_return * 200))

        return 0

    def _calculate_recovery_component(self, returns: np.ndarray) -> float:
        """Calculate drawdown recovery speed component."""
        if len(returns) < 10:
            return 0

        cumulative = np.cumprod(1 + returns)
        peak = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - peak) / peak

        # Find drawdown periods and recovery times
        in_drawdown = drawdown < -0.05  # 5% drawdown threshold
        recovery_times = []

        if np.any(in_drawdown):
            # Find drawdown starts and ends
            drawdown_starts = np.where(np.diff(in_drawdown.astype(int)) == 1)[0] + 1
            drawdown_ends = np.where(np.diff(in_drawdown.astype(int)) == -1)[0] + 1

            for start, end in zip(drawdown_starts, drawdown_ends):
                if end > start:
                    recovery_times.append(end - start)

            if recovery_times:
                avg_recovery_time = np.mean(recovery_times)
                # Faster recovery = higher score (inverse relationship)
                return min(10, 10 / (1 + avg_recovery_time))

        return 10  # No significant drawdowns

    def _calculate_correlation_component(self, returns: np.ndarray) -> float:
        """Calculate correlation management component (placeholder)."""
        # This would normally calculate correlation with market/benchmark
        # For now, reward low auto-correlation (diversified trading)
        if len(returns) < 10:
            return 0

        # Calculate lag-1 autocorrelation
        autocorr = np.corrcoef(returns[:-1], returns[1:])[0, 1]

        # Lower autocorrelation = better diversification
        if not np.isnan(autocorr):
            return min(10, max(0, (1 - abs(autocorr)) * 10))

        return 5  # Default score

    def _weighted_score(self, components: RiskScoreComponents) -> float:
        """Calculate weighted overall score from components."""
        # Maximum possible score is 130, scale to 0-100
        total = (
            components.sharpe_component +
            components.sortino_component +
            components.drawdown_component +
            components.consistency_component +
            components.leverage_component +
            components.volatility_component +
            components.time_component +
            components.recovery_component +
            components.correlation_component
        )

        return min(100, (total / 130) * 100)

    def _peer_comparative_score(self, components: RiskScoreComponents,
                              peer_data: List[Dict]) -> float:
        """Calculate peer-comparative score."""
        # This would normally compare against peer performance
        # For now, apply a modest boost to base score
        base_score = self._weighted_score(components)

        # Simple percentile-based adjustment
        peer_scores = [p.get('score', 50) for p in peer_data]
        if peer_scores:
            percentile = (base_score > np.array(peer_scores)).mean()
            # Boost based on relative performance
            return min(100, base_score + percentile * 20)

        return base_score

    def calculate_stress_test_score(self, trades: List[Trade],
                                  stress_scenarios: List[Dict]) -> float:
        """
        Calculate stress test resilience score.

        Args:
            trades: Historical trade data
            stress_scenarios: List of stress scenario configurations

        Returns:
            Stress test resilience score (0-100)
        """
        if not trades:
            return 0

        # Extract return series
        returns_data = self._extract_returns(trades, 1000.0)  # Assume 1000 initial capital
        returns = returns_data['returns']

        if len(returns) == 0:
            return 0

        stress_scores = []

        for scenario in stress_scenarios:
            scenario_score = self._apply_stress_scenario(returns, scenario)
            stress_scores.append(scenario_score)

        if stress_scores:
            return np.mean(stress_scores)

        return 0

    def _apply_stress_scenario(self, returns: np.ndarray, scenario: Dict) -> float:
        """Apply a single stress scenario to return series."""
        scenario_type = scenario.get('type', 'volatility_spike')

        if scenario_type == 'volatility_spike':
            # Simulate volatility spike
            multiplier = scenario.get('volatility_multiplier', 2.0)
            stressed_returns = returns * multiplier

        elif scenario_type == 'market_crash':
            # Simulate market crash
            crash_magnitude = scenario.get('crash_magnitude', -0.20)
            crash_position = scenario.get('crash_position', 0.5)  # Position in series

            stressed_returns = returns.copy()
            if len(stressed_returns) > int(crash_position * len(stressed_returns)):
                stressed_returns[int(crash_position * len(stressed_returns))] = crash_magnitude

        else:
            stressed_returns = returns

        # Calculate resilience based on stressed returns
        if len(stressed_returns) > 1:
            cumulative = np.cumprod(1 + stressed_returns)
            peak = np.maximum.accumulate(cumulative)
            drawdown = (cumulative - peak) / peak
            max_drawdown = np.min(drawdown)

            # Higher resilience = less severe drawdown under stress
            return max(0, 100 - abs(max_drawdown) * 500)

        return 0
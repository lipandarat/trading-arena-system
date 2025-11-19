"""
Risk Management Engine for Autonomous Trading Arena.

Comprehensive risk assessment and position sizing system that calculates
risk metrics, enforces risk limits, and optimizes position sizes based on
agent risk profiles and market conditions.

Key Features:
- Sharpe ratio, Sortino ratio, maximum drawdown calculations
- Value at Risk (VaR) and volatility measurements
- Risk-adjusted return scoring with overall risk score (0-100)
- Leverage usage monitoring and capital preservation checks
- Position sizing based on risk per trade (default 2%)
- Agent risk profiles (conservative, moderate, aggressive)
- Risk limit violation detection and warning systems
"""

import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from trading_arena.models.trading import Trade
from trading_arena.agents.agent_interface import Position

logger = logging.getLogger(__name__)


@dataclass
class RiskMetrics:
    """
    Comprehensive risk metrics for trading agent performance assessment.

    Contains all calculated risk metrics used for agent evaluation and
    risk management decision making.
    """
    sharpe_ratio: float              # Risk-adjusted return measure
    sortino_ratio: float             # Downside risk-adjusted return
    max_drawdown: float              # Maximum peak-to-trough decline
    current_drawdown: float          # Current drawdown from peak
    volatility: float                # Annualized return volatility
    var_95: float                    # Value at Risk at 95% confidence
    leverage_usage: float            # Current leverage utilization
    consistency_score: float         # % of profitable trading periods
    risk_score: float                # Overall risk score (0-100, higher better)


class RiskManager:
    """
    Comprehensive risk management engine for autonomous trading agents.

    Provides risk assessment, position sizing, and limit monitoring
    capabilities to ensure agents operate within defined risk parameters
    while optimizing for risk-adjusted returns.
    """

    def __init__(self, lookback_days: int = 30):
        """
        Initialize the Risk Manager.

        Args:
            lookback_days: Number of days to look back for risk calculations
        """
        self.lookback_days = lookback_days
        self.min_trades_for_scoring = 20

    def calculate_risk_metrics(self, trades: List[Trade], positions: List[Position],
                             current_capital: float, initial_capital: float) -> RiskMetrics:
        """
        Calculate comprehensive risk metrics from trading history.

        Args:
            trades: List of executed trades
            positions: List of current positions
            current_capital: Current account capital
            initial_capital: Starting account capital

        Returns:
            RiskMetrics object containing all calculated risk measures
        """
        if not trades:
            logger.debug("No trades provided for risk calculation")
            return RiskMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0)

        # Convert trades to DataFrame for analysis
        trade_data = []
        for trade in trades:
            if trade.pnl is not None and initial_capital > 0:
                trade_data.append({
                    'timestamp': trade.execution_timestamp or trade.signal_timestamp,
                    'pnl': float(trade.pnl),
                    'return': float(trade.pnl) / initial_capital
                })

        if not trade_data:
            logger.warning("No valid trade data for risk calculation")
            return RiskMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0)

        df = pd.DataFrame(trade_data)
        df = df.sort_values('timestamp')
        df['cumulative'] = (1 + df['return']).cumprod()

        # Extract return series for calculations
        returns = df['return'].values
        cumulative_returns = df['cumulative'].values

        # Calculate Sharpe Ratio (annualized)
        if len(returns) > 1:
            std_returns = np.std(returns)
            if std_returns > 1e-10:  # More robust than != 0
                sharpe_ratio = np.mean(returns) / std_returns * np.sqrt(252)
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0

        # Calculate Sortino Ratio (downside deviation only)
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 1:
            std_downside = np.std(downside_returns)
            if std_downside > 1e-10:  # More robust than != 0
                sortino_ratio = np.mean(returns) / std_downside * np.sqrt(252)
            else:
                sortino_ratio = 0
        else:
            sortino_ratio = 0

        # Calculate Maximum and Current Drawdown
        peak = np.maximum.accumulate(cumulative_returns)
        # Prevent division by zero
        drawdown = np.where(peak > 1e-10, (cumulative_returns - peak) / peak, 0)
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0
        current_drawdown = drawdown[-1] if len(drawdown) > 0 else 0

        # Calculate Volatility (annualized)
        volatility = np.std(returns) * np.sqrt(252) if len(returns) > 1 else 0

        # Calculate Value at Risk (95% confidence)
        if len(returns) > 1:
            var_95 = np.percentile(returns, 5)
        else:
            var_95 = 0

        # Calculate Leverage Usage from current positions
        total_exposure = sum(abs(pos.size * pos.mark_price) for pos in positions if pos.size and pos.mark_price)
        leverage_usage = total_exposure / current_capital if current_capital > 1e-10 else 0

        # Calculate Consistency Score (percentage of positive returns)
        positive_returns = len(returns[returns > 0])
        consistency_score = positive_returns / len(returns) if len(returns) > 0 else 0

        # Calculate Overall Risk Score (0-100, higher is better)
        risk_score = self._calculate_risk_score(
            sharpe_ratio, sortino_ratio, max_drawdown, volatility,
            consistency_score, leverage_usage
        )

        return RiskMetrics(
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=abs(max_drawdown),
            current_drawdown=abs(current_drawdown),
            volatility=volatility,
            var_95=abs(var_95),
            leverage_usage=leverage_usage,
            consistency_score=consistency_score,
            risk_score=risk_score
        )

    def _calculate_risk_score(self, sharpe: float, sortino: float, max_dd: float,
                            vol: float, consistency: float, leverage: float) -> float:
        """
        Calculate overall risk score (0-100) combining multiple risk factors.

        Scoring methodology:
        - Sharpe ratio: max 30 points (10 points per unit Sharpe)
        - Sortino ratio: max 25 points (8 points per unit Sortino)
        - Drawdown: max 20 points (lower drawdown = higher score)
        - Consistency: max 15 points (percentage of profitable periods)
        - Penalties: excessive leverage and volatility reduce score

        Args:
            sharpe: Sharpe ratio
            sortino: Sortino ratio
            max_dd: Maximum drawdown (absolute value)
            vol: Volatility
            consistency: Consistency score (0-1)
            leverage: Current leverage usage

        Returns:
            Overall risk score between 0 and 100
        """
        # Sharpe ratio score (max 30 points)
        sharpe_score = min(30, max(0, sharpe * 12))

        # Sortino ratio score (max 25 points)
        sortino_score = min(25, max(0, sortino * 10))

        # Drawdown score (max 20 points, lower drawdown = higher score)
        drawdown_score = max(0, 20 - max_dd * 66.67)  # More lenient scaling

        # Consistency score (max 15 points)
        consistency_score = consistency * 15

        # Leverage penalty (excessive leverage reduces score)
        leverage_penalty = 0
        if leverage > 3:
            leverage_penalty = min(10, max(0, (leverage - 3) * 2))

        # Volatility penalty (excessive volatility reduces score)
        vol_penalty = 0
        if vol > 0.5:
            vol_penalty = min(10, max(0, (vol - 0.5) * 10))

        # Calculate total score
        base_score = sharpe_score + sortino_score + drawdown_score + consistency_score
        total_score = max(0, base_score - leverage_penalty - vol_penalty)

        return min(100, total_score)

    def check_risk_limits(self, agent_config: Dict, risk_metrics: RiskMetrics,
                         current_capital: float, initial_capital: float) -> Dict:
        """
        Check if agent is within configured risk limits.

        Generates warnings and violations for risk limit breaches.

        Args:
            agent_config: Agent configuration with risk limits
            risk_metrics: Current risk metrics
            current_capital: Current account capital
            initial_capital: Starting account capital

        Returns:
            Dictionary with warnings, violations, and compliance status
        """
        warnings = []
        violations = []

        # Check maximum drawdown limit
        max_allowed_drawdown = agent_config.get('max_drawdown', 0.30)
        if risk_metrics.current_drawdown > max_allowed_drawdown:
            violations.append(
                f"Drawdown {risk_metrics.current_drawdown:.1%} exceeds limit {max_allowed_drawdown:.1%}"
            )
        elif risk_metrics.current_drawdown > max_allowed_drawdown * 0.8:
            warnings.append(
                f"Drawdown approaching limit: {risk_metrics.current_drawdown:.1%}"
            )

        # Check leverage usage limit
        max_leverage = agent_config.get('max_leverage', 5.0)
        if risk_metrics.leverage_usage > max_leverage:
            violations.append(
                f"Leverage {risk_metrics.leverage_usage:.1f}x exceeds limit {max_leverage}x"
            )
        elif risk_metrics.leverage_usage > max_leverage * 0.8:
            warnings.append(
                f"Leverage approaching limit: {risk_metrics.leverage_usage:.1f}x"
            )

        # Check capital preservation
        min_capital_ratio = agent_config.get('min_capital_ratio', 0.7)
        capital_ratio = current_capital / initial_capital if initial_capital > 0 else 1.0
        if capital_ratio < min_capital_ratio:
            violations.append(
                f"Capital {capital_ratio:.1%} below minimum {min_capital_ratio:.1%}"
            )

        return {
            'warnings': warnings,
            'violations': violations,
            'is_compliant': len(violations) == 0,
            'capital_ratio': capital_ratio,
            'risk_score': risk_metrics.risk_score
        }

    def calculate_position_size(self, agent_config: Dict, market_data: Dict,
                              current_capital: float, risk_per_trade: float = 0.02) -> float:
        """
        Calculate optimal position size based on risk management principles.

        Methodology:
        - Base position from risk per trade (default 2% of capital)
        - Risk multiplier based on agent's risk profile
        - Volatility adjustment for market conditions
        - Maximum position size constraints

        Args:
            agent_config: Agent configuration with risk parameters
            market_data: Market data dictionary with price and volatility
            current_capital: Current available capital
            risk_per_trade: Risk percentage per trade (default 2%)

        Returns:
            Calculated position size in base units
        """
        # Validate input
        entry_price = market_data.get('price', 0)
        if entry_price <= 0 or entry_price is None:
            logger.warning("Invalid entry price for position sizing")
            return 0

        if current_capital <= 0 or current_capital is None:
            logger.warning("Invalid current capital for position sizing")
            return 0

        # Calculate base risk amount
        risk_amount = current_capital * risk_per_trade

        # Apply risk profile multiplier
        risk_profile = agent_config.get('risk_profile', 'moderate').lower()
        risk_multiplier = {
            'conservative': 0.5,
            'moderate': 1.0,
            'aggressive': 1.5
        }.get(risk_profile, 1.0)  # Default to moderate for unknown profiles

        # Apply market volatility adjustment
        volatility_factor = 1.0
        market_volatility = market_data.get('volatility', 0)
        if market_volatility > 0.05:  # High volatility market
            volatility_factor = 0.7
            logger.debug(f"Applied high volatility factor: {volatility_factor}")

        # Calculate base position size
        position_size = (risk_amount * risk_multiplier * volatility_factor) / entry_price

        # Apply maximum position size constraint
        max_position_ratio = agent_config.get('max_position_ratio', 0.1)
        max_position = (current_capital * max_position_ratio) / entry_price
        final_position_size = min(position_size, max_position)

        logger.debug(
            f"Position sizing: risk_amount={risk_amount:.2f}, "
            f"risk_multiplier={risk_multiplier}, volatility_factor={volatility_factor}, "
            f"base_size={position_size:.6f}, max_allowed={max_position:.6f}, "
            f"final_size={final_position_size:.6f}"
        )

        return final_position_size

    def get_risk_profile_config(self, risk_profile: str) -> Dict:
        """
        Get default configuration for a risk profile.

        Args:
            risk_profile: Risk profile name (conservative, moderate, aggressive)

        Returns:
            Dictionary with default configuration parameters
        """
        profiles = {
            'conservative': {
                'max_leverage': 3.0,
                'max_drawdown': 0.15,
                'max_position_ratio': 0.05,
                'risk_per_trade': 0.01,
                'min_capital_ratio': 0.8
            },
            'moderate': {
                'max_leverage': 5.0,
                'max_drawdown': 0.30,
                'max_position_ratio': 0.10,
                'risk_per_trade': 0.02,
                'min_capital_ratio': 0.7
            },
            'aggressive': {
                'max_leverage': 10.0,
                'max_drawdown': 0.50,
                'max_position_ratio': 0.20,
                'risk_per_trade': 0.03,
                'min_capital_ratio': 0.5
            }
        }

        return profiles.get(risk_profile.lower(), profiles['moderate'])

    def validate_risk_configuration(self, config: Dict) -> List[str]:
        """
        Validate risk configuration parameters.

        Args:
            config: Risk configuration dictionary

        Returns:
            List of validation error messages
        """
        errors = []

        # Validate leverage limits
        max_leverage = config.get('max_leverage', 5.0)
        if max_leverage <= 0 or max_leverage > 50:
            errors.append("max_leverage must be between 0 and 50")

        # Validate drawdown limits
        max_drawdown = config.get('max_drawdown', 0.30)
        if max_drawdown <= 0 or max_drawdown > 1:
            errors.append("max_drawdown must be between 0 and 1")

        # Validate position size limits
        max_position_ratio = config.get('max_position_ratio', 0.1)
        if max_position_ratio <= 0 or max_position_ratio > 1:
            errors.append("max_position_ratio must be between 0 and 1")

        # Validate risk per trade
        risk_per_trade = config.get('risk_per_trade', 0.02)
        if risk_per_trade <= 0 or risk_per_trade > 0.1:
            errors.append("risk_per_trade must be between 0 and 0.1")

        # Validate capital ratio
        min_capital_ratio = config.get('min_capital_ratio', 0.7)
        if min_capital_ratio <= 0 or min_capital_ratio > 1:
            errors.append("min_capital_ratio must be between 0 and 1")

        return errors
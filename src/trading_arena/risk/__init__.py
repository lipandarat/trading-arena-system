"""
Risk Management Module for Autonomous Trading Arena.

Provides comprehensive risk assessment, position sizing, and risk limit monitoring
for autonomous trading agents. This module implements:

- Risk metrics calculation (Sharpe ratio, Sortino ratio, maximum drawdown, VaR)
- Risk-adjusted return scoring and overall risk scoring (0-100)
- Position sizing based on risk profiles and per-trade risk limits
- Risk limit violation detection and warning systems
- Leverage usage monitoring and capital preservation checks
- Agent-specific risk profiles (conservative, moderate, aggressive)

The risk management engine ensures agents operate within predefined risk
parameters while optimizing for risk-adjusted returns.
"""

from .manager import RiskManager, RiskMetrics
from .scoring import RiskScorer, RiskScoreComponents, ScoringMethod

__all__ = [
    "RiskManager",
    "RiskMetrics",
    "RiskScorer",
    "RiskScoreComponents",
    "ScoringMethod"
]
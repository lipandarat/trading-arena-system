"""
Agent Runtime Environment for Autonomous Futures Trading Arena.

This package provides the core infrastructure for running autonomous trading agents,
including:

- AgentInterface: Abstract base class for trading agents
- AgentRuntime: Runtime environment for managing agent execution
- Market data structures and trading signals
- Position monitoring and risk management integration

The runtime environment handles:
- Real-time market data fetching from Binance
- Trading signal execution with proper position sizing
- Risk management and position monitoring
- Async task management for scalable agent deployment
"""

from .agent_interface import AgentInterface, MarketData, Position, TradingSignal
from .runtime import AgentRuntime

__all__ = [
    "AgentInterface",
    "MarketData",
    "Position",
    "TradingSignal",
    "AgentRuntime"
]
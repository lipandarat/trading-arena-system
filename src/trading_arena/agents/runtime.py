"""
Agent Runtime Environment for Autonomous Trading.

Provides the core runtime environment for executing autonomous trading agents.
Handles market data fetching, signal execution, position monitoring,
and async task management for scalable agent deployment.
"""

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime

from .agent_interface import AgentInterface, MarketData, Position, TradingSignal
from ..exchanges.binance_client import BinanceFuturesClient

logger = logging.getLogger(__name__)


class AgentRuntime:
    """
    Runtime environment for managing autonomous trading agent execution.

    The runtime handles all the infrastructure concerns required for agents
    to operate autonomously:

    - Real-time market data fetching and caching
    - Trading signal execution with proper position sizing
    - Position monitoring and risk management
    - Async task coordination and error handling
    - Integration with Binance Futures API

    Agents can focus purely on their trading strategy while the runtime
    handles all the operational details.
    """

    def __init__(self, agent: AgentInterface, exchange_client: BinanceFuturesClient):
        """
        Initialize the agent runtime.

        Args:
            agent: The trading agent to run
            exchange_client: Exchange client for market data and order execution
        """
        self.agent = agent
        self.exchange = exchange_client
        self.is_running = False
        self.market_data_cache: Dict[str, MarketData] = {}
        self._tasks: List[asyncio.Task] = []
        self.logger = logging.getLogger(f"runtime.{agent.agent_id}")

    async def start(self, symbols: List[str], update_interval: int = 60):
        """
        Start the agent trading loop.

        Launches concurrent tasks for market data fetching, trading decisions,
        and position monitoring. Runs until stop() is called.

        Args:
            symbols: List of trading symbols to monitor
            update_interval: Market data update interval in seconds (default: 60)
        """
        if self.is_running:
            self.logger.warning("Runtime is already running")
            return

        self.is_running = True
        self.logger.info(f"Starting agent {self.agent.agent_id} with symbols: {symbols}")

        # Create and start concurrent tasks
        tasks = [
            self._market_data_loop(symbols, update_interval),
            self._trading_loop(),
            self._position_monitoring_loop()
        ]

        try:
            self._tasks = [asyncio.create_task(task) for task in tasks]
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except Exception as e:
            self.logger.error(f"Runtime error: {e}")
            raise
        finally:
            await self._cleanup_tasks()

    async def stop(self):
        """
        Stop the agent gracefully.

        Signals all running tasks to stop and waits for them to complete.
        Ensures clean shutdown without orphaned tasks.
        """
        if not self.is_running:
            return

        self.logger.info(f"Stopping agent {self.agent.agent_id}")
        self.is_running = False

        # Cancel all running tasks
        await self._cleanup_tasks()

        # Wait a moment for cleanup
        await asyncio.sleep(0.1)

    async def _cleanup_tasks(self):
        """Clean up running tasks."""
        for task in self._tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._tasks.clear()

    async def _market_data_loop(self, symbols: List[str], interval: int):
        """
        Continuously fetch market data for monitored symbols.

        Fetches OHLCV data and funding rates from the exchange,
        updating the market data cache for agent analysis.

        Args:
            symbols: Trading symbols to monitor
            interval: Update interval in seconds
        """
        self.logger.info(f"Starting market data loop for {symbols}")

        while self.is_running:
            try:
                for symbol in symbols:
                    if not self.is_running:
                        break

                    # Fetch klines (OHLCV data)
                    klines = await self.exchange.client.futures_klines(
                        symbol=symbol,
                        interval='1m',
                        limit=1
                    )

                    # Fetch funding rate
                    funding_rate_data = await self.exchange.client.futures_funding_rate(
                        symbol=symbol,
                        limit=1
                    )

                    if klines:
                        latest = klines[0]
                        funding_rate = (
                            float(funding_rate_data[0]['fundingRate'])
                            if funding_rate_data
                            else None
                        )

                        market_data = MarketData(
                            symbol=symbol,
                            timestamp=datetime.fromtimestamp(latest[0] / 1000),
                            open_price=float(latest[1]),
                            high_price=float(latest[2]),
                            low_price=float(latest[3]),
                            close_price=float(latest[4]),
                            volume=float(latest[5]),
                            funding_rate=funding_rate
                        )

                        self.market_data_cache[symbol] = market_data
                        self.logger.debug(f"Updated market data for {symbol}")

                await asyncio.sleep(interval)

            except Exception as e:
                self.logger.error(f"Error in market data loop: {e}")
                await asyncio.sleep(5)  # Brief pause on error

    async def _trading_loop(self):
        """
        Main trading decision loop.

        Periodically calls the agent to analyze market data and execute
        any generated trading signals. Runs independently of market data
        updates to allow for different analysis frequencies.
        """
        self.logger.info("Starting trading decision loop")

        while self.is_running:
            try:
                if self.market_data_cache:
                    # Get current market data
                    market_data_list = list(self.market_data_cache.values())

                    # Ask agent to analyze and generate signals
                    signals = await self.agent.analyze_market(market_data_list)

                    # Store signals for reference
                    self.agent.last_signals.update(signals)

                    # Execute valid signals
                    for symbol, signal in signals.items():
                        if self.is_running and signal.action in ['BUY', 'SELL']:
                            await self._execute_signal(symbol, signal)

                await asyncio.sleep(30)  # Trading decision frequency

            except Exception as e:
                self.logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(10)  # Brief pause on error

    async def _position_monitoring_loop(self):
        """
        Monitor existing positions for risk management.

        Continuously monitors open positions and provides them to the agent
        for risk management decisions. Handles stop loss, take profit,
        and position size adjustments.
        """
        self.logger.info("Starting position monitoring loop")

        while self.is_running:
            try:
                # Get current positions from exchange
                exchange_positions = await self.exchange.get_open_positions()

                if exchange_positions:
                    # Convert exchange positions to Position objects
                    position_objects = []
                    for pos in exchange_positions:
                        if float(pos['positionAmt']) != 0:
                            position_obj = Position(
                                symbol=pos['symbol'],
                                side='LONG' if float(pos['positionAmt']) > 0 else 'SHORT',
                                size=abs(float(pos['positionAmt'])),
                                entry_price=float(pos['entryPrice']),
                                mark_price=float(pos['markPrice']),
                                unrealized_pnl=float(pos['unRealizedProfit']),
                                percentage_pnl=float(pos['percentage'])
                            )
                            position_objects.append(position_obj)

                            # Update agent's position tracking
                            self.agent.update_position(
                                pos['symbol'],
                                {
                                    'side': position_obj.side,
                                    'size': position_obj.size,
                                    'entry_price': position_obj.entry_price,
                                    'pnl': position_obj.unrealized_pnl
                                }
                            )

                    # Ask agent to manage risk
                    risk_signals = await self.agent.manage_risk(position_objects)

                    # Execute risk management signals
                    for signal in risk_signals:
                        if self.is_running and signal.action in ['SELL', 'BUY']:
                            await self._execute_signal(signal.symbol, signal)

                await asyncio.sleep(10)  # Check positions frequently

            except Exception as e:
                self.logger.error(f"Error in position monitoring: {e}")
                await asyncio.sleep(5)  # Brief pause on error

    async def _execute_signal(self, symbol: str, signal: TradingSignal):
        """
        Execute a trading signal.

        Handles all aspects of signal execution including leverage setting,
        position sizing, order placement, and agent notification.

        Args:
            symbol: Trading symbol
            signal: Trading signal to execute
        """
        try:
            self.logger.info(f"Executing {signal.action} signal for {symbol}")

            # Set leverage if specified
            if signal.leverage:
                await self.exchange.set_leverage(symbol, signal.leverage)

            # Calculate position size if not specified
            quantity = signal.quantity
            if quantity is None or quantity <= 0:
                quantity = await self._calculate_position_size(symbol, signal)

            if quantity > 0:
                side = 'BUY' if signal.action == 'BUY' else 'SELL'

                # Place market order
                order = await self.exchange.place_market_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity
                )

                # Notify agent of fill
                await self.agent.handle_fill(order)

                # Log the decision for audit trail
                await self.agent.log_decision(signal, {
                    'market_data': self.market_data_cache.get(symbol),
                    'positions': self.agent.get_position(symbol),
                    'account_balance': await self._get_available_balance(),
                    'timestamp': datetime.now(),
                    'order_result': order
                })

                self.logger.info(f"Executed {signal.action} order: {order.get('orderId')}")

            else:
                self.logger.warning(f"Calculated quantity is 0 for {symbol}, skipping order")

        except Exception as e:
            self.logger.error(f"Failed to execute signal for {symbol}: {e}")
            # Even failed execution should be logged
            await self.agent.log_decision(signal, {
                'error': str(e),
                'timestamp': datetime.now(),
                'execution_failed': True
            })

    async def _calculate_position_size(self, symbol: str, signal: TradingSignal) -> float:
        """
        Calculate optimal position size based on risk management.

        Implements position sizing based on account balance and risk per trade.
        Uses a 2% risk per trade default with adjustments based on agent config.

        Args:
            symbol: Trading symbol
            signal: Trading signal (may contain sizing hints)

        Returns:
            Calculated position size in base currency units
        """
        try:
            # Get account info
            account = await self.exchange.get_account_info()
            available_balance = float(account['availableBalance'])

            # Risk 2% of available balance per trade (configurable)
            risk_per_trade = self.agent.config.get('risk_per_trade', 0.02)
            risk_amount = available_balance * risk_per_trade

            # Get current price from market data cache
            if symbol not in self.market_data_cache:
                self.logger.warning(f"No market data for {symbol}, using conservative sizing")
                return 0.0

            current_price = self.market_data_cache[symbol].close_price
            if current_price <= 0:
                return 0.0

            # Calculate base position size
            position_size = risk_amount / current_price

            # Apply risk profile multiplier
            risk_profile = self.agent.config.get('risk_profile', 'moderate')
            multipliers = {
                'conservative': 0.5,
                'moderate': 1.0,
                'aggressive': 1.5
            }
            multiplier = multipliers.get(risk_profile, 1.0)
            position_size *= multiplier

            # Apply maximum position size limit
            max_position_ratio = self.agent.config.get('max_position_ratio', 0.1)
            max_position_value = available_balance * max_position_ratio
            max_position_size = max_position_value / current_price

            final_size = min(position_size, max_position_size)

            # Round to appropriate precision
            final_size = round(final_size, 6)

            self.logger.debug(
                f"Calculated position size for {symbol}: {final_size} "
                f"(balance: {available_balance}, risk: {risk_amount})"
            )

            return final_size

        except Exception as e:
            self.logger.error(f"Error calculating position size for {symbol}: {e}")
            return 0.0

    async def _get_available_balance(self) -> float:
        """
        Get available account balance.

        Returns:
            Available balance in USDT
        """
        try:
            account = await self.exchange.get_account_info()
            return float(account['availableBalance'])
        except Exception as e:
            self.logger.error(f"Error getting account balance: {e}")
            return 0.0

    def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """
        Get current market data for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Current market data or None if not available
        """
        return self.market_data_cache.get(symbol)

    def get_all_market_data(self) -> Dict[str, MarketData]:
        """
        Get all cached market data.

        Returns:
            Dictionary of all cached market data by symbol
        """
        return self.market_data_cache.copy()
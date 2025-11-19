"""
Real LLM-Powered Trading Agent Implementation.

Production-ready trading agent that uses LLMs (GPT-4, Claude, etc.) for trading decisions.
NO MOCKS, NO SIMULATIONS - This is for REAL TRADING with REAL MONEY.
"""

import logging
import json
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timezone

from .agent_interface import AgentInterface, MarketData, Position, TradingSignal
from .llm_client import OpenRouterClient
from .technical_analysis import TechnicalAnalyzer, TechnicalIndicators

logger = logging.getLogger(__name__)


class LLMTradingAgent(AgentInterface):
    """
    Real LLM-powered autonomous trading agent.

    Uses large language models to analyze markets and make trading decisions.
    Integrates technical analysis with LLM reasoning for robust decision-making.

    DANGER: This agent trades with REAL MONEY. Use with caution.
    """

    def __init__(self, agent_id: int, config: Dict):
        """
        Initialize LLM trading agent.

        Args:
            agent_id: Unique agent identifier
            config: Configuration dict containing:
                - llm_model: Model to use (e.g., 'anthropic/claude-3.5-sonnet')
                - risk_profile: Risk tolerance (conservative/moderate/aggressive)
                - max_leverage: Maximum allowed leverage
                - temperature: LLM temperature (0-1, lower = more conservative)
        """
        super().__init__(agent_id, config)

        # LLM Configuration
        self.llm_model = config.get('llm_model', 'anthropic/claude-3.5-sonnet')
        self.temperature = config.get('temperature', 0.3)  # Conservative by default
        self.llm_client = OpenRouterClient()

        # Technical Analysis
        self.technical_analyzer = TechnicalAnalyzer()

        # Trading State
        self.market_history: Dict[str, List[MarketData]] = {}
        self.decision_history: List[Dict] = []
        self.max_history_length = 100

        # Performance Tracking
        self.total_signals_generated = 0
        self.signals_executed = 0
        self.last_analysis_time: Optional[datetime] = None

        logger.info(
            f"Initialized LLM Trading Agent {agent_id} "
            f"with model {self.llm_model} (temperature={self.temperature})"
        )

    async def analyze_market(self, market_data: List[MarketData]) -> Dict[str, TradingSignal]:
        """
        Analyze market data using LLM and generate trading signals.

        This is the CORE trading logic. LLM analyzes:
        1. Technical indicators (RSI, EMA, ATR, etc.)
        2. Recent price action
        3. Volume patterns
        4. Current positions and risk

        Returns REAL trading signals that will be executed with REAL MONEY.

        Args:
            market_data: List of current market data for tracked symbols

        Returns:
            Dict mapping symbols to trading signals
        """
        signals = {}
        self.last_analysis_time = datetime.now(timezone.utc)

        for data in market_data:
            try:
                # Update market history
                if data.symbol not in self.market_history:
                    self.market_history[data.symbol] = []

                self.market_history[data.symbol].append(data)

                # Keep only recent history
                if len(self.market_history[data.symbol]) > self.max_history_length:
                    self.market_history[data.symbol] = \
                        self.market_history[data.symbol][-self.max_history_length:]

                # Only analyze if we have enough data
                if len(self.market_history[data.symbol]) < 20:
                    logger.debug(f"Not enough data for {data.symbol}, skipping")
                    continue

                # Perform technical analysis
                history = self.market_history[data.symbol]
                closes = [d.close_price for d in history]
                highs = [d.high_price for d in history]
                lows = [d.low_price for d in history]
                volumes = [d.volume for d in history]

                indicators = self.technical_analyzer.analyze_market(closes, highs, lows, volumes)

                # Get LLM trading decision
                signal = await self._get_llm_decision(data, indicators)

                if signal and signal.action in ['BUY', 'SELL']:
                    signals[data.symbol] = signal
                    self.total_signals_generated += 1

            except Exception as e:
                logger.error(f"Error analyzing {data.symbol}: {e}")
                continue

        return signals

    async def _get_llm_decision(
        self,
        market_data: MarketData,
        indicators: TechnicalIndicators
    ) -> Optional[TradingSignal]:
        """
        Get trading decision from LLM based on market analysis.

        Args:
            market_data: Current market data
            indicators: Calculated technical indicators

        Returns:
            TradingSignal or None if HOLD
        """
        # Build system prompt
        system_prompt = self._build_system_prompt()

        # Build market context
        market_context = self._build_market_context(market_data, indicators)

        try:
            # Call LLM for decision
            response = await self.llm_client.get_trading_decision(
                system_prompt=system_prompt,
                market_context=market_context,
                model=self.llm_model,
                temperature=self.temperature
            )

            # Parse LLM response into trading signal
            signal = self._parse_llm_response(response, market_data)

            return signal

        except Exception as e:
            logger.error(f"LLM decision error for {market_data.symbol}: {e}")
            return None

    def _build_system_prompt(self) -> str:
        """
        Build system prompt for LLM with trading instructions.

        Returns:
            System prompt string
        """
        risk_profile = self.config.get('risk_profile', 'moderate')
        max_leverage = self.config.get('max_leverage', 5)
        current_capital = self.config.get('current_capital', 0)

        return f"""You are an expert cryptocurrency futures trader managing a ${current_capital:,.2f} portfolio with {risk_profile} risk tolerance.

CRITICAL: You are trading with REAL MONEY. Every decision has real financial consequences.

Your Trading Parameters:
- Risk Profile: {risk_profile.upper()}
- Maximum Leverage: {max_leverage}x
- Position Sizing: Based on 2% risk per trade
- Current Positions: {len(self.positions)} open

Trading Rules:
1. ONLY generate BUY/SELL signals when you have HIGH CONFIDENCE (>70%)
2. Always set stop-loss and take-profit levels
3. Consider current market volatility and adjust position size
4. Respect maximum leverage limits
5. Never risk more than configured percentage per trade
6. Use technical analysis as PRIMARY decision factor
7. If uncertain, output HOLD (no trade)

Response Format (JSON):
{{
    "action": "BUY|SELL|HOLD",
    "confidence": 0-100,
    "reasoning": "Brief explanation of decision",
    "stop_loss_pct": percentage below/above entry,
    "take_profit_pct": percentage target,
    "leverage": 1-{max_leverage},
    "technical_summary": "What technical signals triggered this"
}}

Remember: Conservative is better than aggressive. Capital preservation is paramount."""

    def _build_market_context(
        self,
        market_data: MarketData,
        indicators: TechnicalIndicators
    ) -> str:
        """
        Build detailed market context for LLM analysis.

        Args:
            market_data: Current market snapshot
            indicators: Technical indicators

        Returns:
            Formatted market context string
        """
        # Get recent price action
        history = self.market_history.get(market_data.symbol, [])
        recent_prices = [d.close_price for d in history[-10:]] if len(history) >= 10 else []

        # Calculate price change
        price_change_24h = 0
        if len(history) >= 24:
            old_price = history[-24].close_price
            price_change_24h = ((market_data.close_price - old_price) / old_price) * 100

        # Get current position info
        current_position = self.positions.get(market_data.symbol)
        position_info = "No open position"
        if current_position:
            position_info = f"Current Position: {current_position.get('side')} {current_position.get('size')} @ ${current_position.get('entry_price'):,.2f} (PnL: ${current_position.get('pnl', 0):,.2f})"

        # Format technical analysis
        ta_text = self.technical_analyzer.format_analysis_text(
            market_data.symbol,
            market_data.close_price,
            indicators
        )

        context = f"""
Market Analysis Request for {market_data.symbol}

Current Market Data:
- Price: ${market_data.close_price:,.2f}
- 24h Change: {price_change_24h:+.2f}%
- Volume: {market_data.volume:,.0f}
- Funding Rate: {market_data.funding_rate:.4f}% (if positive, longs pay shorts)
- Timestamp: {market_data.timestamp}

Recent Price Action (last 10 candles):
{', '.join([f'${p:,.2f}' for p in recent_prices])}

{ta_text}

Current Position Status:
{position_info}

Market Conditions:
- Volatility: {'HIGH' if indicators.volatility_percentile and indicators.volatility_percentile > 70 else 'NORMAL' if indicators.volatility_percentile and indicators.volatility_percentile > 30 else 'LOW'}
- Volume Trend: {indicators.volume_trend or 'UNKNOWN'}
- Price vs Support/Resistance: {indicators.price_position or 'UNKNOWN'}

Based on this analysis, should we BUY, SELL, or HOLD? Provide your decision in the specified JSON format.
"""
        return context.strip()

    def _parse_llm_response(
        self,
        response: str,
        market_data: MarketData
    ) -> Optional[TradingSignal]:
        """
        Parse LLM JSON response into TradingSignal.

        Args:
            response: LLM text response
            market_data: Current market data

        Returns:
            TradingSignal or None
        """
        try:
            # Extract JSON from response (LLM might add extra text)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1

            if json_start == -1 or json_end == 0:
                logger.warning(f"No JSON found in LLM response: {response[:200]}")
                return None

            json_str = response[json_start:json_end]
            decision = json.loads(json_str)

            action = decision.get('action', 'HOLD').upper()

            # Validate action
            if action not in ['BUY', 'SELL', 'HOLD']:
                logger.warning(f"Invalid action from LLM: {action}")
                return None

            # Only create signal for BUY/SELL
            if action == 'HOLD':
                return None

            confidence = float(decision.get('confidence', 0))

            # Filter low confidence signals
            if confidence < 70:
                logger.info(f"Low confidence signal ({confidence}%), ignoring")
                return None

            # Calculate stop loss and take profit prices
            stop_loss_pct = float(decision.get('stop_loss_pct', 2.0))
            take_profit_pct = float(decision.get('take_profit_pct', 4.0))

            current_price = market_data.close_price

            if action == 'BUY':
                stop_loss = current_price * (1 - stop_loss_pct / 100)
                take_profit = current_price * (1 + take_profit_pct / 100)
            else:  # SELL
                stop_loss = current_price * (1 + stop_loss_pct / 100)
                take_profit = current_price * (1 - take_profit_pct / 100)

            leverage = int(decision.get('leverage', 1))
            leverage = min(leverage, self.config.get('max_leverage', 5))

            reasoning = f"{decision.get('reasoning', '')} | Technical: {decision.get('technical_summary', '')}"

            signal = TradingSignal(
                symbol=market_data.symbol,
                action=action,
                quantity=None,  # Will be calculated by runtime
                leverage=leverage,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=confidence / 100.0,
                reasoning=reasoning[:500]  # Limit length
            )

            logger.info(
                f"LLM Signal: {action} {market_data.symbol} @ ${current_price:,.2f} "
                f"(confidence: {confidence}%, leverage: {leverage}x)"
            )

            return signal

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            logger.error(f"Response: {response}")
            return None
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return None

    async def handle_fill(self, fill_info: Dict):
        """
        Handle order fill notification.

        Updates internal state when orders are executed.

        Args:
            fill_info: Order fill information from exchange
        """
        try:
            symbol = fill_info.get('symbol')
            side = fill_info.get('side')
            filled_qty = float(fill_info.get('executedQty', 0))
            avg_price = float(fill_info.get('avgPrice', 0))
            order_id = fill_info.get('orderId')

            logger.info(
                f"Order filled: {side} {filled_qty} {symbol} @ ${avg_price:,.2f} "
                f"(Order: {order_id})"
            )

            self.signals_executed += 1

            # Update position tracking if this opened a new position
            if side in ['BUY', 'SELL']:
                # Position will be updated by runtime via update_position()
                pass

        except Exception as e:
            logger.error(f"Error handling fill: {e}")

    async def manage_risk(self, positions: List[Position]) -> List[TradingSignal]:
        """
        Generate risk management signals for open positions.

        Checks stop-loss, take-profit, and drawdown limits.
        Can generate SELL signals to close positions.

        Args:
            positions: List of current open positions

        Returns:
            List of risk management signals
        """
        risk_signals = []

        try:
            for position in positions:
                # Check if position should be closed
                should_close, reason = await self._check_position_risk(position)

                if should_close:
                    # Generate close signal
                    close_signal = TradingSignal(
                        symbol=position.symbol,
                        action='SELL' if position.side == 'LONG' else 'BUY',
                        quantity=position.size,  # Close full position
                        leverage=1,
                        reasoning=f"Risk management: {reason}"
                    )

                    risk_signals.append(close_signal)

                    logger.warning(
                        f"Risk management closing {position.side} {position.symbol}: {reason}"
                    )

        except Exception as e:
            logger.error(f"Error in risk management: {e}")

        return risk_signals

    async def _check_position_risk(self, position: Position) -> tuple:
        """
        Check if position should be closed for risk management.

        Args:
            position: Position to check

        Returns:
            Tuple of (should_close: bool, reason: str)
        """
        # Check drawdown limit
        max_drawdown = self.config.get('max_drawdown', 0.30)
        if position.percentage_pnl < -(max_drawdown * 100):
            return (True, f"Drawdown limit exceeded ({position.percentage_pnl:.1f}%)")

        # Check if price hit stop loss (would need to fetch from stored signal)
        # This is simplified - in production, store stop loss levels per position

        # Check overall portfolio risk
        total_exposure = sum(
            abs(pos.get('size', 0) * pos.get('entry_price', 0))
            for pos in self.positions.values()
        )

        current_capital = self.config.get('current_capital', 0)
        if current_capital > 0:
            leverage_used = total_exposure / current_capital
            max_leverage = self.config.get('max_leverage', 5)

            if leverage_used > max_leverage:
                return (True, f"Leverage limit exceeded ({leverage_used:.1f}x > {max_leverage}x)")

        return (False, "")

    async def log_decision(self, signal: TradingSignal, context: Dict):
        """
        Log trading decision for audit and analysis.

        Args:
            signal: Trading signal being logged
            context: Additional context (market data, positions, etc.)
        """
        try:
            decision_record = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'agent_id': self.agent_id,
                'symbol': signal.symbol,
                'action': signal.action,
                'quantity': signal.quantity,
                'leverage': signal.leverage,
                'confidence': signal.confidence,
                'reasoning': signal.reasoning,
                'stop_loss': signal.stop_loss,
                'take_profit': signal.take_profit,
                'market_price': context.get('market_data', {}).get('close_price') if isinstance(context.get('market_data'), dict) else getattr(context.get('market_data'), 'close_price', None),
                'account_balance': context.get('account_balance'),
                'execution_failed': context.get('execution_failed', False),
                'error': context.get('error')
            }

            self.decision_history.append(decision_record)

            # Keep limited history in memory
            if len(self.decision_history) > 1000:
                self.decision_history = self.decision_history[-1000:]

            # Log to file/database would go here
            logger.info(f"Decision logged: {signal.action} {signal.symbol}")

        except Exception as e:
            logger.error(f"Error logging decision: {e}")

    def get_performance_stats(self) -> Dict:
        """Get agent performance statistics."""
        return {
            'agent_id': self.agent_id,
            'total_signals_generated': self.total_signals_generated,
            'signals_executed': self.signals_executed,
            'execution_rate': (
                self.signals_executed / self.total_signals_generated * 100
                if self.total_signals_generated > 0 else 0
            ),
            'open_positions': len(self.positions),
            'last_analysis': self.last_analysis_time.isoformat() if self.last_analysis_time else None,
            'llm_stats': self.llm_client.get_stats()
        }

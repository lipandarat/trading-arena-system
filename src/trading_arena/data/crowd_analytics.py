import asyncio
import json
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy import select, func
from trading_arena.models.trading import Position
from trading_arena.models.agent import Agent

logger = logging.getLogger(__name__)

class CrowdIntelligenceAnalyzer:
    def __init__(self, redis_client, db_session):
        self.redis_client = redis_client
        self.db_session = db_session
        self.update_interval = 30  # seconds

    async def analyze_agent_positions(self, symbol: str = None) -> Dict[str, Any]:
        """Analyze current agent positions for market intelligence."""
        try:
            query = select(Position, Agent).join(Agent).where(
                Position.size != 0  # Only active positions
            )

            if symbol:
                query = query.where(Position.symbol == symbol)

            result = await self.db_session.execute(query)
            positions = result.all()

            processed_positions = await self._process_position_data(positions)

            # Calculate overall intelligence
            intelligence = {
                'symbol': symbol or 'all',
                'total_agents': len(processed_positions),
                'total_positions': len(processed_positions),
                'positions': processed_positions,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

            if processed_positions:
                # Calculate risk metrics for all positions
                risk_metrics = await self.calculate_risk_metrics(processed_positions)
                intelligence.update(risk_metrics)

            return intelligence

        except Exception as e:
            logger.error(f"Error analyzing agent positions: {e}")
            return {}

    async def calculate_market_sentiment(self, symbol: str, positions: List[Dict]) -> Dict[str, Any]:
        """Calculate market sentiment from agent positions."""
        # Filter positions by symbol if provided
        if symbol:
            positions = [pos for pos in positions if pos.get('symbol') == symbol]

        if not positions:
            return {'bullish_ratio': 0.5, 'bearish_ratio': 0.5, 'total_volume': 0}

        long_volume = sum(pos['size'] for pos in positions if pos['side'] == 'LONG')
        short_volume = sum(pos['size'] for pos in positions if pos['side'] == 'SHORT')
        total_volume = long_volume + short_volume

        if total_volume == 0:
            return {'bullish_ratio': 0.5, 'bearish_ratio': 0.5, 'total_volume': 0}

        bullish_ratio = long_volume / total_volume
        bearish_ratio = short_volume / total_volume

        return {
            'bullish_ratio': round(bullish_ratio, 3),
            'bearish_ratio': round(bearish_ratio, 3),
            'total_volume': round(total_volume, 6),
            'long_volume': round(long_volume, 6),
            'short_volume': round(short_volume, 6),
            'symbol': symbol
        }

    async def calculate_risk_metrics(self, positions: List[Dict]) -> Dict[str, Any]:
        """Calculate risk metrics from agent positions."""
        if not positions:
            return {'avg_leverage': 0, 'max_leverage': 0, 'risk_score': 50}

        # Mock leverage calculation (would get from actual data)
        leverages = [pos.get('leverage', 1.0) for pos in positions]

        avg_leverage = sum(leverages) / len(leverages) if leverages else 1.0
        max_leverage = max(leverages) if leverages else 1.0

        # Simple risk score calculation (0-100, higher is riskier)
        risk_score = min(100, (avg_leverage - 1) * 25 + 25)

        return {
            'avg_leverage': round(avg_leverage, 2),
            'max_leverage': round(max_leverage, 2),
            'risk_score': round(risk_score, 1),
            'total_agents': len(positions)
        }

    async def publish_crowd_intelligence(self, intelligence_data: Dict[str, Any]):
        """Publish crowd intelligence data to Redis."""
        try:
            topic = f"crowd-intelligence.{intelligence_data.get('symbol', 'all')}"

            message = {
                'data': intelligence_data,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

            await self.redis_client.publish(
                topic,
                json.dumps(message)
            )

            # Also store latest data in Redis for API access
            await self.redis_client.set(
                f"latest:{topic}",
                json.dumps(message)
            )

            logger.info(f"Published crowd intelligence for {intelligence_data.get('symbol', 'all')}")

        except Exception as e:
            logger.error(f"Failed to publish crowd intelligence: {e}")

    async def _process_position_data(self, positions) -> List[Dict]:
        """Process position data from database result."""
        processed = []

        for position, agent in positions:
            processed.append({
                'symbol': position.symbol,
                'side': 'LONG' if float(position.size) > 0 else 'SHORT',
                'size': abs(float(position.size)),
                'entry_price': float(position.entry_price),
                'mark_price': float(position.mark_price),
                'unrealized_pnl': float(position.unrealized_pnl),
                'agent_id': agent.id,
                'agent_name': agent.name,
                'agent_tier': agent.risk_profile,  # Simplified
                'leverage': 1.0  # Mock data - would get from actual position data
            })

        return processed

    async def start_continuous_analysis(self):
        """Start continuous crowd intelligence analysis."""
        while True:
            try:
                # Analyze all positions
                intelligence = await self.analyze_agent_positions()

                if intelligence:
                    # Publish global intelligence
                    global_data = {
                        'symbol': 'all',
                        'total_agents': intelligence.get('total_agents', 0),
                        'total_positions': intelligence.get('total_positions', 0),
                        'avg_leverage': intelligence.get('avg_leverage', 0),
                        'risk_score': intelligence.get('risk_score', 50)
                    }
                    await self.publish_crowd_intelligence(global_data)

                    # Analyze individual symbols
                    symbols = set(pos.get('symbol') for pos in intelligence.get('positions', []))

                    for symbol in symbols:
                        symbol_positions = [pos for pos in intelligence.get('positions', []) if pos.get('symbol') == symbol]

                        if symbol_positions:
                            sentiment = await self.calculate_market_sentiment(symbol, symbol_positions)
                            risk_metrics = await self.calculate_risk_metrics(symbol_positions)

                            symbol_intelligence = {
                                'symbol': symbol,
                                **sentiment,
                                **risk_metrics
                            }
                            await self.publish_crowd_intelligence(symbol_intelligence)

                await asyncio.sleep(self.update_interval)

            except Exception as e:
                logger.error(f"Error in continuous analysis: {e}")
                await asyncio.sleep(10)  # Wait before retrying
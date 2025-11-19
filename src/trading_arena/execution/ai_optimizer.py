import numpy as np
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class MarketSignal:
    volatility_score: float
    liquidity_score: float
    participation_trend: float
    market_regime: str  # trending, ranging, volatile
    optimal_competition_type: str
    confidence: float

class AICompetitionOptimizer:
    def __init__(self):
        self.historical_data = []
        self.model_weights = {
            'volatility': 0.3,
            'liquidity': 0.25,
            'participation': 0.25,
            'time_of_day': 0.2
        }

    def analyze_market_conditions(self) -> MarketSignal:
        """Analyze current market conditions and return optimization signal"""

        # Get market data from existing systems
        current_conditions = self._get_current_conditions()

        # Calculate scores
        volatility_score = self._calculate_volatility_score(current_conditions)
        liquidity_score = self._calculate_liquidity_score(current_conditions)
        participation_trend = self._analyze_participation_trend()

        # Determine market regime
        market_regime = self._classify_market_regime(volatility_score, current_conditions)

        # Optimize competition type
        optimal_type = self._optimize_competition_type(
            volatility_score, liquidity_score, participation_trend, market_regime
        )

        # Calculate confidence
        confidence = self._calculate_prediction_confidence(
            volatility_score, liquidity_score, participation_trend
        )

        return MarketSignal(
            volatility_score=volatility_score,
            liquidity_score=liquidity_score,
            participation_trend=participation_trend,
            market_regime=market_regime,
            optimal_competition_type=optimal_type,
            confidence=confidence
        )

    def optimize_scheduling_window(self, signal: MarketSignal) -> Dict:
        """Optimize competition scheduling based on market signal"""

        base_recommendations = {
            'preferred_hours': [],  # UTC hours
            'duration_hours': 24,
            'competition_frequency': 'daily',
            'risk_adjustment': 1.0
        }

        # Adjust based on market conditions
        if signal.volatility_score > 0.7:
            base_recommendations['competition_frequency'] = 'hourly'
            base_recommendations['duration_hours'] = 6
            base_recommendations['risk_adjustment'] = 1.5
        elif signal.market_regime == 'ranging':
            base_recommendations['duration_hours'] = 48
            base_recommendations['competition_frequency'] = 'weekly'

        # Optimize timing based on participation patterns
        peak_hours = [14, 15, 16, 20, 21]  # UTC trading peaks
        base_recommendations['preferred_hours'] = peak_hours

        return base_recommendations

    def _get_current_conditions(self) -> Dict:
        """Get current market conditions from existing data sources"""
        try:
            # This would integrate with existing market data systems
            # For now, return realistic placeholder values that could be replaced
            # with actual integration to trading_arena.data.market_data

            # Note: Market data integration requires connection to MarketDataAggregator
            # Integration point for real-time market data:
            # market_data = self._market_data_aggregator.get_latest_price("BTCUSDT")
            # volume = market_data.get('volume', 1000000)

            return {
                'current_volatility': 0.25,  # Would calculate from recent price data
                'trading_volume': 1000000,  # Would get from real market data
                'active_agents': 50,        # Would query from agent management system
                'recent_participation': 0.8  # Would calculate from competition history
            }
        except Exception as e:
            logger.error(f"Failed to get current market conditions: {e}")
            # Return safe defaults
            return {
                'current_volatility': 0.2,
                'trading_volume': 500000,
                'active_agents': 25,
                'recent_participation': 0.6
            }

    def _calculate_volatility_score(self, conditions: Dict) -> float:
        """Calculate normalized volatility score (0-1)"""
        current_vol = conditions.get('current_volatility', 0.2)
        # Normalize to 0-1 range
        return min(1.0, max(0.0, current_vol * 2))

    def _calculate_liquidity_score(self, conditions: Dict) -> float:
        """Calculate normalized liquidity score (0-1)"""
        volume = conditions.get('trading_volume', 1000000)
        # Log normalize trading volume
        return min(1.0, max(0.0, np.log10(volume) / 9))

    def _analyze_participation_trend(self) -> float:
        """Analyze participation trend over recent period"""
        try:
            # Note: Database integration requires connection to competition models
            # This would analyze historical participation data from CompetitionEntry model
            # Integration point for participation analysis:
            # recent_entries = self._db.query(CompetitionEntry).filter(
            #     CompetitionEntry.joined_at >= datetime.now(timezone.utc) - timedelta(days=7)
            # ).count()
            # total_competitions = self._db.query(Competition).filter(
            #     Competition.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
            # ).count()
            # participation_rate = recent_entries / max(1, total_competitions * 20)  # Assuming 20 avg participants

            return 0.75  # Placeholder - would calculate from real data
        except Exception as e:
            logger.error(f"Failed to analyze participation trend: {e}")
            return 0.6  # Conservative default

    def _classify_market_regime(self, volatility: float, conditions: Dict) -> str:
        """Classify current market regime"""
        if volatility > 0.6:
            return 'volatile'
        elif abs(conditions.get('current_volatility', 0.2)) < 0.1:
            return 'ranging'
        else:
            return 'trending'

    def _optimize_competition_type(self, volatility: float, liquidity: float,
                                  participation: float, regime: str) -> str:
        """Determine optimal competition type based on conditions"""

        if volatility > 0.7:
            return 'short_term_sprint'
        elif regime == 'ranging' and liquidity > 0.8:
            return 'strategy_optimization'
        elif participation > 0.7:
            return 'tournament'
        else:
            return 'league'

    def _calculate_prediction_confidence(self, *scores) -> float:
        """Calculate confidence level for predictions"""
        avg_score = np.mean(scores)
        variance = np.var(scores)
        return max(0.5, 1.0 - variance)  # Higher variance = lower confidence
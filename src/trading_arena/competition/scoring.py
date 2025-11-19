"""
Competition scoring system for risk-adjusted performance evaluation.

Provides comprehensive scoring algorithms for different competition formats,
including tournament-specific scoring with risk management components.
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from trading_arena.models.scoring import Score, Performance
from trading_arena.models.agent import Agent
from trading_arena.models.competition import CompetitionEntry
import logging
import math

logger = logging.getLogger(__name__)


class CompetitionScorer:
    """
    Risk-adjusted competition scoring system.

    Implements comprehensive scoring algorithms that balance returns
    with risk management, consistency, and market conditions.
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

        # Tournament scoring weights (total 100%)
        self.tournament_weights = {
            'return_weight': 0.40,      # 40% - raw returns
            'sharpe_weight': 0.35,      # 35% - risk-adjusted returns
            'drawdown_weight': 0.25     # 25% - drawdown control
        }

        # League scoring weights
        self.league_weights = {
            'return_weight': 0.30,      # 30% - raw returns
            'sharpe_weight': 0.25,      # 25% - risk-adjusted returns
            'drawdown_weight': 0.20,    # 20% - drawdown control
            'consistency_weight': 0.15,  # 15% - consistency
            'activity_weight': 0.10     # 10% - trading activity
        }

        # Scoring thresholds
        self.min_trades_for_scoring = 20
        self.max_drawdown_penalty = -50.0
        self.min_return_for_score = -0.50  # -50%
        self.max_return_for_score = 1.0     # 100%

    async def calculate_competition_score(
        self,
        agent_id: int,
        competition_id: int,
        score_type: str = 'competition'
    ) -> float:
        """
        Calculate comprehensive competition score for an agent.

        Args:
            agent_id: Agent identifier
            competition_id: Competition identifier
            score_type: Type of score calculation

        Returns:
            Comprehensive score (0-100)
        """
        try:
            # Get agent's latest performance metrics
            latest_score = await self._get_latest_score(agent_id, competition_id)
            if not latest_score:
                return 0.0

            # Calculate component scores
            return_score = self._calculate_return_score(latest_score.total_return)
            sharpe_score = self._calculate_sharpe_score(latest_score.sharpe_ratio)
            drawdown_score = self._calculate_drawdown_score(latest_score.max_drawdown)
            consistency_score = self._calculate_consistency_score(latest_score)
            activity_score = self._calculate_activity_score(latest_score)

            # Apply weights based on competition type
            if score_type == 'tournament':
                weights = self.tournament_weights
                consistency_score = 0.0  # Not used in tournaments
                activity_score = 0.0      # Not used in tournaments
            else:
                weights = self.league_weights

            # Calculate weighted composite score
            total_score = (
                return_score * weights['return_weight'] +
                sharpe_score * weights['sharpe_weight'] +
                drawdown_score * weights['drawdown_weight'] +
                consistency_score * weights.get('consistency_weight', 0) +
                activity_score * weights.get('activity_weight', 0)
            )

            # Ensure score is within bounds
            return max(0.0, min(100.0, total_score))

        except Exception as e:
            logger.error(f"Error calculating competition score for agent {agent_id}: {e}")
            return 0.0

    async def calculate_tournament_score(self, performance_data: Dict) -> float:
        """
        Calculate tournament-specific score from performance data.

        Uses risk-adjusted scoring optimized for short-term tournaments:
        - Return: 40% weight
        - Sharpe ratio: 35% weight
        - Drawdown control: 25% weight

        Args:
            performance_data: Performance metrics dictionary

        Returns:
            Tournament score (0-100)
        """
        try:
            # Extract performance metrics
            total_return = performance_data.get('return', 0.0)
            sharpe_ratio = performance_data.get('sharpe_ratio', 0.0)
            max_drawdown = performance_data.get('max_drawdown', 1.0)

            # Calculate individual components
            return_score = min(40.0, max(0.0, total_return * 400))  # Cap at 40 points
            sharpe_score = min(35.0, max(0.0, sharpe_ratio * 20))   # Cap at 35 points
            drawdown_score = max(0.0, 25.0 - max_drawdown * 250)     # Penalty system

            # Calculate total tournament score
            tournament_score = return_score + sharpe_score + drawdown_score

            return min(100.0, max(0.0, tournament_score))

        except Exception as e:
            logger.error(f"Error calculating tournament score: {e}")
            return 0.0

    async def get_competition_rankings(
        self,
        competition_id: int,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get current competition rankings with comprehensive scores.

        Args:
            competition_id: Competition identifier
            limit: Maximum number of rankings to return

        Returns:
            List of agent rankings with scores and performance data
        """
        try:
            # Get all competition entries
            entries_result = await self.db.execute(
                select(CompetitionEntry)
                .where(CompetitionEntry.competition_id == competition_id)
                .where(CompetitionEntry.status == 'active')
            )
            entries = entries_result.scalars().all()

            rankings = []
            for entry in entries:
                # Get agent information
                agent = await self.db.get(Agent, entry.agent_id)
                if not agent:
                    continue

                # Get latest score
                latest_score = await self._get_latest_score(entry.agent_id, competition_id)
                if not latest_score:
                    continue

                # Calculate comprehensive score
                competition_score = await self.calculate_competition_score(
                    entry.agent_id, competition_id, 'competition'
                )

                # Calculate risk-adjusted metrics
                risk_adjusted_return = self._calculate_risk_adjusted_return(
                    latest_score.total_return, latest_score.max_drawdown
                )

                rankings.append({
                    'agent_id': agent.id,
                    'agent_name': agent.name,
                    'current_capital': entry.current_capital or agent.current_capital,
                    'entry_capital': entry.entry_capital,
                    'total_return': latest_score.total_return,
                    'sharpe_ratio': latest_score.sharpe_ratio,
                    'max_drawdown': latest_score.max_drawdown,
                    'risk_adjusted_return': risk_adjusted_return,
                    'competition_score': competition_score,
                    'total_trades': latest_score.total_trades,
                    'win_rate': latest_score.win_rate,
                    'current_rank': entry.current_rank,
                    'peak_rank': entry.peak_rank
                })

            # Sort by competition score (descending)
            rankings.sort(key=lambda x: x['competition_score'], reverse=True)

            # Update rankings
            for i, ranking in enumerate(rankings):
                ranking['calculated_rank'] = i + 1

            # Apply limit if specified
            if limit:
                rankings = rankings[:limit]

            return rankings

        except Exception as e:
            logger.error(f"Error getting competition rankings for {competition_id}: {e}")
            return []

    async def calculate_tournament_rankings(
        self,
        agent_performances: List[Dict]
    ) -> List[Dict]:
        """
        Calculate tournament rankings with risk-adjusted scoring.

        Args:
            agent_performances: List of agent performance dictionaries

        Returns:
            Ranked list of agents with tournament scores
        """
        try:
            scored_agents = []

            for performance in agent_performances:
                # Calculate tournament score
                tournament_score = await self.calculate_tournament_score(performance)

                # Calculate risk-adjusted return
                risk_adjusted_return = self._calculate_risk_adjusted_return(
                    performance.get('return', 0.0),
                    performance.get('max_drawdown', 1.0)
                )

                # Create performance breakdown
                total_return = performance.get('return', 0.0)
                sharpe_ratio = performance.get('sharpe_ratio', 0.0)
                max_drawdown = performance.get('max_drawdown', 1.0)

                performance_breakdown = {
                    'return_score': min(40.0, max(0.0, total_return * 400)),
                    'sharpe_score': min(35.0, max(0.0, sharpe_ratio * 20)),
                    'drawdown_penalty': max(-25.0, -max_drawdown * 250),
                    'total_return': total_return,
                    'sharpe_ratio': sharpe_ratio,
                    'max_drawdown': max_drawdown
                }

                scored_agents.append({
                    'agent_id': performance['agent_id'],
                    'agent_name': performance.get('agent_name', f"Agent_{performance['agent_id']}"),
                    'tournament_score': tournament_score,
                    'risk_adjusted_score': risk_adjusted_return,
                    'raw_return': total_return,
                    'performance_breakdown': performance_breakdown,
                    'tier': performance.get('tier', 'unknown')
                })

            # Sort by tournament score (descending)
            scored_agents.sort(key=lambda x: x['tournament_score'], reverse=True)

            # Add rankings
            for i, agent in enumerate(scored_agents):
                agent['rank'] = i + 1

            return scored_agents

        except Exception as e:
            logger.error(f"Error calculating tournament rankings: {e}")
            return []

    def _calculate_return_score(self, total_return: float) -> float:
        """Calculate return component score (0-100)."""
        # Normalize returns to 0-100 scale
        # -50% = 0 points, 0% = 50 points, 100% = 100 points
        normalized_return = (total_return - self.min_return_for_score) / (
            self.max_return_for_score - self.min_return_for_score
        )
        return max(0.0, min(100.0, normalized_return * 100))

    def _calculate_sharpe_score(self, sharpe_ratio: float) -> float:
        """Calculate Sharpe ratio component score (0-100)."""
        # Sharpe ratio scoring: <0 = 0, 0-1 = 0-50, >1 = 50-100
        if sharpe_ratio <= 0:
            return 0.0
        elif sharpe_ratio <= 1.0:
            return sharpe_ratio * 50.0
        else:
            # Diminishing returns above 1.0
            return 50.0 + min(50.0, math.log(sharpe_ratio + 1) * 25.0)

    def _calculate_drawdown_score(self, max_drawdown: float) -> float:
        """Calculate drawdown component score (0-100)."""
        # Drawdown penalty: 0% = 100 points, 50%+ = 0 points
        if max_drawdown <= 0:
            return 100.0
        elif max_drawdown >= 0.5:
            return 0.0
        else:
            return 100.0 * (1.0 - (max_drawdown / 0.5))

    def _calculate_consistency_score(self, score: Score) -> float:
        """Calculate consistency component score (0-100)."""
        try:
            # Consistency factors: win rate, profit factor, trade frequency
            win_rate_score = score.win_rate * 50.0  # 50% weight
            profit_factor_score = min(50.0, max(0.0, (score.profit_factor - 1.0) * 25.0))  # 50% weight

            return win_rate_score + profit_factor_score

        except Exception:
            return 0.0

    def _calculate_activity_score(self, score: Score) -> float:
        """Calculate trading activity component score (0-100)."""
        try:
            # Activity based on number of trades
            if score.total_trades >= self.min_trades_for_scoring:
                # Full credit for minimum trades, bonus for more activity
                return min(100.0, (score.total_trades / self.min_trades_for_scoring) * 100.0)
            else:
                # Linear penalty for insufficient activity
                return (score.total_trades / self.min_trades_for_scoring) * 100.0

        except Exception:
            return 0.0

    def _calculate_risk_adjusted_return(self, total_return: float, max_drawdown: float) -> float:
        """Calculate risk-adjusted return (return per unit of risk)."""
        if max_drawdown == 0:
            return total_return if total_return > 0 else 0.0
        return total_return / max_drawdown

    async def _get_latest_score(self, agent_id: int, competition_id: Optional[int] = None) -> Optional[Score]:
        """Get latest score for an agent."""
        try:
            query = select(Score).where(Score.agent_id == agent_id)

            if competition_id:
                # If competition specified, get competition-specific score
                query = query.where(Score.score_type == 'competition')
            else:
                # Otherwise get latest overall score
                query = query.where(Score.score_type.in_(['daily', 'weekly', 'monthly']))

            latest_score = await self.db.scalar(
                query.order_by(desc(Score.calculated_at)).limit(1)
            )

            return latest_score

        except Exception as e:
            logger.error(f"Error getting latest score for agent {agent_id}: {e}")
            return None

    def calculate_performance_summary(self, scores: List[Score]) -> Dict:
        """
        Calculate performance summary from multiple scores.

        Args:
            scores: List of Score objects

        Returns:
            Performance summary dictionary
        """
        if not scores:
            return {}

        try:
            # Aggregate metrics
            total_returns = [s.total_return for s in scores if s.total_return is not None]
            sharpe_ratios = [s.sharpe_ratio for s in scores if s.sharpe_ratio is not None]
            max_drawdowns = [s.max_drawdown for s in scores if s.max_drawdown is not None]
            win_rates = [s.win_rate for s in scores if s.win_rate is not None]

            summary = {
                'period_count': len(scores),
                'avg_return': sum(total_returns) / len(total_returns) if total_returns else 0.0,
                'best_return': max(total_returns) if total_returns else 0.0,
                'worst_return': min(total_returns) if total_returns else 0.0,
                'avg_sharpe': sum(sharpe_ratios) / len(sharpe_ratios) if sharpe_ratios else 0.0,
                'max_drawdown': max(max_drawdowns) if max_drawdowns else 0.0,
                'avg_win_rate': sum(win_rates) / len(win_rates) if win_rates else 0.0,
                'consistency_score': self._calculate_consistency_metric(total_returns)
            }

            return summary

        except Exception as e:
            logger.error(f"Error calculating performance summary: {e}")
            return {}

    def _calculate_consistency_metric(self, returns: List[float]) -> float:
        """Calculate consistency score from return series."""
        if len(returns) < 2:
            return 0.0

        try:
            # Calculate standard deviation of returns
            avg_return = sum(returns) / len(returns)
            variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
            std_dev = math.sqrt(variance)

            # Consistency score: lower volatility = higher score
            if std_dev == 0:
                return 100.0

            # Normalize to 0-100 scale (inverse of volatility)
            consistency_score = max(0.0, 100.0 - (std_dev * 100))

            return consistency_score

        except Exception:
            return 0.0


# Helper functions for tournament-specific calculations
def calculate_tournament_progression(
    current_participants: int,
    elimination_rate: float = 0.5
) -> Dict:
    """
    Calculate tournament progression structure.

    Args:
        current_participants: Number of current participants
        elimination_rate: Percentage to eliminate each round (default 50%)

    Returns:
        Dictionary with progression details
    """
    rounds = []
    participants = current_participants
    round_num = 1

    while participants > 1:
        advancing = max(1, int(participants * (1 - elimination_rate)))
        eliminated = participants - advancing

        rounds.append({
            'round': round_num,
            'start_participants': participants,
            'advancing': advancing,
            'eliminated': eliminated
        })

        participants = advancing
        round_num += 1

    return {
        'total_rounds': len(rounds),
        'initial_participants': current_participants,
        'final_participants': 1,
        'rounds': rounds
    }
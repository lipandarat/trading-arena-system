"""
Tournament management system for quarterly mega-tournaments.

Implements cross-tier competition with risk-adjusted scoring,
bracket elimination, and meritocratic qualification criteria.
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc, or_
from trading_arena.competition.manager import CompetitionManager
from trading_arena.competition.scoring import CompetitionScorer
from trading_arena.models.competition import Competition, CompetitionEntry
from trading_arena.models.agent import Agent
from trading_arena.models.scoring import Score
import logging

logger = logging.getLogger(__name__)


class TournamentManager(CompetitionManager):
    """
    Manages quarterly mega-tournaments with cross-tier competition.

    Features:
    - Quarterly mega-tournaments with 100 max participants
    - Top 20% from each tier qualify based on risk-adjusted score >65
    - Risk-adjusted tournament scoring (return: 40%, sharpe: 35%, drawdown: 25%)
    - Cross-tier competition with meritocratic scoring
    - 7-day tournament with bracket elimination (bottom 50% eliminated each round)
    - Tournament qualification criteria (score>65, drawdown<30%, minimum activity)
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        self.tournament_duration_days = 7
        self.max_participants = 100
        self.qualification_percentage = 0.20  # Top 20% from each tier qualify
        self.elimination_rate = 0.50  # Bottom 50% eliminated each round
        self.min_risk_score = 65.0  # Minimum risk-adjusted score for qualification
        self.max_drawdown_for_qualification = 0.30  # Maximum 30% drawdown
        self.min_trades_for_qualification = 100  # Minimum trades for qualification
        self.scorer = CompetitionScorer(db_session)

    async def create_quarterly_tournament(
        self,
        name: str,
        start_date: datetime
    ) -> Competition:
        """
        Create quarterly mega-tournament with 7-day duration.

        Args:
            name: Tournament name
            start_date: Tournament start date

        Returns:
            Created tournament instance
        """
        end_date = start_date + timedelta(days=self.tournament_duration_days)

        # Create quarterly tournament with mega-tournament settings
        tournament = await self.create_competition(
            name=name,
            competition_type="tournament",
            start_date=start_date,
            end_date=end_date,
            max_participants=self.max_participants,
            entry_fee=100.0,  # Standard entry fee
            prize_pool=50000.0  # Standard prize pool
        )

        # Update tournament-specific settings
        tournament.scoring_method = "risk_adjusted_tournament"
        tournament.scoring_frequency = "real_time"
        tournament.max_drawdown_limit = 0.40  # 40% max drawdown for tournaments

        await self.db.commit()
        await self.db.refresh(tournament)

        logger.info(f"Created quarterly tournament: {name} ({tournament.id}) "
                   f"from {start_date} to {end_date}")

        return tournament

    async def get_qualified_agents(
        self,
        competition_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Get agents qualified for quarterly tournament with cross-tier qualification.

        Qualification criteria:
        - Risk-adjusted score > 65
        - Maximum drawdown < 30%
        - Minimum activity (100+ trades)
        - Top 20% from each tier

        Args:
            competition_id: Specific tournament ID (optional)

        Returns:
            List of qualified agents with performance data
        """
        try:
            if competition_id:
                # Get qualified agents for specific tournament
                entries_result = await self.db.execute(
                    select(CompetitionEntry)
                    .where(CompetitionEntry.competition_id == competition_id)
                    .where(CompetitionEntry.status == 'active')
                )
            else:
                # Get all agents potentially qualified for next tournament
                entries_result = await self.db.execute(
                    select(CompetitionEntry)
                    .where(CompetitionEntry.competition_id.in_(
                        select(Competition.id)
                        .where(and_(
                            Competition.type == 'league',
                            Competition.status == 'active'
                        ))
                    ))
                    .where(CompetitionEntry.status == 'active')
                )

            entries = entries_result.scalars().all()
            qualified_agents = []

            # Group agents by tier for qualification
            tier_groups = {'bronze': [], 'silver': [], 'gold': [], 'platinum': []}

            for entry in entries:
                # Get agent information
                agent = await self.db.get(Agent, entry.agent_id)
                if not agent:
                    continue

                # Determine agent's current tier
                tier = await self.assign_agent_tier(agent)

                # Get latest performance metrics
                latest_score = await self.db.scalar(
                    select(Score)
                    .where(Score.agent_id == agent.id)
                    .order_by(desc(Score.calculated_at))
                    .limit(1)
                )

                if not latest_score:
                    continue

                # Check qualification criteria
                if self._meets_qualification_criteria(latest_score):
                    tier_groups[tier].append({
                        'agent_id': agent.id,
                        'agent_name': agent.name,
                        'tier': tier,
                        'current_capital': agent.current_capital,
                        'entry_capital': entry.entry_capital,
                        'current_competition_capital': entry.current_capital,
                        'risk_score': latest_score.risk_score,
                        'sharpe_ratio': latest_score.sharpe_ratio,
                        'max_drawdown': latest_score.max_drawdown,
                        'total_return': latest_score.total_return,
                        'total_trades': latest_score.total_trades,
                        'win_rate': latest_score.win_rate,
                        'qualification_score': latest_score.risk_score,
                        'competition_entry_id': entry.id
                    })

            # Select top 20% from each tier (or at least 1 if tier has few agents)
            for tier, agents in tier_groups.items():
                if not agents:
                    continue

                # Sort by risk score (descending)
                agents.sort(key=lambda x: x['risk_score'], reverse=True)

                # Calculate qualification count (top 20% or minimum 1)
                qualify_count = max(1, int(len(agents) * self.qualification_percentage))

                # Take top qualifiers from this tier
                qualified_from_tier = agents[:qualify_count]
                qualified_agents.extend(qualified_from_tier)

                logger.info(f"Tier {tier.title()}: {qualify_count} agents qualified "
                           f"from {len(agents)} total")

            # Sort all qualified agents by risk score for final ranking
            qualified_agents.sort(key=lambda x: x['risk_score'], reverse=True)

            # Limit to maximum participants
            if len(qualified_agents) > self.max_participants:
                qualified_agents = qualified_agents[:self.max_participants]

            logger.info(f"Total qualified agents: {len(qualified_agents)}")

            return qualified_agents

        except Exception as e:
            logger.error(f"Error getting qualified agents: {e}")
            return []

    async def calculate_tournament_rankings(
        self,
        agent_performances: List[Dict]
    ) -> List[Dict]:
        """
        Calculate risk-adjusted tournament rankings.

        Tournament scoring weights:
        - Risk-adjusted returns: 40%
        - Sharpe ratio: 35%
        - Drawdown control: 25%

        Args:
            agent_performances: List of agent performance dictionaries

        Returns:
            Ranked list of agents with tournament scores
        """
        try:
            scored_agents = []

            for performance in agent_performances:
                # Calculate tournament score using scorer
                tournament_score = await self.scorer.calculate_tournament_score(performance)

                # Calculate risk-adjusted return
                risk_adjusted_return = self._risk_adjusted_return(performance)

                # Create detailed performance breakdown
                performance_breakdown = {
                    'return_score': min(40.0, max(0.0, performance.get('return', 0.0) * 400)),
                    'sharpe_score': min(35.0, max(0.0, performance.get('sharpe_ratio', 0.0) * 20)),
                    'drawdown_penalty': max(-25.0, -performance.get('max_drawdown', 1.0) * 250)
                }

                scored_agents.append({
                    'agent_id': performance['agent_id'],
                    'agent_name': performance.get('agent_name', f"Agent_{performance['agent_id']}"),
                    'tournament_score': tournament_score,
                    'raw_return': performance.get('return', 0.0),
                    'risk_adjusted_score': risk_adjusted_return,
                    'performance_breakdown': performance_breakdown,
                    'tier': performance.get('tier', 'unknown'),
                    'sharpe_ratio': performance.get('sharpe_ratio', 0.0),
                    'max_drawdown': performance.get('max_drawdown', 1.0)
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

    async def run_tournament_round(
        self,
        competition_id: int,
        round_num: int
    ) -> Dict:
        """
        Execute tournament round with bracket elimination.

        Eliminates bottom 50% of participants each round until winner determined.

        Args:
            competition_id: Competition identifier
            round_num: Current round number

        Returns:
            Round results with advancing and eliminated agents
        """
        try:
            # Get current participants
            participants = await self.get_qualified_agents(competition_id)

            if len(participants) <= 2:
                # Tournament complete - determine winner
                if participants:
                    # Calculate final rankings
                    rankings = await self.calculate_tournament_rankings(participants)
                    winner = rankings[0] if rankings else participants[0]
                else:
                    winner = None

                return {
                    'round': round_num,
                    'status': 'completed',
                    'winner': winner,
                    'final_rankings': rankings if 'rankings' in locals() else participants,
                    'total_participants': len(participants)
                }

            # Calculate current rankings for this round
            rankings = await self.calculate_tournament_rankings(participants)

            # Eliminate bottom 50% (or as close as possible)
            total_participants = len(rankings)
            eliminate_count = max(1, int(total_participants * self.elimination_rate))

            # Separate advancing and eliminated agents
            advancing = rankings[:-eliminate_count] if eliminate_count < total_participants else rankings[:1]
            eliminated = rankings[-eliminate_count:] if eliminate_count < total_participants else rankings[1:]

            # Update competition entries for eliminated agents
            for agent in eliminated:
                await self._eliminate_agent(competition_id, agent['agent_id'], f"Eliminated in round {round_num}")

            logger.info(f"Round {round_num} complete: {len(advancing)} advancing, {len(eliminated)} eliminated")

            return {
                'round': round_num,
                'status': 'active',
                'total_participants': total_participants,
                'advancing': advancing,
                'eliminated': eliminated,
                'next_round_participants': len(advancing),
                'elimination_rate': len(eliminated) / total_participants
            }

        except Exception as e:
            logger.error(f"Error running tournament round {round_num}: {e}")
            return {
                'round': round_num,
                'status': 'error',
                'error': str(e),
                'total_participants': 0
            }

    def _meets_qualification_criteria(self, score: Score) -> bool:
        """
        Check if agent meets tournament qualification criteria.

        Criteria:
        - Risk-adjusted score: > 65
        - Maximum drawdown: < 30%
        - Minimum activity: 100 trades

        Args:
            score: Agent's latest score

        Returns:
            True if agent qualifies, False otherwise
        """
        try:
            # Handle None values gracefully
            risk_score = getattr(score, 'risk_score', 0) or 0
            max_drawdown = getattr(score, 'max_drawdown', 1.0) or 1.0
            total_trades = getattr(score, 'total_trades', 0) or 0

            meets_score = risk_score > self.min_risk_score
            meets_drawdown = max_drawdown < self.max_drawdown_for_qualification
            meets_activity = total_trades >= self.min_trades_for_qualification

            return meets_score and meets_drawdown and meets_activity

        except Exception as e:
            logger.error(f"Error checking qualification criteria: {e}")
            return False

    def _calculate_tournament_score(self, performance: Dict) -> float:
        """
        Calculate composite tournament score (0-100).

        Uses risk-adjusted scoring:
        - Return: 40% weight (capped at 40 points)
        - Sharpe ratio: 35% weight (capped at 35 points)
        - Drawdown control: 25% weight (penalty system)

        Args:
            performance: Performance metrics dictionary

        Returns:
            Tournament score (0-100)
        """
        try:
            total_return = performance.get('return', 0.0)
            sharpe_ratio = performance.get('sharpe_ratio', 0.0)
            max_drawdown = performance.get('max_drawdown', 1.0)

            # Calculate individual components
            return_score = min(40.0, max(0.0, total_return * 400))  # Cap at 40 points
            sharpe_score = min(35.0, max(0.0, sharpe_ratio * 20))   # Cap at 35 points
            drawdown_score = max(0.0, 25.0 - max_drawdown * 250)     # Penalty system

            total_score = return_score + sharpe_score + drawdown_score

            return min(100.0, max(0.0, total_score))

        except Exception as e:
            logger.error(f"Error calculating tournament score: {e}")
            return 0.0

    def _risk_adjusted_return(self, performance: Dict) -> float:
        """
        Calculate risk-adjusted return (return per unit of risk).

        Args:
            performance: Performance metrics dictionary

        Returns:
            Risk-adjusted return
        """
        try:
            total_return = performance.get('return', 0.0)
            max_drawdown = performance.get('max_drawdown', 1.0)

            if max_drawdown == 0:
                return total_return if total_return > 0 else 0.0

            return total_return / max_drawdown

        except Exception as e:
            logger.error(f"Error calculating risk-adjusted return: {e}")
            return 0.0

    async def _eliminate_agent(
        self,
        competition_id: int,
        agent_id: int,
        reason: str
    ) -> None:
        """
        Mark agent as eliminated from tournament.

        Args:
            competition_id: Competition identifier
            agent_id: Agent identifier
            reason: Elimination reason
        """
        try:
            # Find competition entry
            entry = await self.db.scalar(
                select(CompetitionEntry)
                .where(and_(
                    CompetitionEntry.competition_id == competition_id,
                    CompetitionEntry.agent_id == agent_id
                ))
            )

            if entry:
                entry.status = 'eliminated'
                entry.elimination_reason = reason
                await self.db.commit()

                logger.info(f"Agent {agent_id} eliminated from competition {competition_id}: {reason}")

        except Exception as e:
            logger.error(f"Error eliminating agent {agent_id}: {e}")

    async def get_tournament_standings(
        self,
        competition_id: int
    ) -> Dict:
        """
        Get current tournament standings and progression.

        Args:
            competition_id: Competition identifier

        Returns:
            Tournament standings with progression info
        """
        try:
            # Get current participants
            participants = await self.get_qualified_agents(competition_id)

            if not participants:
                return {
                    'competition_id': competition_id,
                    'status': 'no_participants',
                    'standings': [],
                    'total_participants': 0
                }

            # Calculate current rankings
            rankings = await self.calculate_tournament_rankings(participants)

            # Get competition info
            competition = await self.db.get(Competition, competition_id)

            # Calculate tournament progression
            progression = self._calculate_tournament_progression(len(rankings))

            return {
                'competition_id': competition_id,
                'competition_name': competition.name if competition else "Unknown",
                'status': competition.status if competition else 'unknown',
                'total_participants': len(rankings),
                'standings': rankings,
                'progression': progression,
                'current_round': progression.get('current_round', 1),
                'estimated_rounds_remaining': progression.get('rounds_remaining', 0)
            }

        except Exception as e:
            logger.error(f"Error getting tournament standings for {competition_id}: {e}")
            return {
                'competition_id': competition_id,
                'status': 'error',
                'error': str(e),
                'standings': [],
                'total_participants': 0
            }

    def _calculate_tournament_progression(self, current_participants: int) -> Dict:
        """
        Calculate tournament progression structure.

        Args:
            current_participants: Number of current participants

        Returns:
            Tournament progression information
        """
        try:
            rounds_remaining = 0
            participants = current_participants
            round_num = 1

            while participants > 1:
                participants = max(1, int(participants * (1 - self.elimination_rate)))
                rounds_remaining += 1
                round_num += 1

            return {
                'current_round': 1,
                'total_rounds_estimated': rounds_remaining,
                'rounds_remaining': rounds_remaining,
                'participants_per_round': self._calculate_participants_per_round(current_participants)
            }

        except Exception as e:
            logger.error(f"Error calculating tournament progression: {e}")
            return {}

    def _calculate_participants_per_round(self, initial_participants: int) -> List[int]:
        """Calculate number of participants per round."""
        participants_per_round = [initial_participants]
        current = initial_participants

        while current > 1:
            current = max(1, int(current * (1 - self.elimination_rate)))
            participants_per_round.append(current)

        return participants_per_round
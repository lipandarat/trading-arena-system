"""
League management system for trading competitions.

Manages ongoing league competitions with tier progression, monthly cycles,
and cross-tier eligibility checking.
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from trading_arena.competition.manager import CompetitionManager
from trading_arena.models.competition import Competition, CompetitionEntry
from trading_arena.models.agent import Agent
from trading_arena.models.scoring import Score
import logging

logger = logging.getLogger(__name__)

class LeagueManager(CompetitionManager):
    """Manages ongoing league competitions with hybrid scoring and tier progression"""

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session)
        self.league_duration_days = 30
        self.promotion_threshold = 0.10  # Top 10% get promoted
        self.demotion_threshold = 0.15  # Bottom 15% get demoted

    async def create_monthly_league(self, tier: str, start_date: datetime) -> Competition:
        """Create monthly league for specific tier"""

        end_date = start_date + timedelta(days=self.league_duration_days)

        return await self.create_competition(
            name=f"{tier.title()} League - {start_date.strftime('%B %Y')}",
            competition_type="league",
            start_date=start_date,
            end_date=end_date,
            max_participants=None,  # Unlimited for leagues
            entry_fee=0.0,
            prize_pool=self._get_tier_prize_pool(tier)
        )

    async def process_monthly_progression(self, previous_league_id: int,
                                        new_league_id: int) -> List[Dict]:
        """Process promotions and demotions based on league performance"""

        # Get league standings
        standings = await self.update_competition_standings(previous_league_id)
        total_participants = standings['total_participants']

        if total_participants == 0:
            return []

        promotions = []
        demotions = []

        # Calculate promotion cutoff (top 10%)
        promotion_cutoff = max(1, int(total_participants * self.promotion_threshold))
        demotion_cutoff = max(1, int(total_participants * self.demotion_threshold))

        # Get all agent IDs that need tier evaluation
        promotion_agent_ids = [standing['agent_id'] for standing in standings['standings'][:promotion_cutoff]]
        demotion_agent_ids = [standing['agent_id'] for standing in standings['standings'][-demotion_cutoff:]]

        # Combine and dedupe agent IDs for efficient querying
        all_agent_ids = list(set(promotion_agent_ids + demotion_agent_ids))

        # Batch fetch all agents at once instead of individual queries
        if all_agent_ids:
            result = await self.db.execute(
                select(Agent).where(Agent.id.in_(all_agent_ids))
            )
            agents = {agent.id: agent for agent in result.scalars().all()}
        else:
            agents = {}

        # Process promotions (top performers)
        for i, standing in enumerate(standings['standings'][:promotion_cutoff]):
            # Get agent from pre-fetched dictionary
            agent = agents.get(standing['agent_id'])
            if not agent:
                continue  # Skip if agent not found

            current_tier = await self.assign_agent_tier(agent)

            # Determine next tier
            next_tier = self._get_next_tier(current_tier)
            if next_tier and next_tier != current_tier:
                promotions.append({
                    'agent_id': standing['agent_id'],
                    'agent_name': standing['agent_name'],
                    'from_tier': current_tier,
                    'to_tier': next_tier,
                    'rank': i + 1,
                    'score': standing['score']
                })

        # Process demotions (bottom performers)
        bottom_standings = standings['standings'][-demotion_cutoff:]
        for i, standing in enumerate(bottom_standings):
            # Get agent from pre-fetched dictionary
            agent = agents.get(standing['agent_id'])
            if not agent:
                continue  # Skip if agent not found

            current_tier = await self.assign_agent_tier(agent)

            # Determine previous tier
            prev_tier = self._get_previous_tier(current_tier)
            if prev_tier and prev_tier != current_tier:
                demotions.append({
                    'agent_id': standing['agent_id'],
                    'agent_name': standing['agent_name'],
                    'from_tier': current_tier,
                    'to_tier': prev_tier,
                    'rank': total_participants - len(bottom_standings) + i + 1,
                    'score': standing['score']
                })

        # Log progression results
        logger.info(f"League progression: {len(promotions)} promotions, {len(demotions)} demotions")

        return promotions + demotions

    async def check_cross_tier_eligibility(self, agent_data: Dict) -> bool:
        """Check if agent qualifies for cross-tier competition"""

        # Cross-tier eligibility requirements:
        # 1. Minimum capital: $10,000
        # 2. Risk score: >60
        # 3. Maximum drawdown: <25%
        # 4. Leverage usage: <5x

        meets_capital = agent_data['current_capital'] >= 10000.0
        meets_risk_score = agent_data['risk_score'] > 60.0
        meets_drawdown = agent_data['max_drawdown'] < 0.25
        meets_leverage = agent_data['leverage_usage'] < 5.0

        return meets_capital and meets_risk_score and meets_drawdown and meets_leverage

    async def get_league_tiers(self) -> Dict[str, List[Competition]]:
        """Get all active leagues grouped by tier"""

        result = await self.db.execute(
            select(Competition)
            .where(and_(
                Competition.type == 'league',
                Competition.status == 'active'
            ))
            .order_by(Competition.start_date.desc())
        )
        leagues = result.scalars().all()

        tiers = {
            'bronze': [],
            'silver': [],
            'gold': [],
            'platinum': []
        }

        for league in leagues:
            for tier_name in tiers.keys():
                if tier_name.lower() in league.name.lower():
                    tiers[tier_name].append(league)
                    break

        return tiers

    def _get_tier_prize_pool(self, tier: str) -> float:
        """Get prize pool amount for tier"""
        prize_pools = {
            'bronze': 1000.0,
            'silver': 5000.0,
            'gold': 15000.0,
            'platinum': 50000.0
        }
        return prize_pools.get(tier.lower(), 1000.0)

    def _get_next_tier(self, current_tier: str) -> Optional[str]:
        """Get next higher tier"""
        tier_progression = ['bronze', 'silver', 'gold', 'platinum']
        try:
            current_index = tier_progression.index(current_tier.lower())
            if current_index < len(tier_progression) - 1:
                return tier_progression[current_index + 1]
        except ValueError:
            pass
        return None

    def _get_previous_tier(self, current_tier: str) -> Optional[str]:
        """Get previous lower tier"""
        tier_progression = ['bronze', 'silver', 'gold', 'platinum']
        try:
            current_index = tier_progression.index(current_tier.lower())
            if current_index > 0:
                return tier_progression[current_index - 1]
        except ValueError:
            pass
        return None

    async def update_competition_standings(self, competition_id: int) -> Dict:
        """Update and return competition standings

        Returns a dictionary with:
        - total_participants: Total number of participants
        - standings: List of participant standings with agent_id, agent_name, score
        """

        # Get all entries for the competition with proper join and null handling
        result = await self.db.execute(
            select(CompetitionEntry, Agent)
            .join(Agent, CompetitionEntry.agent_id == Agent.id, isouter=True)
            .where(CompetitionEntry.competition_id == competition_id)
            .order_by(CompetitionEntry.current_score.desc().nullslast())
        )
        entries = result.all()

        # Build standings with null checks
        standings = []
        for entry, agent in entries:
            # Handle case where agent might be None
            agent_name = agent.name if agent else f"Agent {entry.agent_id}"
            score = entry.current_score if entry.current_score is not None else 0.0
            rank = entry.current_rank if entry.current_rank is not None else 0
            capital = entry.current_capital if entry.current_capital is not None else entry.entry_capital

            standings.append({
                'agent_id': entry.agent_id,
                'agent_name': agent_name,
                'score': score,
                'rank': rank,
                'capital': capital
            })

        return {
            'total_participants': len(standings),
            'standings': standings
        }
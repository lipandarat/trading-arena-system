from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from trading_arena.models.competition import Competition, CompetitionEntry
from trading_arena.models.agent import Agent
from trading_arena.models.scoring import Score
import logging

logger = logging.getLogger(__name__)

class CompetitionManager:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def create_competition(self, name: str, competition_type: str,
                               start_date: datetime, end_date: Optional[datetime] = None,
                               max_participants: Optional[int] = None,
                               entry_fee: float = 0.0, prize_pool: float = 0.0) -> Competition:
        """Create new competition with hybrid model support"""

        competition = Competition(
            name=name,
            type=competition_type,  # 'league' or 'tournament'
            start_date=start_date,
            end_date=end_date,
            max_participants=max_participants,
            entry_fee=entry_fee,
            prize_pool=prize_pool,
            status='upcoming'
        )

        self.db.add(competition)
        await self.db.commit()
        await self.db.refresh(competition)

        logger.info(f"Created {competition_type} competition: {name}")
        return competition

    async def register_agent(self, agent_id: int, competition_id: int) -> CompetitionEntry:
        """Register agent for competition with capacity validation"""

        # Check if competition has space
        competition = await self.db.get(Competition, competition_id)
        if not competition:
            raise ValueError("Competition not found")

        if competition.max_participants:
            current_entries = await self.db.scalar(
                select(func.count(CompetitionEntry.id))
                .where(CompetitionEntry.competition_id == competition_id)
            )
            if current_entries >= competition.max_participants:
                raise ValueError("Competition is full")

        # Check if agent already registered
        existing = await self.db.scalar(
            select(CompetitionEntry)
            .where(and_(
                CompetitionEntry.agent_id == agent_id,
                CompetitionEntry.competition_id == competition_id
            ))
        )
        if existing:
            raise ValueError("Agent already registered")

        entry = CompetitionEntry(
            agent_id=agent_id,
            competition_id=competition_id,
            joined_at=datetime.now(timezone.utc)
        )

        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)

        logger.info(f"Agent {agent_id} registered for competition {competition_id}")
        return entry

    async def assign_agent_tier(self, agent: Agent) -> str:
        """Dynamic tier assignment based on performance and capital"""

        # Get agent's latest risk score
        latest_score = await self.db.scalar(
            select(Score)
            .where(Score.agent_id == agent.id)
            .order_by(Score.calculated_at.desc())
            .limit(1)
        )

        risk_score = latest_score.risk_score if latest_score else 0

        # Tier assignment logic
        if risk_score > 80 and agent.current_capital >= 20000:
            return "platinum"
        elif risk_score > 65 and agent.current_capital >= 5000:
            return "gold"
        elif risk_score > 50 and agent.current_capital >= 1000:
            return "silver"
        else:
            return "bronze"

    async def get_active_competitions(self) -> List[Competition]:
        """Get all currently active competitions"""
        now = datetime.now(timezone.utc)

        result = await self.db.execute(
            select(Competition)
            .where(and_(
                Competition.start_date <= now,
                or_(Competition.end_date.is_(None), Competition.end_date > now),
                Competition.status == 'active'
            ))
        )
        return result.scalars().all()
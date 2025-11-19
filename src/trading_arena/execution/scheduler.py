import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from trading_arena.execution.ai_optimizer import AICompetitionOptimizer, MarketSignal
from trading_arena.execution.event_triggers import EventTriggerManager
from trading_arena.models.competition import Competition, CompetitionEntry
from trading_arena.db import get_database

logger = logging.getLogger(__name__)

@dataclass
class SchedulerConfig:
    """Configuration for competition scheduler"""

    # Scheduling intervals (seconds)
    scheduling_loop_interval: int = 60
    event_monitoring_interval: int = 30
    lifecycle_check_interval: int = 10

    # Competition thresholds
    high_priority_threshold: float = 0.7
    max_participants_default: int = 100
    min_participants_default: int = 1
    default_duration_hours: int = 24
    max_duration_hours: int = 168  # 1 week
    min_duration_hours: int = 1

    # Market conditions
    low_participation_threshold: int = 20
    participation_boost_threshold: int = 30

    # Preparation timing
    default_preparation_minutes: int = 5
    max_preparation_minutes: int = 60
    min_preparation_minutes: int = 1

    # Competition settings
    default_max_leverage: float = 10.0
    default_min_capital: float = 1000.0
    default_max_drawdown_limit: float = 0.50

    @classmethod
    def from_env(cls) -> 'SchedulerConfig':
        """Create configuration from environment variables"""
        return cls(
            scheduling_loop_interval=int(os.getenv('SCHEDULER_LOOP_INTERVAL', 60)),
            event_monitoring_interval=int(os.getenv('EVENT_MONITORING_INTERVAL', 30)),
            lifecycle_check_interval=int(os.getenv('LIFECYCLE_CHECK_INTERVAL', 10)),
            high_priority_threshold=float(os.getenv('HIGH_PRIORITY_THRESHOLD', 0.7)),
            max_participants_default=int(os.getenv('MAX_PARTICIPANTS_DEFAULT', 100)),
            min_participants_default=int(os.getenv('MIN_PARTICIPANTS_DEFAULT', 1)),
            default_duration_hours=int(os.getenv('DEFAULT_DURATION_HOURS', 24)),
            max_duration_hours=int(os.getenv('MAX_DURATION_HOURS', 168)),
            min_duration_hours=int(os.getenv('MIN_DURATION_HOURS', 1)),
            low_participation_threshold=int(os.getenv('LOW_PARTICIPATION_THRESHOLD', 20)),
            participation_boost_threshold=int(os.getenv('PARTICIPATION_BOOST_THRESHOLD', 30)),
            default_preparation_minutes=int(os.getenv('DEFAULT_PREPARATION_MINUTES', 5)),
            max_preparation_minutes=int(os.getenv('MAX_PREPARATION_MINUTES', 60)),
            min_preparation_minutes=int(os.getenv('MIN_PREPARATION_MINUTES', 1)),
            default_max_leverage=float(os.getenv('DEFAULT_MAX_LEVERAGE', 10.0)),
            default_min_capital=float(os.getenv('DEFAULT_MIN_CAPITAL', 1000.0)),
            default_max_drawdown_limit=float(os.getenv('DEFAULT_MAX_DRAWDOWN_LIMIT', 0.50)),
        )

@dataclass
class SchedulingDecision:
    action: str
    competition_type: str
    priority: float
    timestamp: datetime
    parameters: Dict[str, any] = field(default_factory=dict)

@dataclass
class CompetitionInstance:
    id: str
    type: str
    status: str
    start_time: datetime
    end_time: Optional[datetime] = None
    participants: List[str] = field(default_factory=list)
    scheduling_priority: float = 0.5

class CompetitionScheduler:
    def __init__(self, database=None, config: Optional[SchedulerConfig] = None):
        self.config = config or SchedulerConfig.from_env()
        self.database = database
        self.ai_optimizer = AICompetitionOptimizer()
        self.event_triggers = EventTriggerManager()
        self.scheduling_queue: List[SchedulingDecision] = []
        self.is_running = False
        self.scheduler_tasks: List[asyncio.Task] = []

    async def start(self):
        """Start the automated competition scheduler"""
        if self.is_running:
            logger.warning("Competition scheduler is already running")
            return

        self.is_running = True
        logger.info("Starting competition scheduler")

        # Start main scheduling loop
        task1 = asyncio.create_task(self._scheduling_loop())
        self.scheduler_tasks.append(task1)

        # Start event monitoring
        task2 = asyncio.create_task(self._event_monitoring_loop())
        self.scheduler_tasks.append(task2)

        # Start competition lifecycle management
        task3 = asyncio.create_task(self._competition_lifecycle_loop())
        self.scheduler_tasks.append(task3)

        logger.info(f"Started {len(self.scheduler_tasks)} scheduler tasks")

    async def stop(self):
        """Stop the competition scheduler gracefully"""
        self.is_running = False
        logger.info("Stopping competition scheduler")

        # Cancel all running tasks
        for task in self.scheduler_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Error stopping scheduler task: {e}")

        self.scheduler_tasks.clear()
        logger.info("Competition scheduler stopped")

    async def _scheduling_loop(self):
        """Main scheduling decision loop"""
        while self.is_running:
            try:
                # Analyze market conditions
                market_signal = self.ai_optimizer.analyze_market_conditions()

                # Get scheduling recommendations
                recommendations = self.ai_optimizer.optimize_scheduling_window(market_signal)

                # Make scheduling decisions
                decisions = await self._make_scheduling_decisions(market_signal, recommendations)

                # Queue high-priority decisions
                for decision in sorted(decisions, key=lambda x: x.priority, reverse=True):
                    if decision.priority > self.config.high_priority_threshold:
                        self.scheduling_queue.append(decision)

                # Process scheduling queue
                await self._process_scheduling_queue()

                # Adaptive sleep based on market conditions
                sleep_time = self._calculate_adaptive_sleep(market_signal)
                await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.error(f"Error in scheduling loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying

    async def _event_monitoring_loop(self):
        """Monitor for event-driven competition triggers"""
        while self.is_running:
            try:
                # Check for trigger events
                triggered_events = await self.event_triggers.check_triggers()

                for event in triggered_events:
                    decision = SchedulingDecision(
                        action="triggered_competition",
                        competition_type=event.competition_type,
                        priority=event.priority,
                        timestamp=datetime.now(timezone.utc),
                        parameters=event.parameters
                    )
                    self.scheduling_queue.append(decision)
                    logger.info(f"Event triggered competition: {event.competition_type}")

                await asyncio.sleep(self.config.event_monitoring_interval)

            except Exception as e:
                logger.error(f"Error in event monitoring: {e}")
                await asyncio.sleep(60)

    async def _competition_lifecycle_loop(self):
        """Manage competition lifecycle and transitions"""
        if not self.database:
            await self._ensure_database()

        while self.is_running:
            try:
                current_time = datetime.now(timezone.utc)

                async with self.database.get_session() as session:
                    # Check for scheduled competitions to start
                    scheduled_result = await session.execute(
                        select(Competition).where(
                            Competition.status == 'upcoming',
                            Competition.start_date <= current_time
                        )
                    )
                    scheduled_competitions = scheduled_result.scalars().all()

                    for competition in scheduled_competitions:
                        await self._start_competition(competition, session)

                    # Check for active competitions to end
                    active_result = await session.execute(
                        select(Competition).where(
                            Competition.status == 'active',
                            Competition.end_date <= current_time
                        )
                    )
                    active_competitions = active_result.scalars().all()

                    for competition in active_competitions:
                        await self._end_competition(competition, session)

                await asyncio.sleep(self.config.lifecycle_check_interval)

            except Exception as e:
                logger.error(f"Error in competition lifecycle: {e}")
                await asyncio.sleep(60)

    async def _make_scheduling_decisions(self, signal: MarketSignal,
                                       recommendations: Dict) -> List[SchedulingDecision]:
        """Make intelligent scheduling decisions based on AI analysis"""
        decisions = []

        # Time-based scheduling decisions
        current_hour = datetime.now(timezone.utc).hour
        if current_hour in recommendations['preferred_hours']:
            decisions.append(SchedulingDecision(
                action="start_competition",
                competition_type=signal.optimal_competition_type,
                priority=signal.confidence,
                timestamp=datetime.now(timezone.utc),
                parameters={
                    'duration_hours': recommendations['duration_hours'],
                    'risk_adjustment': recommendations['risk_adjustment']
                }
            ))

        # Participation-based decisions
        active_agent_count = await self._get_active_agent_count()
        if active_agent_count < self.config.low_participation_threshold:
            decisions.append(SchedulingDecision(
                action="start_incentive_competition",
                competition_type="beginner_friendly",
                priority=0.6,
                timestamp=datetime.now(timezone.utc),
                parameters={'rewards_multiplier': 2.0}
            ))

        return decisions

    async def _process_scheduling_queue(self):
        """Process pending scheduling decisions"""
        while self.scheduling_queue:
            decision = self.scheduling_queue.pop(0)

            try:
                if decision.action == "start_competition":
                    await self._schedule_new_competition(decision)
                elif decision.action == "triggered_competition":
                    await self._schedule_triggered_competition(decision)
                elif decision.action == "start_incentive_competition":
                    await self._schedule_incentive_competition(decision)

            except Exception as e:
                logger.error(f"Error processing scheduling decision: {e}")

    async def _schedule_new_competition(self, decision: SchedulingDecision):
        """Schedule a new competition based on decision"""
        if not self.database:
            await self._ensure_database()

        try:
            # Validate scheduling parameters
            self._validate_scheduling_decision(decision)

            competition_name = f"{decision.competition_type}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

            # Calculate competition timing
            preparation_time = decision.parameters.get('preparation_minutes', self.config.default_preparation_minutes)
            duration_hours = decision.parameters.get('duration_hours', self.config.default_duration_hours)

            # Validate timing parameters using configuration
            preparation_time = max(self.config.min_preparation_minutes, min(self.config.max_preparation_minutes, preparation_time))
            duration_hours = max(self.config.min_duration_hours, min(self.config.max_duration_hours, duration_hours))

            start_time = datetime.now(timezone.utc) + timedelta(minutes=preparation_time)
            end_time = start_time + timedelta(hours=duration_hours)

            # Validate that end_time is after start_time
            if end_time <= start_time:
                raise ValueError("Competition end time must be after start time")

            # Create competition in database
            async with self.database.get_session() as session:
                competition = Competition(
                    name=competition_name,
                    description=f"Autoscheduled {decision.competition_type} competition",
                    type=decision.competition_type,
                    format='futures',
                    market='crypto',
                    start_date=start_time,
                    end_date=end_time,
                    registration_deadline=start_time,
                    status='upcoming',
                    entry_fee=0.0,
                    prize_pool=decision.parameters.get('rewards_multiplier', 1.0) * 1000,  # Example prize pool
                    max_participants=decision.parameters.get('max_participants', self.config.max_participants_default),
                    min_participants=decision.parameters.get('min_participants', self.config.min_participants_default),
                    max_leverage=decision.parameters.get('max_leverage', self.config.default_max_leverage),
                    min_capital=decision.parameters.get('min_capital', self.config.default_min_capital),
                    scoring_method='risk_adjusted_return',
                    scoring_frequency='real_time',
                    max_drawdown_limit=decision.parameters.get('max_drawdown_limit', self.config.default_max_drawdown_limit)
                )

                session.add(competition)
                await session.flush()  # Get the ID without committing
                await session.refresh(competition)

            logger.info(f"Scheduled new competition: {competition.name} (ID: {competition.id})")

        except Exception as e:
            logger.error(f"Failed to schedule new competition: {e}")
            raise

    def _validate_scheduling_decision(self, decision: SchedulingDecision):
        """Validate scheduling decision parameters"""
        if not decision.action:
            raise ValueError("Decision action cannot be empty")

        if not decision.competition_type:
            raise ValueError("Competition type cannot be empty")

        if not 0 <= decision.priority <= 1:
            raise ValueError("Priority must be between 0 and 1")

        if decision.parameters:
            # Validate specific parameters
            if 'duration_hours' in decision.parameters:
                duration = decision.parameters['duration_hours']
                if not isinstance(duration, (int, float)) or duration <= 0:
                    raise ValueError("Duration hours must be a positive number")

            if 'max_participants' in decision.parameters:
                max_part = decision.parameters['max_participants']
                if not isinstance(max_part, int) or max_part <= 0:
                    raise ValueError("Max participants must be a positive integer")

            if 'rewards_multiplier' in decision.parameters:
                multiplier = decision.parameters['rewards_multiplier']
                if not isinstance(multiplier, (int, float)) or multiplier <= 0:
                    raise ValueError("Rewards multiplier must be a positive number")

    async def _get_active_agent_count(self) -> int:
        """Get current count of active trading agents"""
        if not self.database:
            await self._ensure_database()

        try:
            async with self.database.get_session() as session:
                from sqlalchemy import func, select
                from trading_arena.models.agent import Agent

                # Count agents that are marked as active
                result = await session.execute(
                    select(func.count(Agent.id)).where(Agent.is_active == True)
                )
                return result.scalar() or 0
        except Exception as e:
            logger.error(f"Error getting active agent count: {e}")
            return 50  # Fallback to default value

    async def _ensure_database(self):
        """Ensure database connection is initialized"""
        if not self.database:
            self.database = await get_database()

    def _calculate_adaptive_sleep(self, signal: MarketSignal) -> float:
        """Calculate adaptive sleep time based on market conditions"""
        if signal.volatility_score > 0.7:
            return 30  # High frequency during volatility
        elif signal.market_regime == 'ranging':
            return 300  # Lower frequency during ranging markets
        else:
            return 120  # Normal frequency

    async def _start_competition(self, competition: Competition, session: AsyncSession):
        """Start a scheduled competition"""
        try:
            competition.status = 'active'
            await session.commit()
            logger.info(f"Started competition: {competition.name} (ID: {competition.id})")

            # Integration with existing competition manager would happen here
            # This would notify participants, initialize scoring, etc.

        except Exception as e:
            logger.error(f"Failed to start competition {competition.id}: {e}")
            await session.rollback()

    async def _end_competition(self, competition: Competition, session: AsyncSession):
        """End a running competition"""
        try:
            competition.status = 'completed'
            await session.commit()
            logger.info(f"Completed competition: {competition.name} (ID: {competition.id})")

            # Integration with scoring and ranking systems would happen here
            # This would calculate final scores, distribute prizes, etc.

        except Exception as e:
            logger.error(f"Failed to end competition {competition.id}: {e}")
            await session.rollback()

    def analyze_market_conditions(self) -> Dict:
        """Analyze market conditions and return summary for tests"""
        market_signal = self.ai_optimizer.analyze_market_conditions()
        return {
            "volatility": market_signal.volatility_score,
            "liquidity": market_signal.liquidity_score,
            "participation_rate": market_signal.participation_trend
        }

    # Additional scheduling methods for different competition types
    async def _schedule_triggered_competition(self, decision: SchedulingDecision):
        """Schedule a competition triggered by events"""
        await self._schedule_new_competition(decision)

    async def _schedule_incentive_competition(self, decision: SchedulingDecision):
        """Schedule an incentive competition to boost participation"""
        await self._schedule_new_competition(decision)
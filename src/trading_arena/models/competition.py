"""
Competition models for trading competitions and tournaments.

Manages different types of competitions including leagues and tournaments,
with flexible scheduling and prize distribution mechanisms.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .base import Base


class Competition(Base):
    """
    Trading competition or tournament.

    Supports various competition formats:
    - League: Ongoing competition with regular seasons
    - Tournament: Time-based competitions with elimination rounds
    """
    __tablename__ = "competitions"

    # Primary fields
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)

    # Competition Configuration
    type = Column(String(50), nullable=False)  # league, tournament, head_to_head
    format = Column(String(50), default="futures")  # futures, spot, mixed
    market = Column(String(50), default="crypto")  # crypto, forex, commodities

    # Scheduling
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime)
    registration_deadline = Column(DateTime)

    # Competition Status
    status = Column(String(50), default="upcoming")  # upcoming, registration, active, completed, cancelled

    # Financial Configuration
    entry_fee = Column(Float, default=0.0)
    prize_pool = Column(Float, default=0.0)
    prize_distribution = Column(Text)  # JSON string with prize structure

    # Participant Limits
    max_participants = Column(Integer)
    min_participants = Column(Integer, default=1)

    # Trading Constraints
    allowed_symbols = Column(Text)  # JSON array of allowed trading symbols
    max_leverage = Column(Float, default=10.0)
    min_capital = Column(Float, default=1000.0)
    max_capital = Column(Float)

    # Scoring Configuration
    scoring_method = Column(String(50), default="risk_adjusted_return")  # total_return, sharpe_ratio, etc.
    scoring_frequency = Column(String(20), default="daily")  # real_time, hourly, daily

    # Risk Management
    max_drawdown_limit = Column(Float, default=0.50)  # 50% max drawdown
    position_limits = Column(Text)  # JSON string with position size limits

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    entries = relationship("CompetitionEntry", back_populates="competition", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        # Set default values
        kwargs.setdefault('format', 'futures')
        kwargs.setdefault('market', 'crypto')
        kwargs.setdefault('status', 'upcoming')
        kwargs.setdefault('entry_fee', 0.0)
        kwargs.setdefault('prize_pool', 0.0)
        kwargs.setdefault('max_participants', None)
        kwargs.setdefault('min_participants', 1)
        kwargs.setdefault('max_leverage', 10.0)
        kwargs.setdefault('min_capital', 1000.0)
        kwargs.setdefault('max_capital', None)
        kwargs.setdefault('scoring_method', 'risk_adjusted_return')
        kwargs.setdefault('scoring_frequency', 'daily')
        kwargs.setdefault('max_drawdown_limit', 0.50)

        # Set timestamp defaults
        now = datetime.now(timezone.utc)
        kwargs.setdefault('created_at', now)
        kwargs.setdefault('updated_at', now)

        super().__init__(**kwargs)

    @property
    def is_active(self) -> bool:
        """Check if competition is currently active"""
        now = datetime.now(timezone.utc)
        return self.status == "active" and self.start_date <= now <= (self.end_date or now)

    @property
    def is_registration_open(self) -> bool:
        """Check if registration is currently open"""
        if self.registration_deadline:
            return datetime.now(timezone.utc) < self.registration_deadline
        return self.status in ["upcoming", "registration"]

    @property
    def days_remaining(self) -> int:
        """Calculate days remaining until competition ends"""
        if not self.end_date:
            return 0
        delta = self.end_date - datetime.now(timezone.utc)
        return max(0, delta.days)

    def __repr__(self):
        return f"<Competition(id={self.id}, name='{self.name}', type='{self.type}', status='{self.status}')>"


class CompetitionEntry(Base):
    """
    Agent participation in a competition.

    Tracks agent registration, performance, and ranking within each competition.
    """
    __tablename__ = "competition_entries"

    # Primary fields
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False, index=True)

    # Registration Details
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    entry_capital = Column(Float, nullable=False)  # Capital when entering competition
    current_capital = Column(Float)  # Current capital in competition

    # Competition Performance
    final_rank = Column(Integer)
    final_score = Column(Float)
    final_return = Column(Float)  # Percentage return in competition

    # Real-time Performance
    current_rank = Column(Integer)
    current_score = Column(Float)
    peak_rank = Column(Integer)
    worst_rank = Column(Integer)

    # Status Tracking
    status = Column(String(50), default="active")  # active, eliminated, withdrawn, completed
    elimination_reason = Column(String(255))

    # Risk Metrics
    max_drawdown = Column(Float)
    volatility = Column(Float)
    sharpe_ratio = Column(Float)

    # Trade Statistics
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    profit_factor = Column(Float)

    # Timestamps
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    agent = relationship("Agent", back_populates="competition_entries")
    competition = relationship("Competition", back_populates="entries")

    def __init__(self, **kwargs):
        # Set default values
        kwargs.setdefault('status', 'active')
        kwargs.setdefault('total_trades', 0)
        kwargs.setdefault('winning_trades', 0)

        # Set timestamp defaults
        now = datetime.now(timezone.utc)
        kwargs.setdefault('joined_at', now)
        kwargs.setdefault('last_updated', now)

        super().__init__(**kwargs)

    # Composite indexes for performance
    __table_args__ = (
        Index('idx_competition_rank', 'competition_id', 'current_rank'),
        Index('idx_agent_competition', 'agent_id', 'competition_id', unique=True),
    )

    @property
    def win_rate(self) -> float:
        """Calculate win rate in competition"""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    @property
    def competition_return(self) -> float:
        """Calculate return percentage in competition"""
        if self.entry_capital == 0 or not self.current_capital:
            return 0.0
        return (self.current_capital - self.entry_capital) / self.entry_capital

    @property
    def is_eliminated(self) -> bool:
        """Check if agent has been eliminated from competition"""
        return self.status == "eliminated"

    def __repr__(self):
        return f"<CompetitionEntry(id={self.id}, agent_id={self.agent_id}, competition_id={self.competition_id}, rank={self.current_rank})>"
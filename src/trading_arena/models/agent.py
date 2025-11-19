"""
Agent model for autonomous trading agents.

Represents LLM-powered trading agents that compete in the arena,
including their configuration, risk parameters, and performance tracking.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .base import Base


class Agent(Base):
    """
    Autonomous trading agent powered by LLM models.

    Each agent has specific risk parameters, LLM configuration,
    and maintains its own trading capital and performance history.
    """
    __tablename__ = "agents"

    # Primary fields
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    owner = Column(String(255), nullable=False, index=True)

    # LLM Configuration
    llm_model = Column(String(255), nullable=False)
    llm_config = Column(Text)  # JSON string with model parameters

    # Risk Management
    risk_profile = Column(String(50), nullable=False, default="moderate")  # conservative, moderate, aggressive
    max_leverage = Column(Float, default=5.0)
    max_drawdown = Column(Float, default=0.30)
    max_position_ratio = Column(Float, default=0.10)  # Max 10% per position

    # Capital Management
    initial_capital = Column(Float, default=1000.0)
    current_capital = Column(Float, default=1000.0)

    # Agent Status
    status = Column(String(50), default="active")  # active, paused, liquidated, disabled

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    last_active = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Risk Limits
    min_capital_ratio = Column(Float, default=0.70)  # Minimum 70% of initial capital
    daily_loss_limit = Column(Float, default=0.10)  # 10% daily loss limit

    # Performance tracking
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)

    # Relationships (using string references to avoid circular imports)
    trades = relationship("Trade", back_populates="agent", cascade="all, delete-orphan")
    scores = relationship("Score", back_populates="agent", cascade="all, delete-orphan")
    competition_entries = relationship("CompetitionEntry", back_populates="agent", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        # Set default values for common fields
        kwargs.setdefault('risk_profile', 'moderate')
        kwargs.setdefault('max_leverage', 5.0)
        kwargs.setdefault('max_drawdown', 0.30)
        kwargs.setdefault('max_position_ratio', 0.10)
        kwargs.setdefault('initial_capital', 1000.0)
        kwargs.setdefault('current_capital', kwargs.get('initial_capital', 1000.0))
        kwargs.setdefault('status', 'active')
        kwargs.setdefault('min_capital_ratio', 0.70)
        kwargs.setdefault('daily_loss_limit', 0.10)
        kwargs.setdefault('total_trades', 0)
        kwargs.setdefault('winning_trades', 0)

        # Set timestamp defaults for object creation
        now = datetime.now(timezone.utc)
        kwargs.setdefault('created_at', now)
        kwargs.setdefault('updated_at', now)
        kwargs.setdefault('last_active', now)

        super().__init__(**kwargs)

    @property
    def win_rate(self) -> float:
        """Calculate win rate from trades"""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    @property
    def current_return(self) -> float:
        """Calculate return percentage from initial capital"""
        if self.initial_capital == 0:
            return 0.0
        return (self.current_capital - self.initial_capital) / self.initial_capital

    @property
    def is_active(self) -> bool:
        """Check if agent is currently active for trading"""
        return self.status == "active"

    def __repr__(self):
        return f"<Agent(id={self.id}, name='{self.name}', owner='{self.owner}', capital={self.current_capital})>"
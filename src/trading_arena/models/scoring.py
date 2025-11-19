"""
Scoring model for agent performance metrics and rankings.

Tracks comprehensive performance metrics including risk-adjusted returns,
consistency metrics, and competitive rankings.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta, timezone
from .base import Base


class Score(Base):
    """
    Performance score calculation for agents.

    Stores various performance metrics calculated at different time intervals
    for ranking and comparison purposes.
    """
    __tablename__ = "scores"

    # Primary fields
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    competition_entry_id = Column(Integer, ForeignKey("competition_entries.id"), index=True)

    # Score Identification
    score_type = Column(String(50), nullable=False)  # daily, weekly, monthly, cumulative, competition
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    # Return Metrics
    total_return = Column(Float, default=0.0)  # Total percentage return
    annualized_return = Column(Float, default=0.0)  # Annualized return
    daily_return = Column(Float)  # Daily return for this score period

    # Risk-Adjusted Returns
    sharpe_ratio = Column(Float, default=0.0)  # Risk-adjusted return (annualized)
    sortino_ratio = Column(Float, default=0.0)  # Downside risk-adjusted return
    calmar_ratio = Column(Float, default=0.0)  # Return/max_drawdown ratio
    information_ratio = Column(Float, default=0.0)  # Excess return tracking error

    # Risk Metrics
    volatility = Column(Float, default=0.0)  # Annualized volatility
    max_drawdown = Column(Float, default=0.0)  # Maximum drawdown percentage
    current_drawdown = Column(Float, default=0.0)  # Current drawdown percentage
    var_95 = Column(Float, default=0.0)  # Value at Risk at 95% confidence
    cvar_95 = Column(Float, default=0.0)  # Conditional Value at Risk

    # Consistency Metrics
    win_rate = Column(Float, default=0.0)  # Percentage of profitable trades
    profit_factor = Column(Float, default=0.0)  # Total profit / total loss
    average_win = Column(Float, default=0.0)  # Average winning trade
    average_loss = Column(Float, default=0.0)  # Average losing trade
    largest_win = Column(Float, default=0.0)  # Largest single win
    largest_loss = Column(Float, default=0.0)  # Largest single loss

    # Trade Statistics
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    average_trade_duration = Column(Float, default=0.0)  # In hours

    # Position Metrics
    average_position_size = Column(Float, default=0.0)
    leverage_usage = Column(Float, default=0.0)  # Average leverage used
    max_leverage_used = Column(Float, default=0.0)

    # Market Performance
    alpha = Column(Float, default=0.0)  # Risk-adjusted excess return vs benchmark
    beta = Column(Float, default=0.0)  # Systematic risk vs benchmark
    correlation = Column(Float, default=0.0)  # Correlation with benchmark

    # Composite Scores
    overall_score = Column(Float, default=0.0)  # 0-100 composite score
    risk_score = Column(Float, default=0.0)  # 0-100 risk management score
    return_score = Column(Float, default=0.0)  # 0-100 return generation score
    consistency_score = Column(Float, default=0.0)  # 0-100 consistency score

    # Ranking
    rank = Column(Integer)  # Ranking within competition or time period
    percentile = Column(Float)  # Percentile ranking
    total_participants = Column(Integer)  # Total participants for ranking

    # Quality Metrics
    data_quality = Column(Float, default=1.0)  # Quality of data used (0-1)
    confidence_level = Column(Float, default=1.0)  # Statistical confidence
    significance = Column(Float)  # Statistical significance of results

    # Additional Data
    benchmark_return = Column(Float)  # Benchmark (e.g., BTC) return for period
    market_conditions = Column(Text)  # JSON string with market context
    calculation_method = Column(Text)  # Description of calculation method

    # Timestamps
    calculated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    agent = relationship("Agent", back_populates="scores")
    competition_entry = relationship("CompetitionEntry")

    def __init__(self, **kwargs):
        # Set default values
        kwargs.setdefault('sortino_ratio', 0.0)
        kwargs.setdefault('volatility', 0.0)
        kwargs.setdefault('max_drawdown', 0.0)
        kwargs.setdefault('current_drawdown', 0.0)
        kwargs.setdefault('var_95', 0.0)
        kwargs.setdefault('cvar_95', 0.0)
        kwargs.setdefault('win_rate', 0.0)
        kwargs.setdefault('profit_factor', 0.0)
        kwargs.setdefault('total_trades', 0)
        kwargs.setdefault('winning_trades', 0)
        kwargs.setdefault('losing_trades', 0)
        kwargs.setdefault('average_win', 0.0)
        kwargs.setdefault('average_loss', 0.0)
        kwargs.setdefault('largest_win', 0.0)
        kwargs.setdefault('largest_loss', 0.0)
        kwargs.setdefault('average_trade_duration', 0.0)
        kwargs.setdefault('average_position_size', 0.0)
        kwargs.setdefault('leverage_usage', 0.0)
        kwargs.setdefault('max_leverage_used', 0.0)
        kwargs.setdefault('alpha', 0.0)
        kwargs.setdefault('beta', 0.0)
        kwargs.setdefault('correlation', 0.0)
        kwargs.setdefault('overall_score', 0.0)
        kwargs.setdefault('risk_score', 0.0)
        kwargs.setdefault('return_score', 0.0)
        kwargs.setdefault('consistency_score', 0.0)
        kwargs.setdefault('data_quality', 1.0)
        kwargs.setdefault('confidence_level', 1.0)

        # Set timestamp defaults
        now = datetime.now(timezone.utc)
        kwargs.setdefault('calculated_at', now)
        kwargs.setdefault('created_at', now)
        kwargs.setdefault('updated_at', now)

        super().__init__(**kwargs)

    # Performance indexes
    __table_args__ = (
        Index('idx_agent_score_type', 'agent_id', 'score_type', 'period_end'),
        Index('idx_competition_scores', 'competition_entry_id', 'overall_score'),
        Index('idx_score_ranking', 'score_type', 'rank', 'period_end'),
    )

    @property
    def is_profitable(self) -> bool:
        """Check if agent is profitable for this period"""
        return self.total_return > 0

    @property
    def is_high_risk(self) -> bool:
        """Check if agent has high risk profile"""
        return self.max_drawdown > 0.30 or self.volatility > 0.50

    @property
    def is_consistent(self) -> bool:
        """Check if agent has consistent performance"""
        return self.win_rate > 0.55 and self.profit_factor > 1.5

    @property
    def risk_adjusted_score(self) -> float:
        """Calculate simplified risk-adjusted score"""
        if self.volatility == 0:
            return 0.0
        return self.annualized_return / self.volatility

    @property
    def recovery_factor(self) -> float:
        """Calculate recovery factor (net profit / max drawdown)"""
        if self.max_drawdown == 0:
            return float('inf') if self.total_return > 0 else 0.0
        return self.total_return / abs(self.max_drawdown)

    def calculate_sortino_ratio(self, target_return: float = 0.0) -> float:
        """Calculate Sortino ratio with given target return"""
        if self.total_return <= target_return:
            return 0.0
        # Simplified calculation - in practice would use downside deviation
        return (self.total_return - target_return) / self.max_drawdown if self.max_drawdown != 0 else 0.0

    def calculate_calmar_ratio(self) -> float:
        """Calculate Calmar ratio (annualized return / max drawdown)"""
        return self.annualized_return / abs(self.max_drawdown) if self.max_drawdown != 0 else 0.0

    def __repr__(self):
        return f"<Score(id={self.id}, agent_id={self.agent_id}, type={self.score_type}, overall_score={self.overall_score})>"


class Ranking(Base):
    """
    Historical ranking snapshots for competitions.

    Stores ranking data at specific time points to track
    ranking evolution over time.
    """
    __tablename__ = "rankings"

    # Primary fields
    id = Column(Integer, primary_key=True, index=True)
    competition_id = Column(Integer, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)

    # Ranking Data (JSON string containing array of rankings)
    ranking_data = Column(Text, nullable=False)  # JSON with agent_id, rank, score, etc.

    # Competition State
    total_participants = Column(Integer, nullable=False)
    active_participants = Column(Integer)

    # Market Conditions
    market_volatility = Column(Float)
    market_trend = Column(String(20))  # bull, bear, sideways

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def __init__(self, **kwargs):
        # Set timestamp defaults
        now = datetime.now(timezone.utc)
        kwargs.setdefault('created_at', now)

        super().__init__(**kwargs)

    @property
    def is_recent(self) -> bool:
        """Check if ranking is recent (within last hour)"""
        return datetime.now(timezone.utc) - self.timestamp < timedelta(hours=1)

    def __repr__(self):
        return f"<Ranking(id={self.id}, competition_id={self.competition_id}, timestamp={self.timestamp})>"


class Performance(Base):
    """
    Real-time performance tracking for agents.

    Provides current performance snapshot including
    recent trades, current positions, and live metrics.
    """
    __tablename__ = "performances"

    # Primary fields
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, unique=True, index=True)
    competition_entry_id = Column(Integer, ForeignKey("competition_entries.id"), index=True)

    # Current Capital
    current_capital = Column(Float, default=1000.0)
    available_capital = Column(Float, default=1000.0)
    used_capital = Column(Float, default=0.0)

    # Position Summary
    total_positions = Column(Integer, default=0)
    long_positions = Column(Integer, default=0)
    short_positions = Column(Integer, default=0)
    total_exposure = Column(Float, default=0.0)

    # Today's Performance
    daily_pnl = Column(Float, default=0.0)
    daily_return = Column(Float, default=0.0)
    daily_trades = Column(Integer, default=0)

    # Current Risk Metrics
    current_drawdown = Column(Float, default=0.0)
    leverage_usage = Column(Float, default=0.0)
    margin_usage = Column(Float, default=0.0)

    # Recent Activity
    last_trade_time = Column(DateTime)
    last_signal_time = Column(DateTime)
    last_update = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Status
    status = Column(String(20), default="active")  # active, paused, liquidated
    risk_alerts = Column(Integer, default=0)  # Number of active risk alerts

    # Relationships
    agent = relationship("Agent")
    competition_entry = relationship("CompetitionEntry")

    def __init__(self, **kwargs):
        # Set default values
        kwargs.setdefault('current_capital', 1000.0)
        kwargs.setdefault('available_capital', 1000.0)
        kwargs.setdefault('used_capital', 0.0)
        kwargs.setdefault('total_positions', 0)
        kwargs.setdefault('long_positions', 0)
        kwargs.setdefault('short_positions', 0)
        kwargs.setdefault('total_exposure', 0.0)
        kwargs.setdefault('daily_pnl', 0.0)
        kwargs.setdefault('daily_return', 0.0)
        kwargs.setdefault('daily_trades', 0)
        kwargs.setdefault('current_drawdown', 0.0)
        kwargs.setdefault('leverage_usage', 0.0)
        kwargs.setdefault('margin_usage', 0.0)
        kwargs.setdefault('status', 'active')
        kwargs.setdefault('risk_alerts', 0)

        # Set timestamp defaults
        now = datetime.now(timezone.utc)
        kwargs.setdefault('last_update', now)

        super().__init__(**kwargs)

    @property
    def is_active(self) -> bool:
        """Check if agent is currently active"""
        return self.status == "active"

    @property
    def has_positions(self) -> bool:
        """Check if agent has open positions"""
        return self.total_positions > 0

    @property
    def is_profitable_today(self) -> bool:
        """Check if agent is profitable today"""
        return self.daily_pnl > 0

    def __repr__(self):
        return f"<Performance(id={self.id}, agent_id={self.agent_id}, capital={self.current_capital}, status={self.status})>"
"""
Trading model for trade execution and position tracking.

Records all trading activity executed by agents including order details,
execution information, and performance metrics.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .base import Base


class Trade(Base):
    """
    Individual trade executed by an agent.

    Records complete trade lifecycle including signal generation,
    order execution, and final position closing.
    """
    __tablename__ = "trades"

    # Primary fields
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    competition_entry_id = Column(Integer, ForeignKey("competition_entries.id"), index=True)

    # Trade Identification
    symbol = Column(String(20), nullable=False, index=True)
    exchange = Column(String(50), default="binance")
    trade_group = Column(String(100), index=True)  # Groups related trades together

    # Signal Information
    signal_action = Column(String(10), nullable=False)  # BUY, SELL, HOLD
    signal_reasoning = Column(Text)  # LLM reasoning for the trade
    signal_confidence = Column(Float)  # Confidence level 0-1
    signal_timestamp = Column(DateTime, nullable=False)

    # Order Execution
    order_id = Column(String(100), index=True)  # Exchange order ID
    order_type = Column(String(20), default="MARKET")  # MARKET, LIMIT, STOP
    side = Column(String(10), nullable=False)  # BUY, SELL
    quantity = Column(Float, nullable=False)
    price = Column(Float)  # Limit price for limit orders

    # Execution Details
    executed_quantity = Column(Float, nullable=False)
    executed_price = Column(Float, nullable=False)
    execution_timestamp = Column(DateTime, nullable=False)

    # Position Information
    leverage = Column(Float, default=1.0)
    position_side = Column(String(10))  # LONG, SHORT, BOTH
    entry_price = Column(Float)  # For position trades

    # Financial Calculations
    notional_value = Column(Float)  # quantity * price * leverage
    commission = Column(Float, default=0.0)
    slippage = Column(Float, default=0.0)  # Price slippage in basis points

    # Risk Management
    stop_loss = Column(Float)  # Stop loss price level
    take_profit = Column(Float)  # Take profit price level
    max_loss_amount = Column(Float)

    # Trade Status
    status = Column(String(20), default="pending")  # pending, filled, partial, cancelled, failed

    # Performance Metrics
    pnl = Column(Float, default=0.0)  # Profit/Loss
    pnl_percentage = Column(Float, default=0.0)
    points = Column(Float, default=0.0)  # Price points gained/lost

    # Trade Duration
    duration_seconds = Column(Integer)  # How long the position was held
    bars_held = Column(Integer)  # Number of price bars held

    # Exit Information
    exit_reason = Column(String(50))  # stop_loss, take_profit, signal, timeout, manual
    exit_price = Column(Float)  # Exit price for closed positions
    exit_timestamp = Column(DateTime)

    # Context Data
    market_conditions = Column(Text)  # JSON string with market context
    technical_indicators = Column(Text)  # JSON string with technical analysis
    agent_state = Column(Text)  # JSON string with agent's internal state

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    agent = relationship("Agent", back_populates="trades")
    competition_entry = relationship("CompetitionEntry")

    def __init__(self, **kwargs):
        # Set default values
        kwargs.setdefault('exchange', 'binance')
        kwargs.setdefault('order_type', 'MARKET')
        kwargs.setdefault('pnl', 0.0)
        kwargs.setdefault('pnl_percentage', 0.0)
        kwargs.setdefault('points', 0.0)
        kwargs.setdefault('commission', 0.0)
        kwargs.setdefault('slippage', 0.0)

        # Set timestamp defaults
        now = datetime.now(timezone.utc)
        kwargs.setdefault('created_at', now)
        kwargs.setdefault('updated_at', now)

        super().__init__(**kwargs)

    # Performance indexes
    __table_args__ = (
        Index('idx_agent_symbol_time', 'agent_id', 'symbol', 'execution_timestamp'),
        Index('idx_competition_trades', 'competition_entry_id', 'execution_timestamp'),
        Index('idx_trade_status', 'status', 'created_at'),
    )

    @property
    def is_buy(self) -> bool:
        """Check if this is a buy trade"""
        return self.side.upper() == "BUY"

    @property
    def is_sell(self) -> bool:
        """Check if this is a sell trade"""
        return self.side.upper() == "SELL"

    @property
    def is_long_position(self) -> bool:
        """Check if this opens a long position"""
        return self.position_side == "LONG"

    @property
    def is_short_position(self) -> bool:
        """Check if this opens a short position"""
        return self.position_side == "SHORT"

    @property
    def is_filled(self) -> bool:
        """Check if trade was successfully filled"""
        return self.status == "filled"

    @property
    def is_profitable(self) -> bool:
        """Check if trade is profitable"""
        return self.pnl > 0

    @property
    def calculated_notional_value(self) -> float:
        """Calculate notional value from executed quantity, price, and leverage"""
        if not self.executed_quantity or not self.executed_price:
            return 0.0
        if self.executed_quantity == 0 or self.executed_price == 0:
            return 0.0
        return self.executed_quantity * self.executed_price * (self.leverage or 1.0)

    @property
    def return_percentage(self) -> float:
        """Calculate return as percentage"""
        notional = self.notional_value or self.calculated_notional_value
        if not notional or notional == 0:
            return 0.0
        if not self.pnl:
            return 0.0
        return (self.pnl / notional) * 100

    @property
    def execution_cost(self) -> float:
        """Calculate total execution cost including commission and slippage"""
        notional = self.notional_value or self.calculated_notional_value
        if not notional:
            return self.commission or 0.0
        slippage_cost = (self.slippage or 0.0) * notional / 10000
        return (self.commission or 0.0) + slippage_cost

    def calculate_roi(self, initial_capital: float) -> float:
        """Calculate ROI based on initial capital"""
        if initial_capital == 0:
            return 0.0
        return (self.pnl / initial_capital) * 100

    def __repr__(self):
        return f"<Trade(id={self.id}, agent_id={self.agent_id}, symbol={self.symbol}, side={self.side}, pnl={self.pnl})>"


class Position(Base):
    """
    Current open positions for agents.

    Tracks real-time position data including market value,
    unrealized P&L, and risk metrics.
    """
    __tablename__ = "positions"

    # Primary fields
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    competition_entry_id = Column(Integer, ForeignKey("competition_entries.id"), index=True)

    # Position Identification
    symbol = Column(String(20), nullable=False, index=True)
    exchange = Column(String(50), default="binance")
    position_side = Column(String(10), nullable=False)  # LONG, SHORT

    # Position Size
    quantity = Column(Float, nullable=False)
    notional_value = Column(Float, nullable=False)
    leverage = Column(Float, default=1.0)

    # Entry Details
    entry_price = Column(Float, nullable=False)
    entry_timestamp = Column(DateTime, nullable=False)
    entry_order_id = Column(String(100))

    # Current Market Data
    mark_price = Column(Float, nullable=False)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Financial Metrics
    unrealized_pnl = Column(Float, default=0.0)
    unrealized_pnl_percentage = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)

    # Risk Metrics
    margin_used = Column(Float, default=0.0)
    margin_ratio = Column(Float, default=0.0)
    liquidation_price = Column(Float)

    # Risk Management
    stop_loss = Column(Float)
    take_profit = Column(Float)
    trailing_stop = Column(Float)
    max_loss_amount = Column(Float)

    # Position Status
    status = Column(String(20), default="open")  # open, closing, closed

    # Relationships
    agent = relationship("Agent")
    competition_entry = relationship("CompetitionEntry")

    def __init__(self, **kwargs):
        # Set default values
        kwargs.setdefault('exchange', 'binance')
        kwargs.setdefault('leverage', 1.0)
        kwargs.setdefault('unrealized_pnl', 0.0)
        kwargs.setdefault('unrealized_pnl_percentage', 0.0)
        kwargs.setdefault('realized_pnl', 0.0)
        kwargs.setdefault('margin_used', 0.0)
        kwargs.setdefault('margin_ratio', 0.0)
        kwargs.setdefault('status', 'open')

        # Set timestamp defaults
        now = datetime.now(timezone.utc)
        kwargs.setdefault('last_updated', now)

        super().__init__(**kwargs)

    # Unique constraint
    __table_args__ = (
        Index('idx_agent_position', 'agent_id', 'symbol', 'position_side', unique=True),
    )

    @property
    def is_long(self) -> bool:
        """Check if this is a long position"""
        return self.position_side == "LONG"

    @property
    def is_short(self) -> bool:
        """Check if this is a short position"""
        return self.position_side == "SHORT"

    @property
    def is_profitable(self) -> bool:
        """Check if position is currently profitable"""
        return self.unrealized_pnl > 0

    @property
    def is_open(self) -> bool:
        """Check if position is still open"""
        return self.status == "open"

    @property
    def return_percentage(self) -> float:
        """Calculate return as percentage of notional value"""
        if not self.notional_value or self.notional_value == 0:
            return 0.0
        if not self.unrealized_pnl:
            return 0.0
        return self.unrealized_pnl / self.notional_value

    def calculate_unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L based on current price"""
        if not current_price or not self.entry_price or not self.quantity:
            return 0.0
        if current_price == 0 or self.entry_price == 0 or self.quantity == 0:
            return 0.0

        if self.is_long:
            return (current_price - self.entry_price) * self.quantity
        else:  # SHORT
            return (self.entry_price - current_price) * self.quantity

    def __repr__(self):
        return f"<Position(id={self.id}, agent_id={self.agent_id}, symbol={self.symbol}, side={self.position_side}, pnl={self.unrealized_pnl})>"
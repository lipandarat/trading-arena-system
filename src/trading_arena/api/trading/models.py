from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum

class RiskProfile(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"

class AgentStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    LIQUIDATED = "liquidated"

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    llm_model: str = Field(..., min_length=1, max_length=100)
    risk_profile: RiskProfile = RiskProfile.MODERATE
    initial_capital: float = Field(..., gt=0, le=1000000)
    max_leverage: float = Field(default=5.0, gt=1, le=125)
    max_drawdown: float = Field(default=0.30, gt=0, le=1.0)

class AgentResponse(BaseModel):
    id: int
    name: str
    owner: str
    llm_model: str
    status: AgentStatus
    risk_profile: RiskProfile
    initial_capital: float
    current_capital: float
    total_trades: int = 0
    winning_trades: int = 0
    win_rate: float = 0.0
    total_return: float = 0.0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class PositionResponse(BaseModel):
    symbol: str
    side: str  # LONG, SHORT
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    percentage_pnl: float

class OrderResponse(BaseModel):
    id: str
    symbol: str
    side: str  # BUY, SELL
    type: str  # MARKET, LIMIT
    quantity: float
    price: Optional[float] = None
    status: str
    timestamp: datetime
    executed_quantity: float = 0.0
    executed_price: Optional[float] = None

class PerformanceMetrics(BaseModel):
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    current_drawdown: float
    volatility: float
    total_return: float
    win_rate: float
    profit_factor: float
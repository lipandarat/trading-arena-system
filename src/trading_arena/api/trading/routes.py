from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
import uuid
from datetime import datetime, timezone
from trading_arena.api.auth.jwt_handler import JWTHandler
from trading_arena.api.trading.models import (
    AgentCreate, AgentResponse, PositionResponse,
    OrderResponse, PerformanceMetrics
)
from trading_arena.db import get_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from trading_arena.models import Agent, Trade, Position
from trading_arena.risk.manager import RiskManager
from trading_arena.agents.agent_interface import Position as AgentPosition

router = APIRouter()
security = HTTPBearer()
jwt_handler = JWTHandler()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    """Dependency to get authenticated user"""
    try:
        token_data = jwt_handler.verify_token(credentials.credentials)
        return token_data
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication"
        )

@router.get("/agents", response_model=List[AgentResponse])
async def get_agents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get user's trading agents"""
    # Query agents from database
    result = await db.execute(
        select(Agent)
        .where(Agent.owner == user["username"])
        .order_by(Agent.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    agents = result.scalars().all()

    # Convert to response models
    agent_responses = []
    for agent in agents:
        agent_responses.append(AgentResponse(
            id=agent.id,
            name=agent.name,
            owner=agent.owner,
            llm_model=agent.llm_model,
            status=agent.status,
            risk_profile=agent.risk_profile,
            initial_capital=agent.initial_capital,
            current_capital=agent.current_capital,
            total_trades=agent.total_trades,
            winning_trades=agent.winning_trades,
            win_rate=agent.win_rate,
            total_return=agent.current_return,
            created_at=agent.created_at.isoformat(),
            updated_at=agent.updated_at.isoformat()
        ))

    return agent_responses

@router.post("/agents", response_model=AgentResponse)
async def create_agent(
    agent_data: AgentCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Create new trading agent"""
    # Check if agent name already exists for this user
    existing_result = await db.execute(
        select(Agent).where(
            and_(Agent.name == agent_data.name, Agent.owner == user["username"])
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent with this name already exists"
        )

    # Create new agent
    new_agent = Agent(
        name=agent_data.name,
        owner=user["username"],
        llm_model=agent_data.llm_model,
        risk_profile=agent_data.risk_profile,
        initial_capital=agent_data.initial_capital,
        current_capital=agent_data.initial_capital,
        status="active"
    )

    # Save to database
    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)

    # Return response
    return AgentResponse(
        id=new_agent.id,
        name=new_agent.name,
        owner=new_agent.owner,
        llm_model=new_agent.llm_model,
        status=new_agent.status,
        risk_profile=new_agent.risk_profile,
        initial_capital=new_agent.initial_capital,
        current_capital=new_agent.current_capital,
        total_trades=new_agent.total_trades,
        winning_trades=new_agent.winning_trades,
        win_rate=new_agent.win_rate,
        total_return=new_agent.current_return,
        created_at=new_agent.created_at.isoformat(),
        updated_at=new_agent.updated_at.isoformat()
    )

@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get specific agent details"""
    # Query agent from database
    result = await db.execute(
        select(Agent).where(
            and_(Agent.id == agent_id, Agent.owner == user["username"])
        )
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    # Return agent details
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        owner=agent.owner,
        llm_model=agent.llm_model,
        status=agent.status,
        risk_profile=agent.risk_profile,
        initial_capital=agent.initial_capital,
        current_capital=agent.current_capital,
        total_trades=agent.total_trades,
        winning_trades=agent.winning_trades,
        win_rate=agent.win_rate,
        total_return=agent.current_return,
        created_at=agent.created_at.isoformat(),
        updated_at=agent.updated_at.isoformat()
    )

@router.post("/agents/{agent_id}/start")
async def start_agent(
    agent_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Start trading agent"""
    try:
        # Get agent from database
        result = await db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        agent = result.scalar_one_or_none()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        if agent.owner != user["username"]:
            raise HTTPException(status_code=403, detail="Not authorized to start this agent")

        agent.status = "running"
        db.add(agent)
        await db.commit()

        return {"message": f"Agent {agent_id} started successfully", "status": "running"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start agent: {str(e)}")

@router.post("/agents/{agent_id}/stop")
async def stop_agent(
    agent_id: int,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Stop trading agent"""
    try:
        # Get agent from database
        result = await db.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        agent = result.scalar_one_or_none()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        if agent.owner != user["username"]:
            raise HTTPException(status_code=403, detail="Not authorized to stop this agent")

        agent.status = "stopped"
        db.add(agent)
        await db.commit()

        return {"message": f"Agent {agent_id} stopped successfully", "status": "stopped"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop agent: {str(e)}")

@router.get("/positions", response_model=List[PositionResponse])
async def get_positions(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get current open positions"""
    # Query open positions for user's agents
    result = await db.execute(
        select(Position)
        .join(Agent, Position.agent_id == Agent.id)
        .where(
            and_(
                Agent.owner == user["username"],
                Position.status == "open"
            )
        )
        .order_by(Position.last_updated.desc())
    )
    positions = result.scalars().all()

    # Convert to response models
    position_responses = []
    for position in positions:
        position_responses.append(PositionResponse(
            symbol=position.symbol,
            side=position.position_side,
            size=position.quantity,
            entry_price=position.entry_price,
            mark_price=position.mark_price,
            unrealized_pnl=position.unrealized_pnl,
            percentage_pnl=position.unrealized_pnl_percentage
        ))

    return position_responses

@router.get("/orders", response_model=List[OrderResponse])
async def get_orders(
    limit: int = Query(100, ge=1, le=1000),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get order history"""
    # Query trades (orders) for user's agents
    result = await db.execute(
        select(Trade)
        .join(Agent, Trade.agent_id == Agent.id)
        .where(Agent.owner == user["username"])
        .order_by(Trade.execution_timestamp.desc())
        .limit(limit)
    )
    trades = result.scalars().all()

    # Convert to response models
    order_responses = []
    for trade in trades:
        order_responses.append(OrderResponse(
            id=str(trade.id),
            symbol=trade.symbol,
            side=trade.side,
            type=trade.order_type,
            quantity=trade.quantity,
            status=trade.status,
            timestamp=trade.execution_timestamp.isoformat(),
            executed_quantity=trade.executed_quantity,
            executed_price=trade.executed_price
        ))

    return order_responses

@router.get("/performance", response_model=PerformanceMetrics)
async def get_performance_metrics(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get performance analytics"""
    # Get user's agents
    agents_result = await db.execute(
        select(Agent).where(Agent.owner == user["username"])
    )
    agents = agents_result.scalars().all()

    if not agents:
        return PerformanceMetrics(
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            current_drawdown=0.0,
            volatility=0.0,
            total_return=0.0,
            win_rate=0.0,
            profit_factor=0.0
        )

    # Calculate aggregate performance metrics
    total_trades = sum(agent.total_trades for agent in agents)
    total_winning_trades = sum(agent.winning_trades for agent in agents)
    total_initial_capital = sum(agent.initial_capital for agent in agents)
    total_current_capital = sum(agent.current_capital for agent in agents)

    # Get trades for detailed calculations
    trades_result = await db.execute(
        select(Trade)
        .join(Agent, Trade.agent_id == Agent.id)
        .where(Agent.owner == user["username"])
        .where(Trade.status == "filled")
    )
    trades = trades_result.scalars().all()

    # Calculate metrics
    win_rate = (total_winning_trades / total_trades) if total_trades > 0 else 0.0
    total_return = ((total_current_capital - total_initial_capital) / total_initial_capital) if total_initial_capital > 0 else 0.0

    # Calculate profit factor
    winning_pnl = sum(trade.pnl for trade in trades if trade.pnl and trade.pnl > 0)
    losing_pnl = abs(sum(trade.pnl for trade in trades if trade.pnl and trade.pnl < 0))
    profit_factor = (winning_pnl / losing_pnl) if losing_pnl > 0 else float('inf') if winning_pnl > 0 else 0.0

    # Calculate real metrics using RiskManager
    risk_manager = RiskManager(lookback_days=30)

    # Get current positions for all agents
    positions_result = await db.execute(
        select(Position)
        .join(Agent, Position.agent_id == Agent.id)
        .where(and_(
            Agent.owner == user["username"],
            Position.status == "open"
        ))
    )
    positions = positions_result.scalars().all()

    # Convert to AgentPosition format for risk calculation
    agent_positions = [
        AgentPosition(
            symbol=pos.symbol,
            side=pos.position_side,
            size=pos.quantity,
            entry_price=pos.entry_price,
            mark_price=pos.mark_price or pos.entry_price,
            unrealized_pnl=pos.unrealized_pnl or 0.0
        )
        for pos in positions
    ]

    # Calculate risk metrics if we have trades
    if trades:
        risk_metrics = risk_manager.calculate_risk_metrics(
            trades=list(trades),
            positions=agent_positions,
            current_capital=total_current_capital,
            initial_capital=total_initial_capital
        )

        return PerformanceMetrics(
            sharpe_ratio=risk_metrics.sharpe_ratio,
            sortino_ratio=risk_metrics.sortino_ratio,
            max_drawdown=risk_metrics.max_drawdown,
            current_drawdown=risk_metrics.current_drawdown,
            volatility=risk_metrics.volatility,
            total_return=total_return,
            win_rate=win_rate,
            profit_factor=profit_factor
        )
    else:
        # Return zeros if no trades yet
        return PerformanceMetrics(
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            current_drawdown=0.0,
            volatility=0.0,
            total_return=total_return,
            win_rate=win_rate,
            profit_factor=profit_factor
        )
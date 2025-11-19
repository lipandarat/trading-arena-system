from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from trading_arena.api.auth.models import UserLogin, UserResponse, Token
from trading_arena.api.auth.jwt_handler import JWTHandler
from trading_arena.config import config
from trading_arena.db import get_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from trading_arena.models import Agent

router = APIRouter()
security = HTTPBearer()
jwt_handler = JWTHandler()

@router.post("/login", response_model=Token)
async def login(user_data: UserLogin, db: AsyncSession = Depends(get_db_session)):
    """Authenticate user and return JWT token"""
    # Validate credentials against configuration
    admin_username, admin_password = config.get_admin_credentials()

    if user_data.username != admin_username or user_data.password != admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if admin user has agents in database
    result = await db.execute(
        select(Agent).where(Agent.owner == user_data.username)
    )
    agents_count = len(result.scalars().all())

    # Generate JWT token with user info
    token_data = {
        "user_id": 1,
        "username": user_data.username,
        "role": "admin",
        "agents_count": agents_count
    }
    access_token = jwt_handler.create_access_token(token_data)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 1800  # 30 minutes
    }

@router.get("/profile", response_model=UserResponse)
async def get_profile(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db_session)
):
    """Get current user profile"""
    try:
        token_data = jwt_handler.verify_token(credentials.credentials)

        # Get user's agents count from database
        result = await db.execute(
            select(Agent).where(Agent.owner == token_data["username"])
        )
        agents = result.scalars().all()

        # Calculate total capital across all agents
        total_capital = sum(agent.current_capital for agent in agents)

        return UserResponse(
            id=token_data["user_id"],
            username=token_data["username"],
            email=f"{token_data['username']}@trading-arena.com",
            role=token_data["role"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
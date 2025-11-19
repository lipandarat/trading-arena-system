import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from trading_arena.api.auth.routes import router as auth_router
from trading_arena.api.trading.routes import router as trading_router
from trading_arena.api.middleware import (
    LoggingMiddleware,
    SecurityHeadersMiddleware,
    AdvancedRateLimitMiddleware,
    InputValidationMiddleware,
    CSRFProtectionMiddleware
)
from trading_arena.config import config
from trading_arena.db import validate_database_startup

# Configure CORS based on environment
environment = os.getenv("ENVIRONMENT", "development")
if environment == "production":
    allowed_origins = [
        "https://arena-trading.com",
        "https://www.arena-trading.com",
        "https://api.arena-trading.com"
    ]
else:
    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://arena-frontend:3000"
    ]

app = FastAPI(
    title="Trading Arena API",
    description="Autonomous Futures Trading Competition Platform",
    version="1.0.0",
    docs_url="/api/docs" if environment != "production" else None,
    redoc_url="/api/redoc" if environment != "production" else None,
    openapi_url="/openapi.json" if environment != "production" else None
)

# Security middleware (order matters - first to execute)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(InputValidationMiddleware)
app.add_middleware(CSRFProtectionMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Requested-With",
        "X-CSRF-Token"
    ],
)

# Rate limiting and logging
app.add_middleware(AdvancedRateLimitMiddleware, default_calls=100, default_period=60)
app.add_middleware(LoggingMiddleware)

# Include routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(trading_router, prefix="/api/v1/trading", tags=["Trading"])

@app.on_event("startup")
async def startup_event():
    """Validate database connection on startup."""
    try:
        is_valid = await validate_database_startup()
        if not is_valid:
            raise RuntimeError("Database validation failed on startup")
        print("✅ Database validation passed on startup")
    except Exception as e:
        print(f"❌ Startup validation failed: {e}")
        raise

@app.get("/")
async def root():
    return {"message": "Trading Arena API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "trading-arena-api"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
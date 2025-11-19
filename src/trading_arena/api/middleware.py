import time
import logging
import hashlib
import secrets
from typing import Dict, List
from collections import defaultdict, deque
from fastapi import Request, HTTPException, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Log request
        logger.info(f"Request: {request.method} {request.url.path}")

        response = await call_next(request)

        # Log response
        process_time = time.time() - start_time
        logger.info(f"Response: {response.status_code} in {process_time:.3f}s")

        response.headers["X-Process-Time"] = str(process_time)
        return response

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.clients = {}

    async def dispatch(self, request: Request, call_next):
        # Simple rate limiting by client IP
        client_ip = request.client.host
        now = time.time()

        # Clean old entries
        if client_ip in self.clients:
            self.clients[client_ip] = [
                call_time for call_time in self.clients[client_ip]
                if now - call_time < self.period
            ]
        else:
            self.clients[client_ip] = []

        # Check rate limit
        if len(self.clients[client_ip]) >= self.calls:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        self.clients[client_ip].append(now)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )

        # Remove server information
        response.headers["Server"] = "TradingArena"

        return response


class AdvancedRateLimitMiddleware(BaseHTTPMiddleware):
    """Advanced rate limiting with different limits per endpoint."""

    def __init__(self, app, default_calls: int = 100, default_period: int = 60):
        super().__init__(app)
        self.default_calls = default_calls
        self.default_period = default_period
        self.limits = {
            # Auth endpoints - stricter limits
            "/api/v1/auth/login": {"calls": 5, "period": 300},  # 5 per 5 minutes
            "/api/v1/auth/register": {"calls": 3, "period": 300},  # 3 per 5 minutes
            "/api/v1/auth/refresh": {"calls": 10, "period": 60},  # 10 per minute

            # Trading endpoints - moderate limits
            "/api/v1/trading/agents": {"calls": 50, "period": 60},
            "/api/v1/trading/agent": {"calls": 30, "period": 60},

            # Health check - very permissive
            "/health": {"calls": 1000, "period": 60},
        }
        self.clients: Dict[str, deque] = defaultdict(deque)

    def _get_limit(self, path: str) -> Dict[str, int]:
        """Get rate limit for specific path."""
        for limit_path, limit_config in self.limits.items():
            if path.startswith(limit_path):
                return limit_config
        return {"calls": self.default_calls, "period": self.default_period}

    def _get_client_key(self, request: Request) -> str:
        """Generate client key for rate limiting."""
        # Use IP + User-Agent hash for better client identification
        user_agent = request.headers.get("user-agent", "")
        ip = request.client.host
        client_string = f"{ip}:{user_agent}"
        return hashlib.sha256(client_string.encode()).hexdigest()[:16]

    async def dispatch(self, request: Request, call_next):
        # Skip health checks from rate limiting
        if request.url.path == "/health":
            return await call_next(request)

        client_key = self._get_client_key(request)
        now = time.time()
        limit_config = self._get_limit(request.url.path)

        # Clean old entries
        client_requests = self.clients[client_key]
        while client_requests and now - client_requests[0] > limit_config["period"]:
            client_requests.popleft()

        # Check rate limit
        if len(client_requests) >= limit_config["calls"]:
            logger.warning(f"Rate limit exceeded for {client_key} on {request.url.path}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "limit": limit_config["calls"],
                    "period": limit_config["period"],
                    "retry_after": int(limit_config["period"] - (now - client_requests[0]))
                }
            )

        # Add current request
        client_requests.append(now)

        # Add rate limit headers
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit_config["calls"])
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, limit_config["calls"] - len(client_requests))
        )
        response.headers["X-RateLimit-Reset"] = str(
            int(client_requests[0] + limit_config["period"]) if client_requests else int(now + limit_config["period"])
        )

        return response


class InputValidationMiddleware(BaseHTTPMiddleware):
    """Validate input for common attack patterns."""

    async def dispatch(self, request: Request, call_next):
        # Check for common attack patterns in URL
        suspicious_patterns = [
            "<script", "</script>", "javascript:", "vbscript:", "onload=", "onerror=",
            "../", "..\\", "etc/passwd", "etc/shadow", "cmd.exe", "powershell"
        ]

        url_path = request.url.path.lower()
        query_string = str(request.url.query).lower()

        for pattern in suspicious_patterns:
            if pattern in url_path or pattern in query_string:
                logger.warning(f"Suspicious pattern detected: {pattern} in {request.url}")
                raise HTTPException(status_code=400, detail="Invalid request")

        # Check request body size for POST/PUT requests
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > 10 * 1024 * 1024:  # 10MB limit
                raise HTTPException(status_code=413, detail="Request entity too large")

        return await call_next(request)


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """Basic CSRF protection for state-changing requests."""

    def __init__(self, app, exempt_paths: List[str] = None):
        super().__init__(app)
        self.exempt_paths = exempt_paths or [
            "/health", "/api/docs", "/api/redoc", "/api/v1/auth/login", "/api/v1/auth/register"
        ]

    async def dispatch(self, request: Request, call_next):
        # Skip CSRF for exempt paths and GET requests
        if (request.method in ["GET", "HEAD", "OPTIONS"] or
            any(request.url.path.startswith(path) for path in self.exempt_paths)):
            return await call_next(request)

        # Check Origin header for state-changing requests
        origin = request.headers.get("origin")
        host = request.headers.get("host")

        if origin and host:
            # Basic origin validation
            if not origin.endswith(host.replace(":", "").replace("/", "")):
                logger.warning(f"CSRF attempt blocked: {origin} vs {host}")
                raise HTTPException(status_code=403, detail="CSRF validation failed")

        return await call_next(request)
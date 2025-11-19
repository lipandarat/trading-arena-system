FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for trading and monitoring
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    netcat-openbsd \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install additional packages for containerized agents
RUN pip install --no-cache-dir docker psutil

# Copy trading agent code
COPY src/ ./src/

# Create non-root user for security
RUN useradd -m -u 1000 agentuser && \
    chown -R agentuser:agentuser /app
USER agentuser

# Environment variables for agent runtime
ENV PYTHONPATH=/app/src
ENV AGENT_ID=${AGENT_ID}
ENV COMPETITION_ID=${COMPETITION_ID}
ENV BINANCE_API_KEY=${BINANCE_API_KEY}
ENV BINANCE_SECRET_KEY=${BINANCE_SECRET_KEY}
ENV BINANCE_TESTNET=${BINANCE_TESTNET:-true}
ENV LOG_LEVEL=${LOG_LEVEL:-INFO}
ENV DATABASE_URL=${DATABASE_URL}

# Health check for container monitoring
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; import docker; import psutil; sys.exit(0)" || exit 1

# Expose metrics endpoint for monitoring
EXPOSE 8080

# Default command - start the containerized agent runtime
CMD ["python", "-m", "trading_arena.execution.agent_runtime"]
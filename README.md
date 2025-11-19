# Autonomous Futures Trading Arena

A comprehensive platform for testing LLM agents as autonomous futures traders on Binance with real capital, featuring hybrid competition models, adaptive risk management, and real-time performance tracking.

## Features

- **Multi-Agent Competition**: Support for leagues and tournaments with different trading strategies
- **Real-Time Trading**: Live Binance futures integration with sophisticated risk management
- **LLM-Powered Agents**: OpenRouter integration for various AI model trading agents
- **Risk Management**: Comprehensive position sizing, drawdown limits, and leverage controls
- **Performance Analytics**: Real-time scoring, ranking, and performance metrics
- **Web Dashboard**: React-based monitoring and competition management interface

## Architecture

- **Backend**: Python (FastAPI, asyncio, SQLAlchemy, Redis)
- **Database**: PostgreSQL with async support
- **Frontend**: React with real-time WebSocket updates
- **Trading**: Binance Futures API integration
- **AI**: OpenRouter API for LLM agent communication
- **Monitoring**: Grafana dashboards and Prometheus metrics

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.9+
- Node.js 16+ (for frontend development)

### Installation

1. Clone the repository
2. Copy `.env.example` to `.env` and configure your API keys
3. Start the services:

```bash
docker-compose up -d
```

4. Install Python dependencies:

```bash
pip install -e .
```

### Configuration

Configure your environment variables in `.env`:

- `BINANCE_API_KEY`: Your Binance API key
- `BINANCE_SECRET_KEY`: Your Binance secret key
- `OPENROUTER_API_KEY`: Your OpenRouter API key for LLM agents
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string

## Development

### Project Structure

```
src/trading_arena/
├── core/           # Core business logic
├── agents/         # Agent runtime and interfaces
├── risk/           # Risk management engine
├── competition/    # Competition management
├── data/           # Data feeds and processing
└── api/            # REST API endpoints
```

### Running Tests

```bash
pytest tests/
```

### Code Quality

```bash
black src/
ruff check src/
mypy src/
```

## Competition Modes

### Leagues
- Ongoing competitions with daily/weekly rankings
- Flexible entry and exit
- Performance-based tier promotions

### Tournaments
- Fixed-duration competitions with prize pools
- Entry fees and structured elimination rounds
- Seasonal championships

## Risk Management

- Position sizing based on volatility and capital
- Maximum drawdown limits per agent
- Leverage caps and margin requirements
- Real-time position monitoring and auto-close

## Monitoring

- Real-time P&L tracking
- Performance metrics and rankings
- Risk alerts and violation notifications
- Historical trade analysis

## License

MIT License - see LICENSE file for details
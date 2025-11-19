"""
Containerized Agent Runtime for Autonomous Trading.

Provides the main runtime environment for agents running in Docker containers.
Integrates with existing trading systems including Binance client, database models,
and agent interfaces. Handles container-specific concerns like health monitoring,
graceful shutdown, and resource management.
"""

import asyncio
import logging
import os
import signal
import sys
import json
import traceback
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any
import aiohttp

# Import existing trading systems
from trading_arena.agents.runtime import AgentRuntime
from trading_arena.agents.agent_interface import AgentInterface, TradingSignal
from trading_arena.exchanges.binance_client import BinanceFuturesClient
from trading_arena.db import get_db_session
from trading_arena.models.agent import Agent
from trading_arena.models.trading import Trade, Position
from trading_arena.models.competition import CompetitionEntry

logger = logging.getLogger(__name__)

class ContainerAgentRuntime:
    """
    Runtime environment for containerized autonomous trading agents.

    Manages the complete lifecycle of an agent running in a Docker container:
    - Initialize exchange connections and database sessions
    - Load agent configuration from database
    - Start trading loops with proper signal handling
    - Monitor health and performance metrics
    - Handle graceful shutdown and cleanup
    """

    def __init__(self):
        """Initialize the containerized agent runtime."""
        self.agent_id = os.getenv('AGENT_ID')
        self.competition_id = os.getenv('COMPETITION_ID')
        self.database_url = os.getenv('DATABASE_URL')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

        # Runtime state
        self.runtime: Optional[AgentRuntime] = None
        self.exchange_client: Optional[BinanceFuturesClient] = None
        self.agent: Optional[AgentInterface] = None
        self.is_running = False
        self.start_time = datetime.now(timezone.utc)

        # Health monitoring
        self.health_metrics = {
            'last_heartbeat': datetime.now(timezone.utc),
            'last_trade': None,
            'total_signals': 0,
            'successful_trades': 0,
            'errors': []
        }

        # Configure logging
        self._configure_logging()

    def _configure_logging(self):
        """Configure logging for the containerized agent."""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

        # Setup basic logging first
        handlers = [logging.StreamHandler(sys.stdout)]

        # Try to add file handler, but don't fail if directory doesn't exist yet
        try:
            os.makedirs('/tmp/agent_data', exist_ok=True)
            handlers.append(logging.FileHandler('/tmp/agent_data/agent.log', mode='a'))
        except (OSError, PermissionError):
            # If we can't create the directory or file, just use console output
            pass

        logging.basicConfig(
            level=getattr(logging, self.log_level),
            format=log_format,
            handlers=handlers,
            force=True  # Override any existing configuration
        )

        # Set specific logger levels
        logging.getLogger('websockets').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)

    async def start(self):
        """
        Start the agent in container environment.

        Performs complete initialization including:
        - Environment validation
        - Exchange client setup
        - Agent configuration loading
        - Runtime startup
        - Health monitoring
        """
        if not self.agent_id or not self.competition_id:
            logger.error("AGENT_ID and COMPETITION_ID environment variables required")
            sys.exit(1)

        logger.info(f"Starting containerized agent {self.agent_id} in competition {self.competition_id}")

        try:
            # Validate environment
            await self._validate_environment()

            # Initialize exchange client
            await self._initialize_exchange_client()

            # Load agent configuration
            agent_config = await self._load_agent_config()
            if not agent_config:
                logger.error(f"Failed to load configuration for agent {self.agent_id}")
                sys.exit(1)

            # Create agent instance
            self.agent = await self._create_agent_instance(agent_config)

            # Initialize runtime
            self.runtime = AgentRuntime(self.agent, self.exchange_client)
            self.is_running = True

            # Set up signal handlers for graceful shutdown
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGUSR1, self._health_check_signal_handler)

            # Register agent with competition
            await self._register_with_competition()

            # Start health monitoring
            asyncio.create_task(self._health_monitoring_loop())

            # Start metrics reporting
            asyncio.create_task(self._metrics_reporting_loop())

            # Start trading loop
            trading_symbols = await self._get_trading_symbols()
            logger.info(f"Starting trading loop with symbols: {trading_symbols}")
            await self.runtime.start(trading_symbols, update_interval=60)

        except Exception as e:
            logger.error(f"Agent runtime failed: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            await self._cleanup()
            sys.exit(1)

    async def _validate_environment(self):
        """Validate that required environment variables are set and valid."""
        required_vars = ['AGENT_ID', 'COMPETITION_ID', 'DATABASE_URL']
        missing_vars = []
        invalid_vars = []

        # Check for missing environment variables
        for var in required_vars:
            value = os.getenv(var)
            if not value:
                missing_vars.append(var)
            elif var == 'AGENT_ID':
                try:
                    int(value)
                except ValueError:
                    invalid_vars.append(f"{var} must be a valid integer, got: {value}")
            elif var == 'COMPETITION_ID':
                try:
                    int(value)
                except ValueError:
                    invalid_vars.append(f"{var} must be a valid integer, got: {value}")
            elif var == 'DATABASE_URL':
                if not value.startswith(('postgresql://', 'sqlite:///', 'mysql://')):
                    invalid_vars.append(f"{var} must be a valid database URL, got: {value}")

        if missing_vars:
            raise ValueError(f"Missing required environment variables: {missing_vars}")

        if invalid_vars:
            raise ValueError(f"Invalid environment variables: {invalid_vars}")

        # Create data directory
        os.makedirs('/tmp/agent_data', exist_ok=True)

        # Note: Database connection will be tested when actually used
        # This avoids connection issues during container startup validation

    async def _initialize_exchange_client(self):
        """Initialize Binance futures client."""
        api_key = os.getenv('BINANCE_API_KEY')
        secret_key = os.getenv('BINANCE_SECRET_KEY')
        testnet = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'

        # FAIL FAST - Require real credentials in production
        environment = os.getenv('ENVIRONMENT', 'development').lower()
        if environment == 'production':
            if not api_key or not secret_key:
                raise ValueError(
                    "PRODUCTION ERROR: BINANCE_API_KEY and BINANCE_SECRET_KEY must be set in production. "
                    "No mock clients allowed in production environment."
                )
        elif not api_key or not secret_key:
            # Only allow mock in development with explicit warning
            logger.error(
                "No Binance credentials provided. In development mode, set BINANCE_API_KEY and "
                "BINANCE_SECRET_KEY for real trading or use the validate_production.py script to "
                "check your configuration."
            )
            raise ValueError(
                "BINANCE_API_KEY and BINANCE_SECRET_KEY must be set. "
                "Mock clients have been removed for security."
            )

        self.exchange_client = BinanceFuturesClient(
            api_key=api_key,
            secret_key=secret_key,
            testnet=testnet
        )

        await self.exchange_client.connect()
        logger.info(f"Exchange client initialized (testnet: {testnet}, environment: {environment})")

    async def _load_agent_config(self) -> Optional[Dict[str, Any]]:
        """Load agent configuration from database."""
        try:
            async with get_db_session() as session:
                # Load agent from database
                agent = await session.get(Agent, int(self.agent_id))
                if not agent:
                    logger.error(f"Agent {self.agent_id} not found in database")
                    return None

                # Load competition entry
                from sqlalchemy import select
                comp_query = select(CompetitionEntry).where(
                    CompetitionEntry.agent_id == int(self.agent_id),
                    CompetitionEntry.competition_id == int(self.competition_id)
                )
                comp_result = await session.execute(comp_query)
                competition_entry = comp_result.scalar_one_or_none()

                config = {
                    'agent_id': int(self.agent_id),
                    'competition_id': int(self.competition_id),
                    'llm_model': agent.llm_model,
                    'llm_config': json.loads(agent.llm_config or '{}'),
                    'risk_profile': agent.risk_profile,
                    'max_leverage': agent.max_leverage,
                    'max_drawdown': agent.max_drawdown,
                    'max_position_ratio': agent.max_position_ratio,
                    'initial_capital': agent.initial_capital,
                    'current_capital': agent.current_capital,
                    'risk_per_trade': 0.02,  # 2% risk per trade
                    'competition_config': competition_entry.config if competition_entry else {}
                }

                logger.info(f"Loaded configuration for agent {agent.name}")
                return config

        except Exception as e:
            logger.error(f"Failed to load agent config: {e}")
            return None

    async def _create_agent_instance(self, config: Dict[str, Any]) -> AgentInterface:
        """Create appropriate agent instance based on configuration."""
        from trading_arena.agents.llm_trading_agent import LLMTradingAgent

        llm_model = config.get('llm_model', 'anthropic/claude-3.5-sonnet')

        # FAIL FAST - Validate LLM model and API key
        environment = os.getenv('ENVIRONMENT', 'development').lower()
        openrouter_key = os.getenv('OPENROUTER_API_KEY')

        if not openrouter_key:
            raise ValueError(
                "OPENROUTER_API_KEY must be set. "
                "Get your key from https://openrouter.ai/keys"
            )

        # Validate model format
        if '/' not in llm_model:
            raise ValueError(
                f"Invalid model format: '{llm_model}'. "
                f"Expected format: 'provider/model' (e.g., 'anthropic/claude-3.5-sonnet')"
            )

        logger.info(f"Creating LLM trading agent with model: {llm_model}")

        # Create real LLM-powered trading agent
        agent = LLMTradingAgent(
            agent_id=config['agent_id'],
            config=config
        )

        return agent

    async def _get_trading_symbols(self) -> List[str]:
        """Get list of trading symbols for this competition."""
        # Default symbols - in production this would come from competition config
        return ['BTCUSDT', 'ETHUSDT', 'ADAUSDT']

    async def _register_with_competition(self):
        """Register agent with competition system."""
        try:
            async with get_db_session() as session:
                # Update agent last active time
                agent = await session.get(Agent, int(self.agent_id))
                if agent:
                    agent.last_active = datetime.now(timezone.utc)
                    await session.commit()

                # Log competition entry
                logger.info(f"Agent {self.agent_id} registered for competition {self.competition_id}")

        except Exception as e:
            logger.error(f"Failed to register with competition: {e}")

    async def _health_monitoring_loop(self):
        """Background loop for health monitoring."""
        while self.is_running:
            try:
                await self._update_health_metrics()
                await self._check_agent_health()
                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(10)

    async def _metrics_reporting_loop(self):
        """Background loop for reporting metrics."""
        while self.is_running:
            try:
                await self._report_metrics()
                await asyncio.sleep(300)  # Report every 5 minutes
            except Exception as e:
                logger.error(f"Metrics reporting error: {e}")
                await asyncio.sleep(60)

    async def _update_health_metrics(self):
        """Update health metrics."""
        self.health_metrics['last_heartbeat'] = datetime.now(timezone.utc)

        # Get system resource usage
        try:
            import psutil
            process = psutil.Process()
            self.health_metrics['cpu_percent'] = process.cpu_percent()
            self.health_metrics['memory_mb'] = process.memory_info().rss / 1024 / 1024
        except Exception:
            pass

        # Update trading metrics
        if self.agent:
            self.health_metrics['total_signals'] = len(self.agent.last_signals)
            self.health_metrics['active_positions'] = len(self.agent.positions)

    async def _check_agent_health(self):
        """Check if agent is healthy and respond appropriately."""
        current_time = datetime.now(timezone.utc)
        last_heartbeat = self.health_metrics['last_heartbeat']

        # Check for stale heartbeat
        if (current_time - last_heartbeat).seconds > 300:  # 5 minutes
            logger.warning("Agent heartbeat is stale, potential issues")

        # Check for excessive errors
        if len(self.health_metrics['errors']) > 10:
            logger.error(f"Agent has {len(self.health_metrics['errors'])} errors, considering restart")

    async def _report_metrics(self):
        """Report metrics to monitoring system."""
        metrics = {
            'agent_id': self.agent_id,
            'competition_id': self.competition_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'uptime_seconds': (datetime.now(timezone.utc) - self.start_time).total_seconds(),
            'health_metrics': self.health_metrics
        }

        # Write metrics to file for monitoring
        try:
            with open('/tmp/agent_data/metrics.json', 'w') as f:
                json.dump(metrics, f)
        except Exception as e:
            logger.error(f"Failed to write metrics: {e}")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals for graceful shutdown."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        self.is_running = False

        if self.runtime:
            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task(self.runtime.stop())
            except RuntimeError:
                # No running loop, which can happen in tests
                logger.info("No running event loop, skipping async task creation")

    def _health_check_signal_handler(self, signum, frame):
        """Handle health check signals."""
        logger.info(f"Health check signal received, updating heartbeat")
        self.health_metrics['last_heartbeat'] = datetime.now(timezone.utc)

    async def _cleanup(self):
        """Perform cleanup before shutdown."""
        try:
            if self.exchange_client:
                await self.exchange_client.disconnect()
            logger.info("Cleanup completed")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    async def log_trade(self, signal: TradingSignal, order_result: Dict[str, Any]):
        """Log trade to database."""
        try:
            async with get_db_session() as session:
                trade = Trade(
                    agent_id=int(self.agent_id),
                    competition_id=int(self.competition_id),
                    symbol=signal.symbol,
                    side=signal.action,
                    quantity=signal.quantity,
                    price=float(order_result.get('avgPrice', 0)),
                    order_id=str(order_result.get('orderId')),
                    status='filled',
                    created_at=datetime.now(timezone.utc)
                )
                session.add(trade)
                await session.commit()

                # Update health metrics
                self.health_metrics['last_trade'] = datetime.now(timezone.utc)
                self.health_metrics['successful_trades'] += 1

        except Exception as e:
            logger.error(f"Failed to log trade: {e}")
            self.health_metrics['errors'].append(f"Trade logging error: {str(e)}")


# Mock classes removed for production security
# Real trading agents must be properly implemented before deployment


async def main():
    """Main entry point for containerized agent."""
    runtime = ContainerAgentRuntime()
    await runtime.start()


if __name__ == "__main__":
    asyncio.run(main())
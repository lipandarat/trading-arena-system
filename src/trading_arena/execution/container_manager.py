"""
Docker Container Manager for Agent Runtime System.

Provides containerized execution environment for autonomous trading agents
with resource isolation, health monitoring, and automatic recovery capabilities.
Integrates with existing trading systems including Binance client and database.
"""

import asyncio
import docker
import json
import logging
import os
import psutil
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from trading_arena.db import get_database
from trading_arena.config import config

logger = logging.getLogger(__name__)

@dataclass
class ContainerConfig:
    """Configuration for agent containers."""
    image: str = "trading-arena-agent:latest"
    memory_limit: str = "512m"
    cpu_limit: float = 1.0
    network_mode: str = "host"
    restart_policy: str = "on-failure"
    environment_vars: Dict[str, str] = field(default_factory=dict)
    volume_mounts: List[str] = field(default_factory=list)
    port_bindings: Dict[str, int] = field(default_factory=dict)

@dataclass
class AgentContainer:
    """Represents a running agent container."""
    container_id: str
    container_name: str
    agent_id: str
    competition_id: str
    status: str  # running, stopped, failed, restarting, paused
    created_at: datetime
    last_health_check: Optional[datetime] = None
    last_restart: Optional[datetime] = None
    restart_count: int = 0
    resource_usage: Dict[str, float] = field(default_factory=dict)
    health_status: str = "unknown"
    error_message: Optional[str] = None

class DockerContainerManager:
    """
    Manages Docker containers for autonomous trading agents.

    Provides complete lifecycle management including:
    - Container creation and deletion
    - Resource monitoring and limits
    - Health checking and automatic recovery
    - Integration with trading systems
    - Performance metrics collection
    """

    def __init__(self):
        """Initialize Docker container manager."""
        try:
            self.client = docker.from_env()
            self.client.ping()  # Test Docker connection
            logger.info("Docker client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise

        self.containers: Dict[str, AgentContainer] = {}
        self.default_config = ContainerConfig()
        self._monitoring_task = None
        self._is_monitoring = False

    async def start_agent_container(self, agent_id: str, competition_id: str,
                                  config: Optional[ContainerConfig] = None,
                                  database_url: Optional[str] = None,
                                  api_credentials: Optional[Dict[str, str]] = None) -> str:
        """
        Start a new agent container for trading.

        Args:
            agent_id: ID of the agent to run
            competition_id: ID of the competition
            config: Container configuration (uses default if None)
            database_url: Database connection URL
            api_credentials: Trading API credentials

        Returns:
            Container ID if successful

        Raises:
            Exception: If container creation fails
        """
        if config is None:
            config = self.default_config

        # Get real database URL if not provided
        if not database_url:
            database_url = config.database_url or "postgresql+asyncpg://arena_user:arena_pass@postgres:5432/trading_arena"

        container_name = f"agent_{agent_id}_{competition_id}"

        # Prepare environment variables with real system integration
        env_vars = {
            'AGENT_ID': str(agent_id),
            'COMPETITION_ID': str(competition_id),
            'PYTHONPATH': '/app/src',
            'LOG_LEVEL': os.getenv('LOG_LEVEL', 'INFO'),
            'DATABASE_URL': database_url,
            'TRADING_ARENA_CONFIG': json.dumps({
                'mode': 'competition',
                'environment': os.getenv('ENVIRONMENT', 'development'),
                'binance_testnet': os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'
            }),
            'REDIS_URL': config.redis_url or 'redis://redis:6379/0',
            'KAFKA_BOOTSTRAP_SERVERS': config.kafka_bootstrap_servers or 'kafka:9092'
        }

        # Add API credentials from config if not provided
        if not api_credentials:
            api_credentials = {
                'api_key': os.getenv('BINANCE_API_KEY', ''),
                'secret_key': os.getenv('BINANCE_SECRET_KEY', ''),
                'testnet': os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'
            }

        # Add API credentials if provided
        if api_credentials:
            env_vars.update({
                'BINANCE_API_KEY': api_credentials.get('api_key', ''),
                'BINANCE_SECRET_KEY': api_credentials.get('secret_key', ''),
                'BINANCE_TESTNET': str(api_credentials.get('testnet', True)).lower()
            })

        # Merge with config environment variables
        env_vars.update(config.environment_vars)

        # Prepare volume mounts
        volumes = [
            '/root/src:/app/src:ro',  # Read-only source code
            f'/tmp/agent_{agent_id}:/tmp/agent_data',  # Agent-specific data
            '/var/run/docker.sock:/var/run/docker.sock:ro'  # Docker socket for monitoring
        ]
        volumes.extend(config.volume_mounts)

        # Prepare port bindings
        port_bindings = {}
        if config.port_bindings:
            port_bindings = {f"{port}/tcp": port for port in config.port_bindings.values()}

        try:
            # Create and start container
            container = self.client.containers.run(
                config.image,
                name=container_name,
                detach=True,
                environment=env_vars,
                mem_limit=config.memory_limit,
                cpu_quota=int(config.cpu_limit * 100000),
                cpu_period=100000,
                network_mode=config.network_mode,
                restart_policy={"Name": config.restart_policy, "MaximumRetryCount": 3},
                volumes=volumes,
                port_bindings=port_bindings,
                healthcheck={
                    'test': ["CMD", "python", "-c", "import sys; sys.exit(0)"],
                    'interval': 30 * 1000000000,  # 30 seconds in nanoseconds
                    'timeout': 10 * 1000000000,  # 10 seconds in nanoseconds
                    'retries': 3
                }
            )

            # Track container
            agent_container = AgentContainer(
                container_id=container.id,
                container_name=container_name,
                agent_id=str(agent_id),
                competition_id=str(competition_id),
                status='running',
                created_at=datetime.now(timezone.utc)
            )

            self.containers[container.id] = agent_container

            logger.info(f"Started agent container: {container_name} ({container.id})")
            return container.id

        except Exception as e:
            logger.error(f"Failed to start container {container_name}: {e}")
            raise

    async def stop_agent_container(self, container_id: str, timeout: int = 30) -> bool:
        """
        Stop an agent container gracefully.

        Args:
            container_id: Docker container ID
            timeout: Graceful shutdown timeout in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            container = self.client.containers.get(container_id)

            # Try graceful stop first
            container.stop(timeout=timeout)
            container.remove()

            if container_id in self.containers:
                self.containers[container_id].status = 'stopped'

            logger.info(f"Stopped container: {container_id}")
            return True

        except docker.errors.NotFound:
            logger.warning(f"Container {container_id} not found, marking as stopped")
            if container_id in self.containers:
                self.containers[container_id].status = 'stopped'
            return True

        except Exception as e:
            logger.error(f"Failed to stop container {container_id}: {e}")
            return False

    async def restart_agent_container(self, container_id: str) -> bool:
        """
        Restart an agent container.

        Args:
            container_id: Docker container ID

        Returns:
            True if successful, False otherwise
        """
        try:
            container = self.client.containers.get(container_id)
            container.restart()

            if container_id in self.containers:
                self.containers[container_id].status = 'running'
                self.containers[container_id].last_health_check = datetime.now(timezone.utc)
                self.containers[container_id].last_restart = datetime.now(timezone.utc)
                self.containers[container_id].restart_count += 1

            logger.info(f"Restarted container: {container_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to restart container {container_id}: {e}")
            return False

    async def get_container_stats(self, container_id: str) -> Dict[str, float]:
        """
        Get resource usage statistics for a container.

        Args:
            container_id: Docker container ID

        Returns:
            Dictionary with resource usage metrics
        """
        try:
            container = self.client.containers.get(container_id)
            stats = container.stats(stream=False)

            # Calculate CPU usage percentage
            cpu_usage = 0.0
            if 'cpu_stats' in stats and 'precpu_stats' in stats:
                cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                           stats['precpu_stats']['cpu_usage']['total_usage']
                system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                              stats['precpu_stats']['system_cpu_usage']

                if system_delta > 0:
                    cpu_usage = (cpu_delta / system_delta) * 100

            # Calculate memory usage
            memory_usage = 0.0
            memory_mb = 0.0
            if 'memory_stats' in stats:
                usage = stats['memory_stats']['usage']
                limit = stats['memory_stats'].get('limit', usage)
                memory_usage = (usage / limit) * 100 if limit > 0 else 0
                memory_mb = usage / (1024 * 1024)

            # Get network statistics
            network_rx_mb = 0.0
            network_tx_mb = 0.0
            if 'networks' in stats:
                for network in stats['networks'].values():
                    network_rx_mb += network.get('rx_bytes', 0) / (1024 * 1024)
                    network_tx_mb += network.get('tx_bytes', 0) / (1024 * 1024)

            resource_usage = {
                'cpu_percent': round(cpu_usage, 2),
                'memory_percent': round(memory_usage, 2),
                'memory_mb': round(memory_mb, 2),
                'network_rx_mb': round(network_rx_mb, 2),
                'network_tx_mb': round(network_tx_mb, 2)
            }

            # Update container record
            if container_id in self.containers:
                self.containers[container_id].resource_usage = resource_usage

            return resource_usage

        except Exception as e:
            logger.error(f"Failed to get stats for container {container_id}: {e}")
            return {}

    async def health_check_containers(self) -> Dict[str, Dict[str, any]]:
        """
        Perform health check on all containers.

        Returns:
            Dictionary mapping container IDs to health status
        """
        health_status = {}

        for container_id, agent_container in self.containers.items():
            try:
                container = self.client.containers.get(container_id)
                container.reload()

                # Get Docker health status
                docker_health = "unknown"
                if hasattr(container, 'attrs') and 'Health' in container.attrs.get('State', {}):
                    health_info = container.attrs['State']['Health']
                    if health_info:
                        docker_health = health_info.get('Status', 'unknown')

                # Check container status
                docker_status = container.status

                # Get resource usage
                resource_stats = await self.get_container_stats(container_id)

                # Determine overall health
                is_healthy = (
                    docker_status in ('running', 'paused') and
                    docker_health in ('healthy', 'starting') and
                    resource_stats.get('memory_percent', 0) < 95 and
                    resource_stats.get('cpu_percent', 0) < 95
                )

                status_info = {
                    'docker_status': docker_status,
                    'health_status': docker_health,
                    'is_healthy': is_healthy,
                    'resource_usage': resource_stats,
                    'last_check': datetime.now(timezone.utc).isoformat(),
                    'restart_count': agent_container.restart_count,
                    'uptime_seconds': (datetime.now(timezone.utc) - agent_container.created_at).total_seconds()
                }

                health_status[container_id] = status_info

                # Update container status
                agent_container.status = docker_status
                agent_container.health_status = docker_health
                agent_container.last_health_check = datetime.now(timezone.utc)

                # Check if container needs restart
                if not is_healthy and docker_status == 'exited' and agent_container.status != 'stopped':
                    logger.warning(f"Container {container_id} is unhealthy, attempting restart")
                    if agent_container.restart_count < 3:  # Max 3 automatic restarts
                        await self.restart_agent_container(container_id)
                    else:
                        logger.error(f"Container {container_id} exceeded max restart attempts")
                        agent_container.status = 'failed'
                        agent_container.error_message = "Exceeded maximum restart attempts"

            except Exception as e:
                logger.error(f"Health check failed for container {container_id}: {e}")
                health_status[container_id] = {
                    'docker_status': 'error',
                    'health_status': 'error',
                    'is_healthy': False,
                    'error': str(e),
                    'last_check': datetime.now(timezone.utc).isoformat()
                }

        return health_status

    async def cleanup_stopped_containers(self, max_age_hours: int = 24) -> int:
        """
        Clean up stopped containers older than specified age.

        Args:
            max_age_hours: Maximum age in hours before cleanup

        Returns:
            Number of containers cleaned up
        """
        cleaned_count = 0
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        containers_to_remove = []
        for container_id, agent_container in self.containers.items():
            if (agent_container.status == 'stopped' and
                agent_container.created_at < cutoff_time):
                containers_to_remove.append(container_id)

        for container_id in containers_to_remove:
            try:
                container = self.client.containers.get(container_id)
                container.remove(force=True)

                # Clean up agent data directory
                agent_id = self.containers[container_id].agent_id
                agent_data_dir = f"/tmp/agent_{agent_id}"
                if os.path.exists(agent_data_dir):
                    import shutil
                    shutil.rmtree(agent_data_dir, ignore_errors=True)

                del self.containers[container_id]
                cleaned_count += 1
                logger.info(f"Cleaned up stopped container: {container_id}")

            except Exception as e:
                logger.error(f"Failed to cleanup container {container_id}: {e}")

        return cleaned_count

    def get_running_containers(self) -> List[AgentContainer]:
        """Get list of currently running containers."""
        return [
            container for container in self.containers.values()
            if container.status == 'running'
        ]

    def get_container_info(self, container_id: str) -> Optional[AgentContainer]:
        """Get information about a specific container."""
        return self.containers.get(container_id)

    def get_all_containers(self) -> Dict[str, AgentContainer]:
        """Get all tracked containers."""
        return self.containers.copy()

    async def get_container_logs(self, container_id: str, lines: int = 100) -> str:
        """
        Get logs from a container.

        Args:
            container_id: Docker container ID
            lines: Number of recent lines to fetch

        Returns:
            Log output as string
        """
        try:
            container = self.client.containers.get(container_id)
            logs = container.logs(tail=lines, timestamps=True)
            return logs.decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to get logs for container {container_id}: {e}")
            return f"Error retrieving logs: {str(e)}"

    async def start_monitoring(self, interval_seconds: int = 60):
        """
        Start background health monitoring for all containers.

        Args:
            interval_seconds: Monitoring interval in seconds
        """
        if self._is_monitoring:
            logger.warning("Container monitoring is already running")
            return

        self._is_monitoring = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop(interval_seconds))
        logger.info(f"Started container monitoring with {interval_seconds}s interval")

    async def stop_monitoring(self):
        """Stop background health monitoring."""
        if not self._is_monitoring:
            return

        self._is_monitoring = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped container monitoring")

    async def _monitoring_loop(self, interval_seconds: int):
        """Background monitoring loop."""
        while self._is_monitoring:
            try:
                await self.health_check_containers()
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(10)  # Brief pause on error

    async def get_system_resources(self) -> Dict[str, float]:
        """
        Get system resource usage for the host machine.

        Returns:
            Dictionary with system resource metrics
        """
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)

            # Memory usage
            memory = psutil.virtual_memory()

            # Disk usage
            disk = psutil.disk_usage('/')

            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_gb': memory.available / (1024**3),
                'disk_percent': disk.percent,
                'disk_free_gb': disk.free / (1024**3)
            }
        except Exception as e:
            logger.error(f"Failed to get system resources: {e}")
            return {}

    async def export_container_metrics(self) -> Dict[str, any]:
        """
        Export container metrics for monitoring systems.

        Returns:
            Dictionary with all container metrics
        """
        metrics = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'total_containers': len(self.containers),
            'running_containers': len(self.get_running_containers()),
            'stopped_containers': len([c for c in self.containers.values() if c.status == 'stopped']),
            'failed_containers': len([c for c in self.containers.values() if c.status == 'failed']),
            'containers': {}
        }

        for container_id, container in self.containers.items():
            metrics['containers'][container_id] = {
                'agent_id': container.agent_id,
                'competition_id': container.competition_id,
                'status': container.status,
                'health_status': container.health_status,
                'created_at': container.created_at.isoformat(),
                'restart_count': container.restart_count,
                'resource_usage': container.resource_usage,
                'uptime_seconds': (datetime.now(timezone.utc) - container.created_at).total_seconds()
            }

        # Add system resources
        metrics['system_resources'] = await self.get_system_resources()

        return metrics
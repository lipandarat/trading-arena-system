"""
WebSocket server for real-time leaderboard updates.

Provides WebSocket functionality for streaming leaderboard updates
to connected clients in real-time. Integrates with Redis pub/sub
to receive leaderboard updates and broadcast them to WebSocket clients.
"""

import asyncio
import json
import logging
from typing import Set, Dict, Any, Optional
from datetime import datetime, timezone
import websockets
from websockets.server import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class LeaderboardWebSocketServer:
    """
    WebSocket server for real-time leaderboard streaming.

    Maintains connected clients and broadcasts leaderboard updates
    received from Redis pub/sub channels.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8765, redis_client=None):
        """
        Initialize WebSocket server.

        Args:
            host: Host to bind the server to
            port: Port to listen on
            redis_client: Redis client for subscribing to leaderboard updates
        """
        self.host = host
        self.port = port
        self.redis_client = redis_client
        self.clients: Set[WebSocketServerProtocol] = set()
        self.server = None
        self.redis_task = None
        self.running = False

    async def register_client(self, websocket: WebSocketServerProtocol):
        """
        Register a new WebSocket client.

        Args:
            websocket: WebSocket connection object
        """
        self.clients.add(websocket)
        client_info = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info(f"Client connected: {client_info}. Total clients: {len(self.clients)}")

        # Send initial leaderboard data to new client
        await self.send_initial_data(websocket)

    async def unregister_client(self, websocket: WebSocketServerProtocol):
        """
        Unregister a WebSocket client.

        Args:
            websocket: WebSocket connection object
        """
        if websocket in self.clients:
            self.clients.remove(websocket)
            client_info = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
            logger.info(f"Client disconnected: {client_info}. Total clients: {len(self.clients)}")

    async def send_initial_data(self, websocket: WebSocketServerProtocol):
        """
        Send initial leaderboard data to a newly connected client.

        Args:
            websocket: WebSocket connection to send data to
        """
        try:
            if self.redis_client:
                # Get latest global leaderboard
                try:
                    global_data = await self.redis_client.get('latest_leaderboard:global')
                    if global_data:
                        await websocket.send(global_data)
                        logger.debug("Sent initial global leaderboard to client")
                except Exception as e:
                    logger.error(f"Error getting initial global leaderboard: {e}")

                # Get latest competition leaderboard
                try:
                    competition_data = await self.redis_client.get('latest_leaderboard:competition')
                    if competition_data:
                        await websocket.send(competition_data)
                        logger.debug("Sent initial competition leaderboard to client")
                except Exception as e:
                    logger.error(f"Error getting initial competition leaderboard: {e}")

        except Exception as e:
            logger.error(f"Error sending initial data to client: {e}")

    async def broadcast_to_clients(self, message: str):
        """
        Broadcast a message to all connected WebSocket clients.

        Args:
            message: JSON message to broadcast
        """
        if not self.clients:
            return

        # Create list of clients to send to (avoid modifying set during iteration)
        clients_to_send = list(self.clients)
        disconnected_clients = []

        for client in clients_to_send:
            try:
                await client.send(message)
            except ConnectionClosed:
                disconnected_clients.append(client)
            except Exception as e:
                logger.error(f"Error sending message to client: {e}")
                disconnected_clients.append(client)

        # Remove disconnected clients
        for client in disconnected_clients:
            await self.unregister_client(client)

        if disconnected_clients:
            logger.info(f"Removed {len(disconnected_clients)} disconnected clients")

    async def listen_to_redis_updates(self):
        """
        Listen for leaderboard updates from Redis pub/sub.

        Subscribes to the leaderboard-updates channel and broadcasts
        received messages to all WebSocket clients.
        """
        if not self.redis_client:
            logger.warning("No Redis client available, skipping Redis updates")
            return

        try:
            # Subscribe to leaderboard updates channel
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe('leaderboard-updates')

            logger.info("Listening for leaderboard updates from Redis")

            while self.running:
                try:
                    message = await pubsub.get_message(timeout=1.0)
                    if message and message['type'] == 'message':
                        # Broadcast the leaderboard update to all WebSocket clients
                        await self.broadcast_to_clients(message['data'].decode('utf-8'))
                        logger.debug(f"Broadcasted leaderboard update to {len(self.clients)} clients")

                except asyncio.TimeoutError:
                    # Timeout is expected, continue listening
                    continue
                except Exception as e:
                    logger.error(f"Error processing Redis message: {e}")
                    await asyncio.sleep(1)  # Brief pause before continuing

        except Exception as e:
            logger.error(f"Error in Redis listener: {e}")
        finally:
            if 'pubsub' in locals():
                await pubsub.unsubscribe('leaderboard-updates')
                await pubsub.close()

    async def handle_client_connection(self, websocket: WebSocketServerProtocol, path: str):
        """
        Handle individual WebSocket client connection.

        Args:
            websocket: WebSocket connection object
            path: WebSocket connection path
        """
        await self.register_client(websocket)

        try:
            # Keep connection alive and listen for client messages
            async for message in websocket:
                try:
                    # Parse client message
                    data = json.loads(message)
                    await self.handle_client_message(websocket, data)
                except json.JSONDecodeError:
                    logger.warning(f"Received invalid JSON from client: {message}")
                except Exception as e:
                    logger.error(f"Error handling client message: {e}")

        except ConnectionClosed:
            logger.info("Client connection closed")
        except Exception as e:
            logger.error(f"Error in client connection handler: {e}")
        finally:
            await self.unregister_client(websocket)

    async def handle_client_message(self, websocket: WebSocketServerProtocol, data: Dict[str, Any]):
        """
        Handle messages received from WebSocket clients.

        Args:
            websocket: WebSocket connection object
            data: Parsed message data from client
        """
        message_type = data.get('type')

        if message_type == 'subscribe':
            # Handle subscription to specific leaderboard types
            leaderboard_types = data.get('leaderboard_types', ['global', 'competition'])
            response = {
                'type': 'subscription_confirmed',
                'leaderboard_types': leaderboard_types,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            await websocket.send(json.dumps(response))
            logger.info(f"Client subscribed to: {leaderboard_types}")

        elif message_type == 'get_history':
            # Handle request for historical data
            agent_id = data.get('agent_id')
            days = data.get('days', 30)

            if agent_id and self.redis_client:
                try:
                    # This would integrate with the leaderboard class to get history
                    # For now, send a placeholder response
                    response = {
                        'type': 'history_data',
                        'agent_id': agent_id,
                        'days': days,
                        'data': [],  # Would contain actual history data
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                    await websocket.send(json.dumps(response))
                except Exception as e:
                    logger.error(f"Error getting history for agent {agent_id}: {e}")

        elif message_type == 'ping':
            # Handle ping for connection health check
            response = {
                'type': 'pong',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            await websocket.send(json.dumps(response))

        else:
            logger.warning(f"Unknown message type: {message_type}")

    async def start_server(self):
        """
        Start the WebSocket server and Redis listener.

        Creates the WebSocket server and starts listening for both
        client connections and Redis updates in parallel tasks.
        """
        try:
            # Create WebSocket server
            self.server = await websockets.serve(
                self.handle_client_connection,
                self.host,
                self.port
            )

            self.running = True

            logger.info(f"WebSocket server started on {self.host}:{self.port}")

            # Start Redis listener task
            if self.redis_client:
                self.redis_task = asyncio.create_task(self.listen_to_redis_updates())

            logger.info("Leaderboard WebSocket server is running")

        except Exception as e:
            logger.error(f"Failed to start WebSocket server: {e}")
            await self.stop_server()
            raise

    async def stop_server(self):
        """
        Stop the WebSocket server and clean up resources.

        Closes all client connections, stops the Redis listener,
        and shuts down the WebSocket server.
        """
        logger.info("Stopping WebSocket server...")

        self.running = False

        # Close all client connections
        if self.clients:
            clients_to_close = list(self.clients)
            for client in clients_to_close:
                try:
                    await client.close()
                except Exception as e:
                    logger.error(f"Error closing client connection: {e}")

            self.clients.clear()

        # Cancel Redis listener task
        if self.redis_task:
            self.redis_task.cancel()
            try:
                await self.redis_task
            except asyncio.CancelledError:
                pass
            self.redis_task = None

        # Close WebSocket server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

        logger.info("WebSocket server stopped")

    async def get_server_status(self) -> Dict[str, Any]:
        """
        Get current server status and statistics.

        Returns:
            Dictionary containing server status information
        """
        return {
            'running': self.running,
            'host': self.host,
            'port': self.port,
            'connected_clients': len(self.clients),
            'redis_connected': self.redis_client is not None,
            'redis_listener_active': self.redis_task is not None and not self.redis_task.done(),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

    async def send_custom_message(self, message_type: str, data: Dict[str, Any]):
        """
        Send a custom message to all connected clients.

        Args:
            message_type: Type of the custom message
            data: Message data payload
        """
        message = {
            'type': message_type,
            'data': data,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        await self.broadcast_to_clients(json.dumps(message))


# Convenience function for creating and running the server
async def run_leaderboard_websocket_server(host: str = "0.0.0.0", port: int = 8765, redis_client=None):
    """
    Run the leaderboard WebSocket server.

    Args:
        host: Host to bind the server to
        port: Port to listen on
        redis_client: Redis client for subscribing to updates
    """
    server = LeaderboardWebSocketServer(host=host, port=port, redis_client=redis_client)

    try:
        await server.start_server()

        # Keep server running indefinitely
        while server.running:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Received interrupt signal, stopping server...")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        await server.stop_server()


# Example usage and testing function
async def test_websocket_server():
    """
    Test function for the WebSocket server.
    """
    import logging

    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # Create mock Redis client for testing
    class MockRedis:
        def __init__(self):
            self.pubsub = MockPubSub()

        async def get(self, key):
            return None

        async def subscribe(self, channel):
            pass

    class MockPubSub:
        async def subscribe(self, channel):
            pass

        async def get_message(self, timeout=None):
            await asyncio.sleep(timeout)
            return None

        async def unsubscribe(self, channel):
            pass

        async def close(self):
            pass

    # Run server with mock Redis
    mock_redis = MockRedis()
    await run_leaderboard_websocket_server(host="0.0.0.0", port=8765, redis_client=mock_redis)


if __name__ == "__main__":
    asyncio.run(test_websocket_server())
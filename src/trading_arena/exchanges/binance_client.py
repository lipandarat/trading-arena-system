"""
Binance Futures client wrapper for trading arena integration.

Provides a clean async interface to Binance Futures API with proper error handling,
logging, and support for both testnet and production environments.
"""

from binance import AsyncClient
from binance.exceptions import BinanceAPIException
from typing import Dict, List, Optional
import asyncio
import logging

logger = logging.getLogger(__name__)


class BinanceFuturesClient:
    """
    Async Binance Futures client wrapper with error handling and auto-reconnection.

    Supports both testnet and production environments, providing methods for
    account management, position tracking, and order execution.
    """

    def __init__(self, api_key: str, secret_key: str, testnet: bool = False):
        """
        Initialize Binance Futures client.

        Args:
            api_key: Binance API key
            secret_key: Binance secret key
            testnet: Whether to use testnet (default: False for production)
        """
        self.client: Optional[AsyncClient] = None
        self.api_key = api_key
        self.secret_key = secret_key
        self.testnet = testnet
        self._connection_lock = asyncio.Lock()

    async def connect(self):
        """
        Establish connection to Binance Futures API.

        Raises:
            Exception: If connection fails
        """
        async with self._connection_lock:
            if self.client is not None:
                return

            try:
                self.client = await AsyncClient.create(
                    api_key=self.api_key,
                    api_secret=self.secret_key,
                    testnet=self.testnet
                )
                # Test connection
                await self.client.ping()
                logger.info(f"Connected to Binance Futures API ({'testnet' if self.testnet else 'production'})")
            except Exception as e:
                logger.error(f"Failed to connect to Binance: {e}")
                self.client = None
                raise

    async def get_account_info(self) -> Dict:
        """
        Get futures account information.

        Returns:
            Dictionary containing account details including balances, margins, etc.

        Raises:
            BinanceAPIException: If API call fails
        """
        if not self.client:
            await self.connect()

        max_retries = 3
        for attempt in range(max_retries):
            try:
                account_info = await self.client.futures_account()
                logger.debug("Retrieved account information")
                return account_info
            except BinanceAPIException as e:
                logger.error(f"Failed to get account info (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
            except Exception as e:
                logger.error(f"Unexpected error getting account info: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1 * (attempt + 1))

    async def get_open_positions(self) -> List[Dict]:
        """
        Get all open futures positions.

        Returns:
            List of position dictionaries, filtered to exclude zero-size positions

        Raises:
            BinanceAPIException: If API call fails
        """
        if not self.client:
            await self.connect()

        try:
            positions = await self.client.futures_position_information()
            # Filter out positions with zero size
            open_positions = [pos for pos in positions if float(pos['positionAmt']) != 0]
            logger.debug(f"Retrieved {len(open_positions)} open positions")
            return open_positions
        except BinanceAPIException as e:
            logger.error(f"Failed to get positions: {e}")
            raise

    async def place_market_order(self, symbol: str, side: str, quantity: float) -> Dict:
        """
        Place a market order.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            side: Order side ('BUY' or 'SELL')
            quantity: Order quantity

        Returns:
            Dictionary containing order details

        Raises:
            BinanceAPIException: If order placement fails
            ValueError: If parameters are invalid
        """
        if not self.client:
            await self.connect()

        # Validate parameters
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"Invalid symbol: {symbol}")

        if side not in ['BUY', 'SELL']:
            raise ValueError(f"Invalid side: {side}. Must be BUY or SELL")

        if not quantity or quantity <= 0:
            raise ValueError(f"Invalid quantity: {quantity}. Must be positive")

        try:
            order = await self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=quantity
            )
            logger.info(f"Placed {side} market order: {quantity} {symbol}")
            return order
        except BinanceAPIException as e:
            logger.error(f"Failed to place market order: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error placing market order: {e}")
            raise

    async def set_leverage(self, symbol: str, leverage: int) -> Dict:
        """
        Set leverage for a specific symbol.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            leverage: Leverage multiplier (1-125)

        Returns:
            Dictionary containing leverage change response

        Raises:
            BinanceAPIException: If leverage setting fails
        """
        if not self.client:
            await self.connect()

        try:
            result = await self.client.futures_change_leverage(
                symbol=symbol,
                leverage=leverage
            )
            logger.info(f"Set leverage for {symbol} to {leverage}x")
            return result
        except BinanceAPIException as e:
            logger.error(f"Failed to set leverage: {e}")
            raise

    async def close_connection(self):
        """Close the Binance client connection."""
        if self.client:
            await self.client.close_connection()
            self.client = None
            logger.info("Closed Binance Futures connection")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close_connection()
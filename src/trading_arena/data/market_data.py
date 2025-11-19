import asyncio
import json
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
from trading_arena.exchanges.binance_client import BinanceFuturesClient

logger = logging.getLogger(__name__)

class MarketDataAggregator:
    def __init__(self, kafka_producer, binance_client: BinanceFuturesClient, update_interval: int = 1, retry_delay: int = 5):
        self.kafka_producer = kafka_producer
        self.binance_client = binance_client
        self.symbols = []
        self.is_running = False
        self.tasks = []
        self.update_interval = update_interval  # seconds
        self.retry_delay = retry_delay  # seconds
        self.previous_prices = {}  # Store previous close prices for change calculations

    async def start_collection(self, symbols: List[str]):
        """Start collecting market data for specified symbols."""
        if self.is_running:
            logger.warning("Market data collection already running")
            return

        self.symbols = symbols
        self.is_running = True

        # Start data collection tasks for each symbol
        for symbol in symbols:
            task = asyncio.create_task(self._collect_symbol_data(symbol))
            self.tasks.append(task)

        logger.info(f"Started market data collection for {len(symbols)} symbols")

    async def stop_collection(self):
        """Stop market data collection."""
        self.is_running = False

        # Cancel all running tasks
        for task in self.tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self.tasks, return_exceptions=True)

        self.tasks.clear()
        self.previous_prices.clear()  # Clear previous prices when stopping
        logger.info("Stopped market data collection")

    def _calculate_price_changes(self, symbol: str, current_close: float) -> tuple[float, float]:
        """
        Calculate price change and price change percent.

        Args:
            symbol: Trading symbol
            current_close: Current close price

        Returns:
            Tuple of (price_change, price_change_percent)
        """
        if symbol not in self.previous_prices:
            self.previous_prices[symbol] = current_close
            return 0.0, 0.0

        previous_close = self.previous_prices[symbol]
        price_change = current_close - previous_close
        price_change_percent = (price_change / previous_close) * 100 if previous_close != 0 else 0.0

        # Update previous price for next calculation
        self.previous_prices[symbol] = current_close

        return price_change, price_change_percent

    async def _collect_symbol_data(self, symbol: str):
        """Collect market data for a specific symbol."""
        while self.is_running:
            try:
                # Ensure Binance client is connected
                if not self.binance_client.client:
                    await self.binance_client.connect()

                # Fetch klines data using the real Binance client
                klines = await self.binance_client.client.futures_klines(
                    symbol=symbol,
                    interval='1m',
                    limit=1
                )

                if klines:
                    latest = klines[0]
                    close_price = float(latest[4])
                    price_change, price_change_percent = self._calculate_price_changes(symbol, close_price)

                    market_data = {
                        'symbol': symbol,
                        'timestamp': int(latest[0]),
                        'datetime': datetime.fromtimestamp(latest[0] / 1000, tz=timezone.utc).isoformat(),
                        'open': float(latest[1]),
                        'high': float(latest[2]),
                        'low': float(latest[3]),
                        'close': close_price,
                        'volume': float(latest[5]),
                        'price_change': price_change,
                        'price_change_percent': price_change_percent,
                        'liquidity_score': self._calculate_liquidity_score(latest),
                        'volatility_score': self._calculate_volatility_score(symbol, float(latest[2]), float(latest[3]), close_price)
                    }

                    await self._publish_market_data(market_data)

                await asyncio.sleep(self.update_interval)

            except Exception as e:
                logger.error(f"Error collecting data for {symbol}: {e}")
                await asyncio.sleep(self.retry_delay)  # Wait before retrying

    async def _publish_market_data(self, market_data: Dict[str, Any]):
        """Publish market data to Kafka topic."""
        try:
            topic = f"market-data.{market_data['symbol'].lower()}"

            await self.kafka_producer.send_and_wait(
                topic=topic,
                value=json.dumps(market_data).encode('utf-8'),
                key=market_data['symbol'].encode('utf-8')
            )

        except Exception as e:
            logger.error(f"Failed to publish market data to Kafka: {e}")

    async def process_market_data(self, symbol: str):
        """Process market data for a specific symbol (used in tests)."""
        try:
            # Fetch klines data
            klines = await self.binance_client.client.futures_klines(
                symbol=symbol,
                interval='1m',
                limit=1
            )

            if klines:
                latest = klines[0]
                close_price = float(latest[4])
                price_change, price_change_percent = self._calculate_price_changes(symbol, close_price)

                market_data = {
                    'symbol': symbol,
                    'timestamp': int(latest[0]),
                    'datetime': datetime.fromtimestamp(latest[0] / 1000, tz=timezone.utc).isoformat(),
                    'open': float(latest[1]),
                    'high': float(latest[2]),
                    'low': float(latest[3]),
                    'close': close_price,
                    'volume': float(latest[5]),
                    'price_change': price_change,
                    'price_change_percent': price_change_percent
                }

                await self._publish_market_data(market_data)

        except Exception as e:
            logger.error(f"Failed to process market data for {symbol}: {e}")
            raise

    async def get_latest_price(self, symbol: str) -> Dict[str, Any]:
        """Get latest price data for a symbol."""
        try:
            klines = await self.binance_client.client.futures_klines(
                symbol=symbol,
                interval='1m',
                limit=1
            )

            if klines:
                latest = klines[0]
                return {
                    'symbol': symbol,
                    'price': float(latest[4]),
                    'volume': float(latest[5]),
                    'timestamp': int(latest[0])
                }

        except Exception as e:
            logger.error(f"Failed to get latest price for {symbol}: {e}")

        return None

    def _calculate_liquidity_score(self, kline_data: List) -> float:
        """
        Calculate liquidity score based on volume and price action.

        Args:
            kline_data: Raw kline data from Binance

        Returns:
            Liquidity score between 0 and 1
        """
        try:
            volume = float(kline_data[5])  # Volume
            quote_volume = float(kline_data[7])  # Quote asset volume
            high = float(kline_data[2])
            low = float(kline_data[3])

            # Basic liquidity calculation based on volume and price spread
            if quote_volume == 0:
                return 0.1

            # Volume factor (normalized)
            volume_factor = min(volume / 1000000, 1.0)  # Normalize to 1M base

            # Price spread factor (lower spread = higher liquidity)
            if low > 0:
                spread_factor = 1.0 - min((high - low) / low, 0.5)  # Max 50% spread penalty
            else:
                spread_factor = 0.5

            # Combined liquidity score
            liquidity_score = (volume_factor * 0.7 + spread_factor * 0.3)
            return max(0.1, min(1.0, liquidity_score))

        except Exception as e:
            logger.error(f"Error calculating liquidity score: {e}")
            return 0.5  # Default medium liquidity

    def _calculate_volatility_score(self, symbol: str, high: float, low: float, close: float) -> float:
        """
        Calculate volatility score for the symbol.

        Args:
            symbol: Trading symbol
            high: High price
            low: Low price
            close: Close price

        Returns:
            Volatility score between 0 and 1
        """
        try:
            if low == 0 or close == 0:
                return 0.3  # Default low volatility

            # Calculate price range percentage
            range_pct = (high - low) / close

            # Convert range to volatility score (higher range = higher volatility)
            volatility_score = min(range_pct * 10, 1.0)  # Scale and cap at 1.0

            # Ensure minimum volatility
            return max(0.1, volatility_score)

        except Exception as e:
            logger.error(f"Error calculating volatility score for {symbol}: {e}")
            return 0.3  # Default low volatility

    async def get_market_analysis(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Get comprehensive market analysis for specified symbols.

        Args:
            symbols: List of trading symbols to analyze

        Returns:
            Market analysis data including volatility, liquidity, and trends
        """
        try:
            analysis = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'symbols': {},
                'overall_market': {
                    'avg_volatility': 0.0,
                    'avg_liquidity': 0.0,
                    'trend_direction': 'neutral'
                }
            }

            total_volatility = 0.0
            total_liquidity = 0.0
            valid_symbols = 0

            for symbol in symbols:
                try:
                    # Get latest price data
                    price_data = await self.get_latest_price(symbol)
                    if price_data:
                        # Fetch recent klines for trend analysis
                        if self.binance_client.client:
                            await self.binance_client.connect()

                        klines = await self.binance_client.client.futures_klines(
                            symbol=symbol,
                            interval='5m',
                            limit=20  # Last 20 five-minute candles
                        )

                        if klines:
                            # Calculate metrics
                            latest = klines[-1]
                            high = float(latest[2])
                            low = float(latest[3])
                            close = float(latest[4])

                            volatility = self._calculate_volatility_score(symbol, high, low, close)
                            liquidity = self._calculate_liquidity_score(latest)

                            # Trend analysis (simple price direction)
                            if len(klines) >= 2:
                                prev_close = float(klines[-2][4])
                                if close > prev_close * 1.005:  # 0.5% threshold
                                    trend = 'bullish'
                                elif close < prev_close * 0.995:
                                    trend = 'bearish'
                                else:
                                    trend = 'neutral'
                            else:
                                trend = 'neutral'

                            analysis['symbols'][symbol] = {
                                'price': close,
                                'volume': float(latest[5]),
                                'volatility_score': volatility,
                                'liquidity_score': liquidity,
                                'trend': trend,
                                'price_change_pct': ((close - float(latest[1])) / float(latest[1])) * 100
                            }

                            total_volatility += volatility
                            total_liquidity += liquidity
                            valid_symbols += 1

                except Exception as e:
                    logger.error(f"Error analyzing symbol {symbol}: {e}")
                    continue

            # Calculate overall market metrics
            if valid_symbols > 0:
                analysis['overall_market']['avg_volatility'] = total_volatility / valid_symbols
                analysis['overall_market']['avg_liquidity'] = total_liquidity / valid_symbols

                # Determine overall market trend
                bullish_count = sum(1 for s in analysis['symbols'].values() if s['trend'] == 'bullish')
                bearish_count = sum(1 for s in analysis['symbols'].values() if s['trend'] == 'bearish')

                if bullish_count > bearish_count * 1.5:
                    analysis['overall_market']['trend_direction'] = 'bullish'
                elif bearish_count > bullish_count * 1.5:
                    analysis['overall_market']['trend_direction'] = 'bearish'
                else:
                    analysis['overall_market']['trend_direction'] = 'neutral'

            return analysis

        except Exception as e:
            logger.error(f"Error in market analysis: {e}")
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'symbols': {},
                'overall_market': {'avg_volatility': 0.3, 'avg_liquidity': 0.5, 'trend_direction': 'neutral'}
            }
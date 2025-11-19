"""
Trading arena exchange connectors.

This module provides standardized interfaces to various cryptocurrency exchanges
for futures trading, focusing on Binance Futures as the primary exchange.
"""

from .binance_client import BinanceFuturesClient

__all__ = ['BinanceFuturesClient']
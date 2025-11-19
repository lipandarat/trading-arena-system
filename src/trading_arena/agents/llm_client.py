"""
OpenRouter LLM Client for Trading Decisions.

Real API integration with OpenRouter for accessing GPT-4, Claude, and other LLMs.
NO MOCKS, NO SIMULATIONS - Production ready.
"""

import os
import asyncio
import logging
from typing import Dict, List, Optional, Any
import aiohttp
import json

logger = logging.getLogger(__name__)


class OpenRouterClient:
    """
    Real OpenRouter API client for LLM trading decisions.

    Supports multiple models:
    - GPT-4, GPT-4 Turbo
    - Claude 3 Opus, Sonnet, Haiku
    - Mistral Large
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize OpenRouter client with API key."""
        self.api_key = api_key or os.getenv('OPENROUTER_API_KEY')
        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY must be set. "
                "Get your key from https://openrouter.ai/keys"
            )

        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_count = 0
        self.error_count = 0

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "anthropic/claude-3.5-sonnet",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """
        Make real chat completion request to OpenRouter.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model identifier (e.g., 'anthropic/claude-3.5-sonnet')
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum response tokens
            timeout: Request timeout in seconds

        Returns:
            API response dict

        Raises:
            Exception: If API call fails after retries
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://trading-arena.ai",
            "X-Title": "Trading Arena Agent",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                self.request_count += 1

                async with self.session.post(
                    self.base_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:

                    if response.status == 200:
                        result = await response.json()
                        logger.debug(f"LLM request successful (attempt {attempt + 1})")
                        return result

                    elif response.status == 429:
                        # Rate limited
                        retry_after = int(response.headers.get('Retry-After', retry_delay))
                        logger.warning(f"Rate limited, waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue

                    elif response.status >= 500:
                        # Server error, retry
                        error_text = await response.text()
                        logger.error(f"Server error {response.status}: {error_text}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay * (attempt + 1))
                            continue
                        raise Exception(f"OpenRouter server error: {response.status}")

                    else:
                        # Client error, don't retry
                        error_text = await response.text()
                        logger.error(f"API error {response.status}: {error_text}")
                        raise Exception(f"OpenRouter API error: {response.status} - {error_text}")

            except asyncio.TimeoutError:
                logger.error(f"Request timeout (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                raise Exception("OpenRouter request timeout after retries")

            except Exception as e:
                logger.error(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}")
                self.error_count += 1
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                raise

        raise Exception("Failed to complete OpenRouter request after all retries")

    def extract_content(self, response: Dict[str, Any]) -> str:
        """Extract text content from API response."""
        try:
            return response['choices'][0]['message']['content']
        except (KeyError, IndexError) as e:
            logger.error(f"Failed to extract content from response: {e}")
            logger.error(f"Response: {json.dumps(response, indent=2)}")
            raise Exception(f"Invalid API response format: {e}")

    async def get_trading_decision(
        self,
        system_prompt: str,
        market_context: str,
        model: str = "anthropic/claude-3.5-sonnet",
        temperature: float = 0.3
    ) -> str:
        """
        Get trading decision from LLM.

        Args:
            system_prompt: System instructions for the LLM
            market_context: Current market data and analysis
            model: LLM model to use
            temperature: Lower for more conservative, higher for creative

        Returns:
            LLM response text
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": market_context}
        ]

        response = await self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=2000
        )

        return self.extract_content(response)

    def get_stats(self) -> Dict[str, int]:
        """Get client statistics."""
        return {
            "total_requests": self.request_count,
            "errors": self.error_count,
            "success_rate": (
                (self.request_count - self.error_count) / self.request_count * 100
                if self.request_count > 0 else 0
            )
        }

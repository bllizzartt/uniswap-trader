"""
Market Data Module
Token prices, volume tracking, liquidity analysis, gas monitoring
"""

import os
import json
import logging
import time
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

import requests
import numpy as np

from config import APIS, NETWORKS, TRADING_CONFIG

logger = logging.getLogger(__name__)


class PriceSource(Enum):
    COINGECKO = "coingecko"
    CHAINLINK = "chainlink"
    UNISWAP = "uniswap"
    CUSTOM = "custom"


@dataclass
class TokenPrice:
    """Token price information"""
    symbol: str
    price: float
    timestamp: datetime
    source: PriceSource
    change_24h: float = 0.0
    volume_24h: float = 0.0
    market_cap: float = 0.0


@dataclass
class GasPrice:
    """Gas price information"""
    slow_gwei: float
    average_gwei: float
    fast_gwei: float
    timestamp: datetime


@dataclass
class PoolInfo:
    """Uniswap pool information"""
    token0: str
    token1: str
    fee_tier: int
    liquidity: int
    tvl_usd: float
    volume_24h: float
    apr: float


class MarketDataProvider:
    """
    Comprehensive market data provider
    
    Features:
    - Token prices from multiple sources
    - Volume tracking
    - Liquidity analysis
    - Gas price monitoring
    """
    
    def __init__(
        self,
        network: str = "ethereum",
        cache_ttl: int = 60,
    ):
        """
        Initialize market data provider
        
        Args:
            network: Network name
            cache_ttl: Cache time-to-live in seconds
        """
        self.network = network
        self.network_config = NETWORKS.get(network, NETWORKS["ethereum"])
        self.cache_ttl = cache_ttl
        
        # Cache for prices
        self._price_cache: Dict[str, Tuple[TokenPrice, float]] = {}
        
        # Historical data
        self._price_history: Dict[str, List[Tuple[float, datetime]]] = {}
        
        # API endpoints
        self.coingecko_url = APIS["coingecko"]["base_url"]
        self.coingecko_api_key = APIS["coingecko"]["api_key"]
    
    def get_current_price(
        self,
        token: str,
        source: PriceSource = PriceSource.COINGECKO,
    ) -> float:
        """
        Get current token price
        
        Args:
            token: Token symbol or address
            source: Price source
            
        Returns:
            Current price in USD
        """
        cache_key = f"{token}_{source.value}"
        
        # Check cache
        if cache_key in self._price_cache:
            price, timestamp = self._price_cache[cache_key]
            if (datetime.now() - timestamp).seconds < self.cache_ttl:
                return price.price
        
        # Fetch fresh price
        price = self._fetch_price(token, source)
        
        # Cache it
        self._price_cache[cache_key] = (price, datetime.now())
        
        return price.price
    
    def _fetch_price(
        self,
        token: str,
        source: PriceSource,
    ) -> TokenPrice:
        """Fetch price from source"""
        if source == PriceSource.COINGECKO:
            return self._fetch_coingecko_price(token)
        elif source == PriceSource.CHAINLINK:
            return self._fetch_chainlink_price(token)
        elif source == PriceSource.UNISWAP:
            return self._fetch_uniswap_price(token)
        else:
            return self._fetch_coingecko_price(token)
    
    def _fetch_coingecko_price(self, token: str) -> TokenPrice:
        """Fetch price from CoinGecko"""
        # Map token symbols to CoinGecko IDs
        token_ids = {
            "ETH": "ethereum",
            "WETH": "ethereum",
            "USDC": "usd-coin",
            "USDT": "tether",
            "DAI": "dai",
            "MATIC": "matic-network",
            "ARB": "arbitrum",
        }
        
        token_id = token_ids.get(token.upper(), token.lower())
        
        headers = {}
        if self.coingecko_api_key:
            headers["x-cg-pro-api-key"] = self.coingecko_api_key
        
        try:
            url = f"{self.coingecko_url}/simple/price"
            params = {
                "ids": token_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
                "include_market_cap": "true",
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            token_data = data.get(token_id, {})
            
            return TokenPrice(
                symbol=token,
                price=token_data.get("usd", 0),
                timestamp=datetime.now(),
                source=PriceSource.COINGECKO,
                change_24h=token_data.get("usd_24h_change", 0),
                volume_24h=token_data.get("usd_24h_vol", 0),
                market_cap=token_data.get("usd_market_cap", 0),
            )
            
        except Exception as e:
            logger.error(f"CoinGecko error for {token}: {e}")
            # Return cached or default price
            return TokenPrice(
                symbol=token,
                price=0,
                timestamp=datetime.now(),
                source=PriceSource.COINGECKO,
            )
    
    def _fetch_chainlink_price(self, token: str) -> TokenPrice:
        """Fetch price from Chainlink oracles"""
        # Chainlink oracle addresses (Ethereum mainnet)
        oracle_addresses = {
            "ETH": "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
            "BTC": "0xF4030086522a5bEEa7Bf55f8d2D89E5bfb55e8c2",
            "LINK": "0x2c1d072e96A433b99a0fb5E6C46b5a91eC27D562",
            "USDC": "0x8fFfFfd4AfB6115b954bd326cbe7B4BA274c25bc",
            "USDT": "0xEe9F39fEa0840FBdf4c0379C0e7c3d0a5e2D5c7c",
        }
        
        oracle_address = oracle_addresses.get(token.upper())
        if not oracle_address:
            # Fallback to CoinGecko
            return self._fetch_coingecko_price(token)
        
        # In production, query the Chainlink oracle contract
        # For now, return CoinGecko price
        return self._fetch_coingecko_price(token)
    
    def _fetch_uniswap_price(self, token: str) -> TokenPrice:
        """Fetch price from Uniswap pools"""
        # In production, query Uniswap V3 pools directly
        # For now, use CoinGecko
        return self._fetch_coingecko_price(token)
    
    def get_token_prices_across_dexs(self, token: str) -> Dict[str, float]:
        """
        Get token prices across multiple DEXs
        
        Returns dict of DEX name -> price
        """
        prices = {}
        
        # Uniswap V3
        try:
            uniswap_price = self._fetch_uniswap_price(token)
            prices["uniswap_v3"] = uniswap_price.price
        except Exception as e:
            logger.warning(f"Failed to get Uniswap price: {e}")
        
        # Sushiswap
        try:
            sushiswap_price = self._fetch_sushiswap_price(token)
            prices["sushiswap"] = sushiswap_price.price
        except Exception as e:
            logger.warning(f"Failed to get SushiSwap price: {e}")
        
        # Coinbase (for reference)
        try:
            cb_price = self._fetch_coinbase_price(token)
            prices["coinbase"] = cb_price.price
        except Exception as e:
            logger.warning(f"Failed to get Coinbase price: {e}")
        
        return prices
    
    def _fetch_sushiswap_price(self, token: str) -> TokenPrice:
        """Fetch price from SushiSwap"""
        # Use CoinGecko as reference
        return self._fetch_coingecko_price(token)
    
    def _fetch_coinbase_price(self, token: str) -> TokenPrice:
        """Fetch price from Coinbase"""
        # Use CoinGecko as reference
        return self._fetch_coingecko_price(token)
    
    def get_recent_prices(
        self,
        token: str,
        period: int = 24,
        interval: int = 60,
    ) -> List[float]:
        """
        Get historical prices for token
        
        Args:
            token: Token symbol
            period: Hours of history
            interval: Seconds between data points
            
        Returns:
            List of prices
        """
        # Check memory cache first
        if token in self._price_history:
            history = self._price_history[token]
            cutoff = datetime.now() - timedelta(hours=period)
            recent = [p for p, t in history if t > cutoff]
            if len(recent) >= interval:
                return recent
        
        # Fetch from API
        try:
            prices = self._fetch_historical_prices(token, period)
            self._price_history[token] = [
                (p, datetime.now() - timedelta(hours=period - i))
                for i, p in enumerate(prices)
            ]
            return prices
        except Exception as e:
            logger.error(f"Failed to fetch historical prices: {e}")
            return []
    
    def _fetch_historical_prices(
        self,
        token: str,
        period: int = 24,
    ) -> List[float]:
        """Fetch historical prices from API"""
        # Map token to CoinGecko ID
        token_ids = {
            "ETH": "ethereum",
            "WETH": "ethereum",
            "USDC": "usd-coin",
            "USDT": "tether",
            "DAI": "dai",
        }
        
        token_id = token_ids.get(token.upper(), token.lower())
        
        headers = {}
        if self.coingecko_api_key:
            headers["x-cg-pro-api-key"] = self.coingecko_api_key
        
        # Calculate timestamps
        end_time = int(time.time())
        start_time = end_time - (period * 3600)
        
        url = f"{self.coingecko_url}/coins/{token_id}/market_chart/range"
        params = {
            "vs_currency": "usd",
            "from": start_time,
            "to": end_time,
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        prices = [p[1] for p in data.get("prices", [])]
        return prices
    
    def get_volatility(self, token: str, period: int = 24) -> Optional[float]:
        """
        Calculate token volatility
        
        Returns:
            Volatility as standard deviation of returns
        """
        prices = self.get_recent_prices(token, period)
        
        if len(prices) < 2:
            return None
        
        # Calculate returns
        returns = np.diff(prices) / prices[:-1]
        
        # Annualized volatility
        volatility = np.std(returns) * np.sqrt(365 * 24)
        
        return volatility
    
    def get_volume(self, token: str) -> float:
        """Get 24h trading volume"""
        price = self.get_current_price(token)
        if price:
            return price.volume_24h
        return 0.0
    
    def get_market_cap(self, token: str) -> float:
        """Get market capitalization"""
        price = self.get_current_price(token)
        if price:
            return price.market_cap
        return 0.0
    
    def get_price_change_24h(self, token: str) -> float:
        """Get 24h price change percentage"""
        price = self.get_current_price(token)
        if price:
            return price.change_24h
        return 0.0


class GasPriceProvider:
    """
    Gas price monitoring and estimation
    """
    
    def __init__(self, network: str = "ethereum"):
        """Initialize gas price provider"""
        self.network = network
        self.network_config = NETWORKS.get(network, NETWORKS["ethereum"])
        self.cache_time = 0
        self._cached_gas: Optional[GasPrice] = None
    
    def get_current_gas(self) -> GasPrice:
        """
        Get current gas prices
        
        Returns:
            GasPrice with slow/average/fast prices in Gwei
        """
        # Check cache (60 seconds)
        if self._cached_gas:
            if (datetime.now() - self._cached_gas.timestamp).seconds < 60:
                return self._cached_gas
        
        # Fetch fresh data
        gas = self._fetch_gas_prices()
        self._cached_gas = gas
        
        return gas
    
    def _fetch_gas_prices(self) -> GasPrice:
        """Fetch gas prices from network or API"""
        if self.network == "ethereum":
            return self._fetch_eth_gas()
        elif self.network == "polygon":
            return self._fetch_polygon_gas()
        elif self.network == "arbitrum":
            return self._fetch_arbitrum_gas()
        else:
            return self._fetch_default_gas()
    
    def _fetch_eth_gas(self) -> GasPrice:
        """Fetch Ethereum gas prices"""
        try:
            # Use ETH Gas Station or similar
            response = requests.get(
                "https://api.ethgasstation.info/v2/ethgasAPI.json",
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                return GasPrice(
                    slow_gwei=data.get("safeLow", 10) / 10,
                    average_gwei=data.get("average", 20) / 10,
                    fast_gwei=data.get("fast", 30) / 10,
                    timestamp=datetime.now(),
                )
        except Exception as e:
            logger.warning(f"ETH gas API error: {e}")
        
        # Fallback: estimate from recent blocks
        return self._fetch_default_gas()
    
    def _fetch_polygon_gas(self) -> GasPrice:
        """Fetch Polygon gas prices"""
        try:
            response = requests.get(
                "https://api.polygonscan.com/api?module=gastracker&action=gasoracle",
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json().get("result", {})
                return GasPrice(
                    slow_gwei=float(data.get("SafeGasPrice", 30)),
                    average_gwei=float(data.get("ProposeGasPrice", 40)),
                    fast_gwei=float(data.get("FastGasPrice", 50)),
                    timestamp=datetime.now(),
                )
        except Exception as e:
            logger.warning(f"Polygon gas API error: {e}")
        
        return self._fetch_default_gas()
    
    def _fetch_arbitrum_gas(self) -> GasPrice:
        """Fetch Arbitrum gas prices"""
        # Arbitrum gas is typically much lower
        return GasPrice(
            slow_gwei=0.01,
            average_gwei=0.02,
            fast_gwei=0.05,
            timestamp=datetime.now(),
        )
    
    def _fetch_default_gas(self) -> GasPrice:
        """Default gas prices"""
        return GasPrice(
            slow_gwei=10,
            average_gwei=20,
            fast_gwei=30,
            timestamp=datetime.now(),
        )
    
    def get_gas_for_speed(
        self,
        speed: str = "average",
    ) -> int:
        """
        Get gas price in wei for specified speed
        
        Args:
            speed: 'slow', 'average', or 'fast'
            
        Returns:
            Gas price in wei
        """
        gas = self.get_current_gas()
        
        if speed == "slow":
            gwei = gas.slow_gwei
        elif speed == "fast":
            gwei = gas.fast_gwei
        else:
            gwei = gas.average_gwei
        
        return int(gwei * 1e9)  # Convert to wei
    
    def estimate_swap_gas(
        self,
        token_in: str,
        token_out: str,
        amount: float,
    ) -> int:
        """
        Estimate gas for a swap
        
        Args:
            token_in: Input token
            token_out: Output token
            amount: Swap amount
            
        Returns:
            Estimated gas units
        """
        # Base estimate for Uniswap V3 swap
        base_gas = 100000
        
        # Add for large amounts
        if amount > 10000:
            base_gas += 50000
        
        # Multi-hop swaps
        if token_in != "WETH" and token_out != "WETH":
            base_gas += 50000
        
        return base_gas
    
    def estimate_swap_cost(
        self,
        token_in: str,
        token_out: str,
        amount: float,
        speed: str = "average",
    ) -> float:
        """
        Estimate swap cost in USD
        
        Args:
            token_in: Input token
            token_out: Output token
            amount: Swap amount
            speed: Gas speed
            
        Returns:
            Estimated cost in USD
        """
        gas_units = self.estimate_swap_gas(token_in, token_out, amount)
        gas_price_wei = self.get_gas_for_speed(speed)
        
        # Calculate in ETH (assuming gas token is ETH)
        gas_cost_eth = (gas_units * gas_price_wei) / 1e18
        
        # Get ETH price
        eth_price = 3000.0  # Or fetch from API
        
        return gas_cost_eth * eth_price


class LiquidityAnalyzer:
    """
    Analyze Uniswap V3 pool liquidity
    """
    
    def __init__(
        self,
        network: str = "ethereum",
        web3_provider=None,
    ):
        """Initialize liquidity analyzer"""
        self.network = network
        self.w3 = web3_provider
    
    def get_pool_liquidity(
        self,
        token_a: str,
        token_b: str,
        fee_tier: int = 3000,
    ) -> PoolInfo:
        """
        Get liquidity information for a pool
        
        Args:
            token_a: Token A address
            token_b: Token B address
            fee_tier: Pool fee tier
            
        Returns:
            PoolInfo with liquidity details
        """
        # In production, query the actual pool contract
        # For now, return placeholder data
        
        return PoolInfo(
            token0=token_a,
            token1=token_b,
            fee_tier=fee_tier,
            liquidity=1000000,
            tvl_usd=1000000,
            volume_24h=100000,
            apr=0.1,
        )
    
    def get_liquidity_depth(
        self,
        token_a: str,
        token_b: str,
        fee_tier: int = 3000,
        price_range_pct: float = 1.0,
    ) -> Dict:
        """
        Get liquidity depth within a price range
        
        Args:
            token_a: Token A
            token_b: Token B
            fee_tier: Pool fee tier
            price_range_pct: Price range percentage
            
        Returns:
            Dict with liquidity depth info
        """
        # Calculate liquidity depth
        pool = self.get_pool_liquidity(token_a, token_b, fee_tier)
        
        return {
            "tvl_usd": pool.tvl_usd,
            "liquidity": pool.liquidity,
            "price_range": f"+/-{price_range_pct}%",
            "depth_tokens": pool.tvl_usd / 2,
            "depth_usd": pool.tvl_usd / 2,
        }
    
    def get_best_fee_tier(
        self,
        token_a: str,
        token_b: str,
        volatility: float = 0.5,
    ) -> int:
        """
        Get optimal fee tier based on token volatility
        
        Args:
            token_a: Token A
            token_b: Token B
            volatility: Token volatility
            
        Returns:
            Recommended fee tier
        """
        if volatility > 1.0:
            # High volatility - use higher fee
            return 10000  # 1%
        elif volatility > 0.3:
            return 3000  # 0.3%
        else:
            return 500  # 0.05%

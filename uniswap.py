"""
Uniswap V3 Integration Module
DEX swap execution with 1inch aggregator support
"""

import os
import json
import logging
import time
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum
from web3 import Web3
from web3.contract import Contract

from config import (
    UNISWAP_V3, ONE_INCH, RISK_CONFIG, TRADING_CONFIG, TOKENS, NETWORKS
)
from wallet import MetaMaskWallet, TransactionInfo

logger = logging.getLogger(__name__)


class SwapType(Enum):
    EXACT_INPUT = 0
    EXACT_OUTPUT = 1


@dataclass
class SwapQuote:
    """Swap quote information"""
    token_in: str
    token_out: str
    amount_in: int
    amount_out: int
    price_impact: float
    gas_estimate: int
    router_address: str
    data: str
    protocol: str  # 'uniswap_v3' or '1inch'
    slippage_tolerance: float = 0.005  # 0.5%


@dataclass
class SwapResult:
    """Result of a swap operation"""
    success: bool
    quote: SwapQuote
    tx_info: Optional[TransactionInfo]
    error: Optional[str] = None


class UniswapV3Interactor:
    """
    Uniswap V3 swap execution
    
    Features:
    - Exact input/output swaps
    - Slippage protection
    - Gas estimation
    - Multi-hop swaps
    """
    
    # Uniswap V3 Swap Router ABI (minimal)
    SWAP_ROUTER_ABI = [
        {
            "name": "exactInputSingle",
            "type": "function",
            "inputs": [
                {"name": "tokenIn", "type": "address"},
                {"name": "tokenOut", "type": "address"},
                {"name": "fee", "type": "uint24"},
                {"name": "recipient", "type": "address"},
                {"name": "deadline", "type": "uint256"},
                {"name": "amountIn", "type": "uint256"},
                {"name": "amountOutMinimum", "type": "uint256"},
                {"name": "sqrtPriceLimitX96", "type": "uint160"},
            ],
            "outputs": [{"name": "amountOut", "type": "uint256"}],
        },
        {
            "name": "exactInput",
            "type": "function",
            "inputs": [
                {"name": "path", "type": "bytes"},
                {"name": "recipient", "type": "address"},
                {"name": "deadline", "type": "uint256"},
                {"name": "amountIn", "type": "uint256"},
                {"name": "amountOutMinimum", "type": "uint256"},
            ],
            "outputs": [{"name": "amountOut", "type": "uint256"}],
        },
    ]
    
    def __init__(
        self,
        wallet: MetaMaskWallet,
        network: str = "ethereum",
    ):
        """
        Initialize Uniswap V3 interactor
        
        Args:
            wallet: MetaMaskWallet instance
            network: Network name
        """
        self.wallet = wallet
        self.network = network
        self.w3 = wallet.w3
        self.address = wallet.address
        
        # Initialize contracts
        self._init_contracts()
    
    def _init_contracts(self):
        """Initialize contract instances"""
        # Swap Router
        self.router_address = Web3.to_checksum_address(UNISWAP_V3["router"])
        self.router = self.w3.eth.contract(
            address=self.router_address,
            abi=self.SWAP_ROUTER_ABI,
        )
        
        # Quoter (for getting quotes)
        self.quoter_address = Web3.to_checksum_address(UNISWAP_V3["quoter"])
    
    def get_token_address(self, symbol: str) -> str:
        """Get token address by symbol"""
        # Network-specific overrides
        network_tokens = {
            "ethereum": TOKENS,
            # Add network-specific tokens here
        }
        
        tokens = network_tokens.get(self.network, TOKENS)
        
        if symbol.upper() in tokens:
            return Web3.to_checksum_address(tokens[symbol.upper()]["address"])
        
        raise ValueError(f"Unknown token: {symbol}")
    
    def get_decimals(self, symbol: str) -> int:
        """Get token decimals"""
        network_tokens = {
            "ethereum": TOKENS,
        }
        
        tokens = network_tokens.get(self.network, TOKENS)
        
        if symbol.upper() in tokens:
            return tokens[symbol.upper()]["decimals"]
        
        raise ValueError(f"Unknown token: {symbol}")
    
    def get_quote(
        self,
        token_in: str,
        token_out: str,
        amount_in: float,
        fee: int = 3000,  # 0.3% fee tier
    ) -> SwapQuote:
        """
        Get a swap quote from Uniswap V3
        
        Args:
            token_in: Input token symbol or address
            token_out: Output token symbol or address
            amount_in: Amount to swap (in tokens, not wei)
            fee: Pool fee tier (500=0.05%, 3000=0.3%, 10000=1%)
            
        Returns:
            SwapQuote with quote details
        """
        # Resolve token addresses
        if not Web3.is_address(token_in):
            token_in = self.get_token_address(token_in)
        if not Web3.is_address(token_out):
            token_out = self.get_token_address(token_out)
        
        decimals = self.get_decimals(token_in if not Web3.is_address(token_in) else "ETH")
        amount_wei = int(amount_in * (10 ** decimals))
        
        # Quoter ABI for getting quotes
        quoter_abi = [
            {
                "name": "quoteExactInputSingle",
                "type": "function",
                "inputs": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
                "outputs": [
                    {"name": "amountOut", "type": "uint256"},
                    {"name": "sqrtPriceX96", "type": "uint160"},
                    {"name": "initialized", "type": "bool"},
                ],
            }
        ]
        
        quoter = self.w3.eth.contract(
            address=self.quoter_address,
            abi=quoter_abi,
        )
        
        try:
            result = quoter.functions.quoteExactInputSingle(
                token_in,
                token_out,
                amount_wei,
                fee,
                0,
            ).call()
            
            amount_out = result[0]
            decimals_out = self.get_decimals(token_out if not Web3.is_address(token_out) else "ETH")
            amount_out_tokens = amount_out / (10 ** decimals_out)
            
            # Estimate gas
            gas_estimate = self._estimate_swap_gas(amount_wei, amount_out)
            
            # Calculate price impact (simplified)
            price_impact = self._calculate_price_impact(
                amount_wei, amount_out, token_in, token_out
            )
            
            return SwapQuote(
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_wei,
                amount_out=amount_out,
                price_impact=price_impact,
                gas_estimate=gas_estimate,
                router_address=self.router_address,
                data=b"",
                protocol="uniswap_v3",
                slippage_tolerance=RISK_CONFIG["max_slippage_percent"] / 100,
            )
            
        except Exception as e:
            logger.error(f"Quote error: {e}")
            raise
    
    def _estimate_swap_gas(self, amount_in: int, amount_out: int) -> int:
        """Estimate gas for a swap"""
        # Base gas + proportional to amount
        base_gas = 100000
        amount_factor = amount_in // (10**18)
        return base_gas + (amount_factor * 1000)
    
    def _calculate_price_impact(
        self,
        amount_in: int,
        amount_out: int,
        token_in: str,
        token_out: str,
    ) -> float:
        """Calculate price impact of a swap"""
        # Simplified - in production use actual pool reserves
        # This would need to query the actual pool
        return 0.001  # 0.1% default
    
    def build_swap_data(
        self,
        quote: SwapQuote,
        recipient: Optional[str] = None,
        deadline_seconds: int = 600,
    ) -> dict:
        """
        Build swap transaction data
        
        Args:
            quote: SwapQuote from get_quote
            recipient: Recipient address (defaults to wallet)
            deadline_seconds: Transaction deadline
            
        Returns:
            Transaction data dictionary
        """
        if recipient is None:
            recipient = self.address
        
        deadline = int(time.time()) + deadline_seconds
        
        # Calculate minimum output with slippage
        min_output = int(
            quote.amount_out * (1 - quote.slippage_tolerance)
        )
        
        # For exact input single
        data = self.router.encodeABI(
            "exactInputSingle",
            args=[
                quote.token_in,
                quote.token_out,
                3000,  # fee
                recipient,
                deadline,
                quote.amount_in,
                min_output,
                0,  # sqrtPriceLimitX96
            ],
        )
        
        return {
            "to": self.router_address,
            "data": data,
            "value": 0,
        }
    
    def execute_swap(
        self,
        quote: SwapQuote,
        dry_run: bool = False,
        wait_for_receipt: bool = True,
    ) -> SwapResult:
        """
        Execute a swap
        
        Args:
            quote: SwapQuote from get_quote
            dry_run: If True, simulate without executing
            wait_for_receipt: Wait for transaction confirmation
            
        Returns:
            SwapResult with success status
        """
        if dry_run:
            logger.info(f"[DRY RUN] Would swap {quote.amount_in} for {quote.amount_out}")
            return SwapResult(
                success=True,
                quote=quote,
                tx_info=None,
            )
        
        try:
            # Build transaction
            tx_data = self.build_swap_data(quote)
            
            # Execute transaction
            tx_info = self.wallet.execute_transaction(
                to=tx_data["to"],
                value=tx_data.get("value", 0),
                data=bytes.fromhex(tx_data["data"][2:]),
            )
            
            if tx_info.status == "success":
                logger.info(f"Swap successful: {tx_info.tx_hash}")
                return SwapResult(
                    success=True,
                    quote=quote,
                    tx_info=tx_info,
                )
            else:
                return SwapResult(
                    success=False,
                    quote=quote,
                    tx_info=tx_info,
                    error="Transaction failed",
                )
                
        except Exception as e:
            logger.error(f"Swap error: {e}")
            return SwapResult(
                success=False,
                quote=quote,
                tx_info=None,
                error=str(e),
            )
    
    def get_pool_info(self, token_a: str, token_b: str, fee: int = 3000) -> Dict:
        """Get information about a specific pool"""
        if not Web3.is_address(token_a):
            token_a = self.get_token_address(token_a)
        if not Web3.is_address(token_b):
            token_b = self.get_token_address(token_b)
        
        # In production, query the pool contract
        # For now, return placeholder
        return {
            "token_a": token_a,
            "token_b": token_b,
            "fee": fee,
            "liquidity": 0,
            "tick": 0,
            "sqrt_price": 0,
        }


class OneInchAggregator:
    """
    1inch Aggregator integration for best price execution
    
    Benefits:
    - Routes across multiple DEXs
    - Better liquidity aggregation
    - Built-in slippage protection
    """
    
    def __init__(
        self,
        wallet: MetaMaskWallet,
        network: str = "ethereum",
    ):
        """Initialize 1inch aggregator"""
        self.wallet = wallet
        self.w3 = wallet.w3
        self.network = network
        self.api_url = ONE_INCH["api_url"]
        self.router_address = Web3.to_checksum_address(ONE_INCH["router"])
        
        # 1inch Aggregation Router ABI
        self.router_abi = [
            {
                "name": "swap",
                "type": "function",
                "inputs": [
                    {"name": "desc", "type": "tuple",
                     "components": [
                         {"name": "srcToken", "type": "address"},
                         {"name": "dstToken", "type": "address"},
                         {"name": "srcReceiver", "type": "address"},
                         {"name": "dstReceiver", "type": "address"},
                         {"name": "amount", "type": "uint256"},
                         {"name": "minReturnAmount", "type": "uint256"},
                         {"name": "flags", "type": "uint256"},
                         {"name": "permit", "type": "bytes"},
                     ]},
                    {"name": "data", "type": "bytes"},
                ],
                "outputs": [
                    {"name": "returnAmount", "type": "uint256"},
                    {"name": "spentAmount", "type": "uint256"},
                ],
            }
        ]
        
        self.router = self.w3.eth.contract(
            address=self.router_address,
            abi=self.router_abi,
        )
    
    def get_quote(
        self,
        token_in: str,
        token_out: str,
        amount_in: float,
    ) -> SwapQuote:
        """
        Get a quote from 1inch
        
        Args:
            token_in: Input token address
            token_out: Output token address
            amount_in: Amount to swap
            
        Returns:
            SwapQuote with best route
        """
        # Resolve addresses
        if not Web3.is_address(token_in):
            token_in = self._get_token_address(token_in)
        if not Web3.is_address(token_out):
            token_out = self._get_token_address(token_out)
        
        # Get API quote
        api_url = f"{self.api_url}/{self._get_chain_id()}/quote"
        params = {
            "fromTokenAddress": token_in,
            "toTokenAddress": token_out,
            "amount": str(int(amount_in * (10 ** 18))),
        }
        
        try:
            import requests
            response = requests.get(api_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            amount_out = int(data["toTokenAmount"])
            return SwapQuote(
                token_in=token_in,
                token_out=token_out,
                amount_in=int(amount_in * (10 ** 18)),
                amount_out=amount_out,
                price_impact=0.001,
                gas_estimate=150000,
                router_address=self.router_address,
                data=b"",
                protocol="1inch",
            )
            
        except Exception as e:
            logger.error(f"1inch quote error: {e}")
            raise
    
    def get_swap_data(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        min_return: int,
        recipient: Optional[str] = None,
    ) -> dict:
        """
        Get swap transaction data from 1inch API
        
        Args:
            token_in: Input token address
            token_out: Output token address
            amount_in: Amount in wei
            min_return: Minimum output amount
            recipient: Recipient address
            
        Returns:
            Transaction data dictionary
        """
        api_url = f"{self.api_url}/{self._get_chain_id()}/swap"
        params = {
            "fromTokenAddress": token_in,
            "toTokenAddress": token_out,
            "amount": str(amount_in),
            "slippage": RISK_CONFIG["max_slippage_percent"],
        }
        
        if recipient:
            params["destReceiver"] = recipient
        
        try:
            import requests
            response = requests.get(api_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            tx_data = data["tx"]["data"]
            tx_to = data["tx"]["to"]
            tx_value = int(data["tx"]["value"])
            
            return {
                "to": tx_to,
                "data": tx_data,
                "value": tx_value,
            }
            
        except Exception as e:
            logger.error(f"1inch swap data error: {e}")
            raise
    
    def execute_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: float,
        dry_run: bool = False,
    ) -> SwapResult:
        """
        Execute swap via 1inch
        
        Args:
            token_in: Input token
            token_out: Output token
            amount_in: Amount to swap
            dry_run: Simulate without executing
            
        Returns:
            SwapResult
        """
        # Get quote
        quote = self.get_quote(token_in, token_out, amount_in)
        
        if dry_run:
            return SwapResult(
                success=True,
                quote=quote,
                tx_info=None,
            )
        
        # Get swap data
        swap_data = self.get_swap_data(
            quote.token_in,
            quote.token_out,
            quote.amount_in,
            int(quote.amount_out * (1 - RISK_CONFIG["max_slippage_percent"] / 100)),
        )
        
        try:
            tx_info = self.wallet.execute_transaction(
                to=swap_data["to"],
                value=swap_data.get("value", 0),
                data=bytes.fromhex(swap_data["data"][2:]),
            )
            
            return SwapResult(
                success=tx_info.status == "success",
                quote=quote,
                tx_info=tx_info,
            )
            
        except Exception as e:
            return SwapResult(
                success=False,
                quote=quote,
                tx_info=None,
                error=str(e),
            )
    
    def _get_token_address(self, symbol: str) -> str:
        """Get token address by symbol"""
        # Simplified - use config tokens
        return symbol
    
    def _get_chain_id(self) -> int:
        """Get 1inch chain ID"""
        chain_ids = {
            "ethereum": 1,
            "polygon": 137,
            "arbitrum": 42161,
            "base": 8453,
        }
        return chain_ids.get(self.network, 1)


class DEXAggregator:
    """
    Unified DEX aggregator for best price execution
    
    Routes through:
    - Uniswap V3
    - 1inch
    - Other integrated DEXs
    """
    
    def __init__(
        self,
        wallet: MetaMaskWallet,
        network: str = "ethereum",
        use_1inch: bool = True,
    ):
        """Initialize aggregator"""
        self.wallet = wallet
        self.network = network
        
        self.uniswap = UniswapV3Interactor(wallet, network)
        self.oneinch = OneInchAggregator(wallet, network) if use_1inch else None
    
    def get_best_quote(
        self,
        token_in: str,
        token_out: str,
        amount_in: float,
    ) -> SwapQuote:
        """
        Get best quote across all DEXs
        
        Returns quote with highest output amount
        """
        quotes = []
        
        # Get Uniswap quote
        try:
            uniswap_quote = self.uniswap.get_quote(token_in, token_out, amount_in)
            quotes.append(("uniswap", uniswap_quote))
        except Exception as e:
            logger.warning(f"Uniswap quote failed: {e}")
        
        # Get 1inch quote
        if self.oneinch:
            try:
                oneinch_quote = self.oneinch.get_quote(token_in, token_out, amount_in)
                quotes.append(("1inch", oneinch_quote))
            except Exception as e:
                logger.warning(f"1inch quote failed: {e}")
        
        if not quotes:
            raise ValueError("No quotes available")
        
        # Return best quote (highest output)
        best = max(quotes, key=lambda x: x[1].amount_out)
        logger.info(f"Best quote: {best[0]} - {best[1].amount_out}")
        
        return best[1]
    
    def execute_best_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: float,
        dry_run: bool = False,
    ) -> SwapResult:
        """
        Execute swap via best DEX
        
        Args:
            token_in: Input token
            token_out: Output token
            amount_in: Amount to swap
            dry_run: Simulate without executing
            
        Returns:
            SwapResult
        """
        quote = self.get_best_quote(token_in, token_out, amount_in)
        
        if quote.protocol == "uniswap_v3":
            return self.uniswap.execute_swap(quote, dry_run)
        elif quote.protocol == "1inch" and self.oneinch:
            return self.oneinch.execute_swap(token_in, token_out, amount_in, dry_run)
        else:
            return SwapResult(
                success=False,
                quote=quote,
                tx_info=None,
                error=f"Unknown protocol: {quote.protocol}")

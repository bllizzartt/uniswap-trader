"""
Wallet Integration Module
MetaMask connection via Web3 for Ethereum-compatible networks
"""

import os
import json
import logging
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from web3 import Web3
from web3.eth import Eth
from web3.contract import Contract
from web3.types import TxReceipt, Wei
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3.gas_strategies import time_based_gas_price_strategy, construct_time_based_gas_price_strategy

from config import NETWORKS, ACTIVE_NETWORK, TRADING_CONFIG

logger = logging.getLogger(__name__)


class Network(Enum):
    ETHEREUM = "ethereum"
    POLYGON = "polygon"
    ARBITRUM = "arbitrum"
    BASE = "base"


@dataclass
class WalletBalance:
    """Wallet balance information"""
    native: float
    wrapped_native: float
    usdc: float
    usdt: float
    dai: float
    total_usd: float


@dataclass
class TransactionInfo:
    """Transaction information"""
    tx_hash: str
    from_address: str
    to_address: str
    value: float
    gas_used: int
    gas_price: int
    status: str
    block_number: Optional[int] = None


class MetaMaskWallet:
    """
    MetaMask wallet integration for Web3 trading
    
    Supports:
    - Ethereum, Polygon, Arbitrum, Base networks
    - Balance checking for ETH, WETH, USDC, USDT, DAI
    - Transaction signing and execution
    """
    
    def __init__(
        self,
        private_key: Optional[str] = None,
        network: str = "ethereum",
        rpc_url: Optional[str] = None,
    ):
        """
        Initialize wallet connection
        
        Args:
            private_key: Private key for signing (or None for read-only)
            network: Network name ('ethereum', 'polygon', 'arbitrum', 'base')
            rpc_url: Custom RPC URL (overrides config)
        """
        self.network_name = network
        self.network_config = NETWORKS.get(network, NETWORKS["ethereum"])
        self.chain_id = self.network_config["chain_id"]
        
        # Initialize Web3
        self.rpc_url = rpc_url or self.network_config["rpc_url"]
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        
        # Check connection
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {network} network")
        
        logger.info(f"Connected to {self.network_config['name']}")
        
        # Set gas strategy
        self.w3.eth.set_gas_price_strategy(
            time_based_gas_price_strategy(60)
        )
        
        # Initialize account
        self.account: Optional[LocalAccount] = None
        self.address: Optional[str] = None
        
        if private_key:
            if private_key.startswith("0x"):
                private_key = private_key[2:]
            self.account = Account.from_key(private_key)
            self.address = self.account.address
            logger.info(f"Wallet initialized: {self.address}")
        else:
            logger.warning("No private key provided - read-only mode")
    
    @classmethod
    def from_env(cls, env_var: str = "WALLET_PRIVATE_KEY") -> "MetaMaskWallet":
        """Create wallet from environment variable"""
        private_key = os.getenv(env_var)
        if not private_key:
            raise ValueError(f"Environment variable {env_var} not set")
        return cls(private_key=private_key)
    
    @property
    def is_connected(self) -> bool:
        """Check if wallet is connected"""
        return self.w3.is_connected()
    
    @property
    def block_number(self) -> int:
        """Get current block number"""
        return self.w3.eth.block_number
    
    @property
    def gas_price(self) -> int:
        """Get current gas price in wei"""
        try:
            return self.w3.eth.gas_price
        except Exception:
            return self.w3.eth.get_gas_price()
    
    @property
    def native_balance_wei(self) -> int:
        """Get native token balance in wei"""
        if not self.address:
            return 0
        return self.w3.eth.get_balance(self.address)
    
    @property
    def native_balance(self) -> float:
        """Get native token balance in ether"""
        return self.w3.from_wei(self.native_balance_wei, "ether")
    
    def get_erc20_balance(self, token_address: str, decimals: int = 18) -> Tuple[float, int]:
        """
        Get ERC20 token balance
        
        Args:
            token_address: Token contract address
            decimals: Token decimals
            
        Returns:
            Tuple of (balance in tokens, raw balance in smallest unit)
        """
        if not self.address:
            return 0.0, 0
        
        # Minimal ERC20 ABI
        abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            }
        ]
        
        contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=abi,
        )
        
        raw_balance = contract.functions.balanceOf(self.address).call()
        balance = raw_balance / (10 ** decimals)
        
        return balance, raw_balance
    
    def get_all_balances(self) -> WalletBalance:
        """Get all tracked token balances"""
        if not self.address:
            return WalletBalance(0, 0, 0, 0, 0, 0)
        
        # Get native balance
        native = self.native_balance
        
        # Token addresses (use network-specific when available)
        tokens = {
            "WETH": ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", 18),
            "USDC": ("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 6),
            "USDT": ("0xdAC17F958D2ee523a2206206994597C13D831ec7", 6),
            "DAI": ("0x6B175474E89094C44Da98b954EedeAC495271d0F", 18),
        }
        
        balances = {}
        for token_name, (address, decimals) in tokens.items():
            try:
                balance, _ = self.get_erc20_balance(address, decimals)
                balances[token_name] = balance
            except Exception as e:
                logger.error(f"Error fetching {token_name} balance: {e}")
                balances[token_name] = 0.0
        
        # Estimate total USD (simplified - use current prices)
        # In production, fetch real prices
        eth_price = 3000.0  # Placeholder
        usd_stable = 1.0
        
        total_usd = (
            native * eth_price +
            balances["WETH"] * eth_price +
            balances["USDC"] * usd_stable +
            balances["USDT"] * usd_stable +
            balances["DAI"] * usd_stable
        )
        
        return WalletBalance(
            native=native,
            wrapped_native=balances["WETH"],
            usdc=balances["USDC"],
            usdt=balances["USDT"],
            dai=balances["DAI"],
            total_usd=total_usd,
        )
    
    def build_transaction(
        self,
        to: str,
        value: int = 0,
        data: bytes = b"",
        gas_limit: Optional[int] = None,
    ) -> dict:
        """
        Build a transaction dictionary
        
        Args:
            to: Recipient address
            value: Value in wei
            data: Transaction data
            gas_limit: Optional gas limit override
            
        Returns:
            Transaction dictionary ready for signing
        """
        if not self.address:
            raise ValueError("No account available for signing")
        
        if not gas_limit:
            try:
                gas_limit = self.w3.eth.estimate_gas({
                    "from": self.address,
                    "to": to,
                    "value": value,
                    "data": data,
                })
            except Exception:
                gas_limit = TRADING_CONFIG["default_gas_limit"]
        
        gas_price = int(self.gas_price * TRADING_CONFIG["gas_multiplier"])
        
        transaction = {
            "from": self.address,
            "to": to,
            "value": value,
            "data": data,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "chainId": self.chain_id,
        }
        
        return transaction
    
    def sign_transaction(self, transaction: dict) -> str:
        """
        Sign a transaction
        
        Args:
            transaction: Transaction dictionary
            
        Returns:
            Signed transaction as hex string
        """
        if not self.account:
            raise ValueError("No private key available for signing")
        
        signed = self.account.sign_transaction(transaction)
        return signed.rawTransaction.hex()
    
    def send_raw_transaction(self, signed_tx: str) -> str:
        """
        Send a signed transaction
        
        Args:
            signed_tx: Signed transaction hex string
            
        Returns:
            Transaction hash
        """
        tx_hash = self.w3.eth.send_raw_transaction(
            bytes.fromhex(signed_tx[2:] if signed_tx.startswith("0x") else signed_tx)
        ).hex()
        
        return tx_hash
    
    def execute_transaction(
        self,
        to: str,
        value: int = 0,
        data: bytes = b"",
        gas_limit: Optional[int] = None,
        wait_for_receipt: bool = True,
    ) -> TransactionInfo:
        """
        Execute a transaction end-to-end
        
        Args:
            to: Recipient address
            value: Value in wei
            data: Transaction data
            gas_limit: Optional gas limit
            wait_for_receipt: Wait for transaction confirmation
            
        Returns:
            TransactionInfo with receipt details
        """
        # Build transaction
        tx = self.build_transaction(to, value, data, gas_limit)
        
        # Sign transaction
        signed_tx = self.sign_transaction(tx)
        
        # Send transaction
        tx_hash = self.send_raw_transaction(signed_tx)
        logger.info(f"Transaction sent: {tx_hash}")
        
        if wait_for_receipt:
            return self.wait_for_receipt(tx_hash)
        else:
            return TransactionInfo(
                tx_hash=tx_hash,
                from_address=self.address,
                to_address=to,
                value=self.w3.from_wei(value, "ether"),
                gas_used=0,
                gas_price=0,
                status="pending",
            )
    
    def wait_for_receipt(self, tx_hash: str, timeout: int = 120) -> TransactionInfo:
        """
        Wait for transaction receipt
        
        Args:
            tx_hash: Transaction hash
            timeout: Timeout in seconds
            
        Returns:
            TransactionInfo with receipt details
        """
        receipt = self.w3.eth.wait_for_transaction_receipt(
            tx_hash,
            timeout=timeout,
        )
        
        status = "success" if receipt.status == 1 else "failed"
        
        return TransactionInfo(
            tx_hash=tx_hash,
            from_address=self.address,
            to_address=receipt.to,
            value=self.w3.from_wei(receipt.value, "ether"),
            gas_used=receipt.gasUsed,
            gas_price=receipt.effectiveGasPrice,
            status=status,
            block_number=receipt.blockNumber,
        )
    
    def approve_token(
        self,
        token_address: str,
        spender_address: str,
        amount: int,
    ) -> TransactionInfo:
        """
        Approve an ERC20 token for spending
        
        Args:
            token_address: Token contract address
            spender_address: Address to approve
            amount: Amount to approve (in smallest unit)
            
        Returns:
            TransactionInfo
        """
        abi = [
            {
                "name": "approve",
                "type": "function",
                "inputs": [
                    {"name": "spender", "type": "address"},
                    {"name": "amount", "type": "uint256"},
                ],
                "outputs": [{"name": "", "type": "bool"}],
            }
        ]
        
        contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=abi,
        )
        
        data = contract.encodeABI("approve", [spender_address, amount])
        
        return self.execute_transaction(
            to=token_address,
            value=0,
            data=data,
        )
    
    def check_allowance(
        self,
        token_address: str,
        spender_address: str,
    ) -> int:
        """
        Check token allowance for spender
        
        Args:
            token_address: Token contract address
            spender_address: Spender address
            
        Returns:
            Allowance amount
        """
        abi = [
            {
                "constant": True,
                "inputs": [
                    {"name": "owner", "type": "address"},
                    {"name": "spender", "type": "address"},
                ],
                "name": "allowance",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function",
            }
        ]
        
        contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=abi,
        )
        
        return contract.functions.allowance(
            self.address,
            spender_address,
        ).call()
    
    def switch_network(self, network: str) -> None:
        """
        Switch to a different network
        
        Args:
            network: Network name
        """
        if network not in NETWORKS:
            raise ValueError(f"Unknown network: {network}")
        
        self.network_name = network
        self.network_config = NETWORKS[network]
        self.chain_id = self.network_config["chain_id"]
        self.rpc_url = self.network_config["rpc_url"]
        
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {network}")
        
        logger.info(f"Switched to {self.network_config['name']}")
    
    def __repr__(self) -> str:
        if self.address:
            return f"<MetaMaskWallet: {self.address[:6]}...{self.address[-4:]}>"
        return "<MetaMaskWallet: (read-only)>"

# Uniswap Trading Bot - Configuration
# Settings for German crypto trading compliance

import os
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent

# Trading Mode: 'paper' or 'live'
TRADING_MODE = os.getenv("TRADING_MODE", "paper")

# Network Configuration
NETWORKS = {
    "ethereum": {
        "chain_id": 1,
        "name": "Ethereum Mainnet",
        "rpc_url": os.getenv("ETHEREUM_RPC_URL", "https://eth-mainnet.g.alchemy.com/v2/demo"),
        "explorer_url": "https://etherscan.io",
        "native_currency": "ETH",
        "wrapped_native": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "gas_oracle": "https://ethgasstation.info/api/ethgasAPI.json",
    },
    "polygon": {
        "chain_id": 137,
        "name": "Polygon Mainnet",
        "rpc_url": os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com"),
        "explorer_url": "https://polygonscan.com",
        "native_currency": "MATIC",
        "wrapped_native": "0x0d500B1d8EFAe3FeDDAc8A9D0fB9C7c0c0c0c0c0",
        "gas_oracle": "https://api.polygonscan.com/api?module=gastracker&action=gasoracle",
    },
    "arbitrum": {
        "chain_id": 42161,
        "name": "Arbitrum One",
        "rpc_url": os.getenv("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc"),
        "explorer_url": "https://arbiscan.io",
        "native_currency": "ETH",
        "wrapped_native": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "gas_oracle": "https://api.arbiscan.io/api?module=gastracker&action=gasoracle",
    },
    "base": {
        "chain_id": 8453,
        "name": "Base",
        "rpc_url": os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
        "explorer_url": "https://basescan.org",
        "native_currency": "ETH",
        "wrapped_native": "0x4200000000000000000000000000000000000006",
        "gas_oracle": "https://api.basescan.org/api?module=gastracker&action=gasoracle",
    },
}

# Default network
DEFAULT_NETWORK = os.getenv("DEFAULT_NETWORK", "ethereum")
ACTIVE_NETWORK = NETWORKS.get(DEFAULT_NETWORK, NETWORKS["ethereum"])

# Token Addresses (Uniswap V3)
TOKENS = {
    # Ethereum
    "ETH": {"address": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE", "decimals": 18},
    "WETH": {"address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "decimals": 18},
    "USDC": {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
    "USDT": {"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
    "DAI": {"address": "0x6B175474E89094C44Da98b954EedeAC495271d0F", "decimals": 18},
    # Add more tokens as needed
}

# Uniswap V3 Contracts
UNISWAP_V3 = {
    "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
    "router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
    "quoter": "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
    "multicall": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
}

# 1inch Aggregator
ONE_INCH = {
    "router": "0x1111111254EEB25477B68fb85Ed929f73A960582",
    "api_url": "https://api.1inch.dev/v5.0",
}

# Risk Management
RISK_CONFIG = {
    "max_position_size_percent": 0.10,  # Max 10% of portfolio per trade
    "max_slippage_percent": 1.0,        # Max 1% slippage
    "stop_loss_percent": 5.0,           # 5% stop loss
    "take_profit_percent": 15.0,        # 15% take profit
    "daily_loss_limit_percent": 10.0,   # Max 10% daily loss
    "max_open_positions": 5,            # Max concurrent positions
    "min_liquidity_usd": 10000,         # Min pool liquidity
    "max_gas_price_gwei": 100,          # Max gas price to execute
}

# Trading Parameters
TRADING_CONFIG = {
    "default_gas_limit": 300000,
    "gas_multiplier": 1.2,              # Add 20% buffer to gas estimate
    "confirmation_blocks": 1,           # Blocks to wait for confirmation
    "retry_attempts": 3,
    "retry_delay_seconds": 5,
}

# Strategy Settings
STRATEGIES = {
    "momentum": {
        "trend_period": 14,             # RSI period
        "overbought": 70,               # RSI overbought
        "oversold": 30,                 # RSI oversold
        "min_trend_strength": 0.02,      # Min price change for trend
    },
    "mean_reversion": {
        "lookback_period": 24,          # Hours
        "deviation_threshold": 0.05,    # 5% deviation from mean
    },
    "grid_trading": {
        "grid_levels": 5,
        "grid_spacing_percent": 1.0,     # 1% between grid levels
    },
    "trend_following": {
        "fast_ma_period": 10,
        "slow_ma_period": 30,
    },
}

# Market Data APIs
APIS = {
    "coingecko": {
        "base_url": "https://api.coingecko.com/api/v3",
        "api_key": os.getenv("COINGECKO_API_KEY", ""),
    },
    "chainlink": {
        "base_url": "https://api.chain.link/v1",
    },
    "etherscan": {
        "api_key": os.getenv("ETHERSCAN_API_KEY", ""),
        "base_url": "https://api.etherscan.io/api",
    },
}

# Dashboard Configuration
DASHBOARD = {
    "host": os.getenv("DASHBOARD_HOST", "0.0.0.0"),
    "port": int(os.getenv("DASHBOARD_PORT", 5000)),
    "debug": os.getenv("DASHBOARD_DEBUG", "False").lower() == "true",
    "secret_key": os.getenv("DASHBOARD_SECRET", "dev-secret-change-in-prod"),
}

# Logging Configuration
LOGGING = {
    "level": os.getenv("LOG_LEVEL", "INFO"),
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": PROJECT_ROOT / "logs/trading_bot.log",
    "max_bytes": 10 * 1024 * 1024,  # 10MB
    "backup_count": 5,
}

# German Compliance
COMPLIANCE = {
    "track_all_transactions": True,
    "generate_tax_reports": True,
    "kYC_verified": True,  # Set to True after KYC completion
    "allowed_jurisdictions": ["DE", "EU"],
}

# Emergency Contacts
EMERGENCY = {
    "stop_all_trades": False,
    "emergency_contact": os.getenv("EMERGENCY_CONTACT", ""),
}

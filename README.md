# Uniswap Trading Bot

Automated trading bot for Uniswap DEX with paper trading and risk management.

## Features

- **Multi-Network**: Ethereum, Polygon, Arbitrum, Base
- **Paper Trading**: Test strategies with virtual money
- **Live Trading**: Execute real swaps via MetaMask
- **Strategies**: Arbitrage, Momentum, Grid, Trend Following
- **Risk Management**: Position sizing, stop losses, daily limits
- **Dashboard**: Web interface for monitoring

## Quick Start

### 1. Install Dependencies
```bash
cd /Users/cortana/.openclaw/workspace/projects/uniswap-trader
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your Alchemy API key and wallet details
```

### 3. Run Paper Trading
```bash
python paper_trader.py --network polygon --strategy momentum
```

### 4. Start Dashboard
```bash
python dashboard.py --port 5001
```

## Configuration

Edit `config.py` or set environment variables:
- `ALCHEMY_API_KEY` - Your Alchemy API key
- `PRIVATE_KEY` - MetaMask private key (for live trading)
- `NETWORK` - polygon, ethereum, arbitrum, or base

## Networks

| Network | RPC Endpoint | Gas Cost |
|---------|-------------|----------|
| Polygon | https://polygon-mainnet.g.alchemy.com | Low |
| Arbitrum | https://arb-mainnet.g.alchemy.com | Low |
| Base | https://base-mainnet.g.alchemy.com | Low |
| Ethereum | https://eth-mainnet.g.alchemy.com | High |

## Safety

- Start with paper trading
- Use small amounts for live trading
- Set daily loss limits
- Never share private keys

## License

MIT

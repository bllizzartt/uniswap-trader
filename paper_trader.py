"""
Paper Trading Module
Virtual trading without real money
"""

import os
import json
import logging
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from config import TRADING_MODE, TRADING_CONFIG
from market_data import MarketDataProvider
from risk import RiskManager, RiskLevel
from strategies import TradeSignal, Position, PositionType, OrderStatus

logger = logging.getLogger(__name__)


class PaperWallet:
    """
    Virtual wallet for paper trading
    
    Simulates:
    - Token balances
    - Transaction execution
    - Gas costs (without real payment)
    """
    
    def __init__(
        self,
        initial_eth: float = 10.0,
        initial_usdc: float = 10000.0,
    ):
        """
        Initialize paper wallet
        
        Args:
            initial_eth: Starting ETH balance
            initial_usdc: Starting USDC balance
        """
        self.balances = {
            "ETH": initial_eth,
            "WETH": 0.0,
            "USDC": initial_usdc,
            "USDT": 0.0,
            "DAI": 0.0,
        }
        
        self.address = "0xPaperTrading" + "0" * 34
        self.tx_history: List[Dict] = []
        
        logger.info(f"Paper wallet initialized: {initial_eth} ETH, {initial_usdc} USDC")
    
    @property
    def eth_balance(self) -> float:
        """Get ETH balance"""
        return self.balances.get("ETH", 0.0)
    
    @property
    def usdc_balance(self) -> float:
        """Get USDC balance"""
        return self.balances.get("USDC", 0.0)
    
    @property
    def total_usd(self) -> float:
        """Get total portfolio value in USD"""
        # Assume ETH = $3000
        eth_value = self.balances.get("ETH", 0) * 3000
        weth_value = self.balances.get("WETH", 0) * 3000
        usdc_value = self.balances.get("USDC", 0)
        usdt_value = self.balances.get("USDT", 0)
        dai_value = self.balances.get("DAI", 0)
        
        return eth_value + weth_value + usdc_value + usdt_value + dai_value
    
    def get_balance(self, token: str) -> float:
        """Get token balance"""
        return self.balances.get(token.upper(), 0.0)
    
    def set_balance(self, token: str, amount: float):
        """Set token balance (for testing)"""
        self.balances[token.upper()] = amount
    
    def transfer(
        self,
        token_in: str,
        token_out: str,
        amount_in: float,
        simulated_price: float,
    ) -> Tuple[float, float, Dict]:
        """
        Simulate a token swap
        
        Args:
            token_in: Input token
            token_out: Output token
            amount_in: Amount to swap
            simulated_price: Simulated exchange rate
            
        Returns:
            Tuple of (amount_out, gas_cost, tx_info)
        """
        # Check balance
        balance_in = self.get_balance(token_in)
        if amount_in > balance_in:
            raise ValueError(f"Insufficient {token_in} balance: {balance_in} < {amount_in}")
        
        # Calculate output
        amount_out = amount_in * simulated_price
        
        # Simulate gas cost
        gas_cost = 0.01  # Simulated gas cost in ETH
        
        # Update balances
        self.balances[token_in.upper()] -= amount_in
        self.balances[token_out.upper()] = self.balances.get(token_out.upper(), 0) + amount_out
        
        # Pay gas (if ETH involved)
        if token_in.upper() != "ETH" and token_out.upper() != "ETH":
            self.balances["ETH"] -= gas_cost
        
        # Record transaction
        tx_info = {
            "tx_hash": f"0xPaper{len(self.tx_history):08x}",
            "from": self.address,
            "to": "PaperRouter",
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": amount_in,
            "amount_out": amount_out,
            "gas_cost": gas_cost,
            "timestamp": datetime.now().isoformat(),
            "status": "confirmed",
        }
        
        self.tx_history.append(tx_info)
        
        return amount_out, gas_cost, tx_info
    
    def wrap_eth(self, amount: float) -> Tuple[float, Dict]:
        """Simulate wrapping ETH"""
        if amount > self.balances["ETH"]:
            raise ValueError(f"Insufficient ETH: {self.balances['ETH']} < {amount}")
        
        self.balances["ETH"] -= amount
        self.balances["WETH"] += amount
        
        tx_info = {
            "tx_hash": f"0xPaperWrap{len(self.tx_history):08x}",
            "type": "wrap",
            "amount": amount,
            "timestamp": datetime.now().isoformat(),
        }
        
        return amount, tx_info
    
    def unwrap_weth(self, amount: float) -> Tuple[float, Dict]:
        """Simulate unwrapping WETH"""
        if amount > self.balances["WETH"]:
            raise ValueError(f"Insufficient WETH: {self.balances['WETH']} < {amount}")
        
        self.balances["WETH"] -= amount
        self.balances["ETH"] += amount
        
        tx_info = {
            "tx_hash": f"0xPaperUnwrap{len(self.tx_history):08x}",
            "type": "unwrap",
            "amount": amount,
            "timestamp": datetime.now().isoformat(),
        }
        
        return amount, tx_info


class PaperTrader:
    """
    Paper trading simulator
    
    Features:
    - Virtual portfolio
    - Simulated trades
    - P&L tracking
    - Strategy testing
    """
    
    def __init__(
        self,
        market_data: MarketDataProvider,
        initial_eth: float = 10.0,
        initial_usdc: float = 10000.0,
    ):
        """
        Initialize paper trader
        
        Args:
            market_data: MarketDataProvider instance
            initial_eth: Starting ETH
            initial_usdc: Starting USDC
        """
        self.market_data = market_data
        
        # Initialize wallet
        self.wallet = PaperWallet(initial_eth, initial_usdc)
        
        # Initialize risk manager
        risk_manager = RiskManager(
            market_data=market_data,
            initial_portfolio_value=self.wallet.total_usd,
            paper_mode=True,
        )
        
        self.risk_manager = risk_manager
        
        # Position tracking
        self.positions: Dict[str, Dict] = {}
        self.trade_history: List[Dict] = []
        
        # Performance tracking
        self.start_value = self.wallet.total_usd
        self.highest_value = self.start_value
        self.lowest_value = self.start_value
        
        logger.info(f"Paper trader initialized. Starting value: ${self.start_value:,.2f}")
    
    @property
    def portfolio_value(self) -> float:
        """Get current portfolio value"""
        return self.wallet.total_usd
    
    @property
    def total_pnl(self) -> float:
        """Get total P&L"""
        return self.portfolio_value - self.start_value
    
    @property
    def total_pnl_percent(self) -> float:
        """Get total P&L percentage"""
        if self.start_value > 0:
            return (self.total_pnl / self.start_value) * 100
        return 0.0
    
    def get_token_price(self, token: str) -> float:
        """Get current token price"""
        return self.market_data.get_current_price(token)
    
    def execute_buy(
        self,
        token: str,
        amount_usd: float,
        confidence: float = 1.0,
    ) -> Dict:
        """
        Execute a paper buy order
        
        Args:
            token: Token to buy
            amount_usd: Amount in USD to spend
            confidence: Strategy confidence
            
        Returns:
            Order details
        """
        # Check risk
        allowed, reason = self.risk_manager.can_open_position(token, amount_usd, confidence)
        if not allowed:
            return {
                "success": False,
                "reason": reason,
                "error": "Risk check failed",
            }
        
        # Get current price
        price = self.get_token_price(token)
        if price <= 0:
            return {
                "success": False,
                "error": f"Invalid price for {token}",
            }
        
        # Calculate token amount
        token_amount = amount_usd / price
        
        # Calculate position size
        position_size = self.risk_manager.calculate_position_size(token, confidence)
        
        # Execute swap (USDC -> Token)
        try:
            # Convert USDC to token at current price
            simulated_price = 1 / price  # USDC per token
            
            # Actually swap USDC for tokens
            token_out, gas_cost, tx_info = self.wallet.transfer(
                token_in="USDC",
                token_out=token,
                amount_in=amount_usd,
                simulated_price=1/price,  # Token per USD
            )
            
            # Record position
            position = {
                "token": token,
                "type": "long",
                "size_usd": amount_usd,
                "token_amount": token_out,
                "entry_price": price,
                "entry_time": datetime.now().isoformat(),
                "stop_loss": self.risk_manager.calculate_stop_loss(token, price, "long", confidence),
                "take_profit": self.risk_manager.calculate_take_profit(token, price, "long", confidence),
                "confidence": confidence,
                "entry_tx": tx_info,
            }
            
            self.positions[token] = position
            
            # Update portfolio tracking
            current_value = self.wallet.total_usd
            if current_value > self.highest_value:
                self.highest_value = current_value
            if current_value < self.lowest_value:
                self.lowest_value = current_value
            
            logger.info(f"PAPER BUY: {token} {token_amount:.6f} @ ${price:.2f} (${amount_usd:.2f})")
            
            return {
                "success": True,
                "action": "buy",
                "token": token,
                "amount": token_out,
                "price": price,
                "total_usd": amount_usd,
                "gas_cost": gas_cost,
                "position": position,
            }
            
        except Exception as e:
            logger.error(f"Paper buy error: {e}")
            return {
                "success": False,
                "error": str(e),
            }
    
    def execute_sell(
        self,
        token: str,
        amount_percent: float = 1.0,
    ) -> Dict:
        """
        Execute a paper sell order
        
        Args:
            token: Token to sell
            amount_percent: Percentage of position to sell (0-1)
            
        Returns:
            Order details
        """
        if token not in self.positions:
            return {
                "success": False,
                "error": f"No position in {token}",
            }
        
        position = self.positions[token]
        
        # Calculate sell amount
        sell_amount = position["token_amount"] * amount_percent
        sell_percent = position["size_usd"] * amount_percent
        
        # Get current price
        current_price = self.get_token_price(token)
        
        # Execute swap
        try:
            # Swap token back to USDC
            simulated_price = 1 / current_price  # USD per token
            
            usdc_out, gas_cost, tx_info = self.wallet.transfer(
                token_in=token,
                token_out="USDC",
                amount_in=sell_amount,
                simulated_price=current_price,
            )
            
            # Update position
            position["token_amount"] -= sell_amount
            position["size_usd"] -= sell_percent
            
            # Check if position is closed
            if position["token_amount"] < 0.0001 or amount_percent >= 1.0:
                # Calculate final P&L
                entry_value = position["size_usd"] / (1 - amount_percent) if amount_percent < 1 else position["size_usd"]
                exit_value = sell_percent
                pnl = exit_value - entry_value
                pnl_percent = (pnl / entry_value) * 100 if entry_value > 0 else 0
                
                # Record trade
                trade = {
                    **position,
                    "exit_price": current_price,
                    "exit_time": datetime.now().isoformat(),
                    "exit_tx": tx_info,
                    "pnl": pnl,
                    "pnl_percent": pnl_percent,
                    "close_reason": "manual",
                }
                
                self.trade_history.append(trade)
                del self.positions[token]
                
                logger.info(f"PAPER SELL: {token} @ ${current_price:.2f} (${sell_percent:.2f}), P&L: ${pnl:.2f} ({pnl_percent:.2f}%)")
            else:
                logger.info(f"PAPER SELL: {token} @ ${current_price:.2f} (${sell_percent:.2f})")
            
            return {
                "success": True,
                "action": "sell",
                "token": token,
                "amount": sell_amount,
                "price": current_price,
                "total_usd": sell_percent,
                "gas_cost": gas_cost,
                "remaining_position": position.get("token_amount", 0),
            }
            
        except Exception as e:
            logger.error(f"Paper sell error: {e}")
            return {
                "success": False,
                "error": str(e),
            }
    
    def execute_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: float,
    ) -> Dict:
        """
        Execute a direct paper swap
        
        Args:
            token_in: Input token
            token_out: Output token
            amount_in: Amount to swap
            
        Returns:
            Swap details
        """
        price_in = self.get_token_price(token_in)
        price_out = self.get_token_price(token_out)
        
        if price_out <= 0:
            return {"success": False, "error": f"Invalid price for {token_out}"}
        
        # Calculate output
        value_usd = amount_in * price_in
        amount_out = value_usd / price_out
        
        # Execute
        try:
            out, gas_cost, tx_info = self.wallet.transfer(
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in,
                simulated_price=price_out,
            )
            
            logger.info(f"PAPER SWAP: {amount_in} {token_in} -> {out} {token_out}")
            
            return {
                "success": True,
                "token_in": token_in,
                "token_out": token_out,
                "amount_in": amount_in,
                "amount_out": out,
                "price_in": price_in,
                "price_out": price_out,
                "gas_cost": gas_cost,
                "tx": tx_info,
            }
            
        except Exception as e:
            logger.error(f"Paper swap error: {e}")
            return {"success": False, "error": str(e)}
    
    def check_positions(self) -> List[Dict]:
        """Check all positions for stop loss / take profit"""
        closed_positions = []
        
        for token, position in list(self.positions.items()):
            current_price = self.get_token_price(token)
            
            if not current_price:
                continue
            
            # Update current value
            current_value = position["token_amount"] * current_price
            position["current_price"] = current_price
            position["current_value"] = current_value
            
            # Calculate P&L
            entry_value = position["size_usd"]
            pnl = current_value - entry_value
            pnl_percent = (pnl / entry_value) * 100 if entry_value > 0 else 0
            
            position["pnl"] = pnl
            position["pnl_percent"] = pnl_percent
            
            # Check stop loss
            if position["stop_loss"]:
                if position["type"] == "long" and current_price <= position["stop_loss"]:
                    self.execute_sell(token, 1.0)
                    closed_positions.append({
                        "token": token,
                        "reason": "stop_loss",
                        "exit_price": current_price,
                    })
                    continue
            
            # Check take profit
            if position["take_profit"]:
                if position["type"] == "long" and current_price >= position["take_profit"]:
                    self.execute_sell(token, 1.0)
                    closed_positions.append({
                        "token": token,
                        "reason": "take_profit",
                        "exit_price": current_price,
                    })
                    continue
        
        return closed_positions
    
    def get_portfolio_summary(self) -> Dict:
        """Get portfolio summary"""
        positions_data = []
        
        for token, position in self.positions.items():
            current_price = self.get_token_price(token)
            current_value = position["token_amount"] * current_price
            
            positions_data.append({
                "token": token,
                "amount": position["token_amount"],
                "entry_price": position["entry_price"],
                "current_price": current_price,
                "value": current_value,
                "pnl": current_value - position["size_usd"],
                "pnl_percent": ((current_value / position["size_usd"]) - 1) * 100 if position["size_usd"] > 0 else 0,
                "stop_loss": position["stop_loss"],
                "take_profit": position["take_profit"],
            })
        
        return {
            "total_value": self.portfolio_value,
            "total_pnl": self.total_pnl,
            "total_pnl_percent": self.total_pnl_percent,
            "cash_usdc": self.wallet.get_balance("USDC"),
            "cash_eth": self.wallet.get_balance("ETH"),
            "open_positions": len(self.positions),
            "positions": positions_data,
            "trade_history_count": len(self.trade_history),
        }
    
    def get_performance_report(self) -> Dict:
        """Get detailed performance report"""
        if not self.trade_history:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_trade": 0.0,
                "best_trade": {"pnl": 0, "token": ""},
                "worst_trade": {"pnl": 0, "token": ""},
            }
        
        winning_trades = [t for t in self.trade_history if t.get("pnl", 0) > 0]
        losing_trades = [t for t in self.trade_history if t.get("pnl", 0) <= 0]
        
        total_pnl = sum(t.get("pnl", 0) for t in self.trade_history)
        avg_trade = total_pnl / len(self.trade_history)
        
        best_trade = max(self.trade_history, key=lambda t: t.get("pnl", 0))
        worst_trade = min(self.trade_history, key=lambda t: t.get("pnl", 0))
        
        return {
            "total_trades": len(self.trade_history),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": (len(winning_trades) / len(self.trade_history)) * 100 if self.trade_history else 0,
            "total_pnl": total_pnl,
            "avg_trade": avg_trade,
            "best_trade": {
                "token": best_trade.get("token", ""),
                "pnl": best_trade.get("pnl", 0),
                "pnl_percent": best_trade.get("pnl_percent", 0),
            },
            "worst_trade": {
                "token": worst_trade.get("token", ""),
                "pnl": worst_trade.get("pnl", 0),
                "pnl_percent": worst_trade.get("pnl_percent", 0),
            },
            "peak_value": self.highest_value,
            "trough_value": self.lowest_value,
        }
    
    def reset(self, initial_eth: float = 10.0, initial_usdc: float = 10000.0):
        """Reset paper trader with new balances"""
        self.wallet = PaperWallet(initial_eth, initial_usdc)
        self.positions = {}
        self.trade_history = []
        self.start_value = self.wallet.total_usd
        self.highest_value = self.start_value
        self.lowest_value = self.start_value
        
        logger.info(f"Paper trader reset. Starting value: ${self.start_value:,.2f}")

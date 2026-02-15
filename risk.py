"""
Risk Management Module
Position sizing, stop losses, portfolio protection
"""

import os
import json
import logging
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from config import RISK_CONFIG, TRADING_CONFIG, NETWORKS
from market_data import MarketDataProvider

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class RiskMetrics:
    """Risk assessment metrics"""
    risk_score: float  # 0-100
    risk_level: RiskLevel
    max_position_size: float
    recommended_stop_loss: float
    recommended_take_profit: float
    volatility: float
    liquidity_risk: bool
    smart_contract_risk: bool
    market_impact: float


@dataclass
class PortfolioMetrics:
    """Portfolio-level metrics"""
    total_value: float
    daily_pnl: float
    daily_pnl_percent: float
    total_pnl: float
    total_pnl_percent: float
    open_positions_value: float
    open_positions_count: int
    risk_exposure: float
    leverage: float


class RiskManager:
    """
    Comprehensive risk management for trading
    
    Features:
    - Position sizing based on risk
    - Stop loss and take profit calculation
    - Daily loss limits
    - Portfolio exposure monitoring
    - Emergency stop functionality
    """
    
    def __init__(
        self,
        market_data: MarketDataProvider,
        initial_portfolio_value: float = 0,
        paper_mode: bool = True,
    ):
        """
        Initialize risk manager
        
        Args:
            market_data: MarketDataProvider instance
            initial_portfolio_value: Starting portfolio value
            paper_mode: Paper trading mode (no real risk)
        """
        self.market_data = market_data
        self.paper_mode = paper_mode
        
        # Portfolio tracking
        self.initial_portfolio_value = initial_portfolio_value
        self.current_portfolio_value = initial_portfolio_value
        self.daily_start_value = initial_portfolio_value
        
        # Daily tracking
        self.daily_loss_limit = RISK_CONFIG["daily_loss_limit_percent"] / 100
        self.daily_highest_value = initial_portfolio_value
        self.daily_trades = 0
        self.daily_losses = 0
        
        # Position limits
        self.max_open_positions = RISK_CONFIG["max_open_positions"]
        self.max_position_percent = RISK_CONFIG["max_position_size_percent"]
        
        # Emergency stop
        self.emergency_stop_active = False
        self.emergency_stop_reason: Optional[str] = None
        
        # Position tracking
        self.positions: Dict[str, Dict] = {}
        
        # Transaction history
        self.trade_history: List[Dict] = []
    
    def set_portfolio_value(self, value: float):
        """Update current portfolio value"""
        self.current_portfolio_value = value
        if value > self.daily_highest_value:
            self.daily_highest_value = value
    
    def can_open_position(
        self,
        token: str,
        position_size: float,
        confidence: float = 1.0,
    ) -> Tuple[bool, str]:
        """
        Check if position can be opened
        
        Args:
            token: Token to trade
            position_size: Position size in USD
            confidence: Strategy confidence (0-1)
            
        Returns:
            Tuple of (allowed, reason)
        """
        # Check emergency stop
        if self.emergency_stop_active:
            return False, f"Emergency stop active: {self.emergency_stop_reason}"
        
        # Check position count
        if len(self.positions) >= self.max_open_positions:
            return False, f"Max positions ({self.max_open_positions}) reached"
        
        # Check daily loss limit
        daily_pnl = self.current_portfolio_value - self.daily_start_value
        daily_pnl_percent = daily_pnl / self.daily_start_value if self.daily_start_value > 0 else 0
        
        if daily_pnl_percent < -self.daily_loss_limit:
            return False, f"Daily loss limit ({RISK_CONFIG['daily_loss_limit_percent']}%) reached"
        
        # Check position size limit
        max_position_value = self.current_portfolio_value * self.max_position_percent
        if position_size > max_position_value:
            return False, f"Position size ({position_size}) exceeds max ({max_position_value})"
        
        # Check token-specific risk
        risk_metrics = self.assess_token_risk(token)
        if risk_metrics.risk_level == RiskLevel.HIGH and confidence < 0.8:
            return False, f"High risk token with low confidence"
        
        return True, "Position allowed"
    
    def calculate_position_size(
        self,
        token: str,
        confidence: float,
        portfolio_value: Optional[float] = None,
    ) -> float:
        """
        Calculate optimal position size
        
        Args:
            token: Token to trade
            confidence: Strategy confidence (0-1)
            portfolio_value: Override portfolio value
            
        Returns:
            Recommended position size in USD
        """
        if portfolio_value is None:
            portfolio_value = self.current_portfolio_value
        
        # Get risk metrics
        risk = self.assess_token_risk(token)
        
        # Base position size
        base_size = portfolio_value * self.max_position_percent
        
        # Adjust for confidence
        confidence_adjustment = confidence
        
        # Adjust for risk
        if risk.risk_level == RiskLevel.HIGH:
            risk_adjustment = 0.5
        elif risk.risk_level == RiskLevel.MEDIUM:
            risk_adjustment = 0.75
        else:
            risk_adjustment = 1.0
        
        # Adjust for volatility
        volatility_adjustment = 1.0
        if risk.volatility:
            if risk.volatility > 1.0:  # Very volatile
                volatility_adjustment = 0.5
            elif risk.volatility > 0.5:
                volatility_adjustment = 0.75
        
        # Calculate final position size
        position_size = (
            base_size *
            confidence_adjustment *
            risk_adjustment *
            volatility_adjustment
        )
        
        # Ensure minimum size
        min_size = 100  # $100 minimum
        if position_size < min_size:
            position_size = min_size
        
        return position_size
    
    def calculate_stop_loss(
        self,
        token: str,
        entry_price: float,
        position_type: str = "long",
        confidence: float = 1.0,
    ) -> float:
        """
        Calculate stop loss price
        
        Args:
            token: Token being traded
            entry_price: Position entry price
            position_type: 'long' or 'short'
            confidence: Strategy confidence
            
        Returns:
            Stop loss price
        """
        # Get risk metrics
        risk = self.assess_token_risk(token)
        
        # Base stop loss percentage
        base_stop_pct = RISK_CONFIG["stop_loss_percent"] / 100
        
        # Adjust for confidence
        confidence_stop_multiplier = 1.0 + (1 - confidence) * 0.5
        
        # Adjust for volatility
        if risk.volatility and risk.volatility > 0.5:
            base_stop_pct *= risk.volatility * 2
        
        # Cap stop loss
        max_stop_pct = 0.20  # 20% max
        base_stop_pct = min(base_stop_pct, max_stop_pct)
        
        # Calculate stop loss price
        if position_type == "long":
            stop_price = entry_price * (1 - base_stop_pct * confidence_stop_multiplier)
        else:
            stop_price = entry_price * (1 + base_stop_pct * confidence_stop_multiplier)
        
        return stop_price
    
    def calculate_take_profit(
        self,
        token: str,
        entry_price: float,
        position_type: str = "long",
        confidence: float = 1.0,
    ) -> float:
        """
        Calculate take profit price
        
        Args:
            token: Token being traded
            entry_price: Position entry price
            position_type: 'long' or 'short'
            confidence: Strategy confidence
            
        Returns:
            Take profit price
        """
        # Base take profit percentage
        base_tp_pct = RISK_CONFIG["take_profit_percent"] / 100
        
        # Adjust for confidence
        confidence_tp_multiplier = 1.0 + confidence * 0.5
        
        # Calculate take profit price
        if position_type == "long":
            tp_price = entry_price * (1 + base_tp_pct * confidence_tp_multiplier)
        else:
            tp_price = entry_price * (1 - base_tp_pct * confidence_tp_multiplier)
        
        return tp_price
    
    def assess_token_risk(self, token: str) -> RiskMetrics:
        """
        Assess risk for a specific token
        
        Args:
            token: Token to assess
            
        Returns:
            RiskMetrics with assessment
        """
        # Get market data
        volatility = self.market_data.get_volatility(token)
        volume = self.market_data.get_volume(token)
        market_cap = self.market_data.get_market_cap(token)
        
        # Calculate risk score (0-100)
        risk_score = 0
        
        # Volatility risk (0-40 points)
        if volatility:
            if volatility > 2.0:
                risk_score += 40
            elif volatility > 1.0:
                risk_score += 30
            elif volatility > 0.5:
                risk_score += 20
            else:
                risk_score += 10
        
        # Liquidity risk (0-30 points)
        liquidity_risk = False
        if market_cap < 1000000:  # < $1M market cap
            risk_score += 30
            liquidity_risk = True
        elif market_cap < 10000000:  # < $10M
            risk_score += 20
            liquidity_risk = True
        
        # Volume risk (0-20 points)
        if volume < 10000:  # < $10K daily volume
            risk_score += 20
        elif volume < 100000:
            risk_score += 10
        
        # Smart contract risk (0-10 points)
        smart_contract_risk = False
        # Would check audit status, contract age, etc.
        # For now, assume standard ERC20
        
        # Market impact estimate
        market_impact = 0.001  # 0.1% for standard trades
        
        # Determine risk level
        if risk_score >= 60:
            risk_level = RiskLevel.HIGH
        elif risk_score >= 30:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW
        
        return RiskMetrics(
            risk_score=risk_score,
            risk_level=risk_level,
            max_position_size=self.calculate_position_size(token, 0.5),
            recommended_stop_loss=0,
            recommended_take_profit=0,
            volatility=volatility or 0.5,
            liquidity_risk=liquidity_risk,
            smart_contract_risk=smart_contract_risk,
            market_impact=market_impact,
        )
    
    def get_portfolio_metrics(self) -> PortfolioMetrics:
        """Get current portfolio metrics"""
        # Calculate P&L
        total_pnl = self.current_portfolio_value - self.initial_portfolio_value
        total_pnl_percent = (
            (total_pnl / self.initial_portfolio_value * 100)
            if self.initial_portfolio_value > 0 else 0
        )
        
        # Daily P&L
        daily_pnl = self.current_portfolio_value - self.daily_start_value
        daily_pnl_percent = (
            (daily_pnl / self.daily_start_value * 100)
            if self.daily_start_value > 0 else 0
        )
        
        # Open positions
        open_positions_value = sum(
            p.get("value", 0) for p in self.positions.values()
        )
        
        # Risk exposure
        risk_exposure = (
            open_positions_value / self.current_portfolio_value
            if self.current_portfolio_value > 0 else 0
        )
        
        return PortfolioMetrics(
            total_value=self.current_portfolio_value,
            daily_pnl=daily_pnl,
            daily_pnl_percent=daily_pnl_percent,
            total_pnl=total_pnl,
            total_pnl_percent=total_pnl_percent,
            open_positions_value=open_positions_value,
            open_positions_count=len(self.positions),
            risk_exposure=risk_exposure,
            leverage=1.0,  # No leverage by default
        )
    
    def open_position(
        self,
        token: str,
        position_type: str,
        size: float,
        entry_price: float,
        confidence: float = 1.0,
    ) -> Dict:
        """
        Record opening a position
        
        Args:
            token: Token symbol
            position_type: 'long' or 'short'
            size: Position size in USD
            entry_price: Entry price
            confidence: Strategy confidence
            
        Returns:
            Position details dict
        """
        # Calculate stops
        stop_loss = self.calculate_stop_loss(token, entry_price, position_type, confidence)
        take_profit = self.calculate_take_profit(token, entry_price, position_type, confidence)
        
        position = {
            "token": token,
            "type": position_type,
            "size": size,
            "entry_price": entry_price,
            "current_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "confidence": confidence,
            "pnl": 0,
            "pnl_percent": 0,
            "opened_at": datetime.now().isoformat(),
        }
        
        self.positions[token] = position
        
        logger.info(f"Opened {position_type} position: {token} @ {entry_price}")
        
        return position
    
    def close_position(
        self,
        token: str,
        exit_price: float,
        reason: str = "manual",
    ) -> Optional[Dict]:
        """
        Record closing a position
        
        Args:
            token: Token to close
            exit_price: Exit price
            reason: Close reason
            
        Returns:
            Position details or None if not found
        """
        if token not in self.positions:
            return None
        
        position = self.positions[token]
        
        # Calculate P&L
        if position["type"] == "long":
            pnl = (exit_price - position["entry_price"]) * position["size"] / position["entry_price"]
        else:
            pnl = (position["entry_price"] - exit_price) * position["size"] / position["entry_price"]
        
        pnl_percent = (pnl / position["size"]) * 100
        
        position["exit_price"] = exit_price
        position["pnl"] = pnl
        position["pnl_percent"] = pnl_percent
        position["closed_at"] = datetime.now().isoformat()
        position["close_reason"] = reason
        
        # Update daily stats
        if pnl < 0:
            self.daily_losses += 1
        
        self.daily_trades += 1
        
        # Add to history
        self.trade_history.append(position.copy())
        
        # Remove from active positions
        del self.positions[token]
        
        logger.info(f"Closed {position['type']} position: {token} @ {exit_price}, PnL: {pnl:.2f} ({pnl_percent:.2f}%)")
        
        return position
    
    def check_position_exits(self, current_prices: Dict[str, float]) -> List[Dict]:
        """
        Check all positions for exit signals
        
        Args:
            current_prices: Current token prices
            
        Returns:
            List of closed positions
        """
        closed = []
        
        for token, position in list(self.positions.items()):
            current_price = current_prices.get(token)
            if not current_price:
                continue
            
            # Update current price
            position["current_price"] = current_price
            
            # Calculate current P&L
            if position["type"] == "long":
                pnl = (current_price - position["entry_price"]) / position["entry_price"]
            else:
                pnl = (position["entry_price"] - current_price) / position["entry_price"]
            
            position["pnl"] = pnl * position["size"]
            position["pnl_percent"] = pnl * 100
            
            # Check stop loss
            if position["stop_loss"]:
                if position["type"] == "long" and current_price <= position["stop_loss"]:
                    closed.append(self.close_position(token, current_price, "stop_loss"))
                    continue
                elif position["type"] == "short" and current_price >= position["stop_loss"]:
                    closed.append(self.close_position(token, current_price, "stop_loss"))
                    continue
            
            # Check take profit
            if position["take_profit"]:
                if position["type"] == "long" and current_price >= position["take_profit"]:
                    closed.append(self.close_position(token, current_price, "take_profit"))
                    continue
                elif position["type"] == "short" and current_price <= position["take_profit"]:
                    closed.append(self.close_position(token, current_price, "take_profit"))
                    continue
        
        return closed
    
    def reset_daily_stats(self):
        """Reset daily statistics (call at start of day)"""
        self.daily_start_value = self.current_portfolio_value
        self.daily_highest_value = self.current_portfolio_value
        self.daily_trades = 0
        self.daily_losses = 0
        
        logger.info("Daily stats reset")
    
    def activate_emergency_stop(self, reason: str):
        """Activate emergency stop - halts all trading"""
        self.emergency_stop_active = True
        self.emergency_stop_reason = reason
        
        logger.critical(f"EMERGENCY STOP ACTIVATED: {reason}")
    
    def deactivate_emergency_stop(self):
        """Deactivate emergency stop"""
        self.emergency_stop_active = False
        self.emergency_stop_reason = None
        
        logger.info("Emergency stop deactivated")
    
    def get_status(self) -> Dict:
        """Get current risk status"""
        portfolio = self.get_portfolio_metrics()
        
        return {
            "emergency_stop": self.emergency_stop_active,
            "emergency_reason": self.emergency_stop_reason,
            "portfolio_value": portfolio.total_value,
            "daily_pnl": portfolio.daily_pnl,
            "daily_pnl_percent": portfolio.daily_pnl_percent,
            "open_positions": len(self.positions),
            "daily_trades": self.daily_trades,
            "daily_losses": self.daily_losses,
            "positions": self.positions,
        }

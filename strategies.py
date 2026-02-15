"""
Trading Strategies Module
Multiple strategies for automated crypto trading on Uniswap
"""

import os
import json
import logging
import time
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from enum import Enum

from config import STRATEGIES, RISK_CONFIG, TRADING_CONFIG
from market_data import MarketDataProvider

logger = logging.getLogger(__name__)


class PositionType(Enum):
    LONG = "long"
    SHORT = "short"


class OrderStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


@dataclass
class Position:
    """Trading position"""
    token: str
    entry_price: float
    amount: float
    position_type: PositionType
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    entry_time: datetime = field(default_factory=datetime.now)
    status: OrderStatus = OrderStatus.OPEN
    pnl: float = 0.0
    pnl_percent: float = 0.0
    metadata: Dict = field(default_factory=dict)


@dataclass
class TradeSignal:
    """Trading signal from strategy"""
    token: str
    action: str  # 'buy', 'sell', 'hold'
    confidence: float  # 0-1
    strategy: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)


class BaseStrategy(ABC):
    """Base class for trading strategies"""
    
    def __init__(
        self,
        name: str,
        market_data: MarketDataProvider,
        config: Optional[Dict] = None,
    ):
        """
        Initialize strategy
        
        Args:
            name: Strategy name
            market_data: MarketDataProvider instance
            config: Strategy configuration
        """
        self.name = name
        self.market_data = market_data
        self.config = config or {}
        self.active_positions: List[Position] = []
        self.trade_history: List[Dict] = []
    
    @abstractmethod
    def analyze(self, token: str) -> TradeSignal:
        """
        Analyze market and generate signal
        
        Args:
            token: Token to analyze
            
        Returns:
            TradeSignal with action and confidence
        """
        pass
    
    def calculate_position_size(
        self,
        token: str,
        confidence: float,
        current_price: float,
        portfolio_value: float,
    ) -> float:
        """
        Calculate position size based on risk management
        
        Args:
            token: Token to trade
            confidence: Signal confidence (0-1)
            current_price: Current token price
            portfolio_value: Total portfolio value
            
        Returns:
            Position size in tokens
        """
        # Base position size (percentage of portfolio)
        base_size_percent = RISK_CONFIG["max_position_size_percent"]
        
        # Adjust for confidence
        confidence_multiplier = confidence
        
        # Adjust for volatility (if available)
        volatility = self.market_data.get_volatility(token)
        if volatility:
            volatility_adjustment = min(1.0, 0.5 / volatility) if volatility > 0.5 else 1.0
        else:
            volatility_adjustment = 1.0
        
        # Final position size
        position_percent = base_size_percent * confidence_multiplier * volatility_adjustment
        
        # Calculate position value
        position_value = portfolio_value * position_percent
        
        # Convert to token amount
        position_size = position_value / current_price
        
        return position_size
    
    def check_stop_loss(self, position: Position, current_price: float) -> bool:
        """Check if stop loss is triggered"""
        if not position.stop_loss:
            return False
        
        if position.position_type == PositionType.LONG:
            return current_price <= position.stop_loss
        else:
            return current_price >= position.stop_loss
    
    def check_take_profit(self, position: Position, current_price: float) -> bool:
        """Check if take profit is triggered"""
        if not position.take_profit:
            return False
        
        if position.position_type == PositionType.LONG:
            return current_price >= position.take_profit
        else:
            return current_price <= position.take_profit
    
    def update_positions(self, current_prices: Dict[str, float]) -> List[Position]:
        """Update all positions and check exits"""
        closed_positions = []
        
        for position in self.active_positions:
            current_price = current_prices.get(position.token)
            if not current_price:
                continue
            
            # Calculate P&L
            if position.position_type == PositionType.LONG:
                position.pnl = (current_price - position.entry_price) * position.amount
                position.pnl_percent = ((current_price / position.entry_price) - 1) * 100
            else:
                position.pnl = (position.entry_price - current_price) * position.amount
                position.pnl_percent = ((position.entry_price / current_price) - 1) * 100
            
            # Check exits
            if self.check_stop_loss(position, current_price):
                position.status = OrderStatus.CLOSED
                closed_positions.append(position)
                self.trade_history.append({
                    "token": position.token,
                    "action": "stop_loss",
                    "entry_price": position.entry_price,
                    "exit_price": current_price,
                    "pnl": position.pnl,
                    "pnl_percent": position.pnl_percent,
                    "timestamp": datetime.now(),
                })
            elif self.check_take_profit(position, current_price):
                position.status = OrderStatus.CLOSED
                closed_positions.append(position)
                self.trade_history.append({
                    "token": position.token,
                    "action": "take_profit",
                    "entry_price": position.entry_price,
                    "exit_price": current_price,
                    "pnl": position.pnl,
                    "pnl_percent": position.pnl_percent,
                    "timestamp": datetime.now(),
                })
        
        # Remove closed positions
        self.active_positions = [
            p for p in self.active_positions
            if p.status == OrderStatus.OPEN
        ]
        
        return closed_positions
    
    def get_performance(self) -> Dict:
        """Get strategy performance metrics"""
        if not self.trade_history:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
            }
        
        winning_trades = [t for t in self.trade_history if t["pnl"] > 0]
        losing_trades = [t for t in self.trade_history if t["pnl"] <= 0]
        
        total_pnl = sum(t["pnl"] for t in self.trade_history)
        avg_pnl = total_pnl / len(self.trade_history)
        
        return {
            "total_trades": len(self.trade_history),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": len(winning_trades) / len(self.trade_history) * 100,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
        }


class MomentumStrategy(BaseStrategy):
    """
    Momentum Trading Strategy
    
    Buys tokens showing strong upward momentum
    Sells when momentum weakens
    """
    
    def __init__(
        self,
        market_data: MarketDataProvider,
        config: Optional[Dict] = None,
    ):
        """Initialize momentum strategy"""
        super().__init__("momentum", market_data, config)
        self.strategy_config = STRATEGIES.get("momentum", {})
        self.price_history: Dict[str, List[float]] = {}
    
    def analyze(self, token: str) -> TradeSignal:
        """Analyze momentum for token"""
        # Get price data
        prices = self.market_data.get_recent_prices(token, period=24)
        
        if len(prices) < 10:
            return TradeSignal(
                token=token,
                action="hold",
                confidence=0.0,
                strategy=self.name,
                metadata={"reason": "insufficient_data"},
            )
        
        # Calculate RSI
        rsi = self._calculate_rsi(prices)
        
        # Calculate momentum
        momentum = self._calculate_momentum(prices)
        
        # Generate signal
        action = "hold"
        confidence = 0.0
        
        if rsi < self.strategy_config.get("oversold", 30):
            # Oversold - potential buy
            action = "buy"
            confidence = (30 - rsi) / 30
        elif rsi > self.strategy_config.get("overbought", 70):
            # Overbought - potential sell
            action = "sell"
            confidence = (rsi - 70) / 30
        elif momentum > self.strategy_config.get("min_trend_strength", 0.02):
            # Strong uptrend
            action = "buy"
            confidence = min(1.0, momentum * 5)
        elif momentum < -self.strategy_config.get("min_trend_strength", 0.02):
            # Strong downtrend
            action = "sell"
            confidence = min(1.0, abs(momentum) * 5)
        
        return TradeSignal(
            token=token,
            action=action,
            confidence=confidence,
            strategy=self.name,
            metadata={
                "rsi": rsi,
                "momentum": momentum,
                "current_price": prices[-1] if prices else 0,
            },
        )
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate Relative Strength Index"""
        if len(prices) < period + 1:
            return 50.0  # Neutral
        
        deltas = np.diff(prices)
        gains = np.maximum(deltas, 0)
        losses = np.maximum(-deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_momentum(self, prices: List[float], period: int = 10) -> float:
        """Calculate momentum percentage"""
        if len(prices) < period:
            return 0.0
        
        return (prices[-1] - prices[-period]) / prices[-period]


class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion Strategy
    
    Buys when price is below historical average
    Sells when price is above historical average
    """
    
    def __init__(
        self,
        market_data: MarketDataProvider,
        config: Optional[Dict] = None,
    ):
        """Initialize mean reversion strategy"""
        super().__init__("mean_reversion", market_data, config)
        self.strategy_config = STRATEGIES.get("mean_reversion", {})
    
    def analyze(self, token: str) -> TradeSignal:
        """Analyze mean reversion for token"""
        prices = self.market_data.get_recent_prices(token, period=48)
        
        if len(prices) < 24:
            return TradeSignal(
                token=token,
                action="hold",
                confidence=0.0,
                strategy=self.name,
                metadata={"reason": "insufficient_data"},
            )
        
        # Calculate mean and standard deviation
        mean_price = np.mean(prices)
        std_price = np.std(prices)
        
        current_price = prices[-1]
        deviation = (current_price - mean_price) / std_price
        
        # Generate signal
        action = "hold"
        confidence = 0.0
        
        deviation_threshold = self.strategy_config.get("deviation_threshold", 0.05)
        std_threshold = self.strategy_config.get("std_threshold", 2.0)
        
        if deviation < -std_threshold:
            # Price significantly below mean
            action = "buy"
            confidence = min(1.0, abs(deviation) / 3)
        elif deviation > std_threshold:
            # Price significantly above mean
            action = "sell"
            confidence = min(1.0, deviation / 3)
        elif deviation < -0.5 and deviation > -std_threshold:
            # Moderately below mean
            action = "buy"
            confidence = 0.3
        elif deviation > 0.5 and deviation < std_threshold:
            # Moderately above mean
            action = "sell"
            confidence = 0.3
        
        return TradeSignal(
            token=token,
            action=action,
            confidence=confidence,
            strategy=self.name,
            metadata={
                "current_price": current_price,
                "mean_price": mean_price,
                "deviation": deviation,
                "z_score": deviation,
            },
        )


class GridTradingStrategy(BaseStrategy):
    """
    Grid Trading Strategy
    
    Places buy and sell orders at predetermined grid levels
    Profits from price oscillations
    """
    
    def __init__(
        self,
        market_data: MarketDataProvider,
        config: Optional[Dict] = None,
    ):
        """Initialize grid trading strategy"""
        super().__init__("grid_trading", market_data, config)
        self.strategy_config = STRATEGIES.get("grid_trading", {})
        self.grid_levels: Dict[str, List[float]] = {}
    
    def setup_grid(
        self,
        token: str,
        price: float,
        num_levels: int = None,
        spacing_percent: float = None,
    ) -> List[float]:
        """
        Setup price grid levels
        
        Args:
            token: Token symbol
            price: Current price
            num_levels: Number of grid levels
            spacing_percent: Percentage between levels
            
        Returns:
            List of price levels
        """
        num_levels = num_levels or self.strategy_config.get("grid_levels", 5)
        spacing = spacing_percent or self.strategy_config.get("grid_spacing_percent", 1.0)
        
        # Create symmetric grid around current price
        levels = []
        for i in range(-num_levels // 2, num_levels // 2 + 1):
            level = price * (1 + (i * spacing / 100))
            levels.append(level)
        
        self.grid_levels[token] = levels
        return levels
    
    def analyze(self, token: str) -> TradeSignal:
        """Analyze grid positioning"""
        current_price = self.market_data.get_current_price(token)
        
        if token not in self.grid_levels:
            self.setup_grid(token, current_price)
        
        grid = self.grid_levels[token]
        
        # Find nearest grid levels
        buy_levels = [l for l in grid if l < current_price]
        sell_levels = [l for l in grid if l > current_price]
        
        action = "hold"
        confidence = 0.5
        
        if buy_levels:
            nearest_buy = max(buy_levels)
            distance = (current_price - nearest_buy) / current_price
            if distance < 0.02:  # Close to buy level
                action = "buy"
                confidence = 0.7
        
        if sell_levels:
            nearest_sell = min(sell_levels)
            distance = (nearest_sell - current_price) / current_price
            if distance < 0.02:  # Close to sell level
                if action == "buy":
                    action = "hold"  # Cancel if both
                else:
                    action = "sell"
                    confidence = 0.7
        
        return TradeSignal(
            token=token,
            action=action,
            confidence=confidence,
            strategy=self.name,
            metadata={
                "current_price": current_price,
                "grid": grid,
                "buy_levels": buy_levels,
                "sell_levels": sell_levels,
            },
        )


class TrendFollowingStrategy(BaseStrategy):
    """
    Trend Following Strategy
    
    Uses moving average crossovers to identify trends
    Buys when fast MA crosses above slow MA
    Sells when fast MA crosses below slow MA
    """
    
    def __init__(
        self,
        market_data: MarketDataProvider,
        config: Optional[Dict] = None,
    ):
        """Initialize trend following strategy"""
        super().__init__("trend_following", market_data, config)
        self.strategy_config = STRATEGIES.get("trend_following", {})
    
    def analyze(self, token: str) -> TradeSignal:
        """Analyze trend direction"""
        prices = self.market_data.get_recent_prices(token, period=48)
        
        if len(prices) < 30:
            return TradeSignal(
                token=token,
                action="hold",
                confidence=0.0,
                strategy=self.name,
                metadata={"reason": "insufficient_data"},
            )
        
        fast_period = self.strategy_config.get("fast_ma_period", 10)
        slow_period = self.strategy_config.get("slow_ma_period", 30)
        
        fast_ma = np.mean(prices[-fast_period:])
        slow_ma = np.mean(prices[-slow_period:])
        
        current_price = prices[-1]
        
        # Calculate trend strength
        trend_strength = (fast_ma - slow_ma) / slow_ma
        
        # Generate signal
        action = "hold"
        confidence = 0.0
        
        if fast_ma > slow_ma:
            # Uptrend
            if current_price > fast_ma:
                action = "buy"
                confidence = min(1.0, abs(trend_strength) * 10)
            else:
                action = "hold"
                confidence = 0.3
        else:
            # Downtrend
            if current_price < fast_ma:
                action = "sell"
                confidence = min(1.0, abs(trend_strength) * 10)
            else:
                action = "hold"
                confidence = 0.3
        
        return TradeSignal(
            token=token,
            action=action,
            confidence=confidence,
            strategy=self.name,
            metadata={
                "current_price": current_price,
                "fast_ma": fast_ma,
                "slow_ma": slow_ma,
                "trend_strength": trend_strength,
            },
        )


class ArbitrageStrategy(BaseStrategy):
    """
    Arbitrage Strategy
    
    Exploits price differences across different DEXs
    Buys on exchange with lower price, sells on higher price
    """
    
    def __init__(
        self,
        market_data: MarketDataProvider,
        config: Optional[Dict] = None,
    ):
        """Initialize arbitrage strategy"""
        super().__init__("arbitrage", market_data, config)
        self.min_profit_percent = 0.5  # Minimum 0.5% profit to execute
    
    def analyze(self, token: str) -> TradeSignal:
        """Analyze arbitrage opportunities"""
        # Get prices from different sources
        prices = self.market_data.get_token_prices_across_dexs(token)
        
        if len(prices) < 2:
            return TradeSignal(
                token=token,
                action="hold",
                confidence=0.0,
                strategy=self.name,
                metadata={"reason": "insufficient_data"},
            )
        
        min_price = min(prices.values())
        max_price = max(prices.values())
        
        price_spread = (max_price - min_price) / min_price * 100
        
        action = "hold"
        confidence = 0.0
        
        if price_spread > self.min_profit_percent:
            # Arbitrage opportunity
            if price_spread > 1.0:
                confidence = 0.9
            elif price_spread > 0.5:
                confidence = 0.7
            else:
                confidence = 0.5
            
            action = "buy"  # Buy low, sell high
        
        return TradeSignal(
            token=token,
            action=action,
            confidence=confidence,
            strategy=self.name,
            metadata={
                "prices": prices,
                "min_price": min_price,
                "max_price": max_price,
                "spread_percent": price_spread,
            },
        )


class StrategyManager:
    """
    Manages multiple trading strategies
    """
    
    def __init__(
        self,
        market_data: MarketDataProvider,
        paper_mode: bool = True,
    ):
        """Initialize strategy manager"""
        self.market_data = market_data
        self.paper_mode = paper_mode
        self.strategies: Dict[str, BaseStrategy] = {}
        self.active_strategy: Optional[str] = None
        
        # Initialize default strategies
        self._init_strategies()
    
    def _init_strategies(self):
        """Initialize all strategies"""
        self.strategies = {
            "momentum": MomentumStrategy(self.market_data),
            "mean_reversion": MeanReversionStrategy(self.market_data),
            "grid_trading": GridTradingStrategy(self.market_data),
            "trend_following": TrendFollowingStrategy(self.market_data),
            "arbitrage": ArbitrageStrategy(self.market_data),
        }
    
    def set_active_strategy(self, strategy_name: str) -> bool:
        """Set active trading strategy"""
        if strategy_name in self.strategies:
            self.active_strategy = strategy_name
            logger.info(f"Active strategy: {strategy_name}")
            return True
        return False
    
    def analyze(self, token: str) -> List[TradeSignal]:
        """Analyze token with all strategies"""
        signals = []
        
        for name, strategy in self.strategies.items():
            try:
                signal = strategy.analyze(token)
                signals.append(signal)
            except Exception as e:
                logger.error(f"Strategy {name} error: {e}")
        
        return signals
    
    def get_consensus_signal(self, token: str) -> TradeSignal:
        """
        Get consensus signal from all strategies
        
        Returns weighted average signal
        """
        signals = self.analyze(token)
        
        if not signals:
            return TradeSignal(
                token=token,
                action="hold",
                confidence=0.0,
                strategy="consensus",
            )
        
        # Count buy/sell signals
        buy_count = sum(1 for s in signals if s.action == "buy")
        sell_count = sum(1 for s in signals if s.action == "sell")
        hold_count = sum(1 for s in signals if s.action == "hold")
        
        # Calculate weighted confidence
        total_confidence = sum(s.confidence for s in signals)
        avg_confidence = total_confidence / len(signals)
        
        # Determine action
        if buy_count > sell_count:
            action = "buy"
        elif sell_count > buy_count:
            action = "sell"
        else:
            action = "hold"
        
        return TradeSignal(
            token=token,
            action=action,
            confidence=avg_confidence,
            strategy="consensus",
            metadata={
                "signals": [s.to_dict() for s in signals],
                "buy_count": buy_count,
                "sell_count": sell_count,
                "hold_count": hold_count,
            },
        )
    
    def get_strategy_performance(self, strategy_name: str = None) -> Dict:
        """Get performance metrics for strategy(s)"""
        if strategy_name:
            if strategy_name in self.strategies:
                return self.strategies[strategy_name].get_performance()
            return {}
        
        # Aggregate performance
        total_trades = 0
        total_pnl = 0
        win_rate_sum = 0
        
        for strategy in self.strategies.values():
            perf = strategy.get_performance()
            total_trades += perf.get("total_trades", 0)
            total_pnl += perf.get("total_pnl", 0)
            win_rate_sum += perf.get("win_rate", 0)
        
        return {
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "avg_win_rate": win_rate_sum / len(self.strategies) if self.strategies else 0,
        }

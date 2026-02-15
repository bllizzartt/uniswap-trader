#!/usr/bin/env python3
"""
Adaptive Paper Trading Bot with Machine Learning
Learns from failures, improves strategies over time
"""

import os
import json
import sys
import time
import random
from datetime import datetime, timedelta
from collections import deque
import requests

STATE_FILE = "/Users/cortana/.openclaw/workspace/projects/uniswap-trader/auto_trade_state.json"
LEARNING_FILE = "/Users/cortana/.openclaw/workspace/projects/uniswap-trader/learning_data.json"
LOG_FILE = "/Users/cortana/.openclaw/workspace/projects/uniswap-trader/auto_trades.log"

def log(message):
    """Log to file and print"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    with open(LOG_FILE, 'a') as f:
        f.write(log_line + '\n')

def get_matic_price():
    """Fetch live MATIC price"""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=matic-network&vs_currencies=usd",
            timeout=10
        )
        return r.json()['matic-network']['usd']
    except Exception as e:
        return None

def load_state():
    """Load trading state"""
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {
            "balance_usdc": 10000.0,
            "balance_matic": 0.0,
            "trades": [],
            "total_pnl": 0.0,
            "win_count": 0,
            "loss_count": 0,
            "last_price": 0.50,
            "price_history": [],
            "hourly_prices": [],
            "position": None,
            "entry_price": None,
            "last_trade_time": None,
            "trades_today": 0,
            "daily_pnl": 0.0,
            "consecutive_losses": 0,
            "best_trade": None,
            "worst_trade": None
        }

def load_learning_data():
    """Load ML/learning data"""
    try:
        with open(LEARNING_FILE, 'r') as f:
            return json.load(f)
    except:
        return {
            "strategy_performance": {
                "momentum": {"wins": 0, "losses": 0, "total_pnl": 0},
                "dip_buying": {"wins": 0, "losses": 0, "total_pnl": 0},
                "breakout": {"wins": 0, "losses": 0, "total_pnl": 0}
            },
            "failure_analysis": [],
            "success_patterns": [],
            "optimal_params": {
                "momentum_threshold": 2.0,
                "dip_threshold": -3.0,
                "take_profit": 5.0,
                "stop_loss": -3.0,
                "position_size": 0.10
            },
            "market_regimes": {
                "trending_up": {"win_rate": 0, "trades": 0},
                "trending_down": {"win_rate": 0, "trades": 0},
                "choppy": {"win_rate": 0, "trades": 0}
            },
            "lessons_learned": [],
            "adaptation_history": []
        }

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def save_learning_data(data):
    with open(LEARNING_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def detect_market_regime(price_history):
    """Detect if market is trending up, down, or choppy"""
    if len(price_history) < 12:  # Need 1 hour of data (5-min intervals)
        return "unknown"
    
    recent = price_history[-12:]
    first_price = recent[0]
    last_price = recent[-1]
    change_pct = ((last_price / first_price) - 1) * 100
    
    # Calculate volatility
    volatility = sum(abs(recent[i] - recent[i-1]) / recent[i-1] * 100 
                     for i in range(1, len(recent))) / len(recent)
    
    if change_pct > 3 and volatility < 2:
        return "trending_up"
    elif change_pct < -3 and volatility < 2:
        return "trending_down"
    else:
        return "choppy"

def analyze_failures(learning_data, state):
    """Analyze what went wrong in losing trades"""
    recent_trades = state['trades'][-20:]  # Last 20 trades
    losing_trades = [t for t in recent_trades if t.get('pnl', 0) < 0]
    
    if len(losing_trades) < 3:
        return None
    
    # Common patterns in losses
    early_exits = sum(1 for t in losing_trades 
                      if t.get('reason', '').startswith('Stop loss'))
    late_entries = sum(1 for t in losing_trades 
                       if 'dip' in t.get('reason', '').lower())
    
    analysis = {
        "timestamp": datetime.now().isoformat(),
        "total_losses": len(losing_trades),
        "early_exits": early_exits,
        "late_entries": late_entries,
        "avg_loss": sum(t['pnl'] for t in losing_trades) / len(losing_trades),
        "recommendation": None
    }
    
    # Generate recommendations
    if early_exits > len(losing_trades) * 0.5:
        analysis["recommendation"] = "Stop loss too tight, widen to -4%"
    elif late_entries > len(losing_trades) * 0.5:
        analysis["recommendation"] = "Buying dips too early, wait for -5%"
    
    return analysis

def adapt_strategy(learning_data, state):
    """Adjust strategy parameters based on performance"""
    params = learning_data['optimal_params']
    momentum_perf = learning_data['strategy_performance']['momentum']
    dip_perf = learning_data['strategy_performance']['dip_buying']
    
    total_momentum = momentum_perf['wins'] + momentum_perf['losses']
    total_dip = dip_perf['wins'] + dip_perf['losses']
    
    adaptations = []
    
    # Adjust momentum threshold
    if total_momentum >= 5:
        win_rate = momentum_perf['wins'] / total_momentum
        if win_rate < 0.4:
            params['momentum_threshold'] = min(params['momentum_threshold'] + 0.5, 5.0)
            adaptations.append(f"Raised momentum threshold to {params['momentum_threshold']}% (was losing)")
        elif win_rate > 0.6:
            params['momentum_threshold'] = max(params['momentum_threshold'] - 0.3, 1.0)
            adaptations.append(f"Lowered momentum threshold to {params['momentum_threshold']}% (was winning)")
    
    # Adjust stop loss based on failures
    if state['consecutive_losses'] >= 3:
        old_sl = params['stop_loss']
        params['stop_loss'] = -4.0  # Widen stop loss
        adaptations.append(f"Widened stop loss from {old_sl}% to -4% (3 consecutive losses)")
        state['consecutive_losses'] = 0  # Reset counter
    
    # Adjust take profit in trending markets
    regime = detect_market_regime(state.get('hourly_prices', []))
    if regime == "trending_up":
        params['take_profit'] = 7.0  # Let winners run
        adaptations.append("Increased take profit to 7% (trending market)")
    elif regime == "choppy":
        params['take_profit'] = 3.0  # Take quick profits
        adaptations.append("Lowered take profit to 3% (choppy market)")
    
    if adaptations:
        learning_data['adaptation_history'].append({
            "timestamp": datetime.now().isoformat(),
            "changes": adaptations,
            "new_params": params.copy()
        })
    
    return adaptations

def adaptive_strategy(state, current_price, learning_data):
    """Strategy that adapts based on learning data"""
    params = learning_data['optimal_params']
    
    if len(state['hourly_prices']) < 2:
        return None, "Collecting initial data..."
    
    # Calculate metrics
    price_change_5m = ((current_price / state['hourly_prices'][-2]) - 1) * 100
    price_change_1h = ((current_price / state['hourly_prices'][0]) - 1) * 100 if len(state['hourly_prices']) >= 12 else 0
    
    regime = detect_market_regime(state.get('hourly_prices', []))
    position = state['position']
    
    # NO POSITION - Look for entry
    if position is None:
        # Momentum signal (adaptive threshold)
        if price_change_5m >= params['momentum_threshold']:
            return "BUY", f"Momentum +{price_change_5m:.1f}% (regime: {regime})"
        
        # Dip buying (adaptive threshold)
        if price_change_5m <= params['dip_threshold']:
            return "BUY", f"Dip -{abs(price_change_5m):.1f}% (regime: {regime})"
        
        # Breakout in trending market
        if regime == "trending_up" and price_change_1h > 5:
            return "BUY", f"Breakout in uptrend +{price_change_1h:.1f}%"
    
    # HAVE POSITION - Look for exit
    elif position == "LONG":
        entry = state.get('entry_price', current_price)
        pnl_pct = ((current_price / entry) - 1) * 100
        
        # Take profit (adaptive)
        if pnl_pct >= params['take_profit']:
            return "SELL", f"Take profit +{pnl_pct:.1f}%"
        
        # Stop loss (adaptive)
        if pnl_pct <= params['stop_loss']:
            return "SELL", f"Stop loss {pnl_pct:.1f}%"
        
        # Trailing stop in trending market
        if regime == "trending_up" and pnl_pct > 3:
            return "SELL", f"Trailing stop +{pnl_pct:.1f}% (lock gains)"
    
    return None, f"HOLD | 5m: {price_change_5m:+.1f}% | Regime: {regime}"

def execute_trade(state, signal, current_price, reason, learning_data):
    """Execute paper trade and update learning"""
    params = learning_data['optimal_params']
    
    if signal == "BUY" and state['balance_usdc'] >= 100:
        trade_amount = min(state['balance_usdc'] * params['position_size'], 1000)
        matic_received = trade_amount / current_price
        
        state['balance_usdc'] -= trade_amount
        state['balance_matic'] += matic_received
        state['position'] = "LONG"
        state['entry_price'] = current_price
        
        trade = {
            'type': 'BUY',
            'timestamp': datetime.now().isoformat(),
            'usdc_spent': trade_amount,
            'matic_received': matic_received,
            'price': current_price,
            'reason': reason,
            'strategy': 'momentum' if 'momentum' in reason.lower() else 'dip_buying'
        }
        state['trades'].append(trade)
        state['trades_today'] += 1
        
        log(f"🟢 BUY: ${trade_amount:.0f} → {matic_received:.1f} MATIC @ ${current_price:.4f} | {reason}")
        return True
    
    elif signal == "SELL" and state['balance_matic'] > 0:
        matic_sold = state['balance_matic']
        usdc_received = matic_sold * current_price
        
        entry = state.get('entry_price', current_price)
        pnl = (current_price - entry) * matic_sold
        pnl_pct = ((current_price / entry) - 1) * 100
        
        state['balance_usdc'] += usdc_received
        state['balance_matic'] = 0
        state['position'] = None
        state['total_pnl'] += pnl
        state['daily_pnl'] += pnl
        
        # Track consecutive losses
        if pnl > 0:
            state['win_count'] += 1
            state['consecutive_losses'] = 0
            strategy = state['trades'][-1].get('strategy', 'momentum')
            learning_data['strategy_performance'][strategy]['wins'] += 1
            learning_data['strategy_performance'][strategy]['total_pnl'] += pnl
        else:
            state['loss_count'] += 1
            state['consecutive_losses'] += 1
            strategy = state['trades'][-1].get('strategy', 'momentum')
            learning_data['strategy_performance'][strategy]['losses'] += 1
            learning_data['strategy_performance'][strategy]['total_pnl'] += pnl
        
        # Update best/worst trades
        if state['best_trade'] is None or pnl > state['best_trade']['pnl']:
            state['best_trade'] = {'pnl': pnl, 'timestamp': datetime.now().isoformat()}
        if state['worst_trade'] is None or pnl < state['worst_trade']['pnl']:
            state['worst_trade'] = {'pnl': pnl, 'timestamp': datetime.now().isoformat()}
        
        trade = {
            'type': 'SELL',
            'timestamp': datetime.now().isoformat(),
            'matic_sold': matic_sold,
            'usdc_received': usdc_received,
            'price': current_price,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'reason': reason
        }
        state['trades'].append(trade)
        
        emoji = "✅" if pnl > 0 else "❌"
        log(f"🔴 SELL: {matic_sold:.1f} MATIC → ${usdc_received:.0f} | P&L: ${pnl:+.2f} {emoji}")
        return True
    
    return False

def generate_report(state, learning_data, report_type="midday"):
    """Generate comprehensive trading report"""
    
    current_price = state.get('last_price', 0.50)
    matic_value = state['balance_matic'] * current_price
    total_value = state['balance_usdc'] + matic_value
    total_trades = state['win_count'] + state['loss_count']
    win_rate = (state['win_count'] / total_trades * 100) if total_trades > 0 else 0
    
    regime = detect_market_regime(state.get('hourly_prices', []))
    
    # Learning insights
    adaptations = learning_data.get('adaptation_history', [])[-3:]
    failure_analysis = analyze_failures(learning_data, state)
    
    report = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 PAPER TRADING REPORT - {report_type.upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%A %H:%M')}
🪙 MATIC @ ${current_price:.4f}
📈 Market Regime: {regime.upper()}

💰 PORTFOLIO
   USDC: ${state['balance_usdc']:,.2f}
   MATIC: {state['balance_matic']:.2f} (${matic_value:,.2f})
   Total: ${total_value:,.2f}

📊 PERFORMANCE
   Total P&L: ${state['total_pnl']:+.2f}
   Today's P&L: ${state['daily_pnl']:+.2f}
   Win Rate: {win_rate:.1f}% ({state['win_count']}W/{state['loss_count']}L)
   Trades Today: {state['trades_today']}
   Position: {state['position'] or 'NONE'}

🧠 LEARNING & ADAPTATION
"""
    
    # Add strategy performance
    for strategy, perf in learning_data['strategy_performance'].items():
        if perf['wins'] + perf['losses'] > 0:
            sr = perf['wins'] / (perf['wins'] + perf['losses']) * 100
            report += f"   {strategy}: {sr:.0f}% win rate (${perf['total_pnl']:+.2f})\n"
    
    # Add recent adaptations
    if adaptations:
        report += "\n🔧 Recent Adaptations:\n"
        for adapt in adaptations:
            for change in adapt.get('changes', []):
                report += f"   • {change}\n"
    
    # Add failure analysis
    if failure_analysis and failure_analysis.get('recommendation'):
        report += f"\n⚠️  Learning from failures:\n"
        report += f"   {failure_analysis['recommendation']}\n"
    
    # Best/worst trade
    if state['best_trade']:
        report += f"\n🏆 Best: ${state['best_trade']['pnl']:+.2f}"
    if state['worst_trade']:
        report += f" | 😬 Worst: ${state['worst_trade']['pnl']:+.2f}"
    
    report += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    return report

def main():
    """Main trading and reporting loop"""
    
    # Check if this is a report-only run
    report_type = None
    if '--report' in sys.argv:
        idx = sys.argv.index('--report')
        if idx + 1 < len(sys.argv):
            report_type = sys.argv[idx + 1]
    
    # Load data
    state = load_state()
    learning_data = load_learning_data()
    
    # Get current price
    current_price = get_matic_price()
    if current_price is None:
        log("⚠️ Could not fetch price")
        return
    
    state['last_price'] = current_price
    
    # Update price history (keep last 24 hours = 288 5-min intervals)
    state['hourly_prices'].append(current_price)
    if len(state['hourly_prices']) > 288:
        state['hourly_prices'] = state['hourly_prices'][-288:]
    
    # If report mode, just generate and exit
    if report_type:
        report = generate_report(state, learning_data, report_type)
        log(report)
        print(report)
        save_state(state)
        save_learning_data(learning_data)
        return
    
    # Otherwise, run trading logic
    log(f"🤖 Trading cycle started | MATIC: ${current_price:.4f}")
    
    # Analyze and adapt
    adaptations = adapt_strategy(learning_data, state)
    if adaptations:
        for adapt in adaptations:
            log(f"🔧 ADAPTATION: {adapt}")
    
    # Run strategy
    signal, reason = adaptive_strategy(state, current_price, learning_data)
    
    if signal:
        executed = execute_trade(state, signal, current_price, reason, learning_data)
        if executed:
            state['last_trade_time'] = datetime.now().isoformat()
    else:
        log(f"⏸️ {reason}")
    
    # Save everything
    save_state(state)
    save_learning_data(learning_data)
    
    # Quick summary
    log(f"💰 Total P&L: ${state['total_pnl']:+.2f} | Position: {state['position'] or 'NONE'}")

if __name__ == "__main__":
    main()

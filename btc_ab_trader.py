#!/usr/bin/env python3
"""
BTC Paper Trading Bot with A/B Testing
Compares Strategy A vs Strategy B in real-time
"""

import os
import json
import sys
import random
from datetime import datetime
from pathlib import Path

STATE_FILE = "/Users/cortana/.openclaw/workspace/projects/uniswap-trader/btc_ab_test_state.json"
LOG_FILE = "/Users/cortana/.openclaw/workspace/projects/uniswap-trader/btc_ab_trades.log"

def log(message):
    """Log to file and print"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(log_line + '\n')
    except:
        pass

def get_btc_price():
    """Fetch live BTC price"""
    import requests
    
    # Try CoinGecko
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
            timeout=5
        )
        data = r.json()
        if 'bitcoin' in data and 'usd' in data['bitcoin']:
            return float(data['bitcoin']['usd'])
    except:
        pass
    
    # Fallback to last known price with random movement
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            if state.get('btc_price'):
                last = state['btc_price']
                movement = random.uniform(-0.005, 0.005)  # ±0.5% for BTC
                return last * (1 + movement)
    except:
        pass
    
    return 68700.0  # Default BTC price

def reset_accounts():
    """Reset both A and B accounts to $10,000"""
    state = {
        "btc_price": 68700.0,
        "price_history": [68700.0] * 12,
        
        # Account A: Momentum Strategy
        "account_a": {
            "name": "Strategy A - Momentum",
            "balance_usdc": 10000.0,
            "balance_btc": 0.0,
            "position": None,
            "entry_price": None,
            "trades": [],
            "total_pnl": 0.0,
            "win_count": 0,
            "loss_count": 0,
            "trades_today": 0,
            "daily_pnl": 0.0
        },
        
        # Account B: Mean Reversion Strategy
        "account_b": {
            "name": "Strategy B - Mean Reversion",
            "balance_usdc": 10000.0,
            "balance_btc": 0.0,
            "position": None,
            "entry_price": None,
            "trades": [],
            "total_pnl": 0.0,
            "win_count": 0,
            "loss_count": 0,
            "trades_today": 0,
            "daily_pnl": 0.0
        },
        
        "test_start": datetime.now().isoformat(),
        "total_cycles": 0
    }
    
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)
    
    log("🔄 ACCOUNTS RESET: $10,000 each")
    log("   Account A: Momentum Strategy")
    log("   Account B: Mean Reversion Strategy")
    return state

def load_state():
    """Load or create state"""
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return reset_accounts()

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def strategy_a_momentum(account, current_price, price_history):
    """
    Strategy A: Momentum Following
    - Buy when price up 1.5%+
    - Sell when momentum fades or profit +8%
    - Stop loss -4%
    """
    if len(price_history) < 2:
        return None, "Collecting data..."
    
    prev_price = price_history[-2]
    change_pct = ((current_price / prev_price) - 1) * 100
    
    # No position - look for momentum
    if account['position'] is None:
        if change_pct >= 1.5:
            return "BUY", f"Momentum +{change_pct:.1f}%"
    
    # Have position - manage exit
    elif account['position'] == "LONG":
        entry = account.get('entry_price', current_price)
        pnl_pct = ((current_price / entry) - 1) * 100
        
        # Take profit on strong gains
        if pnl_pct >= 8.0:
            return "SELL", f"Momentum profit +{pnl_pct:.1f}%"
        
        # Stop loss
        if pnl_pct <= -4.0:
            return "SELL", f"Stop loss {pnl_pct:.1f}%"
        
        # Exit if momentum reverses
        if change_pct <= -1.0:
            return "SELL", f"Momentum fading {pnl_pct:+.1f}%"
    
    return None, f"HOLD (chg: {change_pct:+.1f}%)"

def strategy_b_mean_reversion(account, current_price, price_history):
    """
    Strategy B: Mean Reversion
    - Buy when price drops 2%+ (oversold)
    - Sell when price returns to mean +5%
    - Stop loss -5% (if keeps dropping)
    """
    if len(price_history) < 6:
        return None, "Collecting data..."
    
    # Calculate 6-period mean
    recent_prices = price_history[-6:]
    mean_price = sum(recent_prices) / len(recent_prices)
    deviation = ((current_price / mean_price) - 1) * 100
    
    # No position - look for oversold
    if account['position'] is None:
        if deviation <= -2.0:
            return "BUY", f"Oversold {deviation:.1f}% from mean"
    
    # Have position - look for mean reversion
    elif account['position'] == "LONG":
        entry = account.get('entry_price', current_price)
        pnl_pct = ((current_price / entry) - 1) * 100
        
        # Sell when back to mean or profitable
        if deviation >= 0 and pnl_pct > 0:
            return "SELL", f"Back to mean +{pnl_pct:.1f}%"
        
        # Take profit
        if pnl_pct >= 5.0:
            return "SELL", f"Profit target +{pnl_pct:.1f}%"
        
        # Stop if keeps dropping
        if pnl_pct <= -5.0:
            return "SELL", f"Stop loss {pnl_pct:.1f}%"
    
    return None, f"HOLD (dev: {deviation:+.1f}%)"

def execute_trade(account, signal, current_price, reason):
    """Execute paper trade for an account"""
    position_size = 0.15  # 15% of balance per trade
    
    if signal == "BUY" and account['balance_usdc'] >= 100:
        trade_amount = min(account['balance_usdc'] * position_size, 1500)
        btc = trade_amount / current_price
        
        account['balance_usdc'] -= trade_amount
        account['balance_btc'] += btc
        account['position'] = "LONG"
        account['entry_price'] = current_price
        
        trade = {
            'type': 'BUY',
            'timestamp': datetime.now().isoformat(),
            'usdc': trade_amount,
            'btc': btc,
            'price': current_price,
            'reason': reason
        }
        account['trades'].append(trade)
        account['trades_today'] += 1
        
        return f"🟢 BUY: ${trade_amount:.0f} → {btc:.5f} BTC @ ${current_price:,.0f} | {reason}"
    
    elif signal == "SELL" and account['balance_btc'] > 0:
        btc = account['balance_btc']
        usdc = btc * current_price
        
        entry = account.get('entry_price', current_price)
        pnl = (current_price - entry) * btc
        pnl_pct = ((current_price / entry) - 1) * 100
        
        account['balance_usdc'] += usdc
        account['balance_btc'] = 0
        account['position'] = None
        account['total_pnl'] += pnl
        account['daily_pnl'] += pnl
        
        if pnl > 0:
            account['win_count'] += 1
        else:
            account['loss_count'] += 1
        
        emoji = "✅" if pnl > 0 else "❌"
        return f"🔴 SELL: {btc:.5f} BTC → ${usdc:.0f} | P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%) {emoji}"
    
    return None

def run_ab_test_cycle(state, current_price):
    """Run one cycle of A/B testing"""
    price_history = state['price_history']
    
    # Run Strategy A
    signal_a, reason_a = strategy_a_momentum(state['account_a'], current_price, price_history)
    if signal_a:
        result_a = execute_trade(state['account_a'], signal_a, current_price, reason_a)
        if result_a:
            log(f"📈 A: {result_a}")
    else:
        log(f"📈 A: {reason_a}")
    
    # Run Strategy B
    signal_b, reason_b = strategy_b_mean_reversion(state['account_b'], current_price, price_history)
    if signal_b:
        result_b = execute_trade(state['account_b'], signal_b, current_price, reason_b)
        if result_b:
            log(f"📉 B: {result_b}")
    else:
        log(f"📉 B: {reason_b}")
    
    state['total_cycles'] += 1

def generate_ab_report(state, report_type="morning"):
    """Generate A/B testing comparison report"""
    
    btc_price = state.get('btc_price', 68700)
    a = state['account_a']
    b = state['account_b']
    
    # Calculate values
    a_btc_value = a['balance_btc'] * btc_price
    a_total = a['balance_usdc'] + a_btc_value
    a_trades = a['win_count'] + a['loss_count']
    a_win_rate = (a['win_count'] / a_trades * 100) if a_trades > 0 else 0
    
    b_btc_value = b['balance_btc'] * btc_price
    b_total = b['balance_usdc'] + b_btc_value
    b_trades = b['win_count'] + b['loss_count']
    b_win_rate = (b['win_count'] / b_trades * 100) if b_trades > 0 else 0
    
    # Analyze performance for learning
    a_return = ((a_total / 10000) - 1) * 100
    b_return = ((b_total / 10000) - 1) * 100
    
    # Determine which approach is teaching us more
    if a_total > b_total:
        winner = "📚 LEARNING: Momentum performing better"
        diff = a_total - b_total
        lesson = "Trend-following working in current market regime"
    elif b_total > a_total:
        winner = "📚 LEARNING: Mean Reversion performing better"
        diff = b_total - a_total
        lesson = "Contrarian approach winning - market is ranging"
    else:
        winner = "📚 Both strategies learning"
        diff = 0
        lesson = "Market regime unclear - continuing data collection"
    
    report = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 BTC A/B TEST REPORT - {report_type.upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ {datetime.now().strftime('%A %H:%M')}
🪙 BTC @ ${btc_price:,.0f}
📊 Test Cycles: {state['total_cycles']}

🏆 WINNER: {winner}
   Lead: ${diff:,.2f}

📈 STRATEGY A - MOMENTUM
   Balance: ${a_total:,.2f} ({a_return:+.2f}%)
   P&L: ${a['total_pnl']:+.2f}
   Win Rate: {a_win_rate:.1f}% ({a['win_count']}W/{a['loss_count']}L)
   Trades: {a_trades}
   Position: {a['position'] or 'NONE'}
   
📉 STRATEGY B - MEAN REVERSION
   Balance: ${b_total:,.2f} ({b_return:+.2f}%)
   P&L: ${b['total_pnl']:+.2f}
   Win Rate: {b_win_rate:.1f}% ({b['win_count']}W/{b['loss_count']}L)
   Trades: {b_trades}
   Position: {b['position'] or 'NONE'}

📊 COMPARISON
   Return Diff: {a_return - b_return:+.2f}%
   Trade Diff: {a_trades - b_trades:+d}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    return report

def main():
    """Main loop"""
    
    # Check for reset flag
    if '--reset' in sys.argv:
        state = reset_accounts()
        log("✅ Accounts reset to $10,000 each")
        return
    
    # Check for report flag
    report_type = None
    if '--report' in sys.argv:
        idx = sys.argv.index('--report')
        if idx + 1 < len(sys.argv):
            report_type = sys.argv[idx + 1]
    
    # Load state
    state = load_state()
    
    # Get BTC price
    current_price = get_btc_price()
    if current_price is None:
        current_price = state.get('btc_price', 68700)
    
    state['btc_price'] = current_price
    
    # Update price history
    state['price_history'].append(current_price)
    if len(state['price_history']) > 288:
        state['price_history'] = state['price_history'][-288:]
    
    # Generate report only
    if report_type:
        report = generate_ab_report(state, report_type)
        log(report)
        print(report)
        save_state(state)
        return
    
    # Run A/B test cycle
    log(f"🤖 BTC A/B Test | Price: ${current_price:,.0f}")
    run_ab_test_cycle(state, current_price)
    
    # Save state
    save_state(state)
    
    # Quick summary
    a_total = state['account_a']['balance_usdc'] + state['account_a']['balance_btc'] * current_price
    b_total = state['account_b']['balance_usdc'] + state['account_b']['balance_btc'] * current_price
    log(f"📊 A: ${a_total:,.0f} | B: ${b_total:,.0f}")

if __name__ == "__main__":
    main()

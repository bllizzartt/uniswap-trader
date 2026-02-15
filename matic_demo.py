#!/usr/bin/env python3
"""
MATIC Paper Trading Demo
Quick test of the Uniswap bot with MATIC on Polygon
"""

import os
import sys
import time
from datetime import datetime

# Mock paper trading environment
VIRTUAL_USDC = 10000.0
VIRTUAL_MATIC = 0.0
MATIC_PRICE = 0.50  # Starting price
POSITIONS = []
TRADES = []

def show_portfolio():
    """Show current portfolio"""
    matic_value = VIRTUAL_MATIC * MATIC_PRICE
    total = VIRTUAL_USDC + matic_value
    
    print("\n" + "="*50)
    print("💼 PAPER TRADING PORTFOLIO")
    print("="*50)
    print(f"Network: Polygon")
    print(f"Token: MATIC")
    print(f"Current Price: ${MATIC_PRICE:.4f}")
    print()
    print(f"USDC Balance: ${VIRTUAL_USDC:,.2f}")
    print(f"MATIC Balance: {VIRTUAL_MATIC:,.2f} (${matic_value:,.2f})")
    print(f"Total Value: ${total:,.2f}")
    print(f"Profit/Loss: ${total - 10000:,.2f}")
    print()
    print(f"Open Positions: {len(POSITIONS)}")
    print(f"Total Trades: {len(TRADES)}")
    print("="*50)

def simulate_buy(amount_usdc):
    """Simulate buying MATIC"""
    global VIRTUAL_USDC, VIRTUAL_MATIC
    
    if amount_usdc > VIRTUAL_USDC:
        print(f"❌ Insufficient funds. Have: ${VIRTUAL_USDC:.2f}, Need: ${amount_usdc:.2f}")
        return
    
    matic_received = amount_usdc / MATIC_PRICE
    VIRTUAL_USDC -= amount_usdc
    VIRTUAL_MATIC += matic_received
    
    trade = {
        'type': 'BUY',
        'amount_usdc': amount_usdc,
        'matic_received': matic_received,
        'price': MATIC_PRICE,
        'time': datetime.now()
    }
    TRADES.append(trade)
    POSITIONS.append(trade)
    
    print(f"✅ BUY: ${amount_usdc:.2f} USDC → {matic_received:.2f} MATIC @ ${MATIC_PRICE:.4f}")

def simulate_sell(percent=100):
    """Simulate selling MATIC"""
    global VIRTUAL_USDC, VIRTUAL_MATIC
    
    if VIRTUAL_MATIC <= 0:
        print("❌ No MATIC to sell")
        return
    
    amount_to_sell = VIRTUAL_MATIC * (percent / 100)
    usdc_received = amount_to_sell * MATIC_PRICE
    
    VIRTUAL_MATIC -= amount_to_sell
    VIRTUAL_USDC += usdc_received
    
    trade = {
        'type': 'SELL',
        'matic_sold': amount_to_sell,
        'usdc_received': usdc_received,
        'price': MATIC_PRICE,
        'time': datetime.now()
    }
    TRADES.append(trade)
    
    if VIRTUAL_MATIC <= 0.01:
        POSITIONS.clear()
    
    print(f"✅ SELL: {amount_to_sell:.2f} MATIC → ${usdc_received:.2f} USDC @ ${MATIC_PRICE:.4f}")

def simulate_price_change(percent):
    """Simulate price movement"""
    global MATIC_PRICE
    old_price = MATIC_PRICE
    MATIC_PRICE *= (1 + percent/100)
    
    direction = "📈 UP" if percent > 0 else "📉 DOWN"
    print(f"\n{direction}: ${old_price:.4f} → ${MATIC_PRICE:.4f} ({percent:+.2f}%)")

def show_menu():
    """Interactive menu"""
    print("\n" + "="*50)
    print("🎮 MATIC PAPER TRADING DEMO")
    print("="*50)
    print("Commands:")
    print("  1. Buy MATIC ($100)")
    print("  2. Buy MATIC ($500)")
    print("  3. Sell 100%")
    print("  4. Sell 50%")
    print("  5. Simulate +5% price jump")
    print("  6. Simulate -5% price drop")
    print("  7. Show portfolio")
    print("  8. Show trade history")
    print("  9. Auto-trade demo")
    print("  0. Exit")
    print("="*50)

def auto_trade_demo():
    """Run automated demo trades"""
    print("\n🤖 AUTO-TRADING DEMO")
    print("Running 3 simulated trades...")
    
    # Trade 1: Buy
    time.sleep(1)
    simulate_buy(1000)
    
    # Price goes up
    time.sleep(1)
    simulate_price_change(+8)
    
    # Trade 2: Sell half at profit
    time.sleep(1)
    simulate_sell(50)
    
    # Price drops
    time.sleep(1)
    simulate_price_change(-5)
    
    # Trade 3: Buy the dip
    time.sleep(1)
    simulate_buy(500)
    
    show_portfolio()

def main():
    """Main demo loop"""
    print("\n🚀 Starting MATIC Paper Trading Demo")
    print("Virtual Balance: $10,000 USDC")
    print("Network: Polygon")
    print("Token: MATIC")
    
    show_portfolio()
    
    while True:
        show_menu()
        choice = input("\nEnter command (0-9): ").strip()
        
        if choice == '1':
            simulate_buy(100)
        elif choice == '2':
            simulate_buy(500)
        elif choice == '3':
            simulate_sell(100)
        elif choice == '4':
            simulate_sell(50)
        elif choice == '5':
            simulate_price_change(+5)
        elif choice == '6':
            simulate_price_change(-5)
        elif choice == '7':
            show_portfolio()
        elif choice == '8':
            print("\n📊 TRADE HISTORY:")
            for i, trade in enumerate(TRADES, 1):
                print(f"{i}. {trade['type']}: {trade}")
        elif choice == '9':
            auto_trade_demo()
        elif choice == '0':
            print("\n👋 Demo ended. Final portfolio:")
            show_portfolio()
            break
        else:
            print("❌ Invalid choice")

if __name__ == "__main__":
    main()

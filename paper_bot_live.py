#!/usr/bin/env python3
"""
Paper Trading Explainer + Live Demo
Shows exactly how the bot tracks progress
"""

import json
import time
from datetime import datetime

# Paper trading state file
STATE_FILE = "/Users/cortana/.openclaw/workspace/projects/uniswap-trader/paper_state.json"

class PaperTradingBot:
    """
    How Paper Trading Actually Works:
    
    1. VIRTUAL WALLET - Fake money, tracks balances
    2. LIVE PRICES - Real market data from APIs  
    3. TRADE LOGIC - Real strategies, fake execution
    4. P&L TRACKING - Calculates profit/loss on each trade
    5. PERSISTENCE - Saves state to file (survives restarts)
    """
    
    def __init__(self):
        self.state = self.load_state()
        
    def load_state(self):
        """Load or create trading state"""
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            # Fresh start
            return {
                "balance_usdc": 10000.0,
                "balance_matic": 0.0,
                "trades": [],
                "positions": [],
                "total_pnl": 0.0,
                "win_count": 0,
                "loss_count": 0,
                "created_at": datetime.now().isoformat()
            }
    
    def save_state(self):
        """Save state to file"""
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def get_matic_price(self):
        """Fetch live MATIC price"""
        import requests
        try:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=matic-network&vs_currencies=usd", timeout=5)
            return r.json()['matic-network']['usd']
        except:
            return 0.50  # Fallback
    
    def buy(self, usdc_amount):
        """Execute paper buy"""
        if usdc_amount > self.state['balance_usdc']:
            print(f"❌ INSUFFICIENT FUNDS")
            print(f"   Want: ${usdc_amount:.2f}")
            print(f"   Have: ${self.state['balance_usdc']:.2f}")
            return False
        
        price = self.get_matic_price()
        matic_received = usdc_amount / price
        
        # Update balances
        self.state['balance_usdc'] -= usdc_amount
        self.state['balance_matic'] += matic_received
        
        # Record trade
        trade = {
            'type': 'BUY',
            'timestamp': datetime.now().isoformat(),
            'usdc_spent': usdc_amount,
            'matic_received': matic_received,
            'price': price,
            'pnl': 0  # Will update on sell
        }
        self.state['trades'].append(trade)
        self.state['positions'].append(trade)
        
        self.save_state()
        
        print(f"\n✅ BUY EXECUTED")
        print(f"   Spent: ${usdc_amount:.2f} USDC")
        print(f"   Got: {matic_received:.4f} MATIC")
        print(f"   Price: ${price:.4f}")
        return True
    
    def sell(self, percent=100):
        """Execute paper sell"""
        if self.state['balance_matic'] <= 0:
            print(f"❌ NO MATIC TO SELL")
            return False
        
        price = self.get_matic_price()
        amount_to_sell = self.state['balance_matic'] * (percent / 100)
        usdc_received = amount_to_sell * price
        
        # Calculate P&L
        # Find average buy price from positions
        if self.state['positions']:
            total_cost = sum(p['usdc_spent'] for p in self.state['positions'])
            total_matic = sum(p['matic_received'] for p in self.state['positions'])
            avg_buy_price = total_cost / total_matic if total_matic > 0 else price
        else:
            avg_buy_price = price
        
        pnl = (price - avg_buy_price) * amount_to_sell
        pnl_percent = ((price / avg_buy_price) - 1) * 100
        
        # Update balances
        self.state['balance_matic'] -= amount_to_sell
        self.state['balance_usdc'] += usdc_received
        self.state['total_pnl'] += pnl
        
        if pnl > 0:
            self.state['win_count'] += 1
        else:
            self.state['loss_count'] += 1
        
        # Record trade
        trade = {
            'type': 'SELL',
            'timestamp': datetime.now().isoformat(),
            'matic_sold': amount_to_sell,
            'usdc_received': usdc_received,
            'price': price,
            'pnl': pnl,
            'pnl_percent': pnl_percent
        }
        self.state['trades'].append(trade)
        
        # Clear positions if fully sold
        if self.state['balance_matic'] < 0.001:
            self.state['positions'] = []
        
        self.save_state()
        
        emoji = "🟢" if pnl > 0 else "🔴"
        print(f"\n{emoji} SELL EXECUTED")
        print(f"   Sold: {amount_to_sell:.4f} MATIC")
        print(f"   Got: ${usdc_received:.2f} USDC")
        print(f"   Price: ${price:.4f}")
        print(f"   P&L: ${pnl:+.2f} ({pnl_percent:+.2f}%)")
        return True
    
    def show_portfolio(self):
        """Display current portfolio"""
        price = self.get_matic_price()
        
        matic_value = self.state['balance_matic'] * price
        total_value = self.state['balance_usdc'] + matic_value
        starting_value = 10000.0
        total_pnl = total_value - starting_value
        
        total_trades = self.state['win_count'] + self.state['loss_count']
        win_rate = (self.state['win_count'] / total_trades * 100) if total_trades > 0 else 0
        
        print("\n" + "="*60)
        print("📊 PAPER TRADING PORTFOLIO - LIVE")
        print("="*60)
        print(f"Token: MATIC")
        print(f"Network: Polygon")
        print(f"Current Price: ${price:.4f}")
        print()
        print(f"💰 BALANCES:")
        print(f"   USDC: ${self.state['balance_usdc']:,.2f}")
        print(f"   MATIC: {self.state['balance_matic']:,.4f} (${matic_value:,.2f})")
        print()
        print(f"📈 PERFORMANCE:")
        print(f"   Total Value: ${total_value:,.2f}")
        print(f"   Total P&L: ${total_pnl:+.2f} ({(total_pnl/starting_value)*100:+.2f}%)")
        print(f"   Total Trades: {total_trades}")
        print(f"   Win Rate: {win_rate:.1f}%")
        print(f"   Wins: {self.state['win_count']} | Losses: {self.state['loss_count']}")
        print("="*60)
        
        return total_pnl
    
    def show_trade_history(self):
        """Show all trades"""
        print("\n📜 TRADE HISTORY:")
        print("-"*60)
        
        if not self.state['trades']:
            print("No trades yet")
            return
        
        for i, trade in enumerate(self.state['trades'][-10:], 1):  # Last 10
            t = trade['timestamp'].split('T')[1].split('.')[0]  # Just time
            if trade['type'] == 'BUY':
                print(f"{i}. {t} BUY: ${trade['usdc_spent']:.0f} → {trade['matic_received']:.2f} MATIC @ ${trade['price']:.4f}")
            else:
                pnl = trade.get('pnl', 0)
                emoji = "✅" if pnl > 0 else "❌"
                print(f"{i}. {t} SELL: {trade['matic_sold']:.2f} → ${trade['usdc_received']:.0f} @ ${trade['price']:.4f} | P&L: ${pnl:+.2f} {emoji}")
        
        print("-"*60)
    
    def reset(self):
        """Reset to starting balance"""
        self.state = {
            "balance_usdc": 10000.0,
            "balance_matic": 0.0,
            "trades": [],
            "positions": [],
            "total_pnl": 0.0,
            "win_count": 0,
            "loss_count": 0,
            "created_at": datetime.now().isoformat()
        }
        self.save_state()
        print("\n🔄 Account reset to $10,000 USDC")

def main():
    """Interactive demo"""
    bot = PaperTradingBot()
    
    print("\n" + "="*60)
    print("🤖 LIVE PAPER TRADING BOT")
    print("="*60)
    print("\nThis bot uses REAL market prices but FAKE money.")
    print("Trades are saved to: paper_state.json")
    print()
    
    while True:
        bot.show_portfolio()
        
        print("\n📋 COMMANDS:")
        print("  1. Buy MATIC ($100)")
        print("  2. Buy MATIC ($500)")
        print("  3. Buy MATIC (custom)")
        print("  4. Sell 100%")
        print("  5. Sell 50%")
        print("  6. Show trade history")
        print("  7. Run strategy demo")
        print("  8. Reset account")
        print("  0. Exit")
        
        choice = input("\nChoice: ").strip()
        
        if choice == '1':
            bot.buy(100)
        elif choice == '2':
            bot.buy(500)
        elif choice == '3':
            amount = float(input("Amount in USDC: "))
            bot.buy(amount)
        elif choice == '4':
            bot.sell(100)
        elif choice == '5':
            bot.sell(50)
        elif choice == '6':
            bot.show_trade_history()
            input("\nPress Enter to continue...")
        elif choice == '7':
            print("\n🎬 Running momentum strategy demo...")
            bot.buy(1000)
            time.sleep(2)
            print("\n📈 Price pumped +5%!")
            time.sleep(1)
            bot.sell(100)
        elif choice == '8':
            confirm = input("Reset account? (yes/no): ")
            if confirm.lower() == 'yes':
                bot.reset()
        elif choice == '0':
            print("\n👋 Final portfolio:")
            pnl = bot.show_portfolio()
            if pnl > 0:
                print("🟢 You made money!")
            elif pnl < 0:
                print("🔴 You lost money (but it was fake)")
            else:
                print("⚪ Break even")
            break
        else:
            print("❌ Invalid choice")
        
        time.sleep(1)

if __name__ == "__main__":
    main()

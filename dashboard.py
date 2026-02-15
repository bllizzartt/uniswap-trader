"""
Dashboard Module
Flask web interface for monitoring and control
"""

import os
import json
import logging
import threading
import time
from typing import Dict, List, Optional
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_socketio import SocketIO, emit

from config import DASHBOARD, TRADING_MODE
from market_data import MarketDataProvider
from paper_trader import PaperTrader
from wallet import MetaMaskWallet
from strategies import StrategyManager

logger = logging.getLogger(__name__)


# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = DASHBOARD["secret_key"]

# Initialize SocketIO for real-time updates
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode=None,  # Use default (threading)
)

# Global instances (initialized in main)
market_data: Optional[MarketDataProvider] = None
paper_trader: Optional[PaperTrader] = None
wallet: Optional[MetaMaskWallet] = None
strategy_manager: Optional[StrategyManager] = None

# Background update thread
update_thread: Optional[threading.Thread] = None
stop_updates = threading.Event()


# ================== ROUTES ==================

@app.route("/")
def index():
    """Main dashboard page"""
    return render_template(
        "dashboard.html",
        trading_mode=TRADING_MODE,
        wallet_connected=wallet is not None,
    )


@app.route("/portfolio")
def portfolio():
    """Portfolio overview page"""
    if paper_trader:
        summary = paper_trader.get_portfolio_summary()
        performance = paper_trader.get_performance_report()
    else:
        summary = {
            "total_value": 0,
            "total_pnl": 0,
            "cash_usdc": 0,
            "cash_eth": 0,
            "open_positions": 0,
        }
        performance = {}
    
    return render_template(
        "portfolio.html",
        summary=summary,
        performance=performance,
    )


@app.route("/positions")
def positions():
    """Open positions page"""
    if paper_trader:
        positions = paper_trader.positions
    else:
        positions = {}
    
    return render_template(
        "positions.html",
        positions=positions,
    )


@app.route("/history")
def history():
    """Trade history page"""
    if paper_trader:
        trades = paper_trader.trade_history
    else:
        trades = []
    
    return render_template(
        "history.html",
        trades=trades,
    )


@app.route("/strategies")
def strategies():
    """Strategy management page"""
    if strategy_manager:
        strategies = {
            name: {
                "name": name,
                "performance": s.get_performance(),
            }
            for name, s in strategy_manager.strategies.items()
        }
        active = strategy_manager.active_strategy
    else:
        strategies = {}
        active = None
    
    return render_template(
        "strategies.html",
        strategies=strategies,
        active_strategy=active,
    )


@app.route("/market")
def market():
    """Market data page"""
    tokens = ["ETH", "WETH", "USDC", "USDT", "DAI"]
    prices = {}
    
    if market_data:
        for token in tokens:
            try:
                prices[token] = {
                    "price": market_data.get_current_price(token),
                    "change_24h": market_data.get_price_change_24h(token),
                    "volume": market_data.get_volume(token),
                }
            except Exception:
                prices[token] = {"price": 0, "change_24h": 0, "volume": 0}
    
    return render_template(
        "market.html",
        prices=prices,
        tokens=tokens,
    )


@app.route("/settings")
def settings():
    """Settings page"""
    return render_template("settings.html")


# ================== API ENDPOINTS ==================

@app.route("/api/portfolio")
def api_portfolio():
    """Get portfolio data"""
    if paper_trader:
        return jsonify(paper_trader.get_portfolio_summary())
    return jsonify({"error": "Paper trader not initialized"})


@app.route("/api/positions")
def api_positions():
    """Get open positions"""
    if paper_trader:
        return jsonify(paper_trader.positions)
    return jsonify({})


@app.route("/api/positions/<token>", methods=["GET", "DELETE"])
def api_position(token):
    """Get or close a position"""
    if not paper_trader:
        return jsonify({"error": "Paper trader not initialized"}), 400
    
    if request.method == "DELETE":
        result = paper_trader.execute_sell(token, 1.0)
        return jsonify(result)
    
    # GET
    if token in paper_trader.positions:
        return jsonify(paper_trader.positions[token])
    return jsonify({"error": "Position not found"}), 404


@app.route("/api/trade", methods=["POST"])
def api_trade():
    """Execute a trade"""
    if not paper_trader:
        return jsonify({"error": "Paper trader not initialized"}), 400
    
    data = request.get_json()
    
    action = data.get("action", "").lower()
    token = data.get("token", "").upper()
    amount = float(data.get("amount", 0))
    
    if action == "buy":
        result = paper_trader.execute_buy(token, amount)
    elif action == "sell":
        result = paper_trader.execute_sell(token, amount / 100)
    else:
        return jsonify({"error": "Invalid action"}), 400
    
    return jsonify(result)


@app.route("/api/swap", methods=["POST"])
def api_swap():
    """Execute a swap"""
    if not paper_trader:
        return jsonify({"error": "Paper trader not initialized"}), 400
    
    data = request.get_json()
    
    token_in = data.get("token_in", "").upper()
    token_out = data.get("token_out", "").upper()
    amount = float(data.get("amount", 0))
    
    result = paper_trader.execute_swap(token_in, token_out, amount)
    
    return jsonify(result)


@app.route("/api/market/<token>")
def api_market_price(token):
    """Get market price for token"""
    if market_data:
        price = market_data.get_current_price(token)
        change = market_data.get_price_change_24h(token)
        return jsonify({
            "token": token,
            "price": price,
            "change_24h": change,
        })
    return jsonify({"error": "Market data not initialized"})


@app.route("/api/strategies")
def api_strategies():
    """Get all strategies"""
    if strategy_manager:
        return jsonify({
            name: {
                "performance": s.get_performance(),
                "active": name == strategy_manager.active_strategy,
            }
            for name, s in strategy_manager.strategies.items()
        })
    return jsonify({})


@app.route("/api/strategies/<strategy_name>", methods=["POST"])
def api_set_strategy(strategy_name):
    """Set active strategy"""
    if not strategy_manager:
        return jsonify({"error": "Strategy manager not initialized"}), 400
    
    success = strategy_manager.set_active_strategy(strategy_name)
    
    if success:
        return jsonify({"success": True, "strategy": strategy_name})
    return jsonify({"error": "Strategy not found"}), 404


@app.route("/api/strategies/<strategy_name>/analyze", methods=["POST"])
def api_analyze_token(strategy_name):
    """Analyze token with strategy"""
    if not strategy_manager:
        return jsonify({"error": "Strategy manager not initialized"}), 400
    
    data = request.get_json()
    token = data.get("token", "ETH")
    
    if strategy_name not in strategy_manager.strategies:
        return jsonify({"error": "Strategy not found"}), 404
    
    strategy = strategy_manager.strategies[strategy_name]
    signal = strategy.analyze(token)
    
    return jsonify({
        "signal": {
            "token": signal.token,
            "action": signal.action,
            "confidence": signal.confidence,
            "strategy": signal.strategy,
            "metadata": signal.metadata,
        }
    })


@app.route("/api/performance")
def api_performance():
    """Get performance report"""
    if paper_trader:
        return jsonify(paper_trader.get_performance_report())
    return jsonify({})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Reset paper trader"""
    if not paper_trader:
        return jsonify({"error": "Paper trader not initialized"}), 400
    
    data = request.get_json() or {}
    initial_eth = float(data.get("initial_eth", 10))
    initial_usdc = float(data.get("initial_usdc", 10000))
    
    paper_trader.reset(initial_eth, initial_usdc)
    
    return jsonify({"success": True})


@app.route("/api/wallet/status")
def api_wallet_status():
    """Get wallet connection status"""
    if wallet:
        balances = wallet.get_all_balances()
        return jsonify({
            "connected": True,
            "address": wallet.address,
            "network": wallet.network_name,
            "balances": {
                "native": balances.native,
                "wrapped_native": balances.wrapped_native,
                "usdc": balances.usdc,
                "usdt": balances.usdt,
                "dai": balances.dai,
                "total_usd": balances.total_usd,
            },
        })
    
    return jsonify({
        "connected": False,
        "address": None,
    })


@app.route("/api/wallet/connect", methods=["POST"])
def api_wallet_connect():
    """Connect wallet"""
    data = request.get_json()
    private_key = data.get("private_key", "")
    
    if not private_key:
        return jsonify({"error": "Private key required"}), 400
    
    try:
        global wallet
        wallet = MetaMaskWallet(private_key=private_key)
        return jsonify({
            "success": True,
            "address": wallet.address,
            "network": wallet.network_name,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ================== REAL-TIME UPDATES ==================

def background_updates():
    """Background thread for real-time updates"""
    while not stop_updates.is_set():
        try:
            # Get portfolio update
            if paper_trader:
                portfolio = paper_trader.get_portfolio_summary()
                socketio.emit("portfolio_update", portfolio)
                
                # Check positions
                closed = paper_trader.check_positions()
                if closed:
                    socketio.emit("positions_closed", closed)
            
            # Get market prices
            if market_data:
                prices = {}
                for token in ["ETH", "USDC"]:
                    try:
                        prices[token] = {
                            "price": market_data.get_current_price(token),
                            "change": market_data.get_price_change_24h(token),
                        }
                    except Exception:
                        pass
                socketio.emit("market_update", prices)
            
            time.sleep(5)  # Update every 5 seconds
            
        except Exception as e:
            logger.error(f"Background update error: {e}")
            time.sleep(10)


@socketio.on("connect")
def handle_connect():
    """Handle client connection"""
    print("Client connected")
    emit("status", {"message": "Connected to trading bot"})


@socketio.on("disconnect")
def handle_disconnect():
    """Handle client disconnection"""
    print("Client disconnected")


@socketio.on("subscribe_market")
def handle_market_subscribe(data):
    """Subscribe to market updates"""
    emit("market_update", {"subscribed": True})


# ================== TEMPLATES ==================

# Create templates directory
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(templates_dir, exist_ok=True)

# Dashboard template
dashboard_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Uniswap Trading Bot</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>
</head>
<body class="bg-gray-900 text-white">
    <nav class="bg-gray-800 border-b border-gray-700">
        <div class="max-w-7xl mx-auto px-4">
            <div class="flex justify-between h-16">
                <div class="flex items-center">
                    <span class="text-xl font-bold text-indigo-400">Uniswap Bot</span>
                </div>
                <div class="flex items-center space-x-4">
                    <span class="text-sm text-gray-400">{{ 'PAPER' if trading_mode == 'paper' else 'LIVE' }} MODE</span>
                    {% if wallet_connected %}
                    <span class="px-2 py-1 bg-green-900 text-green-300 rounded text-sm">Connected</span>
                    {% else %}
                    <span class="px-2 py-1 bg-gray-700 text-gray-300 rounded text-sm">Not Connected</span>
                    {% endif %}
                </div>
            </div>
        </div>
    </nav>

    <main class="max-w-7xl mx-auto py-6 px-4">
        <!-- Stats Cards -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
            <div class="bg-gray-800 rounded-lg p-6">
                <h3 class="text-gray-400 text-sm">Portfolio Value</h3>
                <p class="text-2xl font-bold" id="portfolio-value">$0.00</p>
            </div>
            <div class="bg-gray-800 rounded-lg p-6">
                <h3 class="text-gray-400 text-sm">Total P&L</h3>
                <p class="text-2xl font-bold" id="total-pnl">$0.00</p>
            </div>
            <div class="bg-gray-800 rounded-lg p-6">
                <h3 class="text-gray-400 text-sm">Open Positions</h3>
                <p class="text-2xl font-bold" id="open-positions">0</p>
            </div>
            <div class="bg-gray-800 rounded-lg p-6">
                <h3 class="text-gray-400 text-sm">ETH Price</h3>
                <p class="text-2xl font-bold" id="eth-price">$0.00</p>
            </div>
        </div>

        <!-- Quick Actions -->
        <div class="bg-gray-800 rounded-lg p-6 mb-6">
            <h2 class="text-lg font-semibold mb-4">Quick Trade</h2>
            <div class="flex gap-4">
                <select id="trade-token" class="bg-gray-700 rounded px-4 py-2">
                    <option value="ETH">ETH</option>
                    <option value="USDC">USDC</option>
                </select>
                <select id="trade-action" class="bg-gray-700 rounded px-4 py-2">
                    <option value="buy">Buy</option>
                    <option value="sell">Sell</option>
                </select>
                <input type="number" id="trade-amount" placeholder="Amount (USD)" class="bg-gray-700 rounded px-4 py-2 w-40">
                <button onclick="executeTrade()" class="bg-indigo-600 hover:bg-indigo-700 px-6 py-2 rounded">Execute</button>
            </div>
        </div>

        <!-- Navigation Tabs -->
        <div class="flex space-x-4 mb-6">
            <a href="/" class="px-4 py-2 bg-gray-800 rounded hover:bg-gray-700">Dashboard</a>
            <a href="/positions" class="px-4 py-2 bg-gray-800 rounded hover:bg-gray-700">Positions</a>
            <a href="/history" class="px-4 py-2 bg-gray-800 rounded hover:bg-gray-700">History</a>
            <a href="/strategies" class="px-4 py-2 bg-gray-800 rounded hover:bg-gray-700">Strategies</a>
            <a href="/market" class="px-4 py-2 bg-gray-800 rounded hover:bg-gray-700">Market</a>
        </div>

        {% block content %}{% endblock %}
    </main>

    <script>
        const socket = io();
        
        socket.on('connect', () => {
            console.log('Connected to server');
        });
        
        socket.on('portfolio_update', (data) => {
            document.getElementById('portfolio-value').textContent = '$' + data.total_value.toLocaleString('en-US', {minimumFractionDigits: 2});
            document.getElementById('open-positions').textContent = data.open_positions;
            
            const pnlEl = document.getElementById('total-pnl');
            pnlEl.textContent = (data.total_pnl >= 0 ? '+' : '') + '$' + data.total_pnl.toLocaleString('en-US', {minimumFractionDigits: 2});
            pnlEl.className = 'text-2xl font-bold ' + (data.total_pnl >= 0 ? 'text-green-400' : 'text-red-400');
        });
        
        socket.on('market_update', (data) => {
            if (data.ETH) {
                document.getElementById('eth-price').textContent = '$' + data.ETH.price.toLocaleString('en-US', {minimumFractionDigits: 2});
            }
        });
        
        async function executeTrade() {
            const token = document.getElementById('trade-token').value;
            const action = document.getElementById('trade-action').value;
            const amount = document.getElementById('trade-amount').value;
            
            const response = await fetch('/api/trade', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({token, action, amount: parseFloat(amount)})
            });
            
            const result = await response.json();
            if (result.success) {
                alert('Trade executed successfully!');
            } else {
                alert('Trade failed: ' + result.error);
            }
        }
        
        // Initial data load
        async function loadData() {
            const response = await fetch('/api/portfolio');
            const data = await response.json();
            
            if (data.total_value !== undefined) {
                document.getElementById('portfolio-value').textContent = '$' + data.total_value.toLocaleString('en-US', {minimumFractionDigits: 2});
                document.getElementById('open-positions').textContent = data.open_positions;
            }
        }
        
        loadData();
    </script>
</body>
</html>
"""

# Create dashboard template
with open(os.path.join(templates_dir, "dashboard.html"), "w") as f:
    f.write(dashboard_html)


# ================== MAIN ==================

def create_dashboard(
    market_data_provider: MarketDataProvider,
    paper_trader_instance: PaperTrader = None,
    wallet_instance: MetaMaskWallet = None,
):
    """Create and configure dashboard"""
    global market_data, paper_trader, wallet, strategy_manager
    
    market_data = market_data_provider
    paper_trader = paper_trader_instance
    wallet = wallet_instance
    
    if market_data:
        strategy_manager = StrategyManager(market_data, paper_mode=(TRADING_MODE == "paper"))
    
    return app


def run_dashboard(host: str = None, port: int = None, debug: bool = False):
    """Run the dashboard server"""
    global update_thread
    
    host = host or DASHBOARD["host"]
    port = port or DASHBOARD["port"]
    debug = debug or DASHBOARD["debug"]
    
    # Start background updates
    stop_updates.clear()
    update_thread = threading.Thread(target=background_updates, daemon=True)
    update_thread.start()
    
    logger.info(f"Starting dashboard on {host}:{port}")
    
    try:
        socketio.run(app, host=host, port=port, debug=debug)
    finally:
        stop_updates.set()
        if update_thread:
            update_thread.join(timeout=5)


if __name__ == "__main__":
    # Initialize components
    md = MarketDataProvider()
    pt = PaperTrader(md)
    
    # Create dashboard
    dashboard = create_dashboard(md, pt)
    
    # Run
    run_dashboard(debug=True)

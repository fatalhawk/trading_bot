import os
import logging
from datetime import datetime, timedelta, timezone
from statistics import mean, stdev

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# === ENVIRONMENT VARIABLES ===
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")

# Define highly correlated pairs instead of single symbols
PAIRS = [("KO", "PEP"), ("XOM", "CVX"), ("AMD", "INTC")] 

# === SETUP LOGGING ===
os.makedirs(LOG_DIR, exist_ok=True)
log_path = os.path.join(LOG_DIR, f"log_{datetime.now().date()}.txt")
logging.basicConfig(filename=log_path, level=logging.INFO, format="%(asctime)s - %(message)s")

# === ALPACA CLIENTS ===
trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

def fetch_prices(symbol, lookback_days=30):
    """Fetches historical daily close prices for a given symbol."""
    logging.info(f"Fetching prices for {symbol}...")
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=lookback_days)

    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        start=start,
        end=end,
        timeframe=TimeFrame.Day,
        feed="iex"
    )

    bars = data_client.get_stock_bars(request).data.get(symbol, [])
    return [bar.close for bar in bars]

def execute_trade(symbol, side, qty=1):
    """Helper function to execute a market order."""
    try:
        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.DAY
        )
        response = trading_client.submit_order(order)
        logging.info(f"{symbol}: {side.name} order placed. ID: {response.id}")
    except Exception as e:
        logging.error(f"{symbol}: Error placing {side.name} order: {e}")

def close_position(symbol):
    """Closes an open position for a given symbol if it exists."""
    logging.info(f"Closing position for {symbol}...")
    try:
        trading_client.close_position(symbol)
        logging.info(f"{symbol}: Position closed.")
    except Exception as e:
        # Alpaca throws an error if you try to close a position that doesn't exist
        logging.warning(f"{symbol}: Error closing position: {e}")

def trade_pair(sym_a, sym_b):
    logging.info(f"Trading pair {sym_a}/{sym_b}...")
    prices_a = fetch_prices(sym_a)
    prices_b = fetch_prices(sym_b)

    # Ensure we have aligned data sets
    min_length = min(len(prices_a), len(prices_b))
    if min_length < 2:
        logging.warning(f"{sym_a}/{sym_b}: Not enough data.")
        return

    # Trim to matching lengths if one has less data
    prices_a = prices_a[-min_length:]
    prices_b = prices_b[-min_length:]

    # Calculate historical ratios
    ratios = [a / b for a, b in zip(prices_a, prices_b)]
    
    avg_ratio = mean(ratios)
    stdev_ratio = stdev(ratios)
    current_ratio = ratios[-1]

    # Calculate Z-Score
    z_score = (current_ratio - avg_ratio) / stdev_ratio
    logging.info(f"{sym_a}/{sym_b} - Z-Score: {z_score:.2f} (Ratio: {current_ratio:.2f}, Mean: {avg_ratio:.2f})")

    # Entry Thresholds (2 standard deviations)
    entry_threshold = 2.0
    # Exit Threshold (0.5 standard deviations)
    exit_threshold = 0.5

    # Check if we already have positions open
    positions = {p.symbol: p.side for p in trading_client.get_all_positions()}
    has_pos_a = sym_a in positions
    has_pos_b = sym_b in positions

    # === TRADING LOGIC ===
    if z_score > entry_threshold and not (has_pos_a or has_pos_b):
        # Ratio is too high: A is overvalued, B is undervalued
        logging.info(f"Signal: Short {sym_a}, Buy {sym_b}")
        execute_trade(sym_a, OrderSide.SELL)
        execute_trade(sym_b, OrderSide.BUY)

    elif z_score < -entry_threshold and not (has_pos_a or has_pos_b):
        # Ratio is too low: A is undervalued, B is overvalued
        logging.info(f"Signal: Buy {sym_a}, Short {sym_b}")
        execute_trade(sym_a, OrderSide.BUY)
        execute_trade(sym_b, OrderSide.SELL)

    elif abs(z_score) < exit_threshold and (has_pos_a or has_pos_b):
        # Spread has reverted to the mean, take profit
        logging.info(f"Signal: Mean reverted. Closing positions for {sym_a} and {sym_b}.")
        close_position(sym_a)
        close_position(sym_b)
    else:
        logging.info(f"{sym_a}/{sym_b}: No action taken.")

def run_bot():
    logging.info("=== Starting Daily Pairs Trading ===")
    for pair in PAIRS:
        trade_pair(pair[0], pair[1])
    logging.info("=== Trading Completed ===")

if __name__ == "__main__":
    run_bot()
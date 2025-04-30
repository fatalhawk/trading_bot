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
SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]

# === SETUP LOGGING ===
os.makedirs(LOG_DIR, exist_ok=True)
log_path = os.path.join(LOG_DIR, f"log_{datetime.now().date()}.txt")
logging.basicConfig(filename=log_path, level=logging.INFO, format="%(asctime)s - %(message)s")

# === ALPACA CLIENTS ===
trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)


def fetch_prices(symbol):
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=10)

    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        start=start,
        end=end,
        timeframe=TimeFrame.Day,
        feed="iex"
    )

    bars = data_client.get_stock_bars(request).data.get(symbol, [])
    if len(bars) < 2:
        logging.warning(f"{symbol}: Not enough data to calculate mean or stdev.")
        return []

    return [bar.close for bar in bars]


def trade_symbol(symbol):
    prices = fetch_prices(symbol)
    if len(prices) < 2:
        return

    avg = mean(prices)
    volatility = stdev(prices)
    latest = prices[-1]

    logging.info(f"{symbol}: Latest={latest:.2f}, Mean={avg:.2f}, Stdev={volatility:.2f}")

    # Mean Reversion Logic: Buy if price < mean - stdev, sell if > mean + stdev
    side = None
    if latest < avg - volatility:
        side = OrderSide.BUY
    elif latest > avg + volatility:
        side = OrderSide.SELL

    if side:
        try:
            order = MarketOrderRequest(
                symbol=symbol,
                qty=1,
                side=side,
                time_in_force=TimeInForce.DAY
            )
            response = trading_client.submit_order(order)
            logging.info(f"{symbol}: {side.name} order placed. ID: {response.id}")
        except Exception as e:
            logging.error(f"{symbol}: Error placing order: {e}")
    else:
        logging.info(f"{symbol}: No trade condition met.")


def run_bot():
    logging.info("=== Starting Daily Trading ===")
    for symbol in SYMBOLS:
        trade_symbol(symbol)
    logging.info("=== Trading Completed ===")


if __name__ == "__main__":
    run_bot()

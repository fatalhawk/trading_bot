import os
import datetime
import statistics
import pytz
from alpaca_trade_api.rest import REST, TimeFrame

# === Config ===
STOCKS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
DAYS = 20
LOG_DIR = "logs"

ALPACA_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY")
ALPACA_URL = "https://paper-api.alpaca.markets"

alpaca = REST(ALPACA_KEY, ALPACA_SECRET, ALPACA_URL)

eastern = pytz.timezone("US/Eastern")
now = datetime.datetime.now(eastern)
today_str = now.strftime("%Y-%m-%d")

def log(message):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(f"{LOG_DIR}/log_{today_str}.txt", "a") as f:
        f.write(f"{now.strftime('%H:%M:%S')} - {message}\n")
    print(message)

def get_position(symbol):
    try:
        pos = alpaca.get_position(symbol)
        return float(pos.qty)
    except:
        return 0

def fetch_prices(symbol):
    end = datetime.datetime.now(eastern)
    start = end - datetime.timedelta(days=DAYS * 2)
    bars = alpaca.get_bars(symbol, TimeFrame.Day, start=start, end=end).df
    return bars['close'][-DAYS:].tolist()

def should_buy(prices):
    mean = statistics.mean(prices[:-1])
    std = statistics.stdev(prices[:-1])
    z = (prices[-1] - mean) / std
    return z < -1.0, z

def should_sell(prices):
    mean = statistics.mean(prices[:-1])
    std = statistics.stdev(prices[:-1])
    z = (prices[-1] - mean) / std
    return z > 1.0, z

def trade(symbol):
    try:
        prices = fetch_prices(symbol)
        price = prices[-1]
        qty = get_position(symbol)

        buy, z_buy = should_buy(prices)
        sell, z_sell = should_sell(prices)

        if buy and qty == 0:
            alpaca.submit_order(symbol=symbol, qty=1, side='buy', type='market', time_in_force='day')
            log(f"[{symbol}] BUY at {price:.2f}, Z={z_buy:.2f}")
        elif sell and qty > 0:
            alpaca.submit_order(symbol=symbol, qty=1, side='sell', type='market', time_in_force='day')
            log(f"[{symbol}] SELL at {price:.2f}, Z={z_sell:.2f}")
        else:
            z = z_buy if qty == 0 else z_sell
            log(f"[{symbol}] HOLD at {price:.2f}, Z={z:.2f}")

    except Exception as e:
        log(f"[{symbol}] ERROR: {e}")

def main():
    log("Running daily trade check...")
    for symbol in STOCKS:
        trade(symbol)

if __name__ == "__main__":
    main()

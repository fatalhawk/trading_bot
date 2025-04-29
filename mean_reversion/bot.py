import os
import time
import datetime
import pytz
import statistics
from alpaca_trade_api.rest import REST, TimeFrame

# === CONFIG ===
STOCKS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
DAYS = 20
LOG_DIR = "logs"
CHECK_INTERVAL_MINUTES = 5

# Alpaca setup
ALPACA_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
alpaca = REST(ALPACA_KEY, ALPACA_SECRET, ALPACA_BASE_URL)

# Timezone
eastern = pytz.timezone("US/Eastern")

# Logging
def log(message):
    today = datetime.datetime.now(eastern).strftime("%Y-%m-%d")
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file_path = os.path.join(LOG_DIR, f"log_{today}.txt")
    with open(log_file_path, "a") as f:
        timestamp = datetime.datetime.now(eastern).strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{timestamp} - {message}\n")
    print(message)

# Check market status
def market_is_open():
    clock = alpaca.get_clock()
    return clock.is_open

# Get previous position
def get_position(symbol):
    try:
        positions = alpaca.list_positions()
        for p in positions:
            if p.symbol == symbol:
                return float(p.qty)
        return 0
    except Exception as e:
        log(f"[{symbol}] Error getting position: {e}")
        return 0

# Get historical prices
def fetch_prices(symbol):
    end = datetime.datetime.now(eastern)
    start = end - datetime.timedelta(days=DAYS * 2)
    bars = alpaca.get_bars(symbol, TimeFrame.Day, start=start, end=end).df
    return bars['close'][-DAYS:].tolist()

# Trading signal logic
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

# One trade per day check
last_traded = {}

def trade(symbol):
    try:
        now = datetime.datetime.now(eastern)
        today_str = now.date().isoformat()
        prices = fetch_prices(symbol)
        current_price = prices[-1]
        position = get_position(symbol)

        buy_signal, z_buy = should_buy(prices)
        sell_signal, z_sell = should_sell(prices)

        if last_traded.get(symbol) == today_str:
            log(f"[{symbol}] Already traded today. Skipping.")
            return

        if buy_signal and position == 0:
            alpaca.submit_order(symbol=symbol, qty=1, side='buy', type='market', time_in_force='day')
            log(f"[{symbol}] BUY at {current_price:.2f}, Z: {z_buy:.2f}")
            last_traded[symbol] = today_str

        elif sell_signal and position > 0:
            alpaca.submit_order(symbol=symbol, qty=1, side='sell', type='market', time_in_force='day')
            log(f"[{symbol}] SELL at {current_price:.2f}, Z: {z_sell:.2f}")
            last_traded[symbol] = today_str

        else:
            action = "HOLD"
            z = z_buy if position == 0 else z_sell
            log(f"[{symbol}] {action}, Price: {current_price:.2f}, Z: {z:.2f}")

    except Exception as e:
        log(f"[{symbol}] ERROR: {e}")

# === Main Loop ===
def main():
    log("Bot started.")
    while True:
        now = datetime.datetime.now(eastern)
        weekday = now.weekday()

        if weekday < 5 and market_is_open():
            for symbol in STOCKS:
                trade(symbol)
        else:
            log("Market closed or weekend. Waiting...")

        time.sleep(CHECK_INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    main()

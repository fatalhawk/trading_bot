import os
import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO
from datetime import datetime, timedelta, timezone

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# === ENVIRONMENT VARIABLES ===
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# === 1. FETCH TRAINING DATA ===
def get_historical_data(symbol, days=365):
    """Fetches historical data to train the RL agent."""
    data_client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        start=start,
        end=end,
        timeframe=TimeFrame.Day,
        feed="iex"
    )
    
    bars = data_client.get_stock_bars(request).data.get(symbol, [])
    
    # Convert to Pandas DataFrame for easier manipulation in the Gym Env
    df = pd.DataFrame([{
        'close': bar.close,
        'volume': bar.volume
    } for bar in bars])
    
    # Calculate percentage returns (better for neural networks than raw prices)
    df['return'] = df['close'].pct_change()
    df = df.dropna().reset_index(drop=True)
    return df

# === 2. CREATE THE GYMNASIUM ENVIRONMENT ===
class TradingEnv(gym.Env):
    """A custom trading environment for OpenAI Gymnasium"""
    
    def __init__(self, df, lookback_window=10):
        super(TradingEnv, self).__init__()
        self.df = df
        self.lookback_window = lookback_window
        
        # Actions: 0 = Hold, 1 = Buy, 2 = Sell
        self.action_space = spaces.Discrete(3)
        
        # Observation: [Lookback window of returns] + [Current Position Flag]
        # Adding +1 for the position flag
        self.observation_space = spaces.Box(
            low=-1, high=1, shape=(lookback_window + 1,), dtype=np.float32
        )
        
    def reset(self, seed=None):
        super().reset(seed=seed)
        # Start at the end of the first lookback window
        self.current_step = self.lookback_window
        
        # Portfolio setup
        self.balance = 10000.0  # Starting cash
        self.shares_held = 0
        self.net_worth = self.balance
        
        return self._next_observation(), {}
        
    def _next_observation(self):
        # Get the returns for the lookback window
        frame = self.df['return'].values[self.current_step - self.lookback_window : self.current_step]
        
        # Flag indicating if we currently hold shares (1.0) or not (0.0)
        position_flag = 1.0 if self.shares_held > 0 else 0.0
        
        # Append the position flag to the observation array
        obs = np.append(frame, position_flag)
        return obs.astype(np.float32)
        
    def step(self, action):
        current_price = self.df['close'].values[self.current_step]
        prev_net_worth = self.net_worth
        
        # Execute Action
        if action == 1 and self.shares_held == 0: # Buy
            # Buy as many shares as possible
            self.shares_held = self.balance // current_price
            self.balance -= self.shares_held * current_price
            
        elif action == 2 and self.shares_held > 0: # Sell
            # Sell all shares
            self.balance += self.shares_held * current_price
            self.shares_held = 0
            
        # Update current step and calculate new net worth
        self.current_step += 1
        self.net_worth = self.balance + (self.shares_held * current_price)
        
        # Reward is the change in net worth
        reward = self.net_worth - prev_net_worth
        
        # Check if we reached the end of our historical data
        terminated = self.current_step >= len(self.df) - 1
        truncated = False
        
        return self._next_observation(), reward, terminated, truncated, {}

# === 3. TRAIN AND EXECUTE ===
def run_rl_bot(symbol):
    print(f"Fetching data for {symbol}...")
    df = get_historical_data(symbol, days=700) # Fetch ~2 years of data
    
    if len(df) < 50:
        print("Not enough data to train.")
        return
        
    # Initialize the custom environment
    env = TradingEnv(df)
    
    print("Training the RL Agent (PPO)...")
    # PPO (Proximal Policy Optimization) is a highly stable RL algorithm
    model = PPO("MlpPolicy", env, verbose=0)
    
    # Train for 20,000 timesteps (epochs). In production, this would be much higher.
    model.learn(total_timesteps=20000)
    
    print("Training complete. Evaluating current market state...")
    
    # To get the LIVE prediction, we reset the environment and force it to the final day
    obs, _ = env.reset()
    env.current_step = len(df) - 1 
    current_obs = env._next_observation()
    
    # Let the trained model predict the best action for today
    action, _states = model.predict(current_obs)
    
    action_map = {0: "HOLD", 1: "BUY", 2: "SELL"}
    print(f"[{symbol}] The AI Agent recommends: {action_map[action]}")
    
    # From here, you would route the 'action' variable to your Alpaca MarketOrderRequest 
    # exactly like you did in the Mean Reversion script.

if __name__ == "__main__":
    run_rl_bot("AAPL")
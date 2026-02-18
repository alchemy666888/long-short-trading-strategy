
| Parameter                 | Value                                                                                                                                                                                                                                                         |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Universe**              | BTC, ETH, SOL, XRP, Gold, Silver, Copper, EUR/USD, AUD/USD, TSLA, MCD, NVDA, GOOG, SPY                                                                                                                                                                        |
| **Trading Window**        | 9:30 AM – 4:00 PM ET (all positions closed by 3:55 PM)                                                                                                                                                                                                        |
| **Data Frequency**        | 5-minute bars                                                                                                                                                                                                                                                 |
| **Lookback Period**       | 36 periods (3 hours)                                                                                                                                                                                                                                          |
| **Z-Score Calculation**   | (Current Price - 36-period SMA) / 36-period StdDev of Price                                                                                                                                                                                                   |
| **Entry Threshold**       | Z < -2.0 (Long), Z > +2.0 (Short)                                                                                                                                                                                                                             |
| **Exit (Take Profit)**    | Z crosses 0                                                                                                                                                                                                                                                   |
| **Stop Loss**             | Z < -3.5 (Longs), Z > +3.5 (Shorts)                                                                                                                                                                                                                           |
| **Position Count**        | Up to 3 Longs and 3 Shorts, balanced (equal number of each)                                                                                                                                                                                                   |
| **Selection Logic**       | At each rebalance, rank all assets by Z-score extremity; take top N long candidates (most negative) and top N short candidates (most positive) where N = min(3, #candidates) for each side, but ensure equal numbers by taking the smaller N from both sides. |
| **Position Sizing**       | Equal risk weighting: position size inversely proportional to each asset’s volatility (e.g., 36-period StdDev of 5-min returns). All positions (longs and shorts) receive the same risk allocation.                                                           |
| **Rebalance Schedule**    | 10:00 AM, 12:00 PM, 2:00 PM. At each rebalance, close all existing positions and open new ones based on the latest rankings (full portfolio reset).                                                                                                           |
| **Continuous Monitoring** | Exit conditions (Z=0 or stop) are checked on every bar; if triggered, the position is closed immediately and not re-entered until the next rebalance (if still a candidate).                                                                                  |
| **End-of-Day**            | All remaining positions closed at 3:55 PM ET.                                                                                                                                                                                                                 |

---

# Next Step: Backtesting & Performance Evaluation

To validate this strategy, we need to run a historical simulation. Here’s what we’ll need and what we should look for:

## 1. **Data Requirements**
- **Historical 5-minute OHLCV data** for all 15 assets, aligned to ET timezone.
- For forex and metals, we need continuous futures or spot prices. For crypto, spot prices from a reliable exchange.
- Data must include pre-market (for the 10:00 AM calculation we need data from 9:30 AM onward, so 9:30–10:00 is enough for the first Z-score).
- **Survivorship bias check:** Ensure we use historical constituents (e.g., SPY always existed).

## 2. **Key Assumptions for Realism**
- **Slippage & Commissions:** We must model transaction costs. For each asset class, use typical taker fees:
    - Crypto: 0.1% (varies by exchange)
    - Stocks: $0.005 per share + SEC fees (or $0.01 per share for simplicity)
    - Forex: Spread cost (e.g., 1 pip for EUR/USD = $10 per 100k)
    - Metals: Futures commissions (~$5 per contract) + spread
- **Market Impact:** For simplicity, assume we can execute at the next bar's open with a slippage proportional to volatility (e.g., 0.5× spread). We can refine later.
- **Shorting constraints:** Stocks may have borrow costs; crypto and forex are easy to short via futures or margin. Assume we can short all assets at zero cost (except dividends for stocks, which we ignore in day trading).

## 3. **Performance Metrics to Monitor**
- **Sharpe Ratio** (annualized) – target > 1.5 for a good intraday strategy.
- **Maximum Drawdown** – intraday and daily.
- **Win Rate & Profit Factor** – but for mean reversion, win rate can be high but profit factor moderate.
- **Average Hold Time** – should be less than the rebalance interval.
- **Turnover & Costs** – to ensure profits aren't eaten by fees.
- **Market Neutrality Check** – regress daily P&L against SPY returns; the beta should be near zero. Also check sector exposures.

## 4. **Potential Pitfalls & Refinements**
- **Correlation breakdown:** During high-volatility events (e.g., Fed announcements), mean reversion can fail (trends persist). We might need a volatility filter (e.g., skip trading if VIX spikes).
- **Sparse signals:** On quiet days, we may have fewer than 3 pairs. That's fine, but we must ensure risk is scaled down accordingly.
- **Lookback period sensitivity:** We should test 30, 36, 40 periods to ensure robustness.
- **Threshold sensitivity:** Test 1.5, 2.0, 2.5 for entry, and 3.0, 3.5 for stops.
- **Time-based exits:** Some positions might not revert by close; we force close at 3:55 PM, which could incur losses if they are still extended. That's acceptable.

## 5. **Next Actions**
- If you have access to historical data, we can outline a backtesting framework in Python (or your preferred language).
- We can also discuss paper trading the strategy live to observe behavior.

---

# Backtest 

Excellent. Let's build a comprehensive backtesting plan. We'll break it down into **Data, Framework, Execution Simulation, and Performance Analysis**. I'll provide a clear roadmap so you (or your team) can code this in Python (or any language) and interpret the results.

---

## 1. Backtesting Goals
- Verify if the mean-reversion signal (Z-score extremes) generates positive risk-adjusted returns across the 15 assets.
- Confirm market neutrality: portfolio beta to SPY should be near zero.
- Measure transaction costs impact and optimal position sizing.
- Identify drawdown periods and regime-dependent performance (e.g., high vs. low volatility days).

---

## 2. Data Requirements

### 2.1. Data Sources
You'll need **5-minute OHLCV** (Open, High, Low, Close, Volume) for each asset, aligned to Eastern Time (ET).  
- **Stocks (TSLA, MCD, NVDA, GOOG, SPY):** Use historical data from a provider like Polygon, Alpaca, Yahoo Finance (adjusted for splits/dividends). Ensure timestamps are in ET.
- **Forex (EUR/USD, AUD/USD):** Typically from brokers (Oanda, FXCM) or free sources (TrueFX). Forex is 24/5; we'll filter to our trading window.
- **Metals (Gold, Silver, Copper):** Continuous futures contracts (e.g., GC, SI, HG from CME). Ensure we use front-month with rollover.
- **Crypto (BTC, ETH, SOL, XRP):** From exchanges (Binance, Coinbase) – ensure timestamps are converted to ET.

**Data quality checklist:**
- No gaps during trading hours (for stocks, only market hours matter; for others, we need 24h data but we'll only use the 9:30–16:00 window).
- Adjust for stock splits and dividends.
- For futures, account for rollover (use continuous back-adjusted series or handle rolls explicitly).

### 2.2. Data Period
- At least **2–3 years** to capture different market regimes (e.g., 2021–2023 includes crypto boom/bust, inflation shocks, rate hikes).
- Reserve the last **6 months** for out-of-sample testing (do not use for parameter tuning).

---

## 3. Backtesting Framework

We'll implement a **event-driven backtester** that processes bar by bar, but for simplicity we can use a **vectorized approach** with periodic rebalancing. Since our rebalances happen at fixed times (10:00, 12:00, 14:00 ET), a vectorized method is sufficient: at each rebalance time, compute signals and simulate trades.

### 3.1. Core Steps
1. **Load and align data:** Combine all asset price series into a single DataFrame with datetime index (5-minute bars). Forward-fill missing values carefully (e.g., stocks only have data during market hours; for forex/crypto outside stock hours, we'll still have data but we only trade within 9:30–16:00).
2. **Compute Z-scores for each bar:** For each asset, calculate rolling mean and std dev over the last 36 periods (3 hours). Note: at the start of the day (first bar at 9:30), we don't have 36 bars yet. We can either start trading after enough history is available (e.g., first trade at 10:00, which has data from 9:30 to 9:55 – that's only 6 bars). Wait – we need 36 bars before we can compute the first valid Z-score. So the earliest we can compute is at 9:30 + 36*5 = 9:30 + 180 min = 12:30? That's too late. We need a solution: **use a shorter lookback for the first few hours or use pre-market data for assets that trade 24/7.**

**Correction:** Since we're using a 36-period lookback, at 9:30 we have zero bars from the current day. At 10:00, we have 6 bars (9:30–9:55). That's insufficient. We have two practical fixes:
- **Use a shorter lookback for the first part of the day**, e.g., start with 12 periods (1 hour) and gradually increase as the day progresses. This adds complexity.
- **Use the previous day's last 3 hours** to initialize the Z-score for the current day. That is, for the 10:00 scan, we use the last 36 bars of the previous trading session (for stocks) and the last 36 bars of overnight trading (for forex/crypto). This is common in intraday mean reversion: the "mean" is anchored to recent history, not just today's action.

**Recommended approach:** At each bar, compute the Z-score using the last 36 bars of data available, regardless of whether they cross day boundaries. For stocks, we'll have a gap overnight; we can either use only intraday data from the same day (which means we can't compute until ~12:30) or we use the last 36 bars of the previous day. The latter is more realistic because traders do look at yesterday's closing range. We'll adopt **rolling window across days** for all assets. This ensures we have a Z-score at 10:00 using data from, say, 10:00–16:00 previous day plus 9:30–10:00 today (but for stocks, the previous day's last bars are valid). We must be careful with overnight gaps: if a stock gaps up at open, the Z-score will spike because the price is far from yesterday's mean, which is exactly the signal we want.

Implementation detail: For each asset, maintain a rolling window of the last 36 bars (including overnight/holiday gaps). When a new bar arrives, we append it; if there's a time gap (e.g., weekend), we simply don't add bars; the rolling window will contain bars from before the gap. That's fine.

### 3.2. Signal Generation at Rebalance Times
At 10:00, 12:00, 14:00 (using the bar that closes at that time, e.g., 10:00 bar includes data from 9:55 to 10:00; we'll use the close of that bar as the price for signal calculation), we:
- Compute Z-scores for all assets using the latest rolling window.
- Identify Long candidates: assets with Z < -2.0.
- Identify Short candidates: assets with Z > +2.0.
- Rank Longs by Z (most negative first) and Shorts by Z (most positive first).
- Select up to 3 Longs and 3 Shorts, but ensure equal count: let N = min( number of Long candidates, number of Short candidates, 3 ). Take top N from each list.
- If N = 0, no trades at this rebalance (stay in cash).

### 3.3. Position Sizing (Equal Risk)
For each selected asset i, we need to determine the position size (number of units or notional) such that each position contributes the same risk. Risk is measured as the asset's volatility over the lookback period (e.g., standard deviation of 5-minute returns, annualized or scaled to the holding period). Since we plan to hold until exit or next rebalance, we can use the same volatility estimate.

**Method:**
- Compute daily volatility (or per-bar volatility) for each asset. For simplicity, use the 36-period standard deviation of returns (in percentage terms) as a measure of risk per bar. Then, for a given risk budget per position (say $R risk per trade), the position size (in dollars) is:
  \[
  \text{Position Size}_i = \frac{R}{\sigma_i}
  \]
  where \(\sigma_i\) is the asset's volatility (standard deviation of returns). If we want each position to have the same expected daily move contribution, we can set R based on total capital and number of positions.

**Practical implementation:**
- Choose a target total risk (e.g., 1% of capital per day). If we have up to 6 positions, allocate 0.1667% of capital risk to each. Then position size = (0.001667 * capital) / \(\sigma_i\) (where \(\sigma_i\) is daily volatility). But since we are in a day trade, we can also use the per-bar volatility scaled to expected holding period. Simpler: use the 36-period standard deviation of returns (which is about 3 hours of data) as a proxy for the asset's typical move over that horizon. Then we can set size so that a 1-standard-deviation move in the asset causes a fixed dollar P&L.

We'll define a risk factor: let's assume we want each position to have a **volatility allocation** of $1,000 per 1% daily move? Actually, it's easier:  
- Let \( \text{capital per position} = \frac{\text{Total Capital} \times \text{leverage factor}}{\text{Number of positions}} \). But to equalize risk, we scale by inverse volatility:  
  \[
  \text{Allocated Capital}_i = \frac{\text{Total Risk Budget}}{\sigma_i} \times \frac{1}{\sum_{j} 1/\sigma_j}
  \]
  where Total Risk Budget is some fraction of capital. But simpler: We'll just ensure that the product of position size and volatility is constant across assets.

**In backtest:** We'll maintain a cash account and allocate at each rebalance. We'll compute the number of units (shares, contracts, or forex lots) based on the close price at rebalance time.

### 3.4. Exit Rules Between Rebalances
We continuously monitor positions:
- If a position's Z-score crosses 0 (i.e., from negative to positive for longs, or positive to negative for shorts), we close it at the next bar's open (or current bar's close? We'll use next bar open to avoid look-ahead).
- If stop loss is hit (Z < -3.5 for longs, Z > +3.5 for shorts), close at next bar open.
- At 15:55, close all remaining positions at the close of that bar (or next bar open, but to avoid holding overnight, we'll use the 15:55 bar close as execution price).

### 3.5. Rebalance Execution
At each rebalance time (10:00, 12:00, 14:00), we close all existing positions (using the next bar open after the rebalance signal? Wait, we need to be consistent: if we compute signals at the 10:00 bar (which closes at 10:00), we cannot trade at that exact moment because we only know the close at 10:00:00. In practice, we would place orders at 10:00:01 based on the just-closed bar. So execution happens at the next bar (10:05 open). This is a one-bar delay, which is realistic.

**Sequence:**
- At 10:00 bar close, we have new Z-scores. We compute desired positions.
- At 10:05 open, we execute market orders to close old positions and open new ones. We use the 10:05 open price as execution price.
- Similarly, exits due to Z=0 or stop are checked at each bar close; if triggered, we execute at next bar open.

### 3.6. Handling Multiple Assets and Cash
We'll assume we have a margin account that allows shorting and leverage. We'll start with a capital base (e.g., $1,000,000) and track cash and positions. At each execution, we calculate the required notional for each new position based on the current price and the risk-based allocation. If we don't have enough cash (due to leverage constraints), we scale down positions proportionally. For simplicity, assume we can use leverage up to 4:1 (common for intraday).

---

## 4. Python Implementation Outline

Here's a high-level structure using pandas. We'll assume you have a DataFrame `data` with a MultiIndex (datetime, asset) or a wide format with columns for each asset's price.

```python
import pandas as pd
import numpy as np

# Load data (already aligned and cleaned)
# data: DataFrame with datetime index, columns = asset names, values = close prices

# Parameters
lookback = 36  # periods
entry_z = 2.0
stop_z = 3.5
rebalance_times = ['10:00', '12:00', '14:00']
capital = 1_000_000
risk_per_position = 0.001 * capital  # 0.1% of capital risk per position (adjust)

# Precompute returns and rolling stats
returns = data.pct_change()
rolling_mean = data.rolling(lookback).mean()
rolling_std = data.rolling(lookback).std()
zscore = (data - rolling_mean) / rolling_std

# We'll need to know the next bar's open for execution. If you have opens, use them.
# Assume we have 'open' prices in a separate DataFrame or same structure.
opens = ...  # DataFrame of open prices, same index

# Backtest loop (simplified vectorized version with event simulation)
# We'll iterate through each bar and track positions.

positions = {}  # dict: asset -> (size, entry_z, side)
cash = capital
equity_curve = []

for i, (timestamp, row) in enumerate(data.iterrows()):
    current_time = timestamp.time()
    
    # 1. Check exits for existing positions (based on close of current bar)
    for asset, (size, entry_z_val, side) in list(positions.items()):
        current_z = zscore.loc[timestamp, asset]
        # Exit if z crosses 0 or hits stop
        if (side == 1 and current_z >= 0) or (side == -1 and current_z <= 0) or abs(current_z) >= stop_z:
            # Close at next bar's open
            # We'll handle execution in next iteration; for simplicity, we can record intent
            # But to avoid complexity, we can simulate that we close at this bar's close if we are using close prices.
            # Realistic: use next open. We'll need to look ahead.
            pass
    
    # 2. Check if it's a rebalance time (and we have enough bars to compute signals)
    if current_time in rebalance_times and i >= lookback:
        # Get Z-scores at this bar
        current_z = zscore.loc[timestamp]
        
        long_candidates = current_z[current_z < -entry_z].sort_values()
        short_candidates = current_z[current_z > entry_z].sort_values(ascending=False)
        
        n = min(len(long_candidates), len(short_candidates), 3)
        if n > 0:
            selected_longs = long_candidates.head(n).index.tolist()
            selected_shorts = short_candidates.head(n).index.tolist()
            
            # Close all existing positions (to reset)
            # (We'll need to execute at next open, so we can record that we will close)
            # For simplicity, we can just liquidate at current bar close? But we want to use next open.
            # Let's design: at rebalance signal, we will issue orders to close existing positions at next open,
            # and open new positions at next open.
            # So we need to store the target portfolio and then execute at next bar.
            pass
```

This is getting complex quickly. A more robust approach is to use an event-driven backtester. However, for a first pass, we can **simplify by assuming we trade at the close of the signal bar** (i.e., immediate execution). This introduces a slight look-ahead bias but is acceptable for initial screening. Then we can refine with next-bar execution later.

Given the complexity, I recommend using an existing backtesting library like `backtrader` or `vectorbt` to speed up development. But for learning, custom code is fine.

---

## 5. Important Considerations

### 5.1. Slippage and Costs
- **Stocks:** Use a fixed per-share cost (e.g., $0.005) plus SEC fee (~$0.000022 per $1). For simplicity, use 0.1% of notional for each trade (round trip).
- **Forex:** Spread cost. For EUR/USD, average spread ~0.5 pips ($5 per 100k). Include commission if applicable.
- **Metals:** Futures commissions (~$5 per contract round-turn) plus exchange fees. Also spread cost.
- **Crypto:** Taker fee ~0.1% on most exchanges.
- **Slippage:** Add a buffer of 0.5× the average spread or 0.05% for each trade.

### 5.2. Shorting Constraints
- Stocks: Need borrow availability; assume no hard-to-borrow issues for these liquid names. Possibly add a borrow cost (e.g., 0.3% annualized, negligible for day trades).
- Forex: Shorting is natural via going short the pair.
- Crypto: Shorting via futures or margin; assume zero cost.

### 5.3. Market Impact
For large capital, positions may move the market. Assume we trade small enough that impact is negligible. If capital is large, we need to cap position size relative to average daily volume.

### 5.4. Survivorship Bias
Ensure your historical data includes assets that may have been delisted or changed (not an issue for these major names). But for ETFs like SPY, it's fine.

### 5.5. Look-Ahead Bias
- Do not use future data to compute rolling stats. Our implementation using `.rolling()` on historical data is fine if we shift results appropriately. But when backtesting, we must ensure that at each bar we only use information up to that bar.
- The Z-score at bar `t` uses data from `t-lookback+1` to `t`. That's fine because at bar `t`, we know those prices. However, we then decide to trade at the close of bar `t`. In reality, we would trade at `t+1` open. So to be realistic, we should shift signals by one bar.

### 5.6. Risk Management
- Daily loss limit: Optional. Could stop trading if drawdown exceeds a threshold.
- Correlation check: Ensure positions are not overly concentrated in one sector; but with fully flexible selection, you might occasionally have 3 crypto longs and 3 stock shorts. That's okay as long as risk is balanced.

---

## 6. Performance Metrics to Report

After backtest, compute:
- **Annualized Return**
- **Annualized Volatility**
- **Sharpe Ratio** (risk-free rate = 0 for simplicity)
- **Maximum Drawdown** (percentage and duration)
- **Win Rate** (percentage of profitable trades)
- **Profit Factor** (gross profit / gross loss)
- **Average Hold Time**
- **Average Turnover** (daily)
- **Market Beta** (regress daily returns against SPY)
- **Monthly/Yearly returns**
- **Equity curve**

Also, run sensitivity analysis on:
- Lookback periods (30, 36, 40)
- Entry thresholds (1.5, 2.0, 2.5)
- Stop levels (3.0, 3.5, 4.0)
- Number of positions (2, 3, 4)
- Rebalance frequency (1h, 2h, 3h)

---

## 7. Next Steps

1. **Acquire data** for all 15 assets (5-min bars) for at least 2 years.
2. **Implement the backtest** in Python (or your preferred tool) using the vectorized approach with next-bar execution.
3. **Run initial backtest** without costs to see if the strategy has edge.
4. **Add costs** and re-evaluate.
5. **Optimize parameters** carefully (avoid overfitting by using cross-validation or out-of-sample periods).
6. **Paper trade** the strategy live for a month to observe real-time behavior.


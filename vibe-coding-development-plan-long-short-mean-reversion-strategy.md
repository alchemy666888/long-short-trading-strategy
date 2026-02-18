This plan outlines an iterative, AI-assisted (vibe coding) approach to implementing and backtesting the intraday mean-reversion strategy described in the attached document. The goal is to rapidly prototype, test, and refine the strategy using Python, leveraging modern libraries and AI tools to accelerate development.

## Overview of Vibe Coding Approach

- **Iterative & Exploratory:** Start with a minimal viable backtest and progressively add features. Each iteration produces a runnable script and visual outputs.
- **AI-Assisted Development:** Use GitHub Copilot, ChatGPT, or similar tools to generate code snippets, debug, and refactor quickly.
- **Test-Driven Mindset:** Write small tests or assertions for critical functions (e.g., Z-score calculation, position sizing) to catch errors early.
- **Continuous Feedback:** Run backtests frequently, plot equity curves, and monitor metrics after each major change.

---

## Phase 1: Data Acquisition & Preparation

**Objective:** Obtain clean, aligned 5-minute OHLCV data for all 15 assets, covering at least 2–3 years.

### Steps
1. **Identify Data Sources**
   - **Stocks (TSLA, MCD, NVDA, GOOG, SPY):** Yahoo Finance, Alpaca, Polygon (free tiers may have limitations; consider using `yfinance` for quick start).
   - **Forex (EUR/USD, AUD/USD):** OANDA API, TrueFX, or `yfinance` (forex data may be sparse; consider using `pandas_datareader`).
   - **Metals (Gold, Silver, Copper):** Continuous futures from Yahoo Finance (symbols GC=F, SI=F, HG=F) or Quandl.
   - **Crypto (BTC, ETH, SOL, XRP):** Binance, Coinbase via CCXT library or `yfinance` (e.g., BTC-USD).
2. **Download & Store Data**
   - Write a script to download 5-minute data for each asset.
   - Handle timezone conversion to Eastern Time (ET).
   - For futures, ensure proper rollover handling (or use continuous contracts).
   - Save raw data in Parquet/CSV format with consistent naming.
3. **Data Alignment & Cleaning**
   - Resample to 5-minute bars if necessary (e.g., forex may have irregular ticks).
   - Forward-fill missing bars during trading hours (but do not invent data).
   - For stocks, only keep data within market hours (9:30–16:00 ET) and align with other assets.
   - Create a single wide-format DataFrame with datetime index and columns for each asset's close price (also open/high/low if needed).
4. **Quick Validation**
   - Plot a few assets to ensure data looks correct.
   - Check for large gaps or outliers.

**Tools:** `yfinance`, `pandas`, `ccxt`, `pytz`, `requests`, `tqdm`.

**AI Prompt Ideas:**
- “Write a Python function to download 5-minute historical data for a list of stock tickers using yfinance, handling timezone and resampling.”
- “Generate code to align multiple time series with different timestamps to a common 5-minute grid.”

---

## Phase 2: Core Strategy Logic (Signal Generation)

**Objective:** Implement Z-score calculation, entry/exit conditions, and position sizing logic.

### Steps
1. **Compute Rolling Statistics**
   - For each asset, calculate 36-period rolling mean and standard deviation of close prices.
   - Use `pandas.DataFrame.rolling()` with `min_periods=1` to allow early values (but note that signals before 36 bars are unreliable; we'll filter later).
2. **Calculate Z-Score**
   - `zscore = (close - rolling_mean) / rolling_std`
   - Handle division by zero (set Z-score to NaN when std=0).
3. **Identify Entry Signals at Rebalance Times**
   - Define rebalance times: `["10:00", "12:00", "14:00"]` as Python `time` objects.
   - For each rebalance timestamp, get the latest Z-score for each asset.
   - Filter candidates: long if Z < -2.0, short if Z > +2.0.
   - Rank and select top N (N = min(3, #longs, #shorts)).
4. **Position Sizing (Equal Risk)**
   - Compute rolling standard deviation of 5-minute returns (percentage) for each asset over the same 36-period window.
   - At rebalance, for selected assets, allocate risk equally:
     - Let total risk budget = 1% of capital (example). Each position gets `risk_budget / (2 * N)` (since longs and shorts are balanced).
     - Position size (in dollars) = `position_risk / asset_volatility` (where volatility is the 36-period std of returns, annualized or per-period; simplest: use the std of returns over the lookback as a proxy for expected move).
     - Convert to units: `units = position_size / current_price`.
   - For shorts, units will be negative.
5. **Exit Conditions**
   - Continuously monitor positions: if Z-score crosses 0 or exceeds stop threshold (±3.5), close at next bar's open.
   - Force close all positions at 15:55 ET.

**Tools:** `pandas`, `numpy`, `datetime`.

**AI Prompt Ideas:**
- “Create a function that given a DataFrame of close prices, returns a DataFrame of Z-scores using a rolling window of 36 periods.”
- “Write a function to select top N long and short candidates based on Z-score thresholds, ensuring equal counts.”
- “Implement equal risk position sizing using rolling volatility.”

---

## Phase 3: Backtesting Engine (Vectorized with Event Simulation)

**Objective:** Simulate trading over historical data, tracking portfolio equity and trades.

### Steps
1. **Design Portfolio State**
   - Maintain a DataFrame of positions (asset, units, entry price, entry time, side).
   - Keep a cash balance (starting capital).
   - Track daily equity (cash + market value of positions).
2. **Iterate Bar by Bar (or Vectorized with Shift)**
   - **Approach A (Vectorized with next-bar execution):** Create signal DataFrames shifted by one bar to represent execution at next open. This is simpler but may miss intra-bar exits.
   - **Approach B (Event-driven loop):** Loop through each timestamp, check exits first, then check rebalance times. Execute trades at next open (requires looking ahead one bar). This is more accurate but slower.
   - For vibe coding, start with Approach A (vectorized) to get quick results, then refine to event-driven.
3. **Simulate Trades**
   - At each execution point (rebalance or exit), use the open price of the next bar.
   - Calculate transaction costs (slippage + commissions) as a percentage of notional or fixed per share.
   - Update positions and cash.
4. **Record Trades & Equity**
   - Log each fill (time, asset, side, price, units, cost).
   - Compute daily portfolio value.

**Tools:** `pandas`, `numpy`. For event-driven, consider `backtrader` or `vectorbt` to speed up.

**AI Prompt Ideas:**
- “Generate a backtesting loop that processes a DataFrame of signals and executes trades at next open, with transaction costs.”
- “How to simulate position tracking and equity curve in pandas?”

---

## Phase 4: Performance Analysis & Visualization

**Objective:** Compute key metrics and generate plots to evaluate strategy.

### Steps
1. **Compute Returns**
   - Daily portfolio returns (percentage).
   - Benchmark: SPY buy-and-hold (or just compare to risk-free).
2. **Metrics**
   - Annualized return, volatility, Sharpe ratio (0% risk-free).
   - Maximum drawdown (with duration).
   - Win rate, profit factor, average hold time.
   - Turnover (daily % traded).
   - Market beta (regress daily returns against SPY returns).
3. **Visualizations**
   - Equity curve (log scale) with drawdown shading.
   - Rolling Sharpe (6-month window).
   - Monthly returns heatmap.
   - Distribution of trade returns.
   - Position concentration over time.
4. **Sensitivity Analysis** (initial exploration)
   - Vary lookback (30, 36, 40), entry (1.5, 2.0, 2.5), stop (3.0, 3.5, 4.0), and number of positions (2,3,4).
   - Run backtest for each combination and compare metrics (use a grid search).

**Tools:** `matplotlib`, `seaborn`, `plotly`, `empyrical` (optional).

**AI Prompt Ideas:**
- “Write a function to calculate all common performance metrics from a series of portfolio returns and a list of trades.”
- “Plot an equity curve with drawdown using matplotlib.”

---

## Phase 5: Robustness Checks & Refinements

**Objective:** Validate strategy under different conditions and avoid overfitting.

### Steps
1. **Out-of-Sample Testing**
   - Reserve last 6 months of data for final validation.
   - Do not use OOS data for parameter tuning.
2. **Walk-Forward Analysis**
   - Optimize parameters on rolling in-sample periods and test on subsequent out-of-sample periods.
3. **Monte Carlo Simulation**
   - Randomly shuffle trade outcomes to assess distribution of equity curves.
4. **Stress Tests**
   - Identify worst periods (e.g., COVID crash, crypto crash) and examine behavior.
   - Add a volatility filter (e.g., skip trading if VIX > 30) and test.
5. **Market Neutrality Check**
   - Regress daily P&L against SPY and sector ETFs (XLK, XLF, etc.).
   - Ensure beta near zero.
6. **Transaction Cost Sensitivity**
   - Double costs and see if strategy remains profitable.

**AI Prompt Ideas:**
- “Implement a walk-forward optimization for a trading strategy in Python.”
- “Perform a Monte Carlo simulation by resampling trade returns to generate alternative equity curves.”

---

## Phase 6: Paper Trading & Live Deployment Considerations

**Objective:** Prepare for real-time simulation and eventual live trading.

### Steps
1. **Paper Trading Interface**
   - Use a broker API (Alpaca, Interactive Brokers) to run the strategy in real-time with paper money.
   - Modify backtest code to handle live data feeds and order execution.
2. **Risk Management Additions**
   - Add daily loss limit (e.g., stop trading if drawdown > 2%).
   - Implement position limits based on volume.
3. **Infrastructure**
   - Schedule script to run during market hours (e.g., using cron or cloud function).
   - Logging and alerting (email/SMS on errors or large trades).
4. **Start Small**
   - Begin with minimal capital to validate real-world execution.

**Tools:** `alpaca-trade-api`, `ib_insync`, `schedule`, `logging`.

**AI Prompt Ideas:**
- “Write a Python script that connects to Alpaca paper trading API and places orders based on a simple strategy.”

---

## Milestones & Success Criteria

| Milestone | Deliverable | Time Estimate |
|-----------|-------------|---------------|
| **Phase 1** | Clean, aligned 5-minute dataset for all assets | 2–3 days |
| **Phase 2** | Functions for Z-score, signal selection, position sizing | 1–2 days |
| **Phase 3** | Working backtest (vectorized) with equity curve | 2–3 days |
| **Phase 4** | Performance report with key metrics and plots | 1–2 days |
| **Phase 5** | Sensitivity analysis and robustness tests | 2–3 days |
| **Phase 6** | Paper trading script and one week of live simulation | 3–5 days |

**Success Criteria:**
- Sharpe ratio > 1.5 (after costs) in-sample.
- Maximum drawdown < 10%.
- Market beta < 0.2.
- Strategy holds up in out-of-sample period.

---

## Tools & Libraries Summary

- **Data:** `yfinance`, `ccxt`, `pandas-datareader`, `requests`
- **Manipulation:** `pandas`, `numpy`, `pytz`
- **Backtesting:** `vectorbt` (fast vectorized), `backtrader` (event-driven) – or custom code
- **Visualization:** `matplotlib`, `seaborn`, `plotly`
- **Performance:** `empyrical`, `pyfolio` (optional)
- **Live Trading:** `alpaca-trade-api`, `ib_insync`

---

## Continuous Improvement Loop

- After each phase, review results with AI assistant to identify bugs or enhancements.
- Use AI to suggest alternative implementations (e.g., different volatility estimators, dynamic thresholds).
- Keep a changelog of experiments and outcomes.

This vibe coding plan ensures rapid iteration while maintaining a structured path toward a robust intraday mean-reversion strategy. Let’s start coding!
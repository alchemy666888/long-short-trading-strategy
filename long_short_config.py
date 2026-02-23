ASSETS = {
    # Stocks – use Polygon.io as primary source (5-minute bars)
    "TSLA": {
        "provider": "polygon",
        "polygon_ticker": "TSLA",
        "asset_class": "stock",
    },
    "MCD": {
        "provider": "polygon",
        "polygon_ticker": "MCD",
        "asset_class": "stock",
    },
    "NVDA": {
        "provider": "polygon",
        "polygon_ticker": "NVDA",
        "asset_class": "stock",
    },
    "GOOG": {
        "provider": "polygon",
        "polygon_ticker": "GOOG",
        "asset_class": "stock",
    },
    "SPY": {
        "provider": "polygon",
        "polygon_ticker": "SPY",
        "asset_class": "stock",
    },
    # Forex (Yahoo Finance symbols)
    "EURUSD": {
        "provider": "yahoo",
        "yf_symbol": "EURUSD=X",
        "asset_class": "forex",
        "interval": "5m",
        "period": "60d",
    },
    "AUDUSD": {
        "provider": "yahoo",
        "yf_symbol": "AUDUSD=X",
        "asset_class": "forex",
        "interval": "5m",
        "period": "60d",
    },
    # Metals (continuous futures on Yahoo Finance)
    "GOLD": {
        "provider": "yahoo",
        "yf_symbol": "GC=F",
        "asset_class": "metal",
        "interval": "5m",
        "period": "60d",
    },
    "SILVER": {
        "provider": "yahoo",
        "yf_symbol": "SI=F",
        "asset_class": "metal",
        "interval": "5m",
        "period": "60d",
    },
    "COPPER": {
        "provider": "yahoo",
        "yf_symbol": "HG=F",
        "asset_class": "metal",
        "interval": "5m",
        "period": "60d",
    },
    # Crypto (USD pairs on Yahoo Finance)
    "BTC": {
        "provider": "polygon",
        "polygon_ticker": "X:BTCUSD",
        "asset_class": "crypto",
    },
    "ETH": {
        "provider": "polygon",
        "polygon_ticker": "X:ETHUSD",
        "asset_class": "crypto",
    },
    "SOL": {
        "provider": "polygon",
        "polygon_ticker": "X:SOLUSD",
        "asset_class": "crypto",
    },
    "XRP": {
        "provider": "polygon",
        "polygon_ticker": "X:XRPUSD",
        "asset_class": "crypto",
    },
}

CAPITAL = 1_000_000

# Per-side transaction cost assumptions by asset class (in bps of notional).
# These are intentionally lower than a flat 10 bps so the model is closer to
# liquid-instrument intraday execution, while still conservative for crypto.
TRANSACTION_COST_BPS_BY_CLASS = {
    "stock": 2.0,
    "forex": 1.0,
    "metal": 2.0,
    "crypto": 6.0,
}
DEFAULT_TRANSACTION_COST_BPS = 4.0

TRADING_WINDOW_START = "09:30"
TRADING_WINDOW_END = "16:00"
REBALANCE_TIMES = ["10:00", "12:00", "14:00"]

# Signal/risk parameters
LOOKBACK = 36
ENTRY_Z = 2.2
EXIT_Z = 0.0
STOP_Z = 3.8
MAX_POSITIONS_PER_SIDE = 3
MAX_POSITIONS_PER_CLASS_PER_SIDE = 1
TOTAL_RISK_BUDGET_FRACTION = 0.01
MAX_GROSS_LEVERAGE = 3.0
SIGMA_FLOOR = 1e-4

# Regime filter (SPY realized-volatility z-score).
REGIME_FILTER_ENABLED = True
REGIME_VOL_LOOKBACK_BARS = 78
REGIME_BASELINE_LOOKBACK_BARS = 1560
REGIME_VOL_Z_MAX = 2.0

# Backtest date window (inclusive dates, US/Eastern)
BACKTEST_START_DATE = "2025-06-01"
BACKTEST_END_DATE = "2026-01-31"

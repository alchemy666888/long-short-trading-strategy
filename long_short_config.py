from __future__ import annotations

ASSETS = {
    # Stocks
    "TSLA": {"provider": "polygon", "polygon_ticker": "TSLA", "asset_class": "stock"},
    "MCD": {"provider": "polygon", "polygon_ticker": "MCD", "asset_class": "stock"},
    "NVDA": {"provider": "polygon", "polygon_ticker": "NVDA", "asset_class": "stock"},
    "GOOG": {"provider": "polygon", "polygon_ticker": "GOOG", "asset_class": "stock"},
    "SPY": {"provider": "polygon", "polygon_ticker": "SPY", "asset_class": "stock"},
    # FX
    "EURUSD": {
        "provider": "polygon",
        "polygon_ticker": "C:EURUSD",
        "asset_class": "forex",
    },
    "AUDUSD": {
        "provider": "polygon",
        "polygon_ticker": "C:AUDUSD",
        "asset_class": "forex",
    },
    # Metals
    "GOLD": {
        "provider": "polygon",
        "polygon_ticker": "C:XAUUSD",
        "asset_class": "metal",
    },
    "SILVER": {
        "provider": "polygon",
        "polygon_ticker": "C:XAGUSD",
        "asset_class": "metal",
    },
    "COPPER": {
        "provider": "polygon",
        "polygon_ticker": "C:XCUUSD",
        "asset_class": "metal",
    },
    # Crypto
    "BTC": {"provider": "polygon", "polygon_ticker": "X:BTCUSD", "asset_class": "crypto"},
    "ETH": {"provider": "polygon", "polygon_ticker": "X:ETHUSD", "asset_class": "crypto"},
    "SOL": {"provider": "polygon", "polygon_ticker": "X:SOLUSD", "asset_class": "crypto"},
    "XRP": {"provider": "polygon", "polygon_ticker": "X:XRPUSD", "asset_class": "crypto"},
}

STRATEGY_VERSION = "v5"
PRIMARY_TIMEFRAME = "1D"
EXEC_TIMEFRAME = "4H"
REGIME_TIMEFRAME = "1W"

BACKTEST_START_DATE = "2025-06-01"
BACKTEST_END_DATE = "2026-01-31"
CAPITAL = 1_000_000.0
MARKET_PROXY_ASSET = "SPY"

TRANSACTION_COST_BPS_BY_CLASS = {
    "stock": 2.0,
    "forex": 1.0,
    "metal": 2.0,
    "crypto": 6.0,
}
DEFAULT_TRANSACTION_COST_BPS = 4.0

V5_WEEKLY_WINDOWS = {
    "ret_26w": 26,
    "ret_52w": 52,
    "ma_fast": 20,
    "ma_slow": 40,
}
V5_DAILY_WINDOWS = {
    "ret_5d": 5,
    "ret_20d": 20,
    "ret_60d": 60,
    "ret_120d": 120,
}

EWMA_VOL_HALFLIFE_DAYS = 20
VOL_FLOOR = 1e-4
SCORE_CLIP = 3.0

REGIME_RISK_ON_THRESHOLD = 0.25
REGIME_RISK_OFF_THRESHOLD = -0.25
REGIME_GROSS_CAP_BY_STATE = {
    "RISK_ON": 1.8,
    "NEUTRAL": 1.2,
    "RISK_OFF": 0.8,
}
REGIME_SIDE_TILT_BY_STATE = {
    "RISK_ON": 0.10,
    "NEUTRAL": 0.00,
    "RISK_OFF": -0.10,
}

PANIC_RETURN_LOOKBACK_DAYS = 20
PANIC_VOL_Z_THRESHOLD = 1.5
PANIC_MOMENTUM_MULTIPLIER = 0.5
PANIC_GROSS_CAP = 1.0
PANIC_ENTRY_WIDEN_MULTIPLIER = 1.25

BREADTH_MIN_ACTIVE_ASSETS = 10
BREADTH_MIN_CATEGORIES = 3
BREADTH_MAX_CATEGORY_SHARE = 0.45

PORTFOLIO_DOLLAR_NEUTRAL_TOL = 0.03
GROSS_LEVERAGE_FLOOR = 0.8
NAME_WEIGHT_CAP = 0.10
CATEGORY_GROSS_CAP = 0.30
DAILY_TURNOVER_CAP = 0.15
NO_TRADE_BAND = 0.0025
PARTIAL_REBALANCE_MIN_STEP = 0.50
PARTIAL_REBALANCE_MAX_STEP = 0.70
MIN_HOLD_DAYS = 3
TIME_STOP_DAYS = 15

VOL_TARGET_ANNUAL = 0.10
VOL_TARGET_SCALE_MIN = 0.6
VOL_TARGET_SCALE_MAX = 1.2
RISK_OFF_VOL_SCALE_CAP = 0.85

EXEC_WINDOWS_PER_DAY = 2
EXEC_QUALITY_FULL_THRESHOLD = 0.70
EXEC_QUALITY_HALF_THRESHOLD = 0.30
EXEC_MAX_DEFERS = 2
NET_EDGE_COST_MULTIPLE = 2.0

ATR_LOOKBACK_DAYS = 14
INITIAL_STOP_ATR_MULTIPLE = 2.0
TRAIL_ACTIVATION_R = 1.5
TRAIL_ATR_MULTIPLE = 1.0

DD_5D_TRIGGER = -0.04
DD_5D_GROSS_REDUCTION = 0.35
DD_5D_COOLDOWN_DAYS = 5
DD_20D_TRIGGER = -0.08
DD_20D_FLAT_DAYS = 5

CORR_LOOKBACK_DAYS = 60
CORR_GROSS_CAP = 0.8
CORR_TRIGGER = 0.75
HIGH_VOL_Z_TRIGGER = 2.0

QUALITY_DAILY_COVERAGE_THRESHOLD = 0.98
QUALITY_4H_COVERAGE_THRESHOLD = 0.95
QUALITY_FEATURE_COMPLETENESS_THRESHOLD = 0.97
QUALITY_BREADTH_MIN_ELIGIBLE = 10
QUALITY_BREADTH_MIN_CATEGORIES = 3
QUALITY_BREADTH_MAX_CATEGORY_SHARE = 0.45

STRESS_MISSING_DATA_RATIO = 0.075
STRESS_LIQUIDITY_HAIRCUT = 0.70
STRESS_SHORT_BORROW_BPS_PER_DAY = 2.0

# v3 constants are intentionally kept for rollback and comparison studies.
V3_LEGACY = {
    "TRADING_WINDOW_START": "09:30",
    "TRADING_WINDOW_END": "16:00",
    "REBALANCE_TIMES": ["10:00", "12:00", "14:00"],
    "MAX_GROSS_LEVERAGE": 3.0,
}

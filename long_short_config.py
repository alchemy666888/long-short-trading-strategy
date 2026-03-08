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

STRATEGY_VERSION = "v6"
PRIMARY_TIMEFRAME = "1D"
EXEC_TIMEFRAME = "4H"
REGIME_TIMEFRAME = "1W"

BACKTEST_START_DATE = "2025-01-01"
BACKTEST_END_DATE = "2026-01-31"
CAPITAL = 1_000_000.0
BACKTEST_LEVERAGE_MULTIPLIER = 3.0
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

# v6 analysis-first contract
ANALYSIS_CUTOFF_HOUR_ET = 8
ANALYSIS_MIN_SOURCES_PER_CATALYST = 3
ANALYSIS_MIN_REPORT_RELIABILITY = 0.60
ANALYSIS_MIN_SCENARIO_CONFIDENCE = 0.40
ANALYSIS_MAX_THEME_SHARE = 0.35
ANALYSIS_EVENT_RISK_REDUCTION_MIN = 0.20
ANALYSIS_EVENT_RISK_REDUCTION_MAX = 0.40

ANALYSIS_NEWS_PATH = "data/news/news_events.jsonl"
ANALYSIS_MACRO_CALENDAR_PATH = "data/news/macro_calendar.csv"
ANALYSIS_REPORTS_DIR = "data/analysis/reports"
ANALYSIS_OVERLAYS_PATH = "data/analysis/overlays.pkl"
ANALYSIS_IDEAS_PATH = "data/analysis/ideas.pkl"
ANALYSIS_REPORT_SCHEMA_PATH = "schemas/analysis_report_v6.schema.json"
ANALYSIS_OVERLAY_SCHEMA_PATH = "schemas/analysis_overlay_v6.schema.json"

V6_OVERLAY_WEIGHTS = {
    "asset_catalyst": 0.20,
    "cross_asset_flow": 0.15,
    "macro_regime_beta": 0.10,
}
V6_RELIABILITY_SCALE_FLOOR = 0.50
V6_CONFLICT_CATALYST_THRESHOLD = 0.70
V6_CONFLICT_CAP_MULTIPLIER = 0.50
V6_SEVERE_UNCERTAINTY_GROSS_CAP = 1.0
V6_CRISIS_MACRO_THRESHOLD = -0.70
V6_CRISIS_LONG_REDUCTION = 0.30
V6_HIGH_BETA_CLASSES = {"stock", "crypto"}
V6_REPORT_GROSS_SCALE_BASE = 0.70
V6_REPORT_GROSS_SCALE_MULT = 0.30

V6_IDEA_MIN_ABS_SIGNAL = 1.0
V6_IDEA_SCORE_WEIGHTS = {
    "signal": 0.45,
    "asset_catalyst": 0.25,
    "scenario_confidence": 0.15,
    "report_reliability": 0.15,
}

BETA_BY_ASSET = {
    "TSLA": 1.20,
    "MCD": 0.70,
    "NVDA": 1.30,
    "GOOG": 1.10,
    "SPY": 1.00,
    "EURUSD": 0.50,
    "AUDUSD": 0.80,
    "GOLD": 0.20,
    "SILVER": 0.60,
    "COPPER": 0.90,
    "BTC": 1.50,
    "ETH": 1.60,
    "SOL": 1.80,
    "XRP": 1.70,
}

# v3 constants are intentionally kept for rollback and comparison studies.
V3_LEGACY = {
    "TRADING_WINDOW_START": "09:30",
    "TRADING_WINDOW_END": "16:00",
    "REBALANCE_TIMES": ["10:00", "12:00", "14:00"],
    "MAX_GROSS_LEVERAGE": 3.0,
}

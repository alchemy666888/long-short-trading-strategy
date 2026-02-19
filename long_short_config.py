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
TRANSACTION_COST_BPS = 10  # 0.1% per trade (round-trip approximated per side)

TRADING_WINDOW_START = "09:30"
TRADING_WINDOW_END = "16:00"
REBALANCE_TIMES = ["10:00", "12:00", "14:00"]

"""Central, typed configuration for the platform.

This module is the single source of truth for every tunable value the spec calls out as
"must be configurable": assets, timeframes, indicator parameters, target-generation
horizon/threshold, walk-forward windows, and backtest assumptions. Nothing downstream should
hardcode these — import them from here (or override via environment variables / a
``config/*.yaml`` file, once one exists, without changing this module's shape).

Phase 1 note: this file defines *structure and defaults only*. No indicator, feature, model,
or backtest code exists yet (those are later phases) — this module exists now so that later
phases have one place to plug into rather than inventing config ad hoc.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd


# ---------------------------------------------------------------------------
# 1. Assets
# ---------------------------------------------------------------------------
# The architecture is designed so new assets can be added by appending one entry here —
# nothing elsewhere should special-case a specific symbol.

class AssetClass(str, Enum):
    FOREX = "forex"
    CRYPTO = "crypto"
    METAL = "metal"


@dataclass(frozen=True)
class AssetConfig:
    code: str            # display code, e.g. "EUR/USD"
    yfinance_ticker: str  # data source ticker, e.g. "EURUSD=X"
    asset_class: AssetClass
    is_proxy: bool = False   # True when the ticker is a documented proxy, not the literal asset
    proxy_note: str = ""


ASSETS: dict[str, AssetConfig] = {
    "EURUSD": AssetConfig(
        code="EUR/USD",
        yfinance_ticker="EURUSD=X",
        asset_class=AssetClass.FOREX,
    ),
    "BTCUSD": AssetConfig(
        code="BTC/USD",
        yfinance_ticker="BTC-USD",
        asset_class=AssetClass.CRYPTO,
    ),
    "XAUUSD": AssetConfig(
        code="XAU/USD",
        yfinance_ticker="GC=F",
        asset_class=AssetClass.METAL,
        is_proxy=True,
        proxy_note=(
            "GC=F is COMEX gold futures, the standard free proxy for spot XAU/USD on "
            "yfinance. See docs/data_sources.md for the documented limitation."
        ),
    ),
}


# ---------------------------------------------------------------------------
# 2. Timeframes
# ---------------------------------------------------------------------------
# NOTE: yfinance realistically provides ~60 days of 15m history and ~730 days of 1h
# history, nowhere near the multi-year windows walk-forward validation needs. D1 is the
# multi-year backbone (Phase 2+); M15/H1/H4 are populated with whatever depth is actually
# available and must be labeled as limited-depth in any UI/report that shows them.
# See docs/data_sources.md for the full decision record.

class Timeframe(str, Enum):
    M15 = "M15"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"


TIMEFRAMES: tuple[Timeframe, ...] = (Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1)

# yfinance interval string + max lookback actually honored for each timeframe (documented,
# not enforced yet — enforcement happens in the Phase 2 ingestion module).
TIMEFRAME_DATA_DEPTH = {
    Timeframe.M15: {"yfinance_interval": "15m", "max_lookback_days": 60, "is_backbone": False},
    Timeframe.H1: {"yfinance_interval": "60m", "max_lookback_days": 730, "is_backbone": False},
    Timeframe.H4: {"yfinance_interval": "60m", "max_lookback_days": 730, "is_backbone": False},  # resampled from H1
    Timeframe.D1: {"yfinance_interval": "1d", "max_lookback_days": None, "is_backbone": True},
}

# A bar's timestamp is its OPEN time (standard OHLC convention) -- it is only "available"
# (fully observed, safe to use as a feature) at open + duration, i.e. its CLOSE time. This is
# the single source of truth for that duration, used by both the H1->H4 resampling (Phase 3)
# and every multi-timeframe as-of lookup (Phase 5) to avoid treating a still-forming bar as
# already closed.
BAR_DURATION: dict[Timeframe, pd.Timedelta] = {
    Timeframe.M15: pd.Timedelta(minutes=15),
    Timeframe.H1: pd.Timedelta(hours=1),
    Timeframe.H4: pd.Timedelta(hours=4),
    Timeframe.D1: pd.Timedelta(days=1),
}


# ---------------------------------------------------------------------------
# 3. Technical indicators — exactly five, per spec Section 3. Do not add more here
#    without an explicit spec change.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IndicatorConfig:
    ema_periods: tuple[int, ...] = (20, 50, 200)
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    bb_period: int = 20
    bb_std_dev: float = 2.0


INDICATORS = IndicatorConfig()


# ---------------------------------------------------------------------------
# 4. Prediction target (Section 5) — configurable horizon + volatility-adjusted threshold.
#    future_return = close[t+h] / close[t] - 1
#    BUY  if future_return >  threshold
#    SELL if future_return < -threshold
#    HOLD otherwise
#    threshold is expressed as a multiple of a rolling volatility measure (e.g. ATR% or
#    rolling std of returns) rather than a fixed number, so it adapts per asset/timeframe
#    and avoids arbitrary cutoffs / excessive class imbalance. Exact formula is implemented
#    in Phase 6 (target generation) — this only fixes the configurable knobs.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TargetConfig:
    horizon_bars: int = 12          # forward horizon, in bars of the timeframe being labeled
    volatility_lookback: int = 20   # bars used to estimate local volatility for the threshold
    volatility_multiplier: float = 0.5  # threshold = volatility_multiplier * rolling volatility


TARGET = TargetConfig()


# ---------------------------------------------------------------------------
# 5. Walk-forward validation windows (Section 10) — exact dates configurable.
#    Expanding-window scheme by default; override via env or a future config file.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: str
    train_end: str
    test_start: str
    test_end: str


DEFAULT_WALK_FORWARD_WINDOWS: tuple[WalkForwardWindow, ...] = (
    WalkForwardWindow("2021-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    WalkForwardWindow("2021-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    WalkForwardWindow("2021-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    WalkForwardWindow("2021-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
)


# ---------------------------------------------------------------------------
# 6. Backtest assumptions (Section 11) — all configurable.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 10_000.0
    position_size_pct: float = 0.10   # fraction of equity risked per trade
    transaction_cost_pct: float = 0.0005  # 5 bps per side
    spread_pips: dict[str, float] = field(default_factory=lambda: {
        "EURUSD": 1.0, "BTCUSD": 0.0, "XAUUSD": 0.3,
    })
    stop_loss_atr_multiplier: float = 1.5
    take_profit_atr_multiplier: float = 3.0


BACKTEST = BacktestConfig()


# ---------------------------------------------------------------------------
# 6b. Market regime detection (Section 6) — five labels, rule-based on trend
#     strength + volatility + EMA relationships + ATR, all using only past/current
#     bars. Thresholds configurable, not hardcoded in the detector.
# ---------------------------------------------------------------------------

class RegimeLabel(str, Enum):
    BULLISH_TRENDING = "Bullish Trending"
    BEARISH_TRENDING = "Bearish Trending"
    SIDEWAYS = "Sideways / Range-Bound"
    HIGH_VOLATILITY = "High Volatility"
    LOW_VOLATILITY = "Low Volatility"


@dataclass(frozen=True)
class RegimeConfig:
    trend_lookback_bars: int = 20        # bars used to measure the price move for trend strength
    volatility_lookback_bars: int = 100  # bars used to build each row's own recent volatility distribution
    trend_strength_threshold: float = 1.0    # in ATR-normalized units -- see regime/detector.py
    volatility_high_zscore: float = 1.0      # rolling z-score above which volatility is "High"
    volatility_low_zscore: float = -1.0      # rolling z-score below which volatility is "Low"


REGIME = RegimeConfig()


# ---------------------------------------------------------------------------
# 7. Models (Section 8) — exactly these four, per the spec.
# ---------------------------------------------------------------------------

class ModelName(str, Enum):
    LOGISTIC_REGRESSION = "logistic_regression"
    RANDOM_FOREST = "random_forest"
    SVM = "svm"
    XGBOOST = "xgboost"
    ENSEMBLE = "ensemble"


MODELS: tuple[ModelName, ...] = (
    ModelName.LOGISTIC_REGRESSION,
    ModelName.RANDOM_FOREST,
    ModelName.SVM,
    ModelName.XGBOOST,
)


# ---------------------------------------------------------------------------
# 8. Environment-derived settings (DB connection, JWT secret, etc.)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/market_intelligence",
    )
    jwt_secret: str = os.environ.get("JWT_SECRET", "dev-secret-change-me")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12
    environment: str = os.environ.get("APP_ENV", "development")


SETTINGS = Settings()


# ---------------------------------------------------------------------------
# 9. Scope guardrail — surfaced in the README/dashboard, asserted in tests.
# ---------------------------------------------------------------------------

NOT_LIVE_TRADING_DISCLAIMER = (
    "This platform operates entirely on historical data for research and education. "
    "It is not a live trading system: it does not stream real-time market data, place "
    "orders, connect to a broker, or execute trades. Predictions are not financial advice "
    "and do not guarantee future performance."
)

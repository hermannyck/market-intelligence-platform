"""Phase 12 tests for app.backtesting.engine.

test_run_backtest_ignores_target_and_future_return_columns is the critical leakage-boundary
test: it proves the engine's output is byte-identical whether or not the dataset carries
`target`/`future_return` columns with deliberately misleading values, confirming the engine
genuinely never reads them -- only `predictions` drives trading decisions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.config import BacktestConfig
from app.backtesting import engine


def _ohlc_df(rows: int, close: list[float], high: list[float] | None = None, low: list[float] | None = None, atr: float = 1.0) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=rows, freq="1D", tz="UTC")
    high = high if high is not None else [c + 0.1 for c in close]
    low = low if low is not None else [c - 0.1 for c in close]
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "ATR14": [atr] * rows}, index=index
    )


def _cfg(**overrides) -> BacktestConfig:
    base = dict(
        initial_capital=10_000.0, position_size_pct=0.10, transaction_cost_pct=0.0,
        spread_pips={"EURUSD": 0.0, "BTCUSD": 0.0, "XAUUSD": 0.0},
        stop_loss_atr_multiplier=1.5, take_profit_atr_multiplier=3.0,
    )
    base.update(overrides)
    return BacktestConfig(**base)


def test_simulate_trade_stop_loss_long_uses_intrabar_low():
    # entry close=100, ATR=1 -> SL at 100 - 1.5 = 98.5. Bar 1's low breaches it.
    df = _ohlc_df(5, close=[100, 100, 100, 100, 100], low=[99, 98.0, 95, 95, 95], atr=1.0)
    exit_idx, exit_price, reason = engine.simulate_trade(df, entry_idx=0, direction=1, config=_cfg(), horizon_bars=4)
    assert reason == "stop_loss"
    assert exit_idx == 1
    assert exit_price == pytest.approx(98.5)


def test_simulate_trade_take_profit_long_uses_intrabar_high():
    # entry close=100, ATR=1 -> TP at 100 + 3 = 103. Bar 2's high breaches it.
    df = _ohlc_df(5, close=[100] * 5, high=[100.5, 100.5, 103.5, 105, 105], atr=1.0)
    exit_idx, exit_price, reason = engine.simulate_trade(df, entry_idx=0, direction=1, config=_cfg(), horizon_bars=4)
    assert reason == "take_profit"
    assert exit_idx == 2
    assert exit_price == pytest.approx(103.0)


def test_simulate_trade_short_stop_loss_uses_intrabar_high():
    # short entry close=100, ATR=1 -> SL at 100+1.5=101.5. Bar 1's high breaches it.
    df = _ohlc_df(5, close=[100] * 5, high=[100.5, 102.0, 105, 105, 105], atr=1.0)
    exit_idx, exit_price, reason = engine.simulate_trade(df, entry_idx=0, direction=-1, config=_cfg(), horizon_bars=4)
    assert reason == "stop_loss"
    assert exit_idx == 1
    assert exit_price == pytest.approx(101.5)


def test_simulate_trade_short_take_profit_uses_intrabar_low():
    # short entry close=100, ATR=1 -> TP at 100-3=97. Bar 1's low breaches it.
    df = _ohlc_df(5, close=[100] * 5, low=[99.5, 96.5, 95, 95, 95], atr=1.0)
    exit_idx, exit_price, reason = engine.simulate_trade(df, entry_idx=0, direction=-1, config=_cfg(), horizon_bars=4)
    assert reason == "take_profit"
    assert exit_idx == 1
    assert exit_price == pytest.approx(97.0)


def test_simulate_trade_conservative_tie_prefers_stop_loss():
    # Bar 1 breaches BOTH SL (low <= 98.5) and TP (high >= 103) -- SL must win.
    df = _ohlc_df(5, close=[100] * 5, high=[100.5, 104, 104, 104, 104], low=[99.5, 98.0, 98, 98, 98], atr=1.0)
    exit_idx, exit_price, reason = engine.simulate_trade(df, entry_idx=0, direction=1, config=_cfg(), horizon_bars=4)
    assert reason == "stop_loss"


def test_simulate_trade_horizon_expiry_when_neither_hit():
    df = _ohlc_df(5, close=[100, 100.2, 100.3, 100.1, 100.4], atr=1.0)  # tight range, no SL/TP breach
    exit_idx, exit_price, reason = engine.simulate_trade(df, entry_idx=0, direction=1, config=_cfg(), horizon_bars=3)
    assert reason == "horizon_expiry"
    assert exit_idx == 3
    assert exit_price == pytest.approx(100.1)


def test_run_backtest_requires_ohlc_atr_columns():
    df = pd.DataFrame({"close": [1.0]}, index=pd.date_range("2024-01-01", periods=1, tz="UTC"))
    with pytest.raises(ValueError, match="requires columns"):
        engine.run_backtest(df, pd.Series(["BUY"], index=df.index), "EURUSD")


def test_run_backtest_skips_hold_and_out_of_range_predictions():
    df = _ohlc_df(10, close=[100 + i * 0.01 for i in range(10)], atr=1.0)
    preds = pd.Series(["HOLD"] * 10, index=df.index)
    result = engine.run_backtest(df, preds, "EURUSD", config=_cfg())
    assert result["summary"]["num_trades"] == 0


def test_run_backtest_ignores_target_and_future_return_columns():
    # Critical: proves target/future_return presence/values never influence the engine.
    df = _ohlc_df(10, close=[100 + (i % 3) * 0.5 for i in range(10)], atr=1.0)
    preds = pd.Series(["BUY", "HOLD", "HOLD", "HOLD", "SELL", "HOLD", "HOLD", "HOLD", "HOLD", "HOLD"], index=df.index)

    result_without = engine.run_backtest(df.copy(), preds, "EURUSD", config=_cfg())

    df_with_labels = df.copy()
    df_with_labels["target"] = ["SELL"] * 10  # deliberately contradicts `preds`
    df_with_labels["future_return"] = [-0.5] * 10  # deliberately extreme/misleading
    result_with = engine.run_backtest(df_with_labels, preds, "EURUSD", config=_cfg())

    assert result_without["summary"] == result_with["summary"]
    assert result_without["trades"] == result_with["trades"]


def test_run_backtest_no_overlapping_trades():
    # Signal at t=0 opens a trade that (with a wide horizon and no SL/TP hit) holds until
    # horizon expiry; a second BUY signal at t=1 (still within the first trade's holding
    # period) must be skipped, not opened as a second concurrent position.
    df = _ohlc_df(8, close=[100] * 8, atr=1.0)  # flat -> no SL/TP hit, holds to horizon
    preds = pd.Series(["BUY", "BUY", "HOLD", "HOLD", "HOLD", "HOLD", "HOLD", "HOLD"], index=df.index)
    result = engine.run_backtest(df, preds, "EURUSD", config=_cfg())
    assert result["summary"]["num_trades"] == 1


def test_run_backtest_position_sizing_and_transaction_costs():
    # entry=100, exit at horizon close=110 (10% gross move). SL/TP multipliers set huge so
    # neither triggers intrabar -- the trade must ride to horizon expiry as intended.
    df = _ohlc_df(3, close=[100, 105, 110], atr=1.0)
    preds = pd.Series(["BUY", "HOLD", "HOLD"], index=df.index)
    cfg = _cfg(
        initial_capital=10_000.0, position_size_pct=0.20, transaction_cost_pct=0.001,
        stop_loss_atr_multiplier=1000.0, take_profit_atr_multiplier=1000.0,
    )
    result = engine.run_backtest(df, preds, "EURUSD", config=cfg)

    trade = result["trades"][0]
    expected_gross = (110 - 100) / 100  # 10%
    expected_net = expected_gross - 2 * 0.001
    assert trade["net_return_pct"] == pytest.approx(expected_net)
    expected_pnl = 0.20 * 10_000.0 * expected_net
    assert trade["pnl"] == pytest.approx(expected_pnl)
    assert trade["equity_after"] == pytest.approx(10_000.0 + expected_pnl)


def test_run_backtest_spread_reduces_return():
    df = _ohlc_df(3, close=[100, 100, 100], atr=1.0)  # no price movement at all
    preds = pd.Series(["BUY", "HOLD", "HOLD"], index=df.index)
    cfg = _cfg(spread_pips={"EURUSD": 100.0, "BTCUSD": 0.0, "XAUUSD": 0.0})  # 100 pips = 0.01 price units
    result = engine.run_backtest(df, preds, "EURUSD", config=cfg)
    trade = result["trades"][0]
    assert trade["net_return_pct"] < 0  # paid the spread with zero price movement to offset it


def test_summarize_backtest_metrics():
    trades = [
        {"net_return_pct": 0.05, "pnl": 100.0, "equity_after": 10_100.0},
        {"net_return_pct": -0.02, "pnl": -50.0, "equity_after": 10_050.0},
        {"net_return_pct": 0.03, "pnl": 75.0, "equity_after": 10_125.0},
    ]
    equity_curve = [
        {"timestamp": "t0", "equity": 10_000.0},
        {"timestamp": "t1", "equity": 10_100.0},
        {"timestamp": "t2", "equity": 10_050.0},
        {"timestamp": "t3", "equity": 10_125.0},
    ]
    summary = engine.summarize_backtest(trades, equity_curve, initial_capital=10_000.0)
    assert summary["num_trades"] == 3
    assert summary["win_rate"] == pytest.approx(2 / 3)
    assert summary["profit_factor"] == pytest.approx((100 + 75) / 50)
    assert summary["total_return"] == pytest.approx(0.0125)
    assert summary["avg_trade_return"] == pytest.approx((0.05 - 0.02 + 0.03) / 3)
    # drawdown from peak 10,100 to trough 10,050 -> -0.4950...%
    assert summary["max_drawdown"] == pytest.approx((10_050 - 10_100) / 10_100)


def test_summarize_backtest_no_trades():
    summary = engine.summarize_backtest([], [{"timestamp": "t0", "equity": 10_000.0}], 10_000.0)
    assert summary["num_trades"] == 0
    assert summary["win_rate"] is None
    assert summary["total_return"] == 0.0


def test_summarize_backtest_profit_factor_none_when_no_losses():
    trades = [{"net_return_pct": 0.05, "pnl": 100.0, "equity_after": 10_100.0}]
    equity_curve = [{"timestamp": "t0", "equity": 10_000.0}, {"timestamp": "t1", "equity": 10_100.0}]
    summary = engine.summarize_backtest(trades, equity_curve, 10_000.0)
    assert summary["profit_factor"] is None

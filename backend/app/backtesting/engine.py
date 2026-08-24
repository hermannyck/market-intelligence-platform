"""Phase 12: the real backtesting engine (spec Section 11).

**Distinct from Phase 8's simplified per-window trading diagnostic** (zero costs, no position
sizing, no stop-loss/take-profit, a position "closed" instantly at the already-known
`future_return`) — this is the realistic version: configurable initial capital, notional
position sizing, transaction costs, spread, ATR-based stop-loss/take-profit checked bar by bar
against real intrabar high/low, and a proper time-stepped equity curve.

**Uses PREDICTIONS, never the true target.** `run_backtest` takes a `predictions` Series (model
output at each historical point — typically `app.validation.walk_forward.generate_oos_predictions`,
itself walk-forward: each prediction comes from a model trained only on data before that test
window) as its BUY/HOLD/SELL signal source. It never reads `target`/`future_return` — those are
Phase 6 labels computed with knowledge of the future, and a real backtest execution engine must
not simulate trading against information a live system wouldn't have had (spec: "must use only
predictions generated from information available at that time").

**Position sizing is notional, not risk-based** — `position_size_pct` of current equity is
invested per trade, unleveraged. See `app.config.BacktestConfig.position_size_pct`'s docstring
and `docs/leakage_prevention.md`'s Phase 12 entry for why this was chosen over risk-based
sizing (which implies leverage that can compound into unrealistic equity swings).

**No overlapping trades** — only one position open at a time (spec Section 11 calls this a
"simplified" engine). A signal that fires while a position is already open is skipped.

**Intrabar stop-loss/take-profit** — checked bar by bar from entry using each subsequent bar's
high/low (not just close), up to `app.config.TARGET.horizon_bars` bars ahead (the same horizon
the model's own target was trained to predict over). If a single bar's range breaches both the
stop and the target, stop-loss is assumed to trigger first — a conservative, documented
assumption required by not having intrabar tick data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.config import BACKTEST, PIP_SIZE, TARGET, BacktestConfig

REQUIRED_COLUMNS = ("open", "high", "low", "close", "ATR14")


def simulate_trade(
    dataset: pd.DataFrame, entry_idx: int, direction: int, config: BacktestConfig, horizon_bars: int
) -> tuple[int, float, str]:
    """Scans forward from entry_idx+1 for a stop-loss/take-profit hit using each bar's
    high/low, up to horizon_bars ahead. Returns (exit_idx, exit_price, exit_reason)."""
    entry_price = dataset["close"].iloc[entry_idx]
    atr = dataset["ATR14"].iloc[entry_idx]
    stop_price = entry_price - direction * config.stop_loss_atr_multiplier * atr
    take_profit_price = entry_price + direction * config.take_profit_atr_multiplier * atr

    max_j = min(entry_idx + horizon_bars, len(dataset) - 1)
    for j in range(entry_idx + 1, max_j + 1):
        high, low = dataset["high"].iloc[j], dataset["low"].iloc[j]
        hit_sl = (low <= stop_price) if direction == 1 else (high >= stop_price)
        hit_tp = (high >= take_profit_price) if direction == 1 else (low <= take_profit_price)
        if hit_sl:
            return j, float(stop_price), "stop_loss"  # SL wins ties -- conservative, documented above
        if hit_tp:
            return j, float(take_profit_price), "take_profit"

    exit_idx = max_j if max_j > entry_idx else entry_idx
    return exit_idx, float(dataset["close"].iloc[exit_idx]), "horizon_expiry"


def _build_equity_curve(index: pd.DatetimeIndex, equity_by_time: dict, initial_capital: float) -> list[dict]:
    equity_series = pd.Series(index=index, dtype=float)
    if len(equity_series):
        equity_series.iloc[0] = initial_capital
    for ts, eq in equity_by_time.items():
        equity_series.loc[ts] = eq
    equity_series = equity_series.ffill().fillna(initial_capital)
    return [{"timestamp": str(ts), "equity": float(v)} for ts, v in equity_series.items()]


def summarize_backtest(trades: list[dict], equity_curve: list[dict], initial_capital: float) -> dict:
    n_trades = len(trades)
    if n_trades == 0:
        return {
            "num_trades": 0, "total_return": 0.0, "win_rate": None, "profit_factor": None,
            "sharpe_ratio": None, "max_drawdown": 0.0, "avg_trade_return": None,
            "final_equity": initial_capital,
        }

    returns = np.array([t["net_return_pct"] for t in trades])
    pnls = np.array([t["pnl"] for t in trades])
    final_equity = trades[-1]["equity_after"]
    total_return = (final_equity - initial_capital) / initial_capital

    wins, losses = pnls[pnls > 0], pnls[pnls < 0]
    win_rate = len(wins) / n_trades
    if len(losses) > 0 and losses.sum() != 0:
        profit_factor: float | None = float(wins.sum() / abs(losses.sum()))
    elif wins.sum() > 0:
        profit_factor = None  # undefined (no losing trades to divide by), not a fake "infinity"
    else:
        profit_factor = 0.0

    sharpe_ratio = float(returns.mean() / returns.std()) if returns.std() > 0 else None

    equity_values = np.array([e["equity"] for e in equity_curve])
    running_max = np.maximum.accumulate(equity_values)
    drawdown = (equity_values - running_max) / running_max
    max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0

    return {
        "num_trades": n_trades,
        "total_return": float(total_return),
        "win_rate": float(win_rate),
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "avg_trade_return": float(returns.mean()),
        "final_equity": float(final_equity),
    }


def run_backtest(
    dataset: pd.DataFrame, predictions: pd.Series, asset_key: str, config: BacktestConfig | None = None
) -> dict:
    """dataset: must have open/high/low/close/ATR14, sorted ascending by timestamp -- pass the
    full (not NaN-dropped) features dataset here, not `app.ml.models.prepare_dataset`'s output,
    since dropping rows with any-NaN feature would punch gaps in the continuous bar sequence
    this engine needs for accurate intrabar stop-loss/take-profit scanning.
    predictions: BUY/HOLD/SELL per timestamp -- only timestamps present here are eligible to
    open a trade; HOLD and any timestamp missing from `predictions` are simply skipped.
    """
    config = config or BACKTEST
    missing = [c for c in REQUIRED_COLUMNS if c not in dataset.columns]
    if missing:
        raise ValueError(f"run_backtest requires columns {missing}.")
    if not dataset.index.is_monotonic_increasing:
        raise ValueError("dataset must be sorted ascending by timestamp.")

    predictions = predictions.sort_index()
    index_lookup = {ts: pos for pos, ts in enumerate(dataset.index)}
    horizon_bars = TARGET.horizon_bars
    pip_size = PIP_SIZE.get(asset_key, 0.0001)
    spread_price_delta_per_unit_price = config.spread_pips.get(asset_key, 0.0) * pip_size

    equity = config.initial_capital
    trades: list[dict] = []
    equity_by_time: dict = {}
    next_available_idx = -1

    for ts, signal in predictions.items():
        if signal not in ("BUY", "SELL"):
            continue
        if ts not in index_lookup:
            continue
        entry_idx = index_lookup[ts]
        if entry_idx <= next_available_idx:
            continue  # a position is already open through this bar -- no overlapping trades

        direction = 1 if signal == "BUY" else -1
        entry_price = dataset["close"].iloc[entry_idx]
        atr = dataset["ATR14"].iloc[entry_idx]
        if pd.isna(atr) or atr <= 0 or pd.isna(entry_price) or entry_price <= 0:
            continue  # can't size a stop / no valid price -- skip this signal, no trade

        exit_idx, exit_price_raw, exit_reason = simulate_trade(dataset, entry_idx, direction, config, horizon_bars)

        entry_fill = entry_price + direction * (spread_price_delta_per_unit_price / 2)
        exit_fill = exit_price_raw - direction * (spread_price_delta_per_unit_price / 2)
        gross_return_pct = direction * (exit_fill - entry_fill) / entry_fill
        net_return_pct = gross_return_pct - 2 * config.transaction_cost_pct

        position_notional = config.position_size_pct * equity
        pnl = position_notional * net_return_pct
        equity += pnl

        trades.append(
            {
                "entry_time": str(dataset.index[entry_idx]),
                "exit_time": str(dataset.index[exit_idx]),
                "direction": signal,
                "entry_price": float(entry_price),
                "exit_price": float(exit_price_raw),
                "exit_reason": exit_reason,
                "net_return_pct": float(net_return_pct),
                "pnl": float(pnl),
                "equity_after": float(equity),
            }
        )
        equity_by_time[dataset.index[exit_idx]] = equity
        next_available_idx = exit_idx

    equity_curve = _build_equity_curve(dataset.index, equity_by_time, config.initial_capital)
    summary = summarize_backtest(trades, equity_curve, config.initial_capital)
    return {"trades": trades, "equity_curve": equity_curve, "summary": summary}

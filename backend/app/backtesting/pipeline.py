"""Phase 12 orchestration: get walk-forward out-of-sample predictions (Phase 8's
`generate_oos_predictions` — each prediction from a model trained only on data before that test
window), run the real backtest engine against them, save a report to `models/` — same
never-overwrite convention as every prior phase.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.backtesting.engine import run_backtest
from app.config import ASSETS, BACKTEST
from app.config import MODELS as ALL_MODEL_NAMES
from app.config import TIMEFRAMES, ModelName, Timeframe
from app.features.feature_engineering import find_latest_features
from app.validation.walk_forward import generate_oos_predictions

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"


@dataclass
class BacktestRunResult:
    asset_key: str
    timeframe: str
    model_name: str
    report_path: str
    summary: dict


def save_backtest_report(
    asset_key: str, timeframe: Timeframe, model_name: ModelName, result: dict, num_predictions: int
) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = MODELS_DIR / f"{asset_key}_{timeframe.value}_{model_name.value}_backtest_{stamp}.json"
    if path.exists():
        raise FileExistsError(f"{path} already exists; refusing to overwrite a backtest report.")

    report = {
        "asset_key": asset_key,
        "asset_code": ASSETS[asset_key].code,
        "timeframe": timeframe.value,
        "model_name": model_name.value,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "backtest_config": {
            "initial_capital": BACKTEST.initial_capital,
            "position_size_pct": BACKTEST.position_size_pct,
            "transaction_cost_pct": BACKTEST.transaction_cost_pct,
            "spread_pips": BACKTEST.spread_pips.get(asset_key),
            "stop_loss_atr_multiplier": BACKTEST.stop_loss_atr_multiplier,
            "take_profit_atr_multiplier": BACKTEST.take_profit_atr_multiplier,
        },
        "num_oos_predictions": num_predictions,
        "summary": result["summary"],
        "trades": result["trades"],
        "equity_curve": result["equity_curve"],
    }
    path.write_text(json.dumps(report, indent=2))
    return path


def run_backtest_for_asset_timeframe_model(
    asset_key: str, timeframe: Timeframe, model_name: ModelName
) -> BacktestRunResult:
    predictions = generate_oos_predictions(asset_key, timeframe, model_name)
    if predictions.empty:
        raise ValueError(
            f"No out-of-sample walk-forward predictions available for {asset_key} {timeframe.value} "
            f"{model_name.value} -- run app.validation.walk_forward first (or check data depth)."
        )

    features_df, _ = find_latest_features(asset_key, timeframe)
    result = run_backtest(features_df, predictions, asset_key)

    report_path = save_backtest_report(asset_key, timeframe, model_name, result, len(predictions))
    return BacktestRunResult(
        asset_key=asset_key,
        timeframe=timeframe.value,
        model_name=model_name.value,
        report_path=str(report_path),
        summary=result["summary"],
    )


def run_all_backtests(asset_keys: list[str] | None = None) -> list[dict]:
    asset_keys = asset_keys or list(ASSETS.keys())
    results = []
    for asset_key in asset_keys:
        for timeframe in TIMEFRAMES:
            for model_name in ALL_MODEL_NAMES:
                try:
                    r = run_backtest_for_asset_timeframe_model(asset_key, timeframe, model_name)
                    results.append(
                        {
                            "asset_key": r.asset_key,
                            "timeframe": r.timeframe,
                            "model_name": r.model_name,
                            "report_path": r.report_path,
                            "summary": r.summary,
                        }
                    )
                except (FileNotFoundError, ValueError) as exc:
                    results.append(
                        {
                            "asset_key": asset_key,
                            "timeframe": timeframe.value,
                            "model_name": model_name.value,
                            "error": str(exc),
                        }
                    )
    return results


if __name__ == "__main__":
    for r in run_all_backtests():
        if "error" in r:
            print(f"{r['asset_key']:<8} {r['timeframe']:<4} {r['model_name']:<20} FAILED: {r['error']}")
        else:
            s = r["summary"]
            tr = f"{s['total_return']*100:+.1f}%" if s["total_return"] is not None else "n/a"
            print(
                f"{r['asset_key']:<8} {r['timeframe']:<4} {r['model_name']:<20} "
                f"trades={s['num_trades']:<4} total_return={tr:<8} max_dd={s['max_drawdown']*100:.1f}%"
            )

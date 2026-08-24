import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Bar, BacktestResponse, MarketAnalysisResponse, TargetLabel, Trade } from "../api/types";
import { useApiData } from "../hooks/useApiData";
import { useSelection } from "../hooks/useSelection";
import AsyncState from "../components/AsyncState";
import SignalBadge from "../components/SignalBadge";
import CandlestickChart from "../charts/CandlestickChart";
import EquityCurveChart from "../charts/EquityCurveChart";

// How many of the most recent bars a market-analysis fetch needs to cover. Must exceed the
// FULL row count of every asset/timeframe combo's features file, not just its walk-forward
// test windows -- the backtest report's equity_curve is built over the entire dataset (see
// engine.py::_build_equity_curve), so a truncated `bars` fetch that's shorter than that full
// history would silently cut off earlier out-of-sample bars/trades while still showing their
// already-elapsed effect on equity, corrupting the replay's own numbers. The largest real
// combo (EUR/USD and BTC/USD H1) is ~17,300 rows -- checked directly against real data, not
// guessed.
const MARKET_ANALYSIS_LIMIT = 25000;
// Rolling window of bars shown in the candlestick chart at any one replay position -- a
// progressive "reveal" rather than the whole history at once.
const CHART_WINDOW = 80;
// How many of the most recent closed trades to list in the trade log.
const TRADE_LOG_LIMIT = 20;

const SPEED_OPTIONS = [
  { ms: 2000, label: "0.5x" },
  { ms: 1000, label: "1x" },
  { ms: 500, label: "2x" },
  { ms: 200, label: "4x" },
];

interface ReplayFrame {
  bar: Bar;
  signal: TargetLabel;
  equity: number | null;
  openedTrade: Trade | null;
  closedTrade: Trade | null;
}

/** Builds the replay timeline: only bars that carry a genuine walk-forward out-of-sample
 * signal are included (see the on-page note and docs/leakage_prevention.md's Phase 15 entry) --
 * this is a straight client-side join of two already-fetched, already-verified-leak-free
 * responses by timestamp, no new computation.
 *
 * The two responses format timestamps differently on the wire -- market-analysis's bars go
 * through pandas' own `to_json(date_format="iso")` (e.g. "2022-01-03T05:00:00.000Z"), while the
 * backtest report's signals/trades/equity_curve go through plain `str(pd.Timestamp)` (e.g.
 * "2022-01-03 05:00:00+00:00"). Same instant, different strings -- so every key below is
 * normalized to epoch milliseconds via `Date.parse` before joining, never compared as raw
 * strings. */
function ts(value: string): number {
  return Date.parse(value);
}

function buildFrames(market: MarketAnalysisResponse, backtest: BacktestResponse): ReplayFrame[] {
  // Defensive: a backtest report saved before Phase 15 won't have a "signals" field at all
  // (the "never overwrite" convention means old report files stay on disk as-is).
  const signalByTs = new Map((backtest.signals ?? []).map((s) => [ts(s.timestamp), s.signal]));
  const equityByTs = new Map(backtest.equity_curve.map((e) => [ts(e.timestamp), e.equity]));
  const openedByTs = new Map(backtest.trades.map((t) => [ts(t.entry_time), t]));
  const closedByTs = new Map(backtest.trades.map((t) => [ts(t.exit_time), t]));

  return market.bars
    .filter((b) => signalByTs.has(ts(b.timestamp)))
    .sort((a, b) => ts(a.timestamp) - ts(b.timestamp))
    .map((bar) => ({
      bar,
      signal: signalByTs.get(ts(bar.timestamp)) as TargetLabel,
      equity: equityByTs.get(ts(bar.timestamp)) ?? null,
      openedTrade: openedByTs.get(ts(bar.timestamp)) ?? null,
      closedTrade: closedByTs.get(ts(bar.timestamp)) ?? null,
    }));
}

export default function ReplayPage() {
  const { asset, timeframe, model } = useSelection();
  const marketState = useApiData<MarketAnalysisResponse>(
    () => api.marketAnalysis(asset, timeframe, MARKET_ANALYSIS_LIMIT) as Promise<MarketAnalysisResponse>,
    [asset, timeframe],
  );
  const backtestState = useApiData<BacktestResponse>(
    () => api.backtest(asset, timeframe, model) as Promise<BacktestResponse>,
    [asset, timeframe, model],
  );

  const frames = useMemo(() => {
    if (!marketState.data || !backtestState.data) return [];
    return buildFrames(marketState.data, backtestState.data);
  }, [marketState.data, backtestState.data]);

  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [intervalMs, setIntervalMs] = useState(1000);

  // A new asset/timeframe/model means a new frame set -- start the replay over rather than
  // pointing at a stale index into the previous combination's timeline.
  useEffect(() => {
    setIndex(0);
    setPlaying(false);
  }, [asset, timeframe, model]);

  useEffect(() => {
    if (!playing || frames.length === 0) return;
    const id = window.setInterval(() => {
      setIndex((i) => {
        if (i >= frames.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [playing, intervalMs, frames.length]);

  const loading = marketState.loading || backtestState.loading;
  const error = marketState.error || backtestState.error;
  const notFound = marketState.notFound || backtestState.notFound;

  const current = frames[index] as ReplayFrame | undefined;
  const windowStart = Math.max(0, index - CHART_WINDOW + 1);
  const visibleBars = frames.slice(windowStart, index + 1).map((f) => f.bar);
  const equitySoFar = frames
    .slice(0, index + 1)
    .filter((f) => f.equity !== null)
    .map((f) => ({ timestamp: f.bar.timestamp, equity: f.equity as number }));
  const tradesSoFar = frames
    .slice(0, index + 1)
    .map((f) => f.closedTrade)
    .filter((t): t is Trade => t !== null);

  function step(delta: number) {
    setPlaying(false);
    setIndex((i) => Math.min(Math.max(i + delta, 0), frames.length - 1));
  }

  return (
    <div>
      <div className="page-header">
        <h2>Historical Replay</h2>
        {current && <span className="timestamp">{new Date(current.bar.timestamp).toLocaleString()}</span>}
      </div>

      <AsyncState
        loading={loading}
        error={error}
        notFound={notFound}
        notFoundMessage="No backtest report found for this combination -- run app.backtesting.pipeline first (it depends on app.validation.walk_forward)."
      >
        {frames.length === 0 ? (
          <div className="empty-state">
            No genuinely out-of-sample bars are available to replay for this combination -- the
            walk-forward validator didn't resolve any test windows for it. See Model Lab for why.
          </div>
        ) : (
          <>
            <div className="replay-controls">
              <div className="replay-btn-row">
                <button onClick={() => step(-1)} disabled={index === 0}>
                  ⏮ Step back
                </button>
                <button className="primary" onClick={() => setPlaying((p) => !p)}>
                  {playing ? "⏸ Pause" : "▶ Play"}
                </button>
                <button onClick={() => step(1)} disabled={index >= frames.length - 1}>
                  Step forward ⏭
                </button>
                <button
                  onClick={() => {
                    setPlaying(false);
                    setIndex(0);
                  }}
                >
                  ⏹ Reset
                </button>
                <select value={intervalMs} onChange={(e) => setIntervalMs(Number(e.target.value))}>
                  {SPEED_OPTIONS.map((s) => (
                    <option key={s.ms} value={s.ms}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="replay-scrubber">
                <input
                  type="range"
                  min={0}
                  max={frames.length - 1}
                  value={index}
                  onChange={(e) => {
                    setPlaying(false);
                    setIndex(Number(e.target.value));
                  }}
                />
                <span className="replay-position">
                  Bar {index + 1} / {frames.length}
                </span>
              </div>
              <div className="stat-sub">
                Replay only steps through bars that carry a genuine walk-forward out-of-sample
                signal — exactly the periods a live system could honestly have been evaluated on.
                Periods used only to train a walk-forward window (never scored out-of-sample)
                aren't replayable. See <code>docs/leakage_prevention.md</code>'s Phase 15 entry.
              </div>
            </div>

            {current && (
              <div className="card-grid">
                <div className="card">
                  <h3>Close price</h3>
                  <div className="stat-value">{current.bar.close.toFixed(4)}</div>
                </div>
                <div className="card">
                  <h3>Model signal</h3>
                  <div className="stat-value" style={{ fontSize: "1.1rem" }}>
                    <SignalBadge label={current.signal} />
                  </div>
                </div>
                <div className="card">
                  <h3>Regime</h3>
                  <div className="stat-value" style={{ fontSize: "1.1rem" }}>
                    {(current.bar.regime as string | null) ?? "—"}
                  </div>
                </div>
                <div className="card">
                  <h3>Equity</h3>
                  <div className="stat-value">
                    {current.equity !== null ? `$${current.equity.toFixed(2)}` : "—"}
                  </div>
                </div>
              </div>
            )}

            {current && (current.openedTrade || current.closedTrade) && (
              <div className="replay-event-row" style={{ marginBottom: "1rem" }}>
                {current.openedTrade && (
                  <span className="badge badge-buy">
                    Trade opened: {current.openedTrade.direction} @ {current.openedTrade.entry_price.toFixed(4)}
                  </span>
                )}
                {current.closedTrade && (
                  <span className={`badge ${current.closedTrade.net_return_pct >= 0 ? "badge-buy" : "badge-sell"}`}>
                    Trade closed ({current.closedTrade.exit_reason}): {(current.closedTrade.net_return_pct * 100).toFixed(2)}%
                  </span>
                )}
              </div>
            )}

            <div className="chart-card">
              <h3>Price (last {visibleBars.length} bars)</h3>
              <CandlestickChart bars={visibleBars} />
            </div>

            <div className="chart-card">
              <h3>Equity so far</h3>
              <EquityCurveChart
                equityCurve={equitySoFar}
                initialCapital={backtestState.data?.backtest_config.initial_capital as number | undefined}
              />
            </div>

            <div className="chart-card">
              <h3>Trades closed so far ({tradesSoFar.length})</h3>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Entry</th>
                      <th>Exit</th>
                      <th>Direction</th>
                      <th>Exit reason</th>
                      <th>Net return</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tradesSoFar
                      .slice(-TRADE_LOG_LIMIT)
                      .reverse()
                      .map((t, i) => (
                        <tr key={i}>
                          <td>{new Date(t.entry_time).toLocaleDateString()}</td>
                          <td>{new Date(t.exit_time).toLocaleDateString()}</td>
                          <td>
                            <SignalBadge label={t.direction} />
                          </td>
                          <td>{t.exit_reason}</td>
                          <td style={{ color: t.net_return_pct >= 0 ? "var(--status-good)" : "var(--status-critical)" }}>
                            {(t.net_return_pct * 100).toFixed(2)}%
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
              {tradesSoFar.length === 0 && (
                <div className="stat-sub">No trades have closed yet at this point in the replay.</div>
              )}
            </div>
          </>
        )}
      </AsyncState>
    </div>
  );
}

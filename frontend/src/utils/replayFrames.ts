import type { Bar, BacktestResponse, MarketAnalysisResponse, TargetLabel, Trade } from "../api/types";

export interface ReplayFrame {
  bar: Bar;
  signal: TargetLabel;
  equity: number | null;
  openedTrade: Trade | null;
  closedTrade: Trade | null;
}

/** Builds the Historical Replay timeline (Phase 15): only bars that carry a genuine
 * walk-forward out-of-sample signal are included (see docs/leakage_prevention.md's Phase 15
 * entry) -- this is a straight client-side join of two already-fetched, already-verified-
 * leak-free responses by timestamp, no new computation.
 *
 * The two responses format timestamps differently on the wire -- market-analysis's bars go
 * through pandas' own `to_json(date_format="iso")` (e.g. "2022-01-03T05:00:00.000Z"), while the
 * backtest report's signals/trades/equity_curve go through plain `str(pd.Timestamp)` (e.g.
 * "2022-01-03 05:00:00+00:00"). Same instant, different strings -- a real bug caught during
 * Phase 15's live browser verification, when a naive string-keyed join silently matched
 * nothing. Every key below is normalized to epoch milliseconds via `Date.parse` before
 * joining, never compared as raw strings -- `replayFrames.test.ts` pins this behavior down so
 * it can't silently regress. */
export function ts(value: string): number {
  return Date.parse(value);
}

export function buildFrames(market: MarketAnalysisResponse, backtest: BacktestResponse): ReplayFrame[] {
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

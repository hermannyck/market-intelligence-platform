import { describe, expect, it } from "vitest";
import { buildFrames, ts } from "./replayFrames";
import type { BacktestResponse, Bar, MarketAnalysisResponse, Trade } from "../api/types";

// Minimal valid fixtures matching the real API response shapes (see api/types.ts). Kept
// deliberately small -- these tests exist to pin down the join logic itself, not to exercise
// every optional field.

function makeBar(timestamp: string, close = 100): Bar {
  return { timestamp, open: close, high: close, low: close, close };
}

function makeMarketAnalysis(bars: Bar[]): MarketAnalysisResponse {
  return {
    asset_key: "EURUSD",
    asset_code: "EUR/USD",
    timeframe: "D1",
    current_timestamp: bars[bars.length - 1]?.timestamp ?? "",
    current_price: bars[bars.length - 1]?.close ?? 0,
    bars,
    multi_timeframe_bias: {},
    regime: null,
  };
}

function makeTrade(overrides: Partial<Trade> = {}): Trade {
  return {
    entry_time: "2022-01-03 00:00:00+00:00",
    exit_time: "2022-01-05 00:00:00+00:00",
    direction: "BUY",
    entry_price: 100,
    exit_price: 101,
    exit_reason: "horizon_expiry",
    net_return_pct: 0.01,
    pnl: 10,
    equity_after: 10010,
    ...overrides,
  };
}

function makeBacktest(overrides: Partial<BacktestResponse> = {}): BacktestResponse {
  return {
    asset_key: "EURUSD",
    timeframe: "D1",
    model_name: "random_forest",
    backtest_config: { initial_capital: 10000 },
    summary: {
      num_trades: 0,
      total_return: 0,
      win_rate: null,
      profit_factor: null,
      sharpe_ratio: null,
      max_drawdown: 0,
      avg_trade_return: null,
      final_equity: 10000,
    },
    trades: [],
    equity_curve: [],
    signals: [],
    ...overrides,
  };
}

describe("ts", () => {
  it("normalizes pandas' to_json ISO format and str(pd.Timestamp) format to the same instant", () => {
    // The exact real-world pair that broke the naive string-keyed join during Phase 15's live
    // verification: same UTC instant, two different serializations.
    expect(ts("2022-01-03T05:00:00.000Z")).toBe(ts("2022-01-03 05:00:00+00:00"));
  });
});

describe("buildFrames", () => {
  it("joins bars to signals across the two different timestamp formats market-analysis and the backtest report actually use", () => {
    const market = makeMarketAnalysis([makeBar("2022-01-03T05:00:00.000Z", 1.1)]);
    const backtest = makeBacktest({ signals: [{ timestamp: "2022-01-03 05:00:00+00:00", signal: "BUY" }] });

    const frames = buildFrames(market, backtest);

    expect(frames).toHaveLength(1);
    expect(frames[0].signal).toBe("BUY");
    expect(frames[0].bar.close).toBe(1.1);
  });

  it("excludes bars with no matching out-of-sample signal (the whole point of Phase 15's leakage-safety design)", () => {
    const market = makeMarketAnalysis([
      makeBar("2022-01-01T00:00:00.000Z"), // no signal -- e.g. inside a training-only window
      makeBar("2022-01-02T00:00:00.000Z"), // has a signal
    ]);
    const backtest = makeBacktest({ signals: [{ timestamp: "2022-01-02 00:00:00+00:00", signal: "HOLD" }] });

    const frames = buildFrames(market, backtest);

    expect(frames).toHaveLength(1);
    expect(frames[0].bar.timestamp).toBe("2022-01-02T00:00:00.000Z");
  });

  it("sorts the resulting frames ascending by timestamp even when bars arrive out of order", () => {
    const market = makeMarketAnalysis([
      makeBar("2022-01-03T00:00:00.000Z"),
      makeBar("2022-01-01T00:00:00.000Z"),
      makeBar("2022-01-02T00:00:00.000Z"),
    ]);
    const backtest = makeBacktest({
      signals: [
        { timestamp: "2022-01-01 00:00:00+00:00", signal: "HOLD" },
        { timestamp: "2022-01-02 00:00:00+00:00", signal: "HOLD" },
        { timestamp: "2022-01-03 00:00:00+00:00", signal: "HOLD" },
      ],
    });

    const frames = buildFrames(market, backtest);

    expect(frames.map((f) => f.bar.timestamp)).toEqual([
      "2022-01-01T00:00:00.000Z",
      "2022-01-02T00:00:00.000Z",
      "2022-01-03T00:00:00.000Z",
    ]);
  });

  it("attaches equity, opened-trade, and closed-trade events only to the bars they actually occurred on", () => {
    const market = makeMarketAnalysis([
      makeBar("2022-01-03T00:00:00.000Z"), // entry bar
      makeBar("2022-01-04T00:00:00.000Z"), // neither
      makeBar("2022-01-05T00:00:00.000Z"), // exit bar
    ]);
    const trade = makeTrade({ entry_time: "2022-01-03 00:00:00+00:00", exit_time: "2022-01-05 00:00:00+00:00" });
    const backtest = makeBacktest({
      signals: [
        { timestamp: "2022-01-03 00:00:00+00:00", signal: "BUY" },
        { timestamp: "2022-01-04 00:00:00+00:00", signal: "HOLD" },
        { timestamp: "2022-01-05 00:00:00+00:00", signal: "HOLD" },
      ],
      trades: [trade],
      equity_curve: [
        { timestamp: "2022-01-03 00:00:00+00:00", equity: 10000 },
        { timestamp: "2022-01-05 00:00:00+00:00", equity: 10010 },
      ],
    });

    const frames = buildFrames(market, backtest);

    expect(frames[0].openedTrade).toEqual(trade);
    expect(frames[0].closedTrade).toBeNull();
    expect(frames[0].equity).toBe(10000);

    expect(frames[1].openedTrade).toBeNull();
    expect(frames[1].closedTrade).toBeNull();
    expect(frames[1].equity).toBeNull(); // no equity_curve entry for this bar -- not fabricated

    expect(frames[2].openedTrade).toBeNull();
    expect(frames[2].closedTrade).toEqual(trade);
    expect(frames[2].equity).toBe(10010);
  });

  it("returns an empty timeline, without throwing, for a backtest report saved before Phase 15 (no 'signals' field at all)", () => {
    const market = makeMarketAnalysis([makeBar("2022-01-03T00:00:00.000Z")]);
    const backtest = makeBacktest();
    // Simulate an old report file: delete the field entirely rather than leaving it `[]`.
    const preP15Backtest = { ...backtest } as Partial<BacktestResponse>;
    delete preP15Backtest.signals;

    expect(() => buildFrames(market, preP15Backtest as BacktestResponse)).not.toThrow();
    expect(buildFrames(market, preP15Backtest as BacktestResponse)).toEqual([]);
  });
});

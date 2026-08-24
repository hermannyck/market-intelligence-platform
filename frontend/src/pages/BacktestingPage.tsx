import { api } from "../api/client";
import type { BacktestResponse, PerformanceByRegime } from "../api/types";
import { useApiData } from "../hooks/useApiData";
import { useSelection } from "../hooks/useSelection";
import AsyncState from "../components/AsyncState";
import SignalBadge from "../components/SignalBadge";
import EquityCurveChart from "../charts/EquityCurveChart";

function pct(v: number | undefined | null): string {
  return v === undefined || v === null ? "—" : `${(v * 100).toFixed(2)}%`;
}

export default function BacktestingPage() {
  const { asset, timeframe, model } = useSelection();
  const { data, loading, error, notFound } = useApiData<BacktestResponse>(
    () => api.backtest(asset, timeframe, model) as Promise<BacktestResponse>,
    [asset, timeframe, model],
  );
  const regimeState = useApiData<PerformanceByRegime>(
    () => api.performanceByRegime(asset, timeframe, model) as Promise<PerformanceByRegime>,
    [asset, timeframe, model],
  );

  const s = data?.summary;

  return (
    <div>
      <div className="page-header">
        <h2>Backtesting</h2>
        <span className="timestamp">{model.replace("_", " ")}</span>
      </div>

      <AsyncState loading={loading} error={error} notFound={notFound}>
        {data && s && (
          <>
            <div className="card-grid">
              <div className="card">
                <h3>Total return</h3>
                <div className="stat-value" style={{ color: s.total_return >= 0 ? "var(--status-good)" : "var(--status-critical)" }}>
                  {pct(s.total_return)}
                </div>
              </div>
              <div className="card">
                <h3>Win rate</h3>
                <div className="stat-value">{pct(s.win_rate)}</div>
              </div>
              <div className="card">
                <h3>Profit factor</h3>
                <div className="stat-value">{s.profit_factor?.toFixed(2) ?? "n/a"}</div>
              </div>
              <div className="card">
                <h3>Sharpe ratio</h3>
                <div className="stat-value">{s.sharpe_ratio?.toFixed(3) ?? "n/a"}</div>
              </div>
              <div className="card">
                <h3>Max drawdown</h3>
                <div className="stat-value" style={{ color: "var(--status-critical)" }}>{pct(s.max_drawdown)}</div>
              </div>
              <div className="card">
                <h3># Trades</h3>
                <div className="stat-value">{s.num_trades}</div>
              </div>
            </div>

            <div className="chart-card">
              <h3>Equity curve</h3>
              <EquityCurveChart equityCurve={data.equity_curve} initialCapital={data.backtest_config.initial_capital as number} />
            </div>

            {regimeState.data && !regimeState.notFound && (
              <div className="chart-card">
                <h3>Performance by regime</h3>
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Regime</th>
                        <th># Trades</th>
                        <th>Win rate</th>
                        <th>Avg return</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(regimeState.data).map(([regime, r]) => (
                        <tr key={regime}>
                          <td>{regime}</td>
                          <td>{r.num_trades}</td>
                          <td>{pct(r.win_rate)}</td>
                          <td>{pct(r.avg_return_pct)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div className="chart-card">
              <h3>Trade log ({data.trades.length} trades)</h3>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Entry</th>
                      <th>Exit</th>
                      <th>Direction</th>
                      <th>Exit reason</th>
                      <th>Net return</th>
                      <th>Equity after</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.trades.slice(-50).reverse().map((t, i) => (
                      <tr key={i}>
                        <td>{new Date(t.entry_time).toLocaleDateString()}</td>
                        <td>{new Date(t.exit_time).toLocaleDateString()}</td>
                        <td>
                          <SignalBadge label={t.direction} />
                        </td>
                        <td>{t.exit_reason}</td>
                        <td style={{ color: t.net_return_pct >= 0 ? "var(--status-good)" : "var(--status-critical)" }}>
                          {pct(t.net_return_pct)}
                        </td>
                        <td>${t.equity_after.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="stat-sub">Showing the most recent 50 trades.</div>
            </div>
          </>
        )}
      </AsyncState>
    </div>
  );
}

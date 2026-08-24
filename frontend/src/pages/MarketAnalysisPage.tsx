import { api } from "../api/client";
import type { MarketAnalysisResponse } from "../api/types";
import { useApiData } from "../hooks/useApiData";
import { useSelection } from "../hooks/useSelection";
import AsyncState from "../components/AsyncState";
import CandlestickChart from "../charts/CandlestickChart";
import { AtrChart, MacdChart, RsiChart } from "../charts/IndicatorPanel";
import RegimeDistributionChart from "../charts/RegimeDistributionChart";

export default function MarketAnalysisPage() {
  const { asset, timeframe } = useSelection();
  const { data, loading, error, notFound } = useApiData<MarketAnalysisResponse>(
    () => api.marketAnalysis(asset, timeframe, 200) as Promise<MarketAnalysisResponse>,
    [asset, timeframe],
  );

  return (
    <div>
      <div className="page-header">
        <h2>Market Analysis</h2>
        {data && <span className="timestamp">as of {new Date(data.current_timestamp).toLocaleString()}</span>}
      </div>

      <AsyncState loading={loading} error={error} notFound={notFound}>
        {data && (
          <>
            <div className="card-grid">
              <div className="card">
                <h3>Price</h3>
                <div className="stat-value">{data.current_price.toFixed(4)}</div>
                <div className="stat-sub">{data.asset_code} · {data.timeframe}</div>
              </div>
              {Object.entries(data.multi_timeframe_bias).map(([tf, dir]) => (
                <div className="card" key={tf}>
                  <h3>{tf.replace("_", " ")}</h3>
                  <div className="stat-value" style={{ fontSize: "1.1rem" }}>
                    {dir ?? "—"}
                  </div>
                </div>
              ))}
            </div>

            <div className="chart-card">
              <h3>Price & EMAs</h3>
              <CandlestickChart bars={data.bars} />
              <div className="legend-row">
                <span><span className="legend-swatch" style={{ background: "var(--series-1)" }} />EMA20</span>
                <span><span className="legend-swatch" style={{ background: "var(--series-4)" }} />EMA50</span>
                <span><span className="legend-swatch" style={{ background: "var(--series-7)" }} />EMA200</span>
              </div>
            </div>

            <div className="chart-card">
              <h3>RSI (14)</h3>
              <RsiChart bars={data.bars} />
            </div>
            <div className="chart-card">
              <h3>MACD (12/26/9)</h3>
              <MacdChart bars={data.bars} />
              <div className="legend-row">
                <span><span className="legend-swatch" style={{ background: "var(--series-1)" }} />MACD</span>
                <span><span className="legend-swatch" style={{ background: "var(--series-2)" }} />Signal</span>
              </div>
            </div>
            <div className="chart-card">
              <h3>ATR (14)</h3>
              <AtrChart bars={data.bars} />
            </div>

            {data.regime && (
              <div className="chart-card">
                <h3>Market Regime — current: {data.regime.current_regime ?? "n/a"}</h3>
                <RegimeDistributionChart percentages={data.regime.regime_distribution.percentages} />
              </div>
            )}
          </>
        )}
      </AsyncState>
    </div>
  );
}

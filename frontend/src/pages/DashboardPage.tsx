import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { MarketAnalysisResponse, PredictionsResponse } from "../api/types";
import { useApiData } from "../hooks/useApiData";
import { useSelection } from "../hooks/useSelection";
import AsyncState from "../components/AsyncState";
import SignalBadge from "../components/SignalBadge";
import CandlestickChart from "../charts/CandlestickChart";

export default function DashboardPage() {
  const { asset, timeframe } = useSelection();
  const market = useApiData<MarketAnalysisResponse>(
    () => api.marketAnalysis(asset, timeframe, 100) as Promise<MarketAnalysisResponse>,
    [asset, timeframe],
  );
  const predictions = useApiData<PredictionsResponse>(
    () => api.predictions(asset, timeframe) as Promise<PredictionsResponse>,
    [asset, timeframe],
  );

  return (
    <div>
      <div className="page-header">
        <h2>Dashboard</h2>
        {market.data && <span className="timestamp">as of {new Date(market.data.current_timestamp).toLocaleString()}</span>}
      </div>

      <AsyncState loading={market.loading} error={market.error} notFound={market.notFound}>
        {market.data && (
          <>
            <div className="card-grid">
              <div className="card">
                <h3>{market.data.asset_code}</h3>
                <div className="stat-value">{market.data.current_price.toFixed(4)}</div>
                <div className="stat-sub">{market.data.timeframe}</div>
              </div>
              <div className="card">
                <h3>Signal</h3>
                <div className="stat-value">
                  <SignalBadge label={predictions.data?.consensus_class} />
                </div>
                <div className="stat-sub">
                  {predictions.data?.consensus_ratio ? `${predictions.data.consensus_ratio} models agree` : predictions.loading ? "loading…" : "—"}
                </div>
              </div>
              <div className="card">
                <h3>Regime</h3>
                <div className="stat-value" style={{ fontSize: "1.1rem" }}>
                  {market.data.regime?.current_regime ?? "n/a"}
                </div>
              </div>
              <div className="card">
                <h3>Multi-timeframe bias</h3>
                <div className="stat-value" style={{ fontSize: "1.1rem" }}>
                  {market.data.multi_timeframe_bias.mtf_bias ?? "n/a"}
                </div>
              </div>
            </div>

            <div className="chart-card">
              <h3>Price</h3>
              <CandlestickChart bars={market.data.bars} showEmas={false} />
            </div>

            {predictions.data && (
              <div className="chart-card">
                <h3>Model consensus</h3>
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Model</th>
                        <th>Signal</th>
                        <th>Confidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {predictions.data.predictions.map((p) => (
                        <tr key={p.model_name}>
                          <td>{p.model_name.replace("_", " ")}</td>
                          <td><SignalBadge label={p.predicted_class} /></td>
                          <td>{(p.probabilities[p.predicted_class] * 100).toFixed(1)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <p className="stat-sub">
              See <Link to="/market-analysis">Market Analysis</Link>, <Link to="/predictions">Predictions</Link>,{" "}
              <Link to="/explainability">Explainability</Link>, <Link to="/backtesting">Backtesting</Link> and{" "}
              <Link to="/news-sentiment">News Sentiment</Link> for the full detail behind each of these.
            </p>
          </>
        )}
      </AsyncState>
    </div>
  );
}

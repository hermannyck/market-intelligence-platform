import { api } from "../api/client";
import type { PredictionsResponse } from "../api/types";
import { useApiData } from "../hooks/useApiData";
import { useSelection } from "../hooks/useSelection";
import AsyncState from "../components/AsyncState";
import SignalBadge from "../components/SignalBadge";
import { MODELS } from "../services/navConfig";

const MODEL_LABELS: Record<string, string> = Object.fromEntries(MODELS.map((m) => [m.key, m.label]));

export default function PredictionsPage() {
  const { asset, timeframe } = useSelection();
  const { data, loading, error, notFound } = useApiData<PredictionsResponse>(
    () => api.predictions(asset, timeframe) as Promise<PredictionsResponse>,
    [asset, timeframe],
  );

  return (
    <div>
      <div className="page-header">
        <h2>Predictions</h2>
        {data && <span className="timestamp">as of {new Date(data.timestamp).toLocaleString()}</span>}
      </div>

      <AsyncState loading={loading} error={error} notFound={notFound}>
        {data && (
          <>
            <div className="card-grid">
              <div className="card">
                <h3>Price</h3>
                <div className="stat-value">{data.price.toFixed(4)}</div>
              </div>
              <div className="card">
                <h3>Consensus</h3>
                <div className="stat-value">
                  <SignalBadge label={data.consensus_class} />
                </div>
                <div className="stat-sub">{data.consensus_ratio} models agree</div>
              </div>
            </div>

            <div className="chart-card">
              <h3>Model-by-model breakdown</h3>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>Signal</th>
                      <th>SELL %</th>
                      <th>HOLD %</th>
                      <th>BUY %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.predictions.map((p) => (
                      <tr key={p.model_name}>
                        <td>{MODEL_LABELS[p.model_name] ?? p.model_name}</td>
                        <td>
                          <SignalBadge label={p.predicted_class} />
                        </td>
                        <td>{(p.probabilities.SELL * 100).toFixed(1)}</td>
                        <td>{(p.probabilities.HOLD * 100).toFixed(1)}</td>
                        <td>{(p.probabilities.BUY * 100).toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </AsyncState>
    </div>
  );
}

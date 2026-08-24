import { api } from "../api/client";
import type { ExplainabilityResponse } from "../api/types";
import { useApiData } from "../hooks/useApiData";
import { useSelection } from "../hooks/useSelection";
import AsyncState from "../components/AsyncState";
import SignalBadge from "../components/SignalBadge";
import ShapBarChart from "../charts/ShapBarChart";

export default function ExplainabilityPage() {
  const { asset, timeframe, model } = useSelection();
  const { data, loading, error, notFound } = useApiData<ExplainabilityResponse>(
    () => api.explainability(asset, timeframe, model) as Promise<ExplainabilityResponse>,
    [asset, timeframe, model],
  );

  const local = data?.local_explanations?.[0];

  return (
    <div>
      <div className="page-header">
        <h2>Explainability</h2>
        {local && <span className="timestamp">as of {new Date(local.timestamp).toLocaleString()}</span>}
      </div>

      <AsyncState loading={loading} error={error} notFound={notFound}>
        {data && (
          <>
            {local && (
              <>
                <div className="card-grid">
                  <div className="card">
                    <h3>Prediction</h3>
                    <div className="stat-value">
                      <SignalBadge label={local.predicted_class} />
                    </div>
                  </div>
                  {(["SELL", "HOLD", "BUY"] as const).map((label) => (
                    <div className="card" key={label}>
                      <h3>{label}</h3>
                      <div className="stat-value">{(local.probabilities[label] * 100).toFixed(1)}%</div>
                    </div>
                  ))}
                </div>

                <div className="chart-card">
                  <h3>Why this prediction — top contributing factors</h3>
                  <ShapBarChart
                    values={local.top_factors.map((f) => ({ feature: f.feature, value: f.shap_value }))}
                    signed
                  />
                  <div className="stat-sub">
                    Green = pushed toward {local.predicted_class}, red = pushed away from it.
                  </div>
                </div>
              </>
            )}

            <div className="chart-card">
              <h3>Global feature importance ({model.replace("_", " ")})</h3>
              <ShapBarChart
                values={Object.entries(data.global_feature_importance)
                  .slice(0, 15)
                  .map(([feature, value]) => ({ feature, value }))}
              />
              <div className="stat-sub">Mean absolute SHAP value across a sample of recent rows, averaged over all 3 classes.</div>
            </div>
          </>
        )}
      </AsyncState>
    </div>
  );
}

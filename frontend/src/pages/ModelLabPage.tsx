import { api } from "../api/client";
import type { ModelLabResponse } from "../api/types";
import { useApiData } from "../hooks/useApiData";
import { useSelection } from "../hooks/useSelection";
import AsyncState from "../components/AsyncState";
import { MODELS } from "../services/navConfig";

const MODEL_LABELS: Record<string, string> = Object.fromEntries(MODELS.map((m) => [m.key, m.label]));

function pct(v: number | undefined | null): string {
  return v === undefined || v === null ? "—" : `${(v * 100).toFixed(1)}%`;
}

export default function ModelLabPage() {
  const { asset, timeframe } = useSelection();
  const { data, loading, error, notFound } = useApiData<ModelLabResponse>(
    () => api.modelLab(asset, timeframe) as Promise<ModelLabResponse>,
    [asset, timeframe],
  );

  return (
    <div>
      <div className="page-header">
        <h2>Model Lab</h2>
      </div>

      <AsyncState loading={loading} error={error} notFound={notFound}>
        {data && (
          <>
            <div className="chart-card">
              <h3>Baseline comparison (single chronological split)</h3>
              {data.baseline_comparison ? (
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Model</th>
                        <th>Accuracy</th>
                        <th>F1 (macro)</th>
                        <th>Precision (macro)</th>
                        <th>Recall (macro)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(data.baseline_comparison.models).map(([m, metrics]) => (
                        <tr key={m}>
                          <td>{MODEL_LABELS[m] ?? m}</td>
                          <td>{pct(metrics.accuracy)}</td>
                          <td>{pct(metrics.f1_macro)}</td>
                          <td>{pct(metrics.precision_macro)}</td>
                          <td>{pct(metrics.recall_macro)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-state">No baseline comparison yet.</div>
              )}
            </div>

            <div className="chart-card">
              <h3>Walk-forward overall (mean across resolved windows)</h3>
              {data.walk_forward ? (
                <>
                  <div className="stat-sub" style={{ marginBottom: "0.5rem" }}>
                    {data.walk_forward.n_resolved_windows} windows ({data.walk_forward.window_source})
                  </div>
                  <div className="table-scroll">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Model</th>
                          <th>Accuracy (mean ± std)</th>
                          <th>F1 macro (mean)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(data.walk_forward.overall).map(([m, metrics]) => (
                          <tr key={m}>
                            <td>{MODEL_LABELS[m] ?? m}</td>
                            <td>
                              {pct(metrics.accuracy_mean)} ± {pct(metrics.accuracy_std)}
                              {metrics.accuracy_n_windows === 1 && (
                                <span className="stat-sub"> (1 window — std not meaningful)</span>
                              )}
                            </td>
                            <td>{pct(metrics.f1_macro_mean)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <div className="empty-state">No walk-forward report yet.</div>
              )}
            </div>
          </>
        )}
      </AsyncState>
    </div>
  );
}

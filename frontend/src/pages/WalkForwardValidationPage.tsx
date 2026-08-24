import { api } from "../api/client";
import type { WalkForwardResponse } from "../api/types";
import { useApiData } from "../hooks/useApiData";
import { useSelection } from "../hooks/useSelection";
import AsyncState from "../components/AsyncState";

function pct(v: number | undefined | null): string {
  return v === undefined || v === null ? "—" : `${(v * 100).toFixed(1)}%`;
}

export default function WalkForwardValidationPage() {
  const { asset, timeframe, model } = useSelection();
  const { data, loading, error, notFound } = useApiData<WalkForwardResponse>(
    () => api.walkForward(asset, timeframe) as Promise<WalkForwardResponse>,
    [asset, timeframe],
  );

  return (
    <div>
      <div className="page-header">
        <h2>Walk-Forward Validation</h2>
        {data && (
          <span className="timestamp">
            {data.n_resolved_windows} windows ({data.window_source})
          </span>
        )}
      </div>

      <AsyncState loading={loading} error={error} notFound={notFound}>
        {data && (
          <>
            <div className="chart-card">
              <h3>Per-window results — {model.replace("_", " ")}</h3>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Train</th>
                      <th>Test</th>
                      <th>Source</th>
                      <th>Test rows</th>
                      <th>Accuracy</th>
                      <th>F1 (macro)</th>
                      <th>ROC-AUC</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.windows.map((w, i) => {
                      const m = w.models[model];
                      return (
                        <tr key={i}>
                          <td>
                            {w.window.train_start} → {w.window.train_end}
                          </td>
                          <td>
                            {w.window.test_start} → {w.window.test_end}
                          </td>
                          <td>{w.source}</td>
                          <td>{w.test_rows}</td>
                          <td>{pct(m?.accuracy)}</td>
                          <td>{pct(m?.f1_macro)}</td>
                          <td>{m?.roc_auc_macro !== null && m?.roc_auc_macro !== undefined ? m.roc_auc_macro.toFixed(3) : "n/a"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="chart-card">
              <h3>Overall (mean ± std across windows), all models</h3>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>Accuracy</th>
                      <th>F1 (macro)</th>
                      <th># windows</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.overall).map(([m, metrics]) => (
                      <tr key={m}>
                        <td>{m.replace("_", " ")}</td>
                        <td>
                          {pct(metrics.accuracy_mean)} ± {pct(metrics.accuracy_std)}
                        </td>
                        <td>{pct(metrics.f1_macro_mean)}</td>
                        <td>{metrics.accuracy_n_windows}</td>
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

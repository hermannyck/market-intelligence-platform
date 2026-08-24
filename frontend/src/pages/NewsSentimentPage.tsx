import { api } from "../api/client";
import type { NewsSentimentResponse } from "../api/types";
import { useApiData } from "../hooks/useApiData";
import { useSelection } from "../hooks/useSelection";
import AsyncState from "../components/AsyncState";
import SentimentTimelineChart from "../charts/SentimentTimelineChart";

export default function NewsSentimentPage() {
  const { asset } = useSelection();
  const { data, loading, error, notFound } = useApiData<NewsSentimentResponse>(
    () => api.newsSentiment(asset, 200) as Promise<NewsSentimentResponse>,
    [asset],
  );

  return (
    <div>
      <div className="page-header">
        <h2>News Sentiment</h2>
      </div>

      {data?.source && <div className="disclaimer-banner" style={{ marginBottom: "1rem" }}>{data.source}</div>}

      <AsyncState loading={loading} error={error} notFound={notFound}>
        {data && (
          data.articles.length === 0 ? (
            <div className="empty-state">{data.note ?? "No scored news available for this asset yet."}</div>
          ) : (
            <>
              <div className="chart-card">
                <h3>Sentiment timeline</h3>
                <SentimentTimelineChart articles={data.articles} />
                <div className="legend-row">
                  <span><span className="legend-swatch" style={{ background: "var(--status-good)" }} />Positive</span>
                  <span><span className="legend-swatch" style={{ background: "var(--text-muted)" }} />Neutral</span>
                  <span><span className="legend-swatch" style={{ background: "var(--status-critical)" }} />Negative</span>
                </div>
              </div>

              <div className="chart-card">
                <h3>Recent headlines</h3>
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Headline</th>
                        <th>Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...data.articles]
                        .sort((a, b) => b.published_at.localeCompare(a.published_at))
                        .slice(0, 50)
                        .map((a, i) => (
                          <tr key={i}>
                            <td>{new Date(a.published_at).toLocaleDateString()}</td>
                            <td>{a.headline}</td>
                            <td style={{ color: a.sentiment_score >= 0 ? "var(--status-good)" : "var(--status-critical)" }}>
                              {a.sentiment_score.toFixed(2)}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )
        )}
      </AsyncState>
    </div>
  );
}

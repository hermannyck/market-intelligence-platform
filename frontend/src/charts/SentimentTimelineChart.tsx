import { CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import type { NewsArticle } from "../api/types";

interface Props {
  articles: NewsArticle[];
}

function formatTimestamp(ts: string): string {
  return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function SentimentTimelineChart({ articles }: Props) {
  const sorted = [...articles].sort((a, b) => a.published_at.localeCompare(b.published_at));
  const data = sorted.map((a) => ({ ...a, x: a.published_at, y: a.sentiment_score }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <ScatterChart margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--gridline)" />
        <XAxis
          dataKey="x"
          type="category"
          tickFormatter={formatTimestamp}
          tick={{ fill: "var(--text-muted)", fontSize: 11 }}
          minTickGap={40}
          stroke="var(--baseline)"
        />
        <YAxis dataKey="y" domain={[-1, 1]} tick={{ fill: "var(--text-muted)", fontSize: 11 }} width={40} stroke="var(--baseline)" />
        <ZAxis range={[40, 40]} />
        <ReferenceLine y={0} stroke="var(--baseline)" />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as NewsArticle;
            return (
              <div style={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.5rem 0.65rem", fontSize: "0.78rem", maxWidth: 260 }}>
                <div style={{ color: "var(--text-muted)" }}>{formatTimestamp(d.published_at)}</div>
                <div>{d.headline}</div>
                <div style={{ marginTop: 4 }}>score: {d.sentiment_score.toFixed(2)}</div>
              </div>
            );
          }}
        />
        <Scatter data={data} isAnimationActive={false}>
          {data.map((d, i) => (
            <Cell
              key={i}
              fill={d.y >= 0.1 ? "var(--status-good)" : d.y <= -0.1 ? "var(--status-critical)" : "var(--text-muted)"}
            />
          ))}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}

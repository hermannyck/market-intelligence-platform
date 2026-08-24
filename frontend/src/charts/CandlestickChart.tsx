import { Bar, CartesianGrid, Cell, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Bar as BarType } from "../api/types";

interface Props {
  bars: BarType[];
  showEmas?: boolean;
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function CandlestickChart({ bars, showEmas = true }: Props) {
  const data = bars.map((b) => ({
    ...b,
    wick: [b.low, b.high],
    body: [Math.min(b.open, b.close), Math.max(b.open, b.close)],
    up: b.close >= b.open,
  }));

  return (
    <ResponsiveContainer width="100%" height={340}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--gridline)" vertical={false} />
        <XAxis
          dataKey="timestamp"
          tickFormatter={formatTimestamp}
          stroke="var(--baseline)"
          tick={{ fill: "var(--text-muted)", fontSize: 11 }}
          minTickGap={40}
        />
        <YAxis
          domain={["auto", "auto"]}
          stroke="var(--baseline)"
          tick={{ fill: "var(--text-muted)", fontSize: 11 }}
          width={70}
        />
        <Tooltip content={<CandlestickTooltip />} />
        <Bar dataKey="wick" barSize={1.5} isAnimationActive={false}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.up ? "var(--status-good)" : "var(--status-critical)"} />
          ))}
        </Bar>
        <Bar dataKey="body" barSize={6} isAnimationActive={false}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.up ? "var(--status-good)" : "var(--status-critical)"} />
          ))}
        </Bar>
        {showEmas && (
          <>
            <Line type="monotone" dataKey="EMA20" stroke="var(--series-1)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
            <Line type="monotone" dataKey="EMA50" stroke="var(--series-4)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
            <Line type="monotone" dataKey="EMA200" stroke="var(--series-7)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
          </>
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function CandlestickTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div
      style={{
        background: "var(--surface-1)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "0.5rem 0.65rem",
        fontSize: "0.78rem",
        color: "var(--text-primary)",
      }}
    >
      <div style={{ color: "var(--text-muted)", marginBottom: 4 }}>{formatTimestamp(d.timestamp)}</div>
      <div>O {d.open?.toFixed(4)} &nbsp; H {d.high?.toFixed(4)}</div>
      <div>L {d.low?.toFixed(4)} &nbsp; C {d.close?.toFixed(4)}</div>
    </div>
  );
}

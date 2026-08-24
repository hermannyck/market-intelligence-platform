import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Bar } from "../api/types";

function formatTimestamp(ts: string): string {
  return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function MiniChart({ data, children, height = 110 }: { data: Bar[]; children: React.ReactNode; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--gridline)" vertical={false} />
        <XAxis dataKey="timestamp" tickFormatter={formatTimestamp} tick={{ fill: "var(--text-muted)", fontSize: 10 }} minTickGap={50} stroke="var(--baseline)" />
        <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={40} stroke="var(--baseline)" />
        <Tooltip
          contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 8, fontSize: "0.75rem" }}
          labelFormatter={formatTimestamp}
        />
        {children}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function RsiChart({ bars }: { bars: Bar[] }) {
  return (
    <MiniChart data={bars}>
      <ReferenceLine y={70} stroke="var(--status-critical)" strokeDasharray="3 3" />
      <ReferenceLine y={30} stroke="var(--status-good)" strokeDasharray="3 3" />
      <Line type="monotone" dataKey="RSI14" stroke="var(--series-1)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
    </MiniChart>
  );
}

export function MacdChart({ bars }: { bars: Bar[] }) {
  return (
    <MiniChart data={bars}>
      <ReferenceLine y={0} stroke="var(--baseline)" />
      <Line type="monotone" dataKey="MACD" stroke="var(--series-1)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
      <Line type="monotone" dataKey="MACD_signal" stroke="var(--series-2)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
    </MiniChart>
  );
}

export function AtrChart({ bars }: { bars: Bar[] }) {
  return (
    <MiniChart data={bars}>
      <Line type="monotone" dataKey="ATR14" stroke="var(--series-3)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
    </MiniChart>
  );
}

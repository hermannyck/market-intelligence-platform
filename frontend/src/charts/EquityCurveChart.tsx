import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Props {
  equityCurve: { timestamp: string; equity: number }[];
  initialCapital?: number;
}

function formatTimestamp(ts: string): string {
  return new Date(ts).toLocaleDateString(undefined, { year: "2-digit", month: "short" });
}

export default function EquityCurveChart({ equityCurve, initialCapital }: Props) {
  const baseline = initialCapital ?? equityCurve[0]?.equity ?? 0;
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={equityCurve} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--series-1)" stopOpacity={0.25} />
            <stop offset="100%" stopColor="var(--series-1)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="var(--gridline)" vertical={false} />
        <XAxis dataKey="timestamp" tickFormatter={formatTimestamp} tick={{ fill: "var(--text-muted)", fontSize: 11 }} minTickGap={50} stroke="var(--baseline)" />
        <YAxis domain={["auto", "auto"]} tick={{ fill: "var(--text-muted)", fontSize: 11 }} width={70} stroke="var(--baseline)" />
        <ReferenceLine y={baseline} stroke="var(--baseline)" strokeDasharray="4 4" />
        <Tooltip
          contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 8, fontSize: "0.8rem" }}
          labelFormatter={formatTimestamp}
          formatter={(value: number) => [`$${value.toFixed(2)}`, "Equity"]}
        />
        <Area type="stepAfter" dataKey="equity" stroke="var(--series-1)" strokeWidth={1.75} fill="url(#equityFill)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

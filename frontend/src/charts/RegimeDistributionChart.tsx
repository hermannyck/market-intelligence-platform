import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const REGIME_COLORS: Record<string, string> = {
  "Bullish Trending": "var(--status-good)",
  "Bearish Trending": "var(--status-critical)",
  "Sideways / Range-Bound": "var(--text-muted)",
  "High Volatility": "var(--series-2)",
  "Low Volatility": "var(--series-1)",
};

export default function RegimeDistributionChart({ percentages }: { percentages: Record<string, number> }) {
  const data = Object.entries(percentages).map(([regime, pct]) => ({ regime, pct }));
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
        <XAxis type="number" unit="%" tick={{ fill: "var(--text-muted)", fontSize: 11 }} stroke="var(--baseline)" />
        <YAxis type="category" dataKey="regime" width={130} tick={{ fill: "var(--text-secondary)", fontSize: 11 }} stroke="var(--baseline)" />
        <Tooltip
          contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 8, fontSize: "0.8rem" }}
          formatter={(v: number) => `${v.toFixed(1)}%`}
        />
        <Bar dataKey="pct" isAnimationActive={false} radius={2}>
          {data.map((d, i) => (
            <Cell key={i} fill={REGIME_COLORS[d.regime] ?? "var(--series-1)"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

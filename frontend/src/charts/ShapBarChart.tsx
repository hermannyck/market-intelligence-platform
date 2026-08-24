import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Props {
  /** feature -> signed or unsigned contribution value */
  values: { feature: string; value: number }[];
  /** when true, colors bars by sign (positive/negative); otherwise a single sequential hue */
  signed?: boolean;
}

export default function ShapBarChart({ values, signed = false }: Props) {
  const sorted = [...values].sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  const height = Math.max(160, sorted.length * 32);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={sorted} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
        <CartesianGrid stroke="var(--gridline)" horizontal={false} />
        <XAxis type="number" tick={{ fill: "var(--text-muted)", fontSize: 11 }} stroke="var(--baseline)" />
        <YAxis
          type="category"
          dataKey="feature"
          width={130}
          tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
          stroke="var(--baseline)"
        />
        <Tooltip
          contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 8, fontSize: "0.8rem" }}
          formatter={(value: number) => value.toFixed(4)}
        />
        <Bar dataKey="value" isAnimationActive={false} radius={2}>
          {sorted.map((d, i) => (
            <Cell
              key={i}
              fill={signed ? (d.value >= 0 ? "var(--status-good)" : "var(--status-critical)") : "var(--series-1)"}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

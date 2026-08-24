import type { TargetLabel } from "../api/types";

export default function SignalBadge({ label }: { label: TargetLabel | string | null | undefined }) {
  if (!label) return <span className="badge badge-hold">—</span>;
  const cls = label === "BUY" ? "badge-buy" : label === "SELL" ? "badge-sell" : "badge-hold";
  return <span className={`badge ${cls}`}>{label}</span>;
}

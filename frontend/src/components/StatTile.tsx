import type { ReactNode } from "react";

interface StatTileProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "default" | "warning" | "error" | "online";
}

const TONE_STYLES: Record<NonNullable<StatTileProps["tone"]>, string> = {
  default: "text-surface-50",
  warning: "text-status-warning",
  error: "text-status-error",
  online: "text-status-online",
};

export default function StatTile({ label, value, sub, tone = "default" }: StatTileProps) {
  return (
    <div className="card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-surface-400">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${TONE_STYLES[tone]}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-surface-500">{sub}</p>}
    </div>
  );
}

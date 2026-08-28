export default function ProgressBar({ percent, className = "" }: { percent: number; className?: string }) {
  const clamped = Math.max(0, Math.min(100, percent));
  const tone = clamped > 90 ? "bg-status-error" : clamped > 75 ? "bg-status-warning" : "bg-accent-500";
  return (
    <div className={`h-1.5 w-full overflow-hidden rounded-full bg-surface-800 ${className}`}>
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${clamped}%` }} />
    </div>
  );
}

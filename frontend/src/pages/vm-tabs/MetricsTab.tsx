import { useQuery } from "@tanstack/react-query";

import { FullPageSpinner } from "@/components/Spinner";
import { metrics } from "@/lib/resources";

interface Sample {
  ts: number;
  cpu_percent?: number | null;
  memory_used_mb?: number | null;
}

export default function MetricsTab({ vmUuid }: { vmUuid: string }) {
  const query = useQuery({ queryKey: ["metrics", "vm", vmUuid], queryFn: () => metrics.vm(vmUuid, 3600), refetchInterval: 15000 });

  if (query.isLoading) return <FullPageSpinner />;

  const samples = (query.data?.samples ?? []) as unknown as Sample[];
  const latest = samples.at(-1);

  if (!samples.length) {
    return (
      <div className="card p-6 text-center">
        <p className="text-sm text-surface-300">No metrics reported yet.</p>
        <p className="mt-1 text-xs text-surface-500">
          Per-VM metrics require the agent to push domain stats, which isn't wired into the heartbeat loop in this
          build -- host-level metrics (CPU/memory/storage) are live on the Node detail page.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MiniStat label="CPU" value={latest?.cpu_percent != null ? `${Math.round(latest.cpu_percent)}%` : "-"} />
        <MiniStat label="Memory" value={latest?.memory_used_mb != null ? `${latest.memory_used_mb} MB` : "-"} />
      </div>
      <Sparkline label="CPU %" values={samples.map((s) => s.cpu_percent ?? 0)} />
      <Sparkline label="Memory (MB)" values={samples.map((s) => s.memory_used_mb ?? 0)} />
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="card p-3">
      <p className="text-xs text-surface-400">{label}</p>
      <p className="text-lg font-semibold text-surface-50">{value}</p>
    </div>
  );
}

function Sparkline({ label, values }: { label: string; values: number[] }) {
  const width = 480;
  const height = 60;
  const max = Math.max(...values, 1);
  const points = values.map((v, i) => `${(i / Math.max(values.length - 1, 1)) * width},${height - (v / max) * height}`).join(" ");

  return (
    <div className="card p-4">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-surface-400">{label}</p>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full text-accent-400" preserveAspectRatio="none">
        <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    </div>
  );
}

import { useQueries, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import ErrorBanner from "@/components/ErrorBanner";
import PageHeader from "@/components/PageHeader";
import { FullPageSpinner } from "@/components/Spinner";
import StatTile from "@/components/StatTile";
import StatusBadge from "@/components/StatusBadge";
import { formatDateTime, formatRelativeTime, percentage } from "@/lib/format";
import { events, jobs, metrics, nodes, vms } from "@/lib/resources";

export default function DashboardPage() {
  const nodesQuery = useQuery({ queryKey: ["nodes", "dashboard"], queryFn: () => nodes.list({ page_size: 100 }) });
  const vmsQuery = useQuery({ queryKey: ["vms", "dashboard"], queryFn: () => vms.list({ page_size: 100 }) });
  const jobsQuery = useQuery({ queryKey: ["jobs", "recent"], queryFn: () => jobs.list({ page_size: 8 }) });
  const eventsQuery = useQuery({ queryKey: ["events", "recent"], queryFn: () => events.list({ page_size: 8 }) });

  const onlineNodes = nodesQuery.data?.results.filter((n) => n.status === "ONLINE") ?? [];

  // Live CPU utilization is only meaningful per-node (there's no
  // precomputed fleet-wide figure) -- average the most recent real
  // sample from each online node rather than showing anything made up.
  const cpuSamples = useQueries({
    queries: onlineNodes.slice(0, 20).map((node) => ({
      queryKey: ["metrics", "node", node.uuid, "dashboard"],
      queryFn: () => metrics.node(node.uuid, 120),
      enabled: onlineNodes.length > 0,
    })),
  });

  const cpuValues = cpuSamples
    .map((q) => q.data?.samples.at(-1)?.cpu_percent)
    .filter((v): v is number => typeof v === "number");
  const avgCpu = cpuValues.length ? Math.round(cpuValues.reduce((a, b) => a + b, 0) / cpuValues.length) : null;

  if (nodesQuery.isLoading || vmsQuery.isLoading) return <FullPageSpinner />;

  const totalMemory = nodesQuery.data?.results.reduce((sum, n) => sum + n.memory_total_mb, 0) ?? 0;
  const usedMemory = (nodesQuery.data?.results.reduce((sum, n) => sum + (n.memory_total_mb - n.memory_available_mb), 0) ?? 0);
  const totalStorage = nodesQuery.data?.results.reduce((sum, n) => sum + n.storage_total_gb, 0) ?? 0;
  const usedStorage = nodesQuery.data?.results.reduce((sum, n) => sum + (n.storage_total_gb - n.storage_available_gb), 0) ?? 0;

  const runningVms = vmsQuery.data?.results.filter((vm) => vm.status === "RUNNING").length ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" />

      <ErrorBanner error={nodesQuery.error ?? vmsQuery.error} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatTile label="Nodes" value={nodesQuery.data?.count ?? 0} sub={`${onlineNodes.length} online`} />
        <StatTile label="VMs" value={vmsQuery.data?.count ?? 0} sub={`${runningVms} running`} />
        <StatTile label="CPU" value={avgCpu !== null ? `${avgCpu}%` : "—"} sub={avgCpu !== null ? "avg across online nodes" : "no samples yet"} tone={avgCpu !== null && avgCpu > 85 ? "warning" : "default"} />
        <StatTile label="Memory" value={`${percentage(usedMemory, totalMemory)}%`} sub={`${Math.round(usedMemory / 1024)} / ${Math.round(totalMemory / 1024)} GB`} tone={percentage(usedMemory, totalMemory) > 85 ? "warning" : "default"} />
        <StatTile label="Storage" value={`${percentage(usedStorage, totalStorage)}%`} sub={`${usedStorage} / ${totalStorage} GB`} tone={percentage(usedStorage, totalStorage) > 85 ? "warning" : "default"} />
        <StatTile label="Stopped VMs" value={(vmsQuery.data?.count ?? 0) - runningVms} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-surface-100">Recent Jobs</h2>
            <Link to="/jobs" className="text-xs text-accent-400 hover:underline">
              View all
            </Link>
          </div>
          {jobsQuery.isLoading ? (
            <FullPageSpinner />
          ) : !jobsQuery.data?.results.length ? (
            <p className="py-6 text-center text-xs text-surface-500">No jobs yet.</p>
          ) : (
            <ul className="divide-y divide-surface-800">
              {jobsQuery.data.results.map((job) => (
                <li key={job.uuid} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <div className="min-w-0">
                    <p className="truncate text-surface-200">{job.type}</p>
                    <p className="truncate text-xs text-surface-500">{job.message || job.resource_type}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <StatusBadge status={job.status} />
                    <span className="w-14 text-right text-xs text-surface-500">{formatRelativeTime(job.created_at)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-surface-100">Recent Events</h2>
          </div>
          {eventsQuery.isLoading ? (
            <FullPageSpinner />
          ) : !eventsQuery.data?.results.length ? (
            <p className="py-6 text-center text-xs text-surface-500">No events yet.</p>
          ) : (
            <ul className="divide-y divide-surface-800">
              {eventsQuery.data.results.map((event) => (
                <li key={event.uuid} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <div className="min-w-0">
                    <p className="truncate text-surface-200">{event.type}</p>
                    <p className="truncate text-xs text-surface-500">
                      {event.resource_type}:{event.resource_id}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <StatusBadge status={event.severity} />
                    <span className="w-28 text-right text-xs text-surface-500" title={formatDateTime(event.created_at)}>
                      {formatRelativeTime(event.created_at)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

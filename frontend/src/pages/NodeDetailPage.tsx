import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import ErrorBanner from "@/components/ErrorBanner";
import PageHeader from "@/components/PageHeader";
import ProgressBar from "@/components/ProgressBar";
import { FullPageSpinner } from "@/components/Spinner";
import StatTile from "@/components/StatTile";
import StatusBadge from "@/components/StatusBadge";
import { formatDateTime, formatRelativeTime, percentage } from "@/lib/format";
import { nodes, vms } from "@/lib/resources";
import { useWebSocketSubscription } from "@/lib/ws";
import type { Node } from "@/types/api";

export default function NodeDetailPage() {
  const { uuid = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [issuedToken, setIssuedToken] = useState<string | null>(null);

  const nodeQuery = useQuery({ queryKey: ["nodes", uuid], queryFn: () => nodes.get(uuid), enabled: !!uuid });
  const vmsQuery = useQuery({ queryKey: ["vms", { node: uuid }], queryFn: () => vms.list({ node: uuid, page_size: 100 }), enabled: !!uuid });

  useWebSocketSubscription(uuid ? `/ws/nodes/${uuid}` : null, (data) => {
    const payload = data as Partial<Node> & { uuid?: string };
    if (payload.uuid !== uuid) return;
    queryClient.setQueryData<Node | undefined>(["nodes", uuid], (prev) => (prev ? { ...prev, ...payload } : prev));
  });

  const maintenanceMutation = useMutation({
    mutationFn: (enabled: boolean) => nodes.setMaintenance(uuid, enabled),
    onSuccess: (data) => queryClient.setQueryData(["nodes", uuid], data),
  });

  const registerAgentMutation = useMutation({
    mutationFn: () => nodes.registerAgent(uuid),
    onSuccess: (data) => {
      setIssuedToken(data.token);
      queryClient.invalidateQueries({ queryKey: ["nodes", uuid] });
    },
  });

  const revokeAgentMutation = useMutation({
    mutationFn: () => nodes.revokeAgent(uuid),
    onSuccess: (data) => queryClient.setQueryData(["nodes", uuid], data),
  });

  if (nodeQuery.isLoading) return <FullPageSpinner />;
  if (!nodeQuery.data) return <ErrorBanner error={nodeQuery.error} />;
  const node = nodeQuery.data;

  const runningVms = vmsQuery.data?.results.filter((vm) => vm.status === "RUNNING").length ?? 0;
  const stoppedVms = (vmsQuery.data?.results.length ?? 0) - runningVms;

  return (
    <div className="space-y-6">
      <PageHeader
        title={node.name}
        description={node.fqdn || node.hostname}
        actions={
          <>
            <button className="btn-secondary" onClick={() => maintenanceMutation.mutate(node.admin_state !== "MAINTENANCE")} disabled={maintenanceMutation.isPending}>
              {node.admin_state === "MAINTENANCE" ? "Exit maintenance" : "Enter maintenance"}
            </button>
            {node.agent ? (
              <button className="btn-secondary" onClick={() => revokeAgentMutation.mutate()} disabled={revokeAgentMutation.isPending}>
                Revoke agent token
              </button>
            ) : null}
            <button className="btn-primary" onClick={() => registerAgentMutation.mutate()} disabled={registerAgentMutation.isPending}>
              {node.agent ? "Reissue agent token" : "Issue agent token"}
            </button>
          </>
        }
      />

      <ErrorBanner error={maintenanceMutation.error ?? registerAgentMutation.error ?? revokeAgentMutation.error} />

      {issuedToken && (
        <div className="card space-y-2 border-status-warning/40 p-4">
          <p className="text-sm font-medium text-status-warning">Agent token issued -- shown once, copy it now</p>
          <code className="block break-all rounded-md bg-surface-950 p-2 text-xs text-surface-200">{issuedToken}</code>
          <p className="text-xs text-surface-500">
            Put this in <code>/etc/nodepilot/agent.yaml</code> as <code>agent_token</code> on <strong>{node.hostname}</strong>, along with{" "}
            <code>node_id: {node.uuid}</code>. See docs/installation.md section 2.
          </p>
          <button className="btn-ghost" onClick={() => setIssuedToken(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Status" value={<StatusBadge status={node.status} />} />
        <StatTile label="VMs" value={node.reported_vm_count} sub={`${runningVms} running / ${stoppedVms} stopped`} />
        <StatTile label="Agent" value={<StatusBadge status={node.agent?.status ?? "DISABLED"} />} sub={node.agent_version ? `v${node.agent_version}` : undefined} />
        <StatTile label="Last heartbeat" value={formatRelativeTime(node.last_seen)} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card p-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-surface-400">CPU</p>
          <p className="text-sm text-surface-200">
            {node.cpu_model || "Unknown model"} -- {node.cpu_sockets}S / {node.cpu_cores}C / {node.cpu_threads}T
          </p>
        </div>
        <div className="card p-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-surface-400">Memory</p>
          <ProgressBar percent={percentage(node.memory_total_mb - node.memory_available_mb, node.memory_total_mb)} className="mb-1.5" />
          <p className="text-xs text-surface-400">
            {Math.round((node.memory_total_mb - node.memory_available_mb) / 1024)} / {Math.round(node.memory_total_mb / 1024)} GB used
          </p>
        </div>
        <div className="card p-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-surface-400">Storage</p>
          <ProgressBar percent={percentage(node.storage_total_gb - node.storage_available_gb, node.storage_total_gb)} className="mb-1.5" />
          <p className="text-xs text-surface-400">
            {node.storage_total_gb - node.storage_available_gb} / {node.storage_total_gb} GB used
          </p>
        </div>
      </div>

      <div className="card p-4 text-xs text-surface-400">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-4">
          <dt className="text-surface-500">Kernel</dt>
          <dd className="text-surface-300">{node.kernel || "-"}</dd>
          <dt className="text-surface-500">Architecture</dt>
          <dd className="text-surface-300">{node.architecture || "-"}</dd>
          <dt className="text-surface-500">Registered</dt>
          <dd className="text-surface-300">{formatDateTime(node.created_at)}</dd>
          <dt className="text-surface-500">Admin state</dt>
          <dd className="text-surface-300">{node.admin_state}</dd>
        </dl>
      </div>

      <div className="card p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-surface-100">Virtual machines on this node</h2>
          <button className="btn-secondary" onClick={() => navigate(`/vms/new?node=${node.uuid}`)}>
            + New VM
          </button>
        </div>
        {!vmsQuery.data?.results.length ? (
          <p className="py-6 text-center text-xs text-surface-500">No VMs on this node.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>CPU</th>
                <th>Memory</th>
              </tr>
            </thead>
            <tbody>
              {vmsQuery.data.results.map((vm) => (
                <tr key={vm.uuid}>
                  <td>
                    <Link to={`/vms/${vm.uuid}`} className="font-medium text-surface-100 hover:text-accent-400">
                      {vm.name}
                    </Link>
                  </td>
                  <td>
                    <StatusBadge status={vm.status} />
                  </td>
                  <td>{vm.cpu_count}</td>
                  <td>{vm.memory_mb} MB</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

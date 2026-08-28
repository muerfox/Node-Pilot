import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import EmptyState from "@/components/EmptyState";
import ErrorBanner from "@/components/ErrorBanner";
import Modal from "@/components/Modal";
import PageHeader from "@/components/PageHeader";
import { OrganizationSelect } from "@/components/pickers";
import ProgressBar from "@/components/ProgressBar";
import { FullPageSpinner } from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { formatRelativeTime, percentage } from "@/lib/format";
import { nodes } from "@/lib/resources";

export default function NodesListPage() {
  const [showCreate, setShowCreate] = useState(false);
  const query = useQuery({ queryKey: ["nodes"], queryFn: () => nodes.list({ page_size: 100 }), refetchInterval: 15000 });

  return (
    <div>
      <PageHeader
        title="Nodes"
        description="Hypervisor hosts under management."
        actions={
          <button className="btn-primary" onClick={() => setShowCreate(true)}>
            + Register node
          </button>
        }
      />

      <ErrorBanner error={query.error} />

      {query.isLoading ? (
        <FullPageSpinner />
      ) : !query.data?.results.length ? (
        <EmptyState title="No nodes yet" description="Register a hypervisor to get started, then install the agent on it." />
      ) : (
        <div className="card overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Agent</th>
                <th>Memory</th>
                <th>Storage</th>
                <th>VMs</th>
                <th>Last seen</th>
              </tr>
            </thead>
            <tbody>
              {query.data.results.map((node) => (
                <tr key={node.uuid} className="cursor-pointer">
                  <td>
                    <Link to={`/nodes/${node.uuid}`} className="font-medium text-surface-100 hover:text-accent-400">
                      {node.name}
                    </Link>
                    <p className="text-xs text-surface-500">{node.hostname}</p>
                  </td>
                  <td>
                    <StatusBadge status={node.status} />
                  </td>
                  <td>
                    <StatusBadge status={node.agent?.status ?? "DISABLED"} />
                  </td>
                  <td className="w-40">
                    <div className="flex items-center gap-2">
                      <ProgressBar percent={percentage(node.memory_total_mb - node.memory_available_mb, node.memory_total_mb)} className="w-20" />
                      <span className="text-xs text-surface-400">{Math.round(node.memory_available_mb / 1024)} GB free</span>
                    </div>
                  </td>
                  <td className="w-40">
                    <div className="flex items-center gap-2">
                      <ProgressBar percent={percentage(node.storage_total_gb - node.storage_available_gb, node.storage_total_gb)} className="w-20" />
                      <span className="text-xs text-surface-400">{node.storage_available_gb} GB free</span>
                    </div>
                  </td>
                  <td>{node.reported_vm_count}</td>
                  <td className="text-xs text-surface-400">{formatRelativeTime(node.last_seen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && <CreateNodeModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

function CreateNodeModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [organization, setOrganization] = useState("");
  const [name, setName] = useState("");
  const [hostname, setHostname] = useState("");
  const [fqdn, setFqdn] = useState("");

  const mutation = useMutation({
    mutationFn: () => nodes.create({ organization, name, hostname, fqdn }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["nodes"] });
      onClose();
    },
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    mutation.mutate();
  }

  return (
    <Modal title="Register a node" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="label">Organization</label>
          <OrganizationSelect value={organization} onChange={setOrganization} required />
        </div>
        <div>
          <label className="label">Name</label>
          <input className="input" required value={name} onChange={(e) => setName(e.target.value)} placeholder="node-01" />
        </div>
        <div>
          <label className="label">Hostname</label>
          <input className="input" required value={hostname} onChange={(e) => setHostname(e.target.value)} placeholder="node-01.internal" />
        </div>
        <div>
          <label className="label">FQDN (optional)</label>
          <input className="input" value={fqdn} onChange={(e) => setFqdn(e.target.value)} placeholder="node-01.example.com" />
        </div>

        <ErrorBanner error={mutation.error} />

        <p className="text-xs text-surface-500">
          After registering, open the node and click "Issue agent token" to get the credential for `/etc/nodepilot/agent.yaml` on the host.
        </p>

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? "Registering..." : "Register"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

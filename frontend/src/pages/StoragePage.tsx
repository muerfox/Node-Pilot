import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import EmptyState from "@/components/EmptyState";
import ErrorBanner from "@/components/ErrorBanner";
import Modal from "@/components/Modal";
import PageHeader from "@/components/PageHeader";
import { NodeSelect } from "@/components/pickers";
import ProgressBar from "@/components/ProgressBar";
import { FullPageSpinner } from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { formatBytes, percentage } from "@/lib/format";
import { storagePools } from "@/lib/resources";
import type { StorageType } from "@/types/api";

export default function StoragePage() {
  const [showCreate, setShowCreate] = useState(false);
  const query = useQuery({ queryKey: ["storages"], queryFn: () => storagePools.list({ page_size: 100 }) });

  return (
    <div>
      <PageHeader
        title="Storage"
        description="Storage pools exposed by each node."
        actions={
          <button className="btn-primary" onClick={() => setShowCreate(true)}>
            + Add pool
          </button>
        }
      />

      <ErrorBanner error={query.error} />

      {query.isLoading ? (
        <FullPageSpinner />
      ) : !query.data?.results.length ? (
        <EmptyState title="No storage pools" description="Register a pool on a node before creating VMs or uploading images." />
      ) : (
        <div className="card overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Status</th>
                <th>Usage</th>
                <th>Capabilities</th>
                <th>Shared</th>
              </tr>
            </thead>
            <tbody>
              {query.data.results.map((pool) => (
                <tr key={pool.uuid}>
                  <td className="font-medium text-surface-100">{pool.name}</td>
                  <td>{pool.type}</td>
                  <td>
                    <StatusBadge status={pool.status} />
                  </td>
                  <td className="w-48">
                    <div className="flex items-center gap-2">
                      <ProgressBar percent={percentage(pool.used_bytes, pool.capacity_bytes)} className="w-24" />
                      <span className="text-xs text-surface-400">
                        {formatBytes(pool.available_bytes)} free
                      </span>
                    </div>
                  </td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {pool.capabilities.map((c) => (
                        <span key={c} className="rounded bg-surface-800 px-1.5 py-0.5 text-[10px] text-surface-400">
                          {c}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>{pool.shared ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && <CreatePoolModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

const STORAGE_TYPES: StorageType[] = ["DIRECTORY", "LVM", "LVM_THIN", "ZFS", "NFS", "CEPH_RBD"];

function CreatePoolModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [node, setNode] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState<StorageType>("DIRECTORY");
  const [path, setPath] = useState("");
  const [shared, setShared] = useState(false);

  const mutation = useMutation({
    mutationFn: () => storagePools.create({ node, name, type, path, shared }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["storages"] });
      onClose();
    },
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    mutation.mutate();
  }

  return (
    <Modal title="Add storage pool" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="label">Node</label>
          <NodeSelect value={node} onChange={setNode} />
        </div>
        <div>
          <label className="label">Name</label>
          <input className="input" required value={name} onChange={(e) => setName(e.target.value)} placeholder="local" />
        </div>
        <div>
          <label className="label">Type</label>
          <select className="input" value={type} onChange={(e) => setType(e.target.value as StorageType)}>
            {STORAGE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Path</label>
          <input className="input" required value={path} onChange={(e) => setPath(e.target.value)} placeholder="/var/lib/nodepilot/pools/local" />
          <p className="mt-1 text-xs text-surface-500">Mount point, volume group, dataset, or export path on the node -- see docs/architecture.md.</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-surface-200">
          <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />
          Shared (visible from more than one node -- required for migration)
        </label>

        <ErrorBanner error={mutation.error} />

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending || !node}>
            {mutation.isPending ? "Adding..." : "Add"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import EmptyState from "@/components/EmptyState";
import ErrorBanner from "@/components/ErrorBanner";
import PageHeader from "@/components/PageHeader";
import { FullPageSpinner } from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { vms } from "@/lib/resources";
import type { VMStatus } from "@/types/api";

const STATUS_FILTERS: (VMStatus | "")[] = ["", "RUNNING", "STOPPED", "CREATING", "PAUSED", "ERROR"];

export default function VMsListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<VMStatus | "">("");
  const [search, setSearch] = useState("");

  const query = useQuery({
    queryKey: ["vms", { status, search }],
    queryFn: () => vms.list({ status: status || undefined, search: search || undefined, page_size: 100 }),
    refetchInterval: 10000,
  });

  const startMutation = useMutation({ mutationFn: vms.start, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["vms"] }) });
  const stopMutation = useMutation({ mutationFn: (uuid: string) => vms.stop(uuid), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["vms"] }) });

  return (
    <div>
      <PageHeader
        title="Virtual Machines"
        actions={
          <button className="btn-primary" onClick={() => navigate("/vms/new")}>
            + New VM
          </button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input className="input max-w-xs" placeholder="Search by name or hostname..." value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="flex gap-1">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s || "all"}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${status === s ? "bg-accent-500/15 text-accent-400" : "text-surface-400 hover:bg-surface-800"}`}
              onClick={() => setStatus(s)}
            >
              {s || "All"}
            </button>
          ))}
        </div>
      </div>

      <ErrorBanner error={query.error ?? startMutation.error ?? stopMutation.error} />

      {query.isLoading ? (
        <FullPageSpinner />
      ) : !query.data?.results.length ? (
        <EmptyState title="No virtual machines found" action={<button className="btn-primary mt-2" onClick={() => navigate("/vms/new")}>Create your first VM</button>} />
      ) : (
        <div className="card overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>CPU</th>
                <th>Memory</th>
                <th>Disks</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {query.data.results.map((vm) => (
                <tr key={vm.uuid}>
                  <td>
                    <Link to={`/vms/${vm.uuid}`} className="font-medium text-surface-100 hover:text-accent-400">
                      {vm.name}
                    </Link>
                    {vm.hostname && <p className="text-xs text-surface-500">{vm.hostname}</p>}
                  </td>
                  <td>
                    <StatusBadge status={vm.status} />
                  </td>
                  <td>{vm.cpu_count}</td>
                  <td>{vm.memory_mb} MB</td>
                  <td>{vm.disks.reduce((sum, d) => sum + d.size_bytes, 0) / 1024 ** 3} GB</td>
                  <td className="text-right">
                    {vm.status === "STOPPED" && (
                      <button className="btn-ghost !py-1 !px-2 text-xs" onClick={() => startMutation.mutate(vm.uuid)}>
                        Start
                      </button>
                    )}
                    {vm.status === "RUNNING" && (
                      <button className="btn-ghost !py-1 !px-2 text-xs" onClick={() => stopMutation.mutate(vm.uuid)}>
                        Stop
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

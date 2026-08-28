import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import ErrorBanner from "@/components/ErrorBanner";
import { FullPageSpinner } from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { formatDateTime } from "@/lib/format";
import { jobs } from "@/lib/resources";

const CANCELABLE = ["QUEUED", "RUNNING"];

export default function TasksTab({ vmUuid }: { vmUuid: string }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["jobs", "vm", vmUuid], queryFn: () => jobs.list({ resource_type: "VirtualMachine", resource_id: vmUuid, page_size: 100 }), refetchInterval: 8000 });
  const cancelMutation = useMutation({ mutationFn: jobs.cancel, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs", "vm", vmUuid] }) });

  if (query.isLoading) return <FullPageSpinner />;
  if (!query.data?.results.length) return <p className="py-8 text-center text-xs text-surface-500">No tasks yet.</p>;

  return (
    <div className="space-y-2">
      <ErrorBanner error={cancelMutation.error} />
      <div className="card overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Type</th>
              <th>Status</th>
              <th>Progress</th>
              <th>Message</th>
              <th>Started</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {query.data.results.map((job) => (
              <tr key={job.uuid}>
                <td>{job.type.replaceAll("_", " ")}</td>
                <td>
                  <StatusBadge status={job.status} />
                </td>
                <td>{job.progress}%</td>
                <td className="max-w-xs truncate text-xs text-surface-400" title={job.error || job.message}>
                  {job.error || job.message}
                </td>
                <td className="text-xs text-surface-400">{formatDateTime(job.started_at ?? job.created_at)}</td>
                <td className="text-right">
                  {CANCELABLE.includes(job.status) && (
                    <button className="btn-ghost !py-1 !px-2 text-xs" onClick={() => cancelMutation.mutate(job.uuid)}>
                      Cancel
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

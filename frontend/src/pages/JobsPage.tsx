import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import ErrorBanner from "@/components/ErrorBanner";
import PageHeader from "@/components/PageHeader";
import ProgressBar from "@/components/ProgressBar";
import { FullPageSpinner } from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { formatDateTime, formatRelativeTime } from "@/lib/format";
import { jobs } from "@/lib/resources";
import type { JobStatus } from "@/types/api";

const STATUS_FILTERS: (JobStatus | "")[] = ["", "QUEUED", "RUNNING", "SUCCESS", "FAILED", "CANCELED"];
const CANCELABLE = ["QUEUED", "RUNNING"];

export default function JobsPage() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<JobStatus | "">("");
  const query = useQuery({ queryKey: ["jobs", "all", status], queryFn: () => jobs.list({ status: status || undefined, page_size: 100 }), refetchInterval: 6000 });
  const cancelMutation = useMutation({ mutationFn: jobs.cancel, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs", "all"] }) });

  return (
    <div>
      <PageHeader title="Jobs" description="Every background operation NodePilot has run." />

      <div className="mb-4 flex gap-1">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s || "all"}
            className={`rounded-md px-2.5 py-1 text-xs font-medium ${status === s ? "bg-accent-500/15 text-accent-400" : "text-surface-400 hover:bg-surface-800"}`}
            onClick={() => setStatus(s)}
          >
            {s || "All"}
          </button>
        ))}
      </div>

      <ErrorBanner error={query.error ?? cancelMutation.error} />

      {query.isLoading ? (
        <FullPageSpinner />
      ) : !query.data?.results.length ? (
        <p className="py-8 text-center text-xs text-surface-500">No jobs found.</p>
      ) : (
        <div className="card overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Type</th>
                <th>Resource</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {query.data.results.map((job) => (
                <tr key={job.uuid}>
                  <td>{job.type.replaceAll("_", " ")}</td>
                  <td className="text-xs text-surface-400">
                    {job.resource_type}:{job.resource_id.slice(0, 8)}
                  </td>
                  <td>
                    <StatusBadge status={job.status} />
                  </td>
                  <td className="w-40">
                    <ProgressBar percent={job.progress} className="w-28" />
                  </td>
                  <td className="text-xs text-surface-400" title={formatDateTime(job.created_at)}>
                    {formatRelativeTime(job.created_at)}
                  </td>
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
      )}
    </div>
  );
}

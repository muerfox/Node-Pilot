import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import ProgressBar from "@/components/ProgressBar";
import StatusBadge from "@/components/StatusBadge";
import { jobs } from "@/lib/resources";
import { useWebSocketSubscription } from "@/lib/ws";
import type { Job } from "@/types/api";

const TERMINAL: Job["status"][] = ["SUCCESS", "FAILED", "CANCELED"];

/**
 * Live progress for one Job (section 19's `Creating VM  [####----] 72%`
 * mockup), driven by /ws/jobs/{id}. Falls back to the REST snapshot
 * until the socket delivers its first frame, and calls `onSettled` once
 * the job reaches a terminal state so callers can refresh whatever list
 * the job was mutating.
 */
export default function JobTracker({ jobId, onSettled, compact = false }: { jobId: string; onSettled?: (job: Job) => void; compact?: boolean }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["jobs", jobId], queryFn: () => jobs.get(jobId) });

  useWebSocketSubscription(`/ws/jobs/${jobId}`, (data) => {
    const message = data as { type?: string; job?: Partial<Job> };
    if (!message.job) return;
    queryClient.setQueryData<Job | undefined>(["jobs", jobId], (prev) => (prev ? { ...prev, ...message.job } : (message.job as Job)));
  });

  const job = query.data;

  useEffect(() => {
    if (job && TERMINAL.includes(job.status)) onSettled?.(job);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status]);

  if (!job) return null;

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <StatusBadge status={job.status} />
        {!TERMINAL.includes(job.status) && <ProgressBar percent={job.progress} className="w-16" />}
        <span className="truncate text-xs text-surface-400">{job.message}</span>
      </div>
    );
  }

  return (
    <div className="card space-y-2 p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-surface-100">{job.type.replaceAll("_", " ")}</span>
        <StatusBadge status={job.status} />
      </div>
      <ProgressBar percent={job.progress} />
      <p className="text-xs text-surface-400">{job.message || "Waiting to start..."}</p>
      {job.status === "FAILED" && job.error && <p className="text-xs text-status-error">{job.error}</p>}
    </div>
  );
}

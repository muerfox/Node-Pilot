const STATUS_STYLES: Record<string, string> = {
  // Nodes
  ONLINE: "bg-status-online/15 text-status-online",
  OFFLINE: "bg-status-offline/20 text-surface-300",
  WARNING: "bg-status-warning/15 text-status-warning",
  MAINTENANCE: "bg-accent-500/15 text-accent-400",
  DISABLED: "bg-surface-800 text-surface-400",
  // VMs
  RUNNING: "bg-status-online/15 text-status-online",
  STOPPED: "bg-surface-800 text-surface-300",
  CREATING: "bg-accent-500/15 text-accent-400",
  DELETING: "bg-status-warning/15 text-status-warning",
  PAUSED: "bg-status-warning/15 text-status-warning",
  SUSPENDED: "bg-status-warning/15 text-status-warning",
  MIGRATING: "bg-accent-500/15 text-accent-400",
  ERROR: "bg-status-error/15 text-status-error",
  UNKNOWN: "bg-surface-800 text-surface-400",
  // Jobs
  QUEUED: "bg-surface-800 text-surface-300",
  SUCCESS: "bg-status-online/15 text-status-online",
  FAILED: "bg-status-error/15 text-status-error",
  CANCELING: "bg-status-warning/15 text-status-warning",
  CANCELED: "bg-surface-800 text-surface-400",
  // generic
  ACTIVE: "bg-status-online/15 text-status-online",
  REVOKED: "bg-status-error/15 text-status-error",
  FAILURE: "bg-status-error/15 text-status-error",
  CRITICAL: "bg-status-error/15 text-status-error",
  INFO: "bg-accent-500/15 text-accent-400",
};

export default function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? "bg-surface-800 text-surface-300";
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${style}`}>{status}</span>;
}

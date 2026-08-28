import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import ConfirmButton from "@/components/ConfirmButton";
import ErrorBanner from "@/components/ErrorBanner";
import JobTracker from "@/components/JobTracker";
import Modal from "@/components/Modal";
import { FullPageSpinner } from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { formatBytes, formatDateTime } from "@/lib/format";
import { backupTargets, backups } from "@/lib/resources";

export default function BackupsTab({ vmUuid, organization }: { vmUuid: string; organization: string }) {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [activeJob, setActiveJob] = useState<string | null>(null);

  const query = useQuery({ queryKey: ["backups", vmUuid], queryFn: () => backups.list({ vm: vmUuid, page_size: 100 }) });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["backups", vmUuid] });

  const restoreMutation = useMutation({ mutationFn: backups.restore, onSuccess: (data) => setActiveJob(data.job_id) });
  const deleteMutation = useMutation({ mutationFn: backups.remove, onSuccess: invalidate });

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button className="btn-primary" onClick={() => setShowCreate(true)}>
          + Create backup
        </button>
      </div>

      <ErrorBanner error={query.error ?? restoreMutation.error ?? deleteMutation.error} />
      {activeJob && <JobTracker jobId={activeJob} compact onSettled={() => { invalidate(); setActiveJob(null); }} />}

      {query.isLoading ? (
        <FullPageSpinner />
      ) : !query.data?.results.length ? (
        <p className="py-8 text-center text-xs text-surface-500">No backups yet.</p>
      ) : (
        <div className="card overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Type</th>
                <th>Status</th>
                <th>Size</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {query.data.results.map((backup) => (
                <tr key={backup.uuid}>
                  <td>{backup.type}</td>
                  <td>
                    <StatusBadge status={backup.status} />
                  </td>
                  <td>{formatBytes(backup.size_bytes)}</td>
                  <td className="text-xs text-surface-400">{formatDateTime(backup.created_at)}</td>
                  <td className="text-right">
                    <div className="flex justify-end gap-1.5">
                      {backup.status === "COMPLETED" && (
                        <ConfirmButton className="btn-ghost !py-1 !px-2 text-xs" onConfirm={() => restoreMutation.mutate(backup.uuid)} confirmLabel="Confirm restore">
                          Restore
                        </ConfirmButton>
                      )}
                      <ConfirmButton className="btn-ghost !py-1 !px-2 text-xs text-status-error" onConfirm={() => deleteMutation.mutate(backup.uuid)}>
                        Delete
                      </ConfirmButton>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <CreateBackupModal
          vmUuid={vmUuid}
          organization={organization}
          onClose={() => setShowCreate(false)}
          onCreated={(jobId) => {
            setActiveJob(jobId);
            setShowCreate(false);
          }}
        />
      )}
    </div>
  );
}

function CreateBackupModal({ vmUuid, organization, onClose, onCreated }: { vmUuid: string; organization: string; onClose: () => void; onCreated: (jobId: string) => void }) {
  const [target, setTarget] = useState("");
  const [type, setType] = useState("FULL");
  const targetsQuery = useQuery({ queryKey: ["backup-targets", organization], queryFn: () => backupTargets.list({ organization, page_size: 100 }) });

  const mutation = useMutation({
    mutationFn: () => backups.create(vmUuid, target, type),
    onSuccess: (data) => data.job_id && onCreated(data.job_id),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    mutation.mutate();
  }

  return (
    <Modal title="Create backup" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="label">Target</label>
          <select className="input" required value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">Select a backup target...</option>
            {targetsQuery.data?.results.map((t) => (
              <option key={t.uuid} value={t.uuid}>
                {t.name} ({t.type})
              </option>
            ))}
          </select>
          {!targetsQuery.data?.results.length && !targetsQuery.isLoading && (
            <p className="mt-1 text-xs text-surface-500">No backup targets configured yet -- add one from the Backups page.</p>
          )}
        </div>
        <div>
          <label className="label">Type</label>
          <select className="input" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="FULL">Full</option>
            <option value="INCREMENTAL">Incremental</option>
            <option value="SNAPSHOT">Snapshot-based</option>
          </select>
        </div>
        <ErrorBanner error={mutation.error} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending || !target}>
            Create
          </button>
        </div>
      </form>
    </Modal>
  );
}

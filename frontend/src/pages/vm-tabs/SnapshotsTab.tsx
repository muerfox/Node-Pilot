import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import ConfirmButton from "@/components/ConfirmButton";
import ErrorBanner from "@/components/ErrorBanner";
import JobTracker from "@/components/JobTracker";
import Modal from "@/components/Modal";
import { FullPageSpinner } from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { formatBytes, formatDateTime } from "@/lib/format";
import { snapshots } from "@/lib/resources";

export default function SnapshotsTab({ vmUuid }: { vmUuid: string }) {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [activeJob, setActiveJob] = useState<string | null>(null);

  const query = useQuery({ queryKey: ["snapshots", vmUuid], queryFn: () => snapshots.list({ vm: vmUuid, page_size: 100 }) });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["snapshots", vmUuid] });

  const rollbackMutation = useMutation({ mutationFn: snapshots.rollback, onSuccess: (data) => setActiveJob(data.job_id) });
  const deleteMutation = useMutation({ mutationFn: snapshots.remove, onSuccess: (data) => setActiveJob(data.job_id) });

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button className="btn-primary" onClick={() => setShowCreate(true)}>
          + Create snapshot
        </button>
      </div>

      <ErrorBanner error={query.error ?? rollbackMutation.error ?? deleteMutation.error} />
      {activeJob && <JobTracker jobId={activeJob} compact onSettled={() => { invalidate(); setActiveJob(null); }} />}

      {query.isLoading ? (
        <FullPageSpinner />
      ) : !query.data?.results.length ? (
        <p className="py-8 text-center text-xs text-surface-500">No snapshots yet.</p>
      ) : (
        <div className="card overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Size</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {query.data.results.map((snap) => (
                <tr key={snap.uuid}>
                  <td className="font-medium text-surface-100">
                    {snap.name}
                    {snap.description && <p className="text-xs text-surface-500">{snap.description}</p>}
                  </td>
                  <td>
                    <StatusBadge status={snap.status} />
                  </td>
                  <td>{formatBytes(snap.size_bytes)}</td>
                  <td className="text-xs text-surface-400">{formatDateTime(snap.created_at)}</td>
                  <td className="text-right">
                    <div className="flex justify-end gap-1.5">
                      <ConfirmButton className="btn-ghost !py-1 !px-2 text-xs" onConfirm={() => rollbackMutation.mutate(snap.uuid)} confirmLabel="Confirm rollback">
                        Rollback
                      </ConfirmButton>
                      <ConfirmButton className="btn-ghost !py-1 !px-2 text-xs text-status-error" onConfirm={() => deleteMutation.mutate(snap.uuid)}>
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
        <CreateSnapshotModal
          vmUuid={vmUuid}
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

function CreateSnapshotModal({ vmUuid, onClose, onCreated }: { vmUuid: string; onClose: () => void; onCreated: (jobId: string) => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const mutation = useMutation({
    mutationFn: () => snapshots.create(vmUuid, name, description),
    onSuccess: (data) => data.job_id && onCreated(data.job_id),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    mutation.mutate();
  }

  return (
    <Modal title="Create snapshot" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="label">Name</label>
          <input className="input" required value={name} onChange={(e) => setName(e.target.value)} placeholder="pre-upgrade" />
        </div>
        <div>
          <label className="label">Description</label>
          <textarea className="input" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <ErrorBanner error={mutation.error} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            Create
          </button>
        </div>
      </form>
    </Modal>
  );
}

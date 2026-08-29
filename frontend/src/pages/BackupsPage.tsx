import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import ConfirmButton from "@/components/ConfirmButton";
import EmptyState from "@/components/EmptyState";
import ErrorBanner from "@/components/ErrorBanner";
import Modal from "@/components/Modal";
import { OrganizationSelect } from "@/components/pickers";
import PageHeader from "@/components/PageHeader";
import { FullPageSpinner } from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { formatBytes, formatDateTime } from "@/lib/format";
import { backupSchedules, backupTargets, backups } from "@/lib/resources";
import type { BackupTarget } from "@/types/api";

const SUBTABS = ["Backups", "Schedules", "Targets"] as const;

export default function BackupsPage() {
  const [tab, setTab] = useState<(typeof SUBTABS)[number]>("Backups");
  const [showAddTarget, setShowAddTarget] = useState(false);

  return (
    <div>
      <PageHeader
        title="Backups"
        actions={
          tab === "Targets" ? (
            <button className="btn-primary" onClick={() => setShowAddTarget(true)}>
              + Add target
            </button>
          ) : undefined
        }
      />

      <div className="mb-4 flex gap-1">
        {SUBTABS.map((t) => (
          <button key={t} className={`rounded-md px-2.5 py-1 text-xs font-medium ${tab === t ? "bg-accent-500/15 text-accent-400" : "text-surface-400 hover:bg-surface-800"}`} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      {tab === "Backups" && <BackupsList />}
      {tab === "Schedules" && <SchedulesList />}
      {tab === "Targets" && <TargetsList />}

      {showAddTarget && <AddTargetModal onClose={() => setShowAddTarget(false)} />}
    </div>
  );
}

function BackupsList() {
  const query = useQuery({ queryKey: ["backups", "all"], queryFn: () => backups.list({ page_size: 100 }) });
  if (query.isLoading) return <FullPageSpinner />;
  if (!query.data?.results.length) return <EmptyState title="No backups yet" description="Create one from a VM's Backups tab." />;

  return (
    <div className="card overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>VM</th>
            <th>Type</th>
            <th>Status</th>
            <th>Size</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {query.data.results.map((b) => (
            <tr key={b.uuid}>
              <td className="font-mono text-xs">{b.vm.slice(0, 8)}</td>
              <td>{b.type}</td>
              <td>
                <StatusBadge status={b.status} />
              </td>
              <td>{formatBytes(b.size_bytes)}</td>
              <td className="text-xs text-surface-400">{formatDateTime(b.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SchedulesList() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["backup-schedules"], queryFn: () => backupSchedules.list({ page_size: 100 }) });
  const deleteMutation = useMutation({ mutationFn: backupSchedules.remove, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["backup-schedules"] }) });

  if (query.isLoading) return <FullPageSpinner />;
  if (!query.data?.results.length) return <EmptyState title="No schedules configured" description="Scheduled backups run via Celery Beat -- create one via the API for now (POST /backup-schedules/)." />;

  return (
    <div className="card overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>VM</th>
            <th>Target</th>
            <th>Cron</th>
            <th>Retention</th>
            <th>Enabled</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {query.data.results.map((s) => (
            <tr key={s.uuid}>
              <td className="font-mono text-xs">{s.vm.slice(0, 8)}</td>
              <td className="font-mono text-xs">{s.target.slice(0, 8)}</td>
              <td className="font-mono text-xs">{s.cron_expression}</td>
              <td>{s.retention_days}d</td>
              <td>{s.enabled ? "yes" : "no"}</td>
              <td className="text-right">
                <ConfirmButton className="btn-ghost !py-1 !px-2 text-xs text-status-error" onConfirm={() => deleteMutation.mutate(s.uuid)}>
                  Delete
                </ConfirmButton>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TargetsList() {
  const query = useQuery({ queryKey: ["backup-targets", "all"], queryFn: () => backupTargets.list({ page_size: 100 }) });
  if (query.isLoading) return <FullPageSpinner />;
  if (!query.data?.results.length) return <EmptyState title="No backup targets" description="Add a target (Local, NFS, S3, MinIO, Ceph) to enable backups." />;

  return (
    <div className="card overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Enabled</th>
          </tr>
        </thead>
        <tbody>
          {query.data.results.map((t) => (
            <tr key={t.uuid}>
              <td className="font-medium text-surface-100">{t.name}</td>
              <td>{t.type}</td>
              <td>{t.enabled ? "yes" : "no"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const _S3_LIKE_TYPES: BackupTarget["type"][] = ["S3", "MINIO", "CEPH"];

function AddTargetModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [organization, setOrganization] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState<BackupTarget["type"]>("LOCAL");

  // LOCAL/NFS
  const [path, setPath] = useState("");

  // S3/MinIO/Ceph (RGW) -- all speak the S3 API, endpointUrl is what
  // tells them apart from real AWS S3 (leave blank for real S3).
  const [bucket, setBucket] = useState("");
  const [endpointUrl, setEndpointUrl] = useState("");
  const [region, setRegion] = useState("us-east-1");
  const [prefix, setPrefix] = useState("nodepilot-backups");
  const [accessKeyId, setAccessKeyId] = useState("");
  const [secretAccessKey, setSecretAccessKey] = useState("");

  const isS3Like = _S3_LIKE_TYPES.includes(type);

  const mutation = useMutation({
    mutationFn: () =>
      backupTargets.create({
        organization,
        name,
        type,
        config: isS3Like
          ? { bucket, endpoint_url: endpointUrl || undefined, region, prefix, access_key_id: accessKeyId, secret_access_key: secretAccessKey }
          : { path },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["backup-targets", "all"] });
      onClose();
    },
  });

  return (
    <Modal title="Add backup target" onClose={onClose}>
      <form
        className="space-y-3"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <div>
          <label className="label">Organization</label>
          <OrganizationSelect value={organization} onChange={setOrganization} required />
        </div>
        <div>
          <label className="label">Name</label>
          <input className="input" required value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="label">Type</label>
          <select className="input" value={type} onChange={(e) => setType(e.target.value as BackupTarget["type"])}>
            <option value="LOCAL">Local</option>
            <option value="NFS">NFS</option>
            <option value="S3">S3</option>
            <option value="MINIO">MinIO</option>
            <option value="CEPH">Ceph (RGW, S3-compatible)</option>
          </select>
        </div>

        {!isS3Like && (
          <div>
            <label className="label">Path</label>
            <input className="input" required value={path} onChange={(e) => setPath(e.target.value)} placeholder="/var/lib/nodepilot/backups" />
          </div>
        )}

        {isS3Like && (
          <>
            <div>
              <label className="label">Bucket</label>
              <input className="input" required value={bucket} onChange={(e) => setBucket(e.target.value)} placeholder="nodepilot-backups" />
            </div>
            {type !== "S3" && (
              <div>
                <label className="label">Endpoint URL</label>
                <input className="input" required value={endpointUrl} onChange={(e) => setEndpointUrl(e.target.value)} placeholder="https://minio.example.com" />
              </div>
            )}
            <div>
              <label className="label">Region</label>
              <input className="input" value={region} onChange={(e) => setRegion(e.target.value)} />
            </div>
            <div>
              <label className="label">Key prefix</label>
              <input className="input" value={prefix} onChange={(e) => setPrefix(e.target.value)} />
            </div>
            <div>
              <label className="label">Access key ID</label>
              <input className="input" required value={accessKeyId} onChange={(e) => setAccessKeyId(e.target.value)} />
            </div>
            <div>
              <label className="label">Secret access key</label>
              <input className="input" required type="password" value={secretAccessKey} onChange={(e) => setSecretAccessKey(e.target.value)} />
            </div>
          </>
        )}

        <ErrorBanner error={mutation.error} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending || !organization}>
            Add
          </button>
        </div>
      </form>
    </Modal>
  );
}

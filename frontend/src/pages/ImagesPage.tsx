import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import ConfirmButton from "@/components/ConfirmButton";
import EmptyState from "@/components/EmptyState";
import ErrorBanner from "@/components/ErrorBanner";
import Modal from "@/components/Modal";
import { StorageSelect } from "@/components/pickers";
import ProgressBar from "@/components/ProgressBar";
import { FullPageSpinner } from "@/components/Spinner";
import PageHeader from "@/components/PageHeader";
import StatusBadge from "@/components/StatusBadge";
import { getAccessToken } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { images } from "@/lib/resources";
import { uploadImage } from "@/lib/upload";
import type { Image, ImageType } from "@/types/api";

// A plain <a href> can't carry the Authorization header the download
// endpoint requires (browsers never attach custom headers to a
// navigation), so this fetches with the JWT and hands the browser a
// blob: URL instead.
async function downloadImage(image: Image) {
  const token = getAccessToken();
  const response = await fetch(`/api/v1/images/${image.uuid}/download/`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) return;
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${image.name}.${image.format || "img"}`;
  link.click();
  URL.revokeObjectURL(url);
}

export default function ImagesPage() {
  const queryClient = useQueryClient();
  const [showUpload, setShowUpload] = useState(false);
  const query = useQuery({ queryKey: ["images"], queryFn: () => images.list({ page_size: 100 }) });
  const deleteMutation = useMutation({ mutationFn: images.remove, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["images"] }) });

  return (
    <div>
      <PageHeader
        title="Images"
        description="ISO / QCOW2 / RAW / VMDK library."
        actions={
          <button className="btn-primary" onClick={() => setShowUpload(true)}>
            + Upload
          </button>
        }
      />

      <ErrorBanner error={query.error ?? deleteMutation.error} />

      {query.isLoading ? (
        <FullPageSpinner />
      ) : !query.data?.results.length ? (
        <EmptyState title="No images yet" description="Upload an ISO or disk image to use as a VM template source." />
      ) : (
        <div className="card overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Status</th>
                <th>Size</th>
                <th>SHA-256</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {query.data.results.map((image) => (
                <tr key={image.uuid}>
                  <td className="font-medium text-surface-100">
                    {image.name} {image.version}
                  </td>
                  <td>{image.type}</td>
                  <td>
                    <StatusBadge status={image.status} />
                  </td>
                  <td>{formatBytes(image.size_bytes)}</td>
                  <td className="max-w-[10rem] truncate font-mono text-xs text-surface-500" title={image.sha256}>
                    {image.sha256 || "-"}
                  </td>
                  <td className="text-right">
                    <div className="flex justify-end gap-1.5">
                      {image.status === "READY" && (
                        <button className="btn-ghost !py-1 !px-2 text-xs" onClick={() => downloadImage(image)}>
                          Download
                        </button>
                      )}
                      <ConfirmButton className="btn-ghost !py-1 !px-2 text-xs text-status-error" onConfirm={() => deleteMutation.mutate(image.uuid)}>
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

      {showUpload && <UploadModal onClose={() => setShowUpload(false)} />}
    </div>
  );
}

const IMAGE_TYPES: ImageType[] = ["ISO", "QCOW2", "RAW", "VMDK"];

function UploadModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [version, setVersion] = useState("");
  const [type, setType] = useState<ImageType>("ISO");
  const [storage, setStorage] = useState("");
  const [progress, setProgress] = useState<{ sentBytes: number; totalBytes: number } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [uploading, setUploading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadImage(file, { name, version, type, storage }, setProgress);
      queryClient.invalidateQueries({ queryKey: ["images"] });
      onClose();
    } catch (err) {
      setError(err);
    } finally {
      setUploading(false);
    }
  }

  return (
    <Modal title="Upload image" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="label">File</label>
          <input
            type="file"
            className="input"
            required
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setFile(f);
              if (f && !name) setName(f.name.replace(/\.[^.]+$/, ""));
            }}
          />
        </div>
        <div>
          <label className="label">Name</label>
          <input className="input" required value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="label">Version</label>
          <input className="input" value={version} onChange={(e) => setVersion(e.target.value)} placeholder="24.04" />
        </div>
        <div>
          <label className="label">Type</label>
          <select className="input" value={type} onChange={(e) => setType(e.target.value as ImageType)}>
            {IMAGE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Storage pool</label>
          <StorageSelect value={storage} onChange={setStorage} required />
        </div>

        {progress && (
          <div>
            <ProgressBar percent={(progress.sentBytes / progress.totalBytes) * 100} />
            <p className="mt-1 text-xs text-surface-500">
              {formatBytes(progress.sentBytes)} / {formatBytes(progress.totalBytes)}
            </p>
          </div>
        )}

        <ErrorBanner error={error} />

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose} disabled={uploading}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={uploading || !file || !storage}>
            {uploading ? "Uploading..." : "Upload"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

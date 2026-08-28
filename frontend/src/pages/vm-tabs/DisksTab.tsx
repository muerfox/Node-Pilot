import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import ConfirmButton from "@/components/ConfirmButton";
import ErrorBanner from "@/components/ErrorBanner";
import JobTracker from "@/components/JobTracker";
import Modal from "@/components/Modal";
import { StorageSelect } from "@/components/pickers";
import { formatBytes } from "@/lib/format";
import { vms } from "@/lib/resources";
import type { VirtualMachine } from "@/types/api";

export default function DisksTab({ vm }: { vm: VirtualMachine }) {
  const queryClient = useQueryClient();
  const [showAttach, setShowAttach] = useState(false);
  const [activeJob, setActiveJob] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["vms", vm.uuid] });

  const removeMutation = useMutation({
    mutationFn: (diskUuid: string) => vms.removeDisk(vm.uuid, diskUuid),
    onSuccess: (data) => setActiveJob(data.job_id),
  });

  const resizeMutation = useMutation({
    mutationFn: ({ diskUuid, sizeGb }: { diskUuid: string; sizeGb: number }) => vms.resizeDisk(vm.uuid, diskUuid, sizeGb),
    onSuccess: (data) => setActiveJob(data.job_id),
  });

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button className="btn-primary" onClick={() => setShowAttach(true)}>
          + Attach disk
        </button>
      </div>

      <ErrorBanner error={removeMutation.error ?? resizeMutation.error} />
      {activeJob && <JobTracker jobId={activeJob} compact onSettled={() => { invalidate(); setActiveJob(null); }} />}

      <div className="card overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Size</th>
              <th>Bus</th>
              <th>Boot</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {vm.disks.map((disk) => (
              <tr key={disk.uuid}>
                <td>{disk.name}</td>
                <td>{formatBytes(disk.size_bytes)}</td>
                <td>{disk.bus}</td>
                <td>{disk.bootable ? "yes" : "no"}</td>
                <td className="text-right">
                  <div className="flex justify-end gap-1.5">
                    <button
                      className="btn-ghost !py-1 !px-2 text-xs"
                      onClick={() => {
                        const sizeGb = Number(prompt(`New size in GB (currently ${Math.round(disk.size_bytes / 1024 ** 3)} GB, grow only):`));
                        if (sizeGb > 0) resizeMutation.mutate({ diskUuid: disk.uuid, sizeGb });
                      }}
                    >
                      Resize
                    </button>
                    {!disk.bootable && (
                      <ConfirmButton className="btn-ghost !py-1 !px-2 text-xs text-status-error" onConfirm={() => removeMutation.mutate(disk.uuid)}>
                        Remove
                      </ConfirmButton>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showAttach && (
        <AttachDiskModal
          vmUuid={vm.uuid}
          onClose={() => setShowAttach(false)}
          onCreated={(jobId) => {
            setActiveJob(jobId);
            setShowAttach(false);
          }}
        />
      )}
    </div>
  );
}

function AttachDiskModal({ vmUuid, onClose, onCreated }: { vmUuid: string; onClose: () => void; onCreated: (jobId: string) => void }) {
  const [storage, setStorage] = useState("");
  const [sizeGb, setSizeGb] = useState(20);
  const [bus, setBus] = useState("VIRTIO");

  const mutation = useMutation({
    mutationFn: () => vms.attachDisk(vmUuid, { storage, size_gb: sizeGb, bus }),
    onSuccess: (data) => onCreated(data.job_id),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    mutation.mutate();
  }

  return (
    <Modal title="Attach disk" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="label">Storage pool</label>
          <StorageSelect value={storage} onChange={setStorage} required />
        </div>
        <div>
          <label className="label">Size (GB)</label>
          <input type="number" min={1} className="input" value={sizeGb} onChange={(e) => setSizeGb(Number(e.target.value))} />
        </div>
        <div>
          <label className="label">Bus</label>
          <select className="input" value={bus} onChange={(e) => setBus(e.target.value)}>
            <option value="VIRTIO">VirtIO</option>
            <option value="VIRTIO_SCSI">VirtIO SCSI</option>
            <option value="SATA">SATA</option>
            <option value="IDE">IDE</option>
          </select>
        </div>
        <ErrorBanner error={mutation.error} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending || !storage}>
            Attach
          </button>
        </div>
      </form>
    </Modal>
  );
}

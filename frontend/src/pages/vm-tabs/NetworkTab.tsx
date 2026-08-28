import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import ConfirmButton from "@/components/ConfirmButton";
import ErrorBanner from "@/components/ErrorBanner";
import JobTracker from "@/components/JobTracker";
import Modal from "@/components/Modal";
import { networks, vms } from "@/lib/resources";
import type { VirtualMachine } from "@/types/api";

export default function NetworkTab({ vm }: { vm: VirtualMachine }) {
  const queryClient = useQueryClient();
  const [showAttach, setShowAttach] = useState(false);
  const [activeJob, setActiveJob] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["vms", vm.uuid] });

  const removeMutation = useMutation({
    mutationFn: (nicUuid: string) => vms.removeNic(vm.uuid, nicUuid),
    onSuccess: (data) => setActiveJob(data.job_id),
  });

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button className="btn-primary" onClick={() => setShowAttach(true)}>
          + Attach NIC
        </button>
      </div>

      <ErrorBanner error={removeMutation.error} />
      {activeJob && <JobTracker jobId={activeJob} compact onSettled={() => { invalidate(); setActiveJob(null); }} />}

      <div className="card overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>MAC address</th>
              <th>Model</th>
              <th>VLAN</th>
              <th>IP</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {vm.nics.map((nic) => (
              <tr key={nic.uuid}>
                <td className="font-mono text-xs">{nic.mac_address}</td>
                <td>{nic.model}</td>
                <td>{nic.vlan ?? "-"}</td>
                <td>{nic.ip_address ?? "auto/none"}</td>
                <td className="text-right">
                  <ConfirmButton className="btn-ghost !py-1 !px-2 text-xs text-status-error" onConfirm={() => removeMutation.mutate(nic.uuid)}>
                    Remove
                  </ConfirmButton>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!vm.nics.length && <p className="py-6 text-center text-xs text-surface-500">No network interfaces attached.</p>}
      </div>

      {showAttach && (
        <AttachNicModal
          vm={vm}
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

function AttachNicModal({ vm, onClose, onCreated }: { vm: VirtualMachine; onClose: () => void; onCreated: (jobId: string) => void }) {
  const [network, setNetwork] = useState("");
  const [model, setModel] = useState("VIRTIO");

  const networksQuery = useQuery({ queryKey: ["networks", "picker", vm.node], queryFn: () => networks.list({ node: vm.node ?? undefined, page_size: 100 }) });

  const mutation = useMutation({
    mutationFn: () => vms.attachNic(vm.uuid, { network, model }),
    onSuccess: (data) => onCreated(data.job_id),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    mutation.mutate();
  }

  return (
    <Modal title="Attach network interface" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="label">Network</label>
          <select className="input" required value={network} onChange={(e) => setNetwork(e.target.value)}>
            <option value="">Select a network...</option>
            {networksQuery.data?.results.map((n) => (
              <option key={n.uuid} value={n.uuid}>
                {n.name} ({n.bridge}
                {n.vlan_id ? `.${n.vlan_id}` : ""})
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Model</label>
          <select className="input" value={model} onChange={(e) => setModel(e.target.value)}>
            <option value="VIRTIO">VirtIO</option>
            <option value="E1000">E1000</option>
          </select>
        </div>
        <ErrorBanner error={mutation.error} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending || !network}>
            Attach
          </button>
        </div>
      </form>
    </Modal>
  );
}

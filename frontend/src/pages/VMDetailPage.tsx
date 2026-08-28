import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import ConfirmButton from "@/components/ConfirmButton";
import ErrorBanner from "@/components/ErrorBanner";
import JobTracker from "@/components/JobTracker";
import Modal from "@/components/Modal";
import PageHeader from "@/components/PageHeader";
import { FullPageSpinner } from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { vms } from "@/lib/resources";
import { useWebSocketSubscription } from "@/lib/ws";
import BackupsTab from "@/pages/vm-tabs/BackupsTab";
import ConsoleTab from "@/pages/vm-tabs/ConsoleTab";
import DisksTab from "@/pages/vm-tabs/DisksTab";
import EventsTab from "@/pages/vm-tabs/EventsTab";
import HardwareTab from "@/pages/vm-tabs/HardwareTab";
import MetricsTab from "@/pages/vm-tabs/MetricsTab";
import NetworkTab from "@/pages/vm-tabs/NetworkTab";
import OverviewTab from "@/pages/vm-tabs/OverviewTab";
import SnapshotsTab from "@/pages/vm-tabs/SnapshotsTab";
import TasksTab from "@/pages/vm-tabs/TasksTab";
import type { VirtualMachine } from "@/types/api";

const TABS = ["Overview", "Console", "Hardware", "Disks", "Network", "Snapshots", "Backups", "Metrics", "Events", "Tasks"] as const;
type Tab = (typeof TABS)[number];

export default function VMDetailPage() {
  const { uuid = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("Overview");
  const [activeJob, setActiveJob] = useState<string | null>(null);
  const [cloneOpen, setCloneOpen] = useState(false);

  const query = useQuery({ queryKey: ["vms", uuid], queryFn: () => vms.get(uuid), enabled: !!uuid });

  useWebSocketSubscription(uuid ? `/ws/vms/${uuid}` : null, (data) => {
    const payload = data as { uuid?: string; status?: string; provisioning_state?: string };
    if (payload.uuid !== uuid) return;
    queryClient.setQueryData<VirtualMachine | undefined>(["vms", uuid], (prev) => (prev ? { ...prev, status: payload.status as VirtualMachine["status"], provisioning_state: payload.provisioning_state as VirtualMachine["provisioning_state"] } : prev));
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["vms", uuid] });

  const startMutation = useMutation({ mutationFn: () => vms.start(uuid), onSuccess: (d) => setActiveJob(d.job_id) });
  const stopMutation = useMutation({ mutationFn: () => vms.stop(uuid), onSuccess: (d) => setActiveJob(d.job_id) });
  const rebootMutation = useMutation({ mutationFn: () => vms.reboot(uuid), onSuccess: (d) => setActiveJob(d.job_id) });
  const pauseMutation = useMutation({ mutationFn: () => vms.pause(uuid), onSuccess: (d) => setActiveJob(d.job_id) });
  const resumeMutation = useMutation({ mutationFn: () => vms.resume(uuid), onSuccess: (d) => setActiveJob(d.job_id) });
  const deleteMutation = useMutation({
    mutationFn: () => vms.remove(uuid),
    onSuccess: () => navigate("/vms"),
  });

  if (query.isLoading) return <FullPageSpinner />;
  if (!query.data) return <ErrorBanner error={query.error} />;
  const vm = query.data;

  const anyMutationError = startMutation.error ?? stopMutation.error ?? rebootMutation.error ?? pauseMutation.error ?? resumeMutation.error ?? deleteMutation.error;
  const anyMutationPending = startMutation.isPending || stopMutation.isPending || rebootMutation.isPending || pauseMutation.isPending || resumeMutation.isPending;

  return (
    <div className="space-y-4">
      <PageHeader
        title={vm.name}
        description={
          <span className="flex items-center gap-2">
            <StatusBadge status={vm.status} />
            <span className="text-xs text-surface-500">{vm.uuid}</span>
          </span>
        }
        actions={
          <>
            {vm.status === "STOPPED" && (
              <button className="btn-secondary" onClick={() => startMutation.mutate()} disabled={anyMutationPending}>
                Start
              </button>
            )}
            {vm.status === "RUNNING" && (
              <>
                <button className="btn-secondary" onClick={() => pauseMutation.mutate()} disabled={anyMutationPending}>
                  Pause
                </button>
                <button className="btn-secondary" onClick={() => rebootMutation.mutate()} disabled={anyMutationPending}>
                  Reboot
                </button>
                <button className="btn-secondary" onClick={() => stopMutation.mutate()} disabled={anyMutationPending}>
                  Stop
                </button>
              </>
            )}
            {vm.status === "PAUSED" && (
              <button className="btn-secondary" onClick={() => resumeMutation.mutate()} disabled={anyMutationPending}>
                Resume
              </button>
            )}
            <button className="btn-secondary" onClick={() => setCloneOpen(true)}>
              Clone
            </button>
            <ConfirmButton onConfirm={() => deleteMutation.mutate()} disabled={deleteMutation.isPending}>
              Delete
            </ConfirmButton>
          </>
        }
      />

      <ErrorBanner error={anyMutationError} />
      {activeJob && <JobTracker jobId={activeJob} onSettled={() => { invalidate(); setActiveJob(null); }} />}

      <div className="flex gap-1 overflow-x-auto border-b border-surface-800 pb-px">
        {TABS.map((t) => (
          <button
            key={t}
            className={`shrink-0 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              tab === t ? "border-accent-500 text-accent-400" : "border-transparent text-surface-400 hover:text-surface-100"
            }`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      <div>
        {tab === "Overview" && <OverviewTab vm={vm} />}
        {tab === "Console" && <ConsoleTab vmUuid={vm.uuid} vmStatus={vm.status} />}
        {tab === "Hardware" && <HardwareTab vm={vm} />}
        {tab === "Disks" && <DisksTab vm={vm} />}
        {tab === "Network" && <NetworkTab vm={vm} />}
        {tab === "Snapshots" && <SnapshotsTab vmUuid={vm.uuid} />}
        {tab === "Backups" && <BackupsTab vmUuid={vm.uuid} organization={vm.organization} />}
        {tab === "Metrics" && <MetricsTab vmUuid={vm.uuid} />}
        {tab === "Events" && <EventsTab vmUuid={vm.uuid} />}
        {tab === "Tasks" && <TasksTab vmUuid={vm.uuid} />}
      </div>

      {cloneOpen && <CloneModal vmUuid={vm.uuid} defaultName={`${vm.name}-clone`} onClose={() => setCloneOpen(false)} />}
    </div>
  );
}

function CloneModal({ vmUuid, defaultName, onClose }: { vmUuid: string; defaultName: string; onClose: () => void }) {
  const navigate = useNavigate();
  const [name, setName] = useState(defaultName);
  const [linked, setLinked] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => vms.clone(vmUuid, name, linked),
    onSuccess: (data) => setJobId(data.job_id),
  });

  return (
    <Modal title="Clone VM" onClose={onClose}>
      {jobId ? (
        <div className="space-y-3">
          <JobTracker jobId={jobId} onSettled={(job) => job.status === "SUCCESS" && setTimeout(() => navigate(`/vms/${job.resource_id}`), 800)} />
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="label">New VM name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <label className="flex items-center gap-2 text-sm text-surface-200">
            <input type="checkbox" checked={linked} onChange={(e) => setLinked(e.target.checked)} />
            Linked clone (where the storage backend supports it)
          </label>
          <ErrorBanner error={mutation.error} />
          <div className="flex justify-end gap-2 pt-2">
            <button className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button className="btn-primary" onClick={() => mutation.mutate()} disabled={mutation.isPending || !name}>
              Clone
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

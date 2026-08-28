import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import ErrorBanner from "@/components/ErrorBanner";
import JobTracker from "@/components/JobTracker";
import PageHeader from "@/components/PageHeader";
import { NodeSelect, OrganizationSelect, ProjectSelect, StorageSelect } from "@/components/pickers";
import { networks, vms } from "@/lib/resources";

const STEPS = ["General", "OS", "CPU", "Memory", "Storage", "Network", "Cloud-init", "Review"] as const;

export default function VMCreateWizardPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [step, setStep] = useState(0);
  const [organization, setOrganization] = useState("");
  const [project, setProject] = useState("");
  const [node, setNode] = useState(searchParams.get("node") ?? "");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const [osType, setOsType] = useState("linux");
  const [firmware, setFirmware] = useState<"BIOS" | "UEFI">("BIOS");

  const [cpuCount, setCpuCount] = useState(2);
  const [memoryMb, setMemoryMb] = useState(4096);

  const [storage, setStorage] = useState("");
  const [diskGb, setDiskGb] = useState(20);
  const [diskBus, setDiskBus] = useState<"VIRTIO" | "VIRTIO_SCSI" | "SATA" | "IDE">("VIRTIO");

  const [network, setNetwork] = useState("");
  const [nicModel, setNicModel] = useState<"VIRTIO" | "E1000">("VIRTIO");

  const [cloudInitEnabled, setCloudInitEnabled] = useState(false);
  const [ciHostname, setCiHostname] = useState("");
  const [ciUsername, setCiUsername] = useState("");
  const [ciSshKeys, setCiSshKeys] = useState("");

  const [autostart, setAutostart] = useState(true);
  const [jobId, setJobId] = useState<string | null>(null);

  const idempotencyKey = useMemo(() => crypto.randomUUID(), []);

  const networksQuery = useQuery({ queryKey: ["networks", "picker", node], queryFn: () => networks.list({ node, page_size: 100 }), enabled: !!node });

  const createMutation = useMutation({
    mutationFn: () =>
      vms.create(
        {
          name,
          project,
          node: node || undefined,
          description,
          os_type: osType,
          firmware,
          cpu_count: cpuCount,
          memory_mb: memoryMb,
          disks: [{ storage, size_gb: diskGb, bus: diskBus, bootable: true }],
          nics: network ? [{ network, model: nicModel, bootable: true }] : [],
          cloud_init_enabled: cloudInitEnabled,
          cloud_init_config: cloudInitEnabled
            ? { hostname: ciHostname || name, username: ciUsername || undefined, ssh_keys: ciSshKeys ? ciSshKeys.split("\n").filter(Boolean) : undefined }
            : {},
          autostart,
        },
        idempotencyKey,
      ),
    onSuccess: (data) => {
      if (data.job_id) setJobId(data.job_id);
    },
  });

  const canAdvance: Record<number, boolean> = {
    0: !!organization && !!project && !!name,
    1: true,
    2: cpuCount > 0,
    3: memoryMb >= 128,
    4: !!storage && diskGb > 0,
    5: true,
    6: true,
    7: true,
  };

  if (jobId) {
    return (
      <div className="mx-auto max-w-lg space-y-4">
        <PageHeader title="Deploying VM" description={name} />
        <JobTracker jobId={jobId} onSettled={(job) => job.status === "SUCCESS" && setTimeout(() => navigate(`/vms/${job.resource_id}`), 800)} />
        <button className="btn-secondary" onClick={() => navigate("/vms")}>
          Back to VM list
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Create Virtual Machine" />

      <div className="mb-5 flex items-center gap-1 overflow-x-auto pb-1">
        {STEPS.map((label, i) => (
          <button
            key={label}
            className={`shrink-0 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              i === step ? "bg-accent-500/15 text-accent-400" : i < step ? "text-surface-300" : "text-surface-600"
            }`}
            onClick={() => i < step && setStep(i)}
            disabled={i > step}
          >
            {i + 1}. {label}
          </button>
        ))}
      </div>

      <div className="card space-y-4 p-5">
        {step === 0 && (
          <>
            <Field label="Organization">
              <OrganizationSelect
                value={organization}
                onChange={(v) => {
                  setOrganization(v);
                  setProject("");
                }}
                required
              />
            </Field>
            <Field label="Project">
              <ProjectSelect organization={organization} value={project} onChange={setProject} required />
            </Field>
            <Field label="Name">
              <input className="input" required value={name} onChange={(e) => setName(e.target.value)} placeholder="web-01" />
            </Field>
            <Field label="Description">
              <textarea className="input" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
            </Field>
            <Field label="Node">
              <NodeSelect organization={organization} value={node} onChange={setNode} />
              <p className="mt-1 text-xs text-surface-500">Leave unset to let the scheduler pick the best node by free capacity.</p>
            </Field>
          </>
        )}

        {step === 1 && (
          <>
            <Field label="OS type">
              <input className="input" value={osType} onChange={(e) => setOsType(e.target.value)} placeholder="linux" />
            </Field>
            <Field label="Firmware">
              <select className="input" value={firmware} onChange={(e) => setFirmware(e.target.value as "BIOS" | "UEFI")}>
                <option value="BIOS">BIOS</option>
                <option value="UEFI">UEFI</option>
              </select>
            </Field>
            <p className="text-xs text-surface-500">
              To deploy from a pre-built template (image + defaults) instead, use the Templates page's "Deploy" action.
            </p>
          </>
        )}

        {step === 2 && (
          <Field label="vCPU count">
            <input type="number" min={1} max={256} className="input" value={cpuCount} onChange={(e) => setCpuCount(Number(e.target.value))} />
          </Field>
        )}

        {step === 3 && (
          <Field label="Memory (MB)">
            <input type="number" min={128} step={128} className="input" value={memoryMb} onChange={(e) => setMemoryMb(Number(e.target.value))} />
            <p className="mt-1 text-xs text-surface-500">{(memoryMb / 1024).toFixed(1)} GB</p>
          </Field>
        )}

        {step === 4 && (
          <>
            <Field label="Storage pool">
              <StorageSelect node={node || undefined} value={storage} onChange={setStorage} required />
            </Field>
            <Field label="Disk size (GB)">
              <input type="number" min={1} className="input" value={diskGb} onChange={(e) => setDiskGb(Number(e.target.value))} />
            </Field>
            <Field label="Bus">
              <select className="input" value={diskBus} onChange={(e) => setDiskBus(e.target.value as typeof diskBus)}>
                <option value="VIRTIO">VirtIO</option>
                <option value="VIRTIO_SCSI">VirtIO SCSI</option>
                <option value="SATA">SATA</option>
                <option value="IDE">IDE</option>
              </select>
            </Field>
          </>
        )}

        {step === 5 && (
          <>
            <Field label="Network">
              <select className="input" value={network} onChange={(e) => setNetwork(e.target.value)} disabled={!node}>
                <option value="">{node ? "No network (attach later)" : "Select a node first"}</option>
                {networksQuery.data?.results.map((n) => (
                  <option key={n.uuid} value={n.uuid}>
                    {n.name} ({n.bridge}
                    {n.vlan_id ? `.${n.vlan_id}` : ""})
                  </option>
                ))}
              </select>
            </Field>
            <Field label="NIC model">
              <select className="input" value={nicModel} onChange={(e) => setNicModel(e.target.value as typeof nicModel)}>
                <option value="VIRTIO">VirtIO</option>
                <option value="E1000">E1000</option>
              </select>
            </Field>
            <p className="text-xs text-surface-500">IP: automatic (DHCP) or allocate one manually afterward from the Networks page.</p>
          </>
        )}

        {step === 6 && (
          <>
            <label className="flex items-center gap-2 text-sm text-surface-200">
              <input type="checkbox" checked={cloudInitEnabled} onChange={(e) => setCloudInitEnabled(e.target.checked)} />
              Enable cloud-init
            </label>
            {cloudInitEnabled && (
              <>
                <Field label="Hostname">
                  <input className="input" value={ciHostname} onChange={(e) => setCiHostname(e.target.value)} placeholder={name || "hostname"} />
                </Field>
                <Field label="Username">
                  <input className="input" value={ciUsername} onChange={(e) => setCiUsername(e.target.value)} placeholder="ubuntu" />
                </Field>
                <Field label="SSH public keys (one per line)">
                  <textarea className="input font-mono text-xs" rows={3} value={ciSshKeys} onChange={(e) => setCiSshKeys(e.target.value)} placeholder="ssh-ed25519 AAAA..." />
                </Field>
              </>
            )}
          </>
        )}

        {step === 7 && (
          <div className="space-y-3">
            <SummaryRow label="Name" value={name} />
            <SummaryRow label="CPU" value={`${cpuCount} vCPU`} />
            <SummaryRow label="Memory" value={`${(memoryMb / 1024).toFixed(1)} GB`} />
            <SummaryRow label="Disk" value={`${diskGb} GB (${diskBus})`} />
            <SummaryRow label="Network" value={network || "none"} />
            <SummaryRow label="Cloud-init" value={cloudInitEnabled ? "enabled" : "disabled"} />
            <SummaryRow label="Autostart" value={autostart ? "yes" : "no"} />
            <label className="flex items-center gap-2 text-sm text-surface-200">
              <input type="checkbox" checked={autostart} onChange={(e) => setAutostart(e.target.checked)} />
              Start automatically after creation
            </label>
            <ErrorBanner error={createMutation.error} />
          </div>
        )}

        <div className="flex justify-between border-t border-surface-800 pt-4">
          <button className="btn-secondary" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>
            Back
          </button>
          {step < STEPS.length - 1 ? (
            <button className="btn-primary" onClick={() => setStep((s) => s + 1)} disabled={!canAdvance[step]}>
              Next
            </button>
          ) : (
            <button className="btn-primary" onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
              {createMutation.isPending ? "Deploying..." : "Deploy VM"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className="label">{label}</label>
      {children}
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-surface-800 pb-1.5 text-sm">
      <span className="text-surface-400">{label}</span>
      <span className="text-surface-100">{value}</span>
    </div>
  );
}

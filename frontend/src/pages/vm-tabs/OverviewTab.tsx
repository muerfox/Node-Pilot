import { formatBytes, formatDateTime } from "@/lib/format";
import type { VirtualMachine } from "@/types/api";

export default function OverviewTab({ vm }: { vm: VirtualMachine }) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div className="card space-y-2 p-4">
        <h3 className="text-sm font-semibold text-surface-100">Details</h3>
        <dl className="space-y-1.5 text-sm">
          <Row label="Description" value={vm.description || "-"} />
          <Row label="OS type" value={vm.os_type} />
          <Row label="Provisioning state" value={vm.provisioning_state} />
          <Row label="Autostart" value={vm.autostart ? "yes" : "no"} />
          <Row label="Cloud-init" value={vm.cloud_init_enabled ? "enabled" : "disabled"} />
          <Row label="Created" value={formatDateTime(vm.created_at)} />
          <Row label="Updated" value={formatDateTime(vm.updated_at)} />
        </dl>
      </div>

      <div className="card space-y-2 p-4">
        <h3 className="text-sm font-semibold text-surface-100">Resources</h3>
        <dl className="space-y-1.5 text-sm">
          <Row label="vCPU" value={String(vm.cpu_count)} />
          <Row label="Memory" value={`${(vm.memory_mb / 1024).toFixed(1)} GB`} />
          <Row label="Disks" value={`${vm.disks.length} (${formatBytes(vm.disks.reduce((s, d) => s + d.size_bytes, 0))})`} />
          <Row label="NICs" value={String(vm.nics.length)} />
        </dl>
      </div>

      {vm.last_error && (
        <div className="card border-status-error/40 p-4 lg:col-span-2">
          <h3 className="mb-1 text-sm font-semibold text-status-error">Last error</h3>
          <p className="text-sm text-surface-300">{vm.last_error}</p>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-surface-800/60 pb-1.5">
      <dt className="text-surface-400">{label}</dt>
      <dd className="truncate text-right text-surface-200">{value}</dd>
    </div>
  );
}

import StatusBadge from "@/components/StatusBadge";
import { formatBytes } from "@/lib/format";
import type { VirtualMachine } from "@/types/api";

export default function HardwareTab({ vm }: { vm: VirtualMachine }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="card p-4">
          <h3 className="mb-2 text-sm font-semibold text-surface-100">CPU</h3>
          <p className="text-sm text-surface-300">
            {vm.cpu_count} vCPU ({vm.cpu_sockets} socket / {vm.cpu_cores} core / {vm.cpu_threads} thread)
          </p>
          <p className="text-xs text-surface-500">Model: {vm.cpu_model}</p>
        </div>
        <div className="card p-4">
          <h3 className="mb-2 text-sm font-semibold text-surface-100">BIOS / Machine</h3>
          <p className="text-sm text-surface-300">{vm.firmware}</p>
          <p className="text-xs text-surface-500">Machine type: {vm.machine_type}</p>
        </div>
      </div>

      <div className="card overflow-x-auto p-4">
        <h3 className="mb-2 text-sm font-semibold text-surface-100">Disks</h3>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Size</th>
              <th>Bus</th>
              <th>Device</th>
              <th>Boot</th>
            </tr>
          </thead>
          <tbody>
            {vm.disks.map((disk) => (
              <tr key={disk.uuid}>
                <td>{disk.name}</td>
                <td>{formatBytes(disk.size_bytes)}</td>
                <td>{disk.bus}</td>
                <td className="font-mono text-xs">{disk.device || "-"}</td>
                <td>{disk.bootable ? <StatusBadge status="ACTIVE" /> : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card overflow-x-auto p-4">
        <h3 className="mb-2 text-sm font-semibold text-surface-100">CD/DVD &amp; NICs</h3>
        <table>
          <thead>
            <tr>
              <th>MAC</th>
              <th>Model</th>
              <th>VLAN</th>
              <th>IP</th>
            </tr>
          </thead>
          <tbody>
            {vm.nics.map((nic) => (
              <tr key={nic.uuid}>
                <td className="font-mono text-xs">{nic.mac_address}</td>
                <td>{nic.model}</td>
                <td>{nic.vlan ?? "-"}</td>
                <td>{nic.ip_address ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

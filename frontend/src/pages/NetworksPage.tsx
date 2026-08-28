import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import EmptyState from "@/components/EmptyState";
import ErrorBanner from "@/components/ErrorBanner";
import Modal from "@/components/Modal";
import { NodeSelect } from "@/components/pickers";
import { FullPageSpinner } from "@/components/Spinner";
import PageHeader from "@/components/PageHeader";
import StatusBadge from "@/components/StatusBadge";
import { ipAddresses, networks, subnets } from "@/lib/resources";
import type { NodePilotNetwork } from "@/types/api";

const SUBTABS = ["Networks", "Subnets", "IP Addresses"] as const;

export default function NetworksPage() {
  const [tab, setTab] = useState<(typeof SUBTABS)[number]>("Networks");
  const [showCreateNetwork, setShowCreateNetwork] = useState(false);

  return (
    <div>
      <PageHeader
        title="Networks"
        actions={
          tab === "Networks" ? (
            <button className="btn-primary" onClick={() => setShowCreateNetwork(true)}>
              + Add network
            </button>
          ) : undefined
        }
      />

      <div className="mb-4 flex gap-1">
        {SUBTABS.map((t) => (
          <button
            key={t}
            className={`rounded-md px-2.5 py-1 text-xs font-medium ${tab === t ? "bg-accent-500/15 text-accent-400" : "text-surface-400 hover:bg-surface-800"}`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Networks" && <NetworksList />}
      {tab === "Subnets" && <SubnetsList />}
      {tab === "IP Addresses" && <IPAddressesList />}

      {showCreateNetwork && <CreateNetworkModal onClose={() => setShowCreateNetwork(false)} />}
    </div>
  );
}

function NetworksList() {
  const query = useQuery({ queryKey: ["networks"], queryFn: () => networks.list({ page_size: 100 }) });
  if (query.isLoading) return <FullPageSpinner />;
  if (!query.data?.results.length) return <EmptyState title="No networks" description="Add a Linux bridge network on a node." />;

  return (
    <div className="card overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Bridge</th>
            <th>VLAN</th>
            <th>Status</th>
            <th>DHCP</th>
          </tr>
        </thead>
        <tbody>
          {query.data.results.map((n) => (
            <tr key={n.uuid}>
              <td className="font-medium text-surface-100">{n.name}</td>
              <td>{n.type}</td>
              <td className="font-mono text-xs">{n.bridge}</td>
              <td>{n.vlan_id ?? "-"}</td>
              <td>
                <StatusBadge status={n.status} />
              </td>
              <td>{n.dhcp_enabled ? "yes" : "no"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SubnetsList() {
  const query = useQuery({ queryKey: ["subnets"], queryFn: () => subnets.list({ page_size: 100 }) });
  const [showCreate, setShowCreate] = useState(false);
  const queryClient = useQueryClient();
  const allocateMutation = useMutation({
    mutationFn: (uuid: string) => subnets.allocateIp(uuid),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ips"] }),
  });

  if (query.isLoading) return <FullPageSpinner />;

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button className="btn-secondary" onClick={() => setShowCreate(true)}>
          + Add subnet
        </button>
      </div>
      <ErrorBanner error={allocateMutation.error} />
      {!query.data?.results.length ? (
        <EmptyState title="No subnets" description="Add a subnet to a network to enable IPAM." />
      ) : (
        <div className="card overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>CIDR</th>
                <th>Gateway</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {query.data.results.map((s) => (
                <tr key={s.uuid}>
                  <td className="font-mono text-sm">{s.cidr}</td>
                  <td>{s.gateway ?? "-"}</td>
                  <td className="text-right">
                    <button className="btn-ghost !py-1 !px-2 text-xs" onClick={() => allocateMutation.mutate(s.uuid)} disabled={allocateMutation.isPending}>
                      Allocate next free IP
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {showCreate && <CreateSubnetModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

function IPAddressesList() {
  const query = useQuery({ queryKey: ["ips"], queryFn: () => ipAddresses.list({ page_size: 200 }) });
  const queryClient = useQueryClient();
  const releaseMutation = useMutation({ mutationFn: ipAddresses.release, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ips"] }) });

  if (query.isLoading) return <FullPageSpinner />;
  if (!query.data?.results.length) return <EmptyState title="No allocated IPs yet" />;

  return (
    <div className="card overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>Address</th>
            <th>State</th>
            <th>Note</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {query.data.results.map((ip) => (
            <tr key={ip.uuid}>
              <td className="font-mono text-sm">{ip.address}</td>
              <td>
                <StatusBadge status={ip.state} />
              </td>
              <td className="text-xs text-surface-400">{ip.note || "-"}</td>
              <td className="text-right">
                {ip.state === "ALLOCATED" && (
                  <button className="btn-ghost !py-1 !px-2 text-xs" onClick={() => releaseMutation.mutate(ip.uuid)}>
                    Release
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CreateNetworkModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [node, setNode] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState<NodePilotNetwork["type"]>("BRIDGE");
  const [bridge, setBridge] = useState("");
  const [vlanId, setVlanId] = useState("");

  const mutation = useMutation({
    mutationFn: () => networks.create({ node, name, type, bridge, vlan_id: vlanId ? Number(vlanId) : null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["networks"] });
      onClose();
    },
  });

  return (
    <Modal
      title="Add network"
      onClose={onClose}
    >
      <form
        className="space-y-3"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <div>
          <label className="label">Node</label>
          <NodeSelect value={node} onChange={setNode} />
        </div>
        <div>
          <label className="label">Name</label>
          <input className="input" required value={name} onChange={(e) => setName(e.target.value)} placeholder="production" />
        </div>
        <div>
          <label className="label">Type</label>
          <select className="input" value={type} onChange={(e) => setType(e.target.value as NodePilotNetwork["type"])}>
            <option value="BRIDGE">Bridge</option>
            <option value="VLAN">VLAN</option>
            <option value="NAT">NAT</option>
            <option value="ROUTED">Routed</option>
            <option value="ISOLATED">Isolated</option>
          </select>
        </div>
        <div>
          <label className="label">Bridge</label>
          <input className="input" required value={bridge} onChange={(e) => setBridge(e.target.value)} placeholder="vmbr0" />
        </div>
        <div>
          <label className="label">VLAN ID (optional)</label>
          <input className="input" value={vlanId} onChange={(e) => setVlanId(e.target.value)} placeholder="120" />
        </div>
        <ErrorBanner error={mutation.error} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending || !node}>
            Add
          </button>
        </div>
      </form>
    </Modal>
  );
}

function CreateSubnetModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [network, setNetwork] = useState("");
  const [cidr, setCidr] = useState("");
  const [gateway, setGateway] = useState("");
  const networksQuery = useQuery({ queryKey: ["networks", "picker-all"], queryFn: () => networks.list({ page_size: 100 }) });

  const mutation = useMutation({
    mutationFn: () => subnets.create({ network, cidr, gateway: gateway || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subnets"] });
      onClose();
    },
  });

  return (
    <Modal title="Add subnet" onClose={onClose}>
      <form
        className="space-y-3"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <div>
          <label className="label">Network</label>
          <select className="input" required value={network} onChange={(e) => setNetwork(e.target.value)}>
            <option value="">Select a network...</option>
            {networksQuery.data?.results.map((n) => (
              <option key={n.uuid} value={n.uuid}>
                {n.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">CIDR</label>
          <input className="input" required value={cidr} onChange={(e) => setCidr(e.target.value)} placeholder="10.20.120.0/24" />
        </div>
        <div>
          <label className="label">Gateway (optional)</label>
          <input className="input" value={gateway} onChange={(e) => setGateway(e.target.value)} placeholder="10.20.120.1" />
        </div>
        <ErrorBanner error={mutation.error} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending || !network}>
            Add
          </button>
        </div>
      </form>
    </Modal>
  );
}

import { useQueries } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";

import PageHeader from "@/components/PageHeader";
import { FullPageSpinner } from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { images, ipAddresses, jobs, networks, nodes, storagePools, users, vms } from "@/lib/resources";

export default function SearchResultsPage() {
  const [searchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";

  const [vmsQ, nodesQ, ipsQ, networksQ, storageQ, imagesQ, jobsQ, usersQ] = useQueries({
    queries: [
      { queryKey: ["search", "vms", q], queryFn: () => vms.list({ search: q, page_size: 10 }), enabled: !!q },
      { queryKey: ["search", "nodes", q], queryFn: () => nodes.list({ search: q, page_size: 10 }), enabled: !!q },
      { queryKey: ["search", "ips", q], queryFn: () => ipAddresses.list({ search: q, page_size: 10 }), enabled: !!q },
      { queryKey: ["search", "networks", q], queryFn: () => networks.list({ search: q, page_size: 10 }), enabled: !!q },
      { queryKey: ["search", "storage", q], queryFn: () => storagePools.list({ search: q, page_size: 10 }), enabled: !!q },
      { queryKey: ["search", "images", q], queryFn: () => images.list({ search: q, page_size: 10 }), enabled: !!q },
      { queryKey: ["search", "jobs", q], queryFn: () => jobs.list({ search: q, page_size: 10 }), enabled: !!q },
      { queryKey: ["search", "users", q], queryFn: () => users.list({ search: q, page_size: 10 }), enabled: !!q },
    ],
  });

  const loading = [vmsQ, nodesQ, ipsQ, networksQ, storageQ, imagesQ, jobsQ, usersQ].some((r) => r.isLoading);
  const totalResults =
    (vmsQ.data?.results.length ?? 0) +
    (nodesQ.data?.results.length ?? 0) +
    (ipsQ.data?.results.length ?? 0) +
    (networksQ.data?.results.length ?? 0) +
    (storageQ.data?.results.length ?? 0) +
    (imagesQ.data?.results.length ?? 0) +
    (jobsQ.data?.results.length ?? 0) +
    (usersQ.data?.results.length ?? 0);

  return (
    <div>
      <PageHeader title={`Search: ${q}`} />
      {loading ? (
        <FullPageSpinner />
      ) : totalResults === 0 ? (
        <p className="py-8 text-center text-xs text-surface-500">No results.</p>
      ) : (
        <div className="space-y-4">
          <ResultSection title="Virtual Machines">
            {vmsQ.data?.results.map((vm) => (
              <ResultRow key={vm.uuid} to={`/vms/${vm.uuid}`} title={vm.name} sub={vm.hostname} badge={<StatusBadge status={vm.status} />} />
            ))}
          </ResultSection>
          <ResultSection title="Nodes">
            {nodesQ.data?.results.map((n) => <ResultRow key={n.uuid} to={`/nodes/${n.uuid}`} title={n.name} sub={n.hostname} badge={<StatusBadge status={n.status} />} />)}
          </ResultSection>
          <ResultSection title="IP Addresses">
            {ipsQ.data?.results.map((ip) => <ResultRow key={ip.uuid} to="/networks" title={ip.address} sub={ip.note} badge={<StatusBadge status={ip.state} />} />)}
          </ResultSection>
          <ResultSection title="Networks">
            {networksQ.data?.results.map((n) => <ResultRow key={n.uuid} to="/networks" title={n.name} sub={n.bridge} />)}
          </ResultSection>
          <ResultSection title="Storage">
            {storageQ.data?.results.map((s) => <ResultRow key={s.uuid} to="/storage" title={s.name} sub={s.type} />)}
          </ResultSection>
          <ResultSection title="Images">
            {imagesQ.data?.results.map((i) => <ResultRow key={i.uuid} to="/images" title={i.name} sub={i.type} />)}
          </ResultSection>
          <ResultSection title="Jobs">
            {jobsQ.data?.results.map((j) => <ResultRow key={j.uuid} to="/jobs" title={j.type} sub={j.resource_id} badge={<StatusBadge status={j.status} />} />)}
          </ResultSection>
          <ResultSection title="Users">
            {usersQ.data?.results.map((u) => <ResultRow key={u.uuid} to="/users" title={u.username} sub={u.email} />)}
          </ResultSection>
        </div>
      )}
    </div>
  );
}

function ResultSection({ title, children }: { title: string; children: ReactNode }) {
  const items = Array.isArray(children) ? children.filter(Boolean) : children ? [children] : [];
  if (!items.length) return null;
  return (
    <div className="card p-4">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-surface-400">{title}</h3>
      <div className="divide-y divide-surface-800">{children}</div>
    </div>
  );
}

function ResultRow({ to, title, sub, badge }: { to: string; title: string; sub?: string; badge?: ReactNode }) {
  return (
    <Link to={to} className="flex items-center justify-between gap-3 py-2 text-sm hover:text-accent-400">
      <div className="min-w-0">
        <p className="truncate text-surface-100">{title}</p>
        {sub && <p className="truncate text-xs text-surface-500">{sub}</p>}
      </div>
      {badge}
    </Link>
  );
}

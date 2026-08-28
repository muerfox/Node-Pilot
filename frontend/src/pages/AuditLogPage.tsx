import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import ErrorBanner from "@/components/ErrorBanner";
import PageHeader from "@/components/PageHeader";
import { FullPageSpinner } from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { formatDateTime } from "@/lib/format";
import { auditLogs } from "@/lib/resources";

export default function AuditLogPage() {
  const [search, setSearch] = useState("");
  const query = useQuery({ queryKey: ["audit", search], queryFn: () => auditLogs.list({ search: search || undefined, page_size: 100 }) });

  return (
    <div>
      <PageHeader title="Audit Logs" description="Immutable record of every administrative action." />

      <input className="input mb-4 max-w-xs" placeholder="Search by action or resource..." value={search} onChange={(e) => setSearch(e.target.value)} />

      <ErrorBanner error={query.error} />

      {query.isLoading ? (
        <FullPageSpinner />
      ) : !query.data?.results.length ? (
        <p className="py-8 text-center text-xs text-surface-500">No audit entries found.</p>
      ) : (
        <div className="card overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Resource</th>
                <th>Result</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              {query.data.results.map((entry) => (
                <tr key={entry.uuid}>
                  <td className="text-xs text-surface-400">{formatDateTime(entry.created_at)}</td>
                  <td className="text-sm text-surface-200">{entry.actor_label}</td>
                  <td className="font-mono text-xs">{entry.action}</td>
                  <td className="text-xs text-surface-400">
                    {entry.resource_type}:{entry.resource_id.slice(0, 8)}
                  </td>
                  <td>
                    <StatusBadge status={entry.result} />
                  </td>
                  <td className="text-xs text-surface-500">{entry.ip_address || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

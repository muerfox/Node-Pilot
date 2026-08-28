import { useQuery } from "@tanstack/react-query";

import ErrorBanner from "@/components/ErrorBanner";
import PageHeader from "@/components/PageHeader";
import { FullPageSpinner } from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { formatDateTime, formatRelativeTime } from "@/lib/format";
import { users } from "@/lib/resources";

export default function UsersPage() {
  const query = useQuery({ queryKey: ["users"], queryFn: () => users.list({ page_size: 100 }) });

  return (
    <div>
      <PageHeader title="Users" description="Platform-wide user administration (requires staff access)." />

      <ErrorBanner error={query.error} />

      {query.isLoading ? (
        <FullPageSpinner />
      ) : (
        <div className="card overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Username</th>
                <th>Email</th>
                <th>Status</th>
                <th>Joined</th>
                <th>Last login</th>
              </tr>
            </thead>
            <tbody>
              {query.data?.results.map((user) => (
                <tr key={user.uuid}>
                  <td className="font-medium text-surface-100">
                    {user.username}
                    {user.is_service_account && <span className="ml-1.5 rounded bg-surface-800 px-1 py-0.5 text-[10px] text-surface-400">service</span>}
                  </td>
                  <td className="text-xs text-surface-400">{user.email}</td>
                  <td>
                    <StatusBadge status={user.is_active ? "ACTIVE" : "DISABLED"} />
                  </td>
                  <td className="text-xs text-surface-400">{formatDateTime(user.date_joined)}</td>
                  <td className="text-xs text-surface-400">{formatRelativeTime(user.last_login)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-3 text-xs text-surface-500">
        Creating/editing users and managing per-organization role assignments is available via the API
        (<code>POST /api/v1/users/</code>, <code>POST /api/v1/role-assignments/</code>) -- not yet a form in this
        build.
      </p>
    </div>
  );
}

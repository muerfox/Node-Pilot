import { useQuery } from "@tanstack/react-query";

import { FullPageSpinner } from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { formatDateTime } from "@/lib/format";
import { events } from "@/lib/resources";

export default function EventsTab({ vmUuid }: { vmUuid: string }) {
  const query = useQuery({ queryKey: ["events", "vm", vmUuid], queryFn: () => events.list({ resource_type: "VirtualMachine", resource_id: vmUuid, page_size: 100 }) });

  if (query.isLoading) return <FullPageSpinner />;
  if (!query.data?.results.length) return <p className="py-8 text-center text-xs text-surface-500">No events recorded for this VM.</p>;

  return (
    <div className="card overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>Type</th>
            <th>Severity</th>
            <th>When</th>
          </tr>
        </thead>
        <tbody>
          {query.data.results.map((event) => (
            <tr key={event.uuid}>
              <td>{event.type}</td>
              <td>
                <StatusBadge status={event.severity} />
              </td>
              <td className="text-xs text-surface-400">{formatDateTime(event.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

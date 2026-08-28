import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import ConfirmButton from "@/components/ConfirmButton";
import EmptyState from "@/components/EmptyState";
import ErrorBanner from "@/components/ErrorBanner";
import Modal from "@/components/Modal";
import { OrganizationSelect } from "@/components/pickers";
import PageHeader from "@/components/PageHeader";
import { FullPageSpinner } from "@/components/Spinner";
import { webhooks } from "@/lib/resources";

const SUPPORTED_EVENTS = ["vm.created", "vm.started", "vm.stopped", "vm.deleted", "vm.cloned", "backup.completed", "backup.failed", "node.offline", "node.online"];

export default function WebhooksPage() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const query = useQuery({ queryKey: ["webhooks"], queryFn: () => webhooks.list({ page_size: 100 }) });
  const deleteMutation = useMutation({ mutationFn: webhooks.remove, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["webhooks"] }) });

  return (
    <div>
      <PageHeader
        title="Webhooks"
        description="Outbound HMAC-signed event delivery."
        actions={
          <button className="btn-primary" onClick={() => setShowCreate(true)}>
            + Add webhook
          </button>
        }
      />

      <ErrorBanner error={query.error ?? deleteMutation.error} />

      {query.isLoading ? (
        <FullPageSpinner />
      ) : !query.data?.results.length ? (
        <EmptyState title="No webhooks configured" />
      ) : (
        <div className="card overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>URL</th>
                <th>Events</th>
                <th>Secret</th>
                <th>Enabled</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {query.data.results.map((wh) => (
                <tr key={wh.uuid}>
                  <td className="font-medium text-surface-100">{wh.name}</td>
                  <td className="max-w-xs truncate text-xs text-surface-400">{wh.url}</td>
                  <td className="text-xs text-surface-400">{wh.events.join(", ")}</td>
                  <td className="font-mono text-xs text-surface-500">{wh.secret}</td>
                  <td>{wh.enabled ? "yes" : "no"}</td>
                  <td className="text-right">
                    <ConfirmButton className="btn-ghost !py-1 !px-2 text-xs text-status-error" onConfirm={() => deleteMutation.mutate(wh.uuid)}>
                      Delete
                    </ConfirmButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && <CreateWebhookModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

function CreateWebhookModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [organization, setOrganization] = useState("");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [createdSecret, setCreatedSecret] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => webhooks.create({ organization, name, url, events: selectedEvents }),
    onSuccess: (data) => {
      setCreatedSecret(data.secret);
      queryClient.invalidateQueries({ queryKey: ["webhooks"] });
    },
  });

  function toggleEvent(event: string) {
    setSelectedEvents((prev) => (prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event]));
  }

  if (createdSecret) {
    return (
      <Modal title="Webhook created" onClose={onClose}>
        <div className="space-y-3">
          <p className="text-sm text-status-warning">Signing secret -- shown once, copy it now</p>
          <code className="block break-all rounded-md bg-surface-950 p-2 text-xs text-surface-200">{createdSecret}</code>
          <p className="text-xs text-surface-500">
            Verify deliveries with the <code>X-NodePilot-Signature: sha256=&lt;hmac&gt;</code> header, computed over the raw
            request body with this secret.
          </p>
          <div className="flex justify-end pt-2">
            <button className="btn-primary" onClick={onClose}>
              Done
            </button>
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal title="Add webhook" onClose={onClose}>
      <form
        className="space-y-3"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <div>
          <label className="label">Organization</label>
          <OrganizationSelect value={organization} onChange={setOrganization} required />
        </div>
        <div>
          <label className="label">Name</label>
          <input className="input" required value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="label">URL</label>
          <input className="input" required type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/hooks/nodepilot" />
        </div>
        <div>
          <label className="label">Events</label>
          <div className="grid grid-cols-2 gap-1">
            {SUPPORTED_EVENTS.map((event) => (
              <label key={event} className="flex items-center gap-1.5 text-xs text-surface-300">
                <input type="checkbox" checked={selectedEvents.includes(event)} onChange={() => toggleEvent(event)} />
                {event}
              </label>
            ))}
          </div>
        </div>
        <ErrorBanner error={mutation.error} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending || !organization || !selectedEvents.length}>
            Add
          </button>
        </div>
      </form>
    </Modal>
  );
}

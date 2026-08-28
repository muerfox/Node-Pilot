import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import ConfirmButton from "@/components/ConfirmButton";
import EmptyState from "@/components/EmptyState";
import ErrorBanner from "@/components/ErrorBanner";
import Modal from "@/components/Modal";
import PageHeader from "@/components/PageHeader";
import { FullPageSpinner } from "@/components/Spinner";
import { formatDateTime, formatRelativeTime } from "@/lib/format";
import { apiTokens } from "@/lib/resources";

export default function TokensPage() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const query = useQuery({ queryKey: ["tokens"], queryFn: () => apiTokens.list() });
  const revokeMutation = useMutation({ mutationFn: apiTokens.revoke, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tokens"] }) });

  return (
    <div>
      <PageHeader
        title="API Tokens"
        description="Personal tokens for scripts and the CLI (Authorization: Token &lt;value&gt;)."
        actions={
          <button className="btn-primary" onClick={() => setShowCreate(true)}>
            + New token
          </button>
        }
      />

      <ErrorBanner error={query.error ?? revokeMutation.error} />

      {query.isLoading ? (
        <FullPageSpinner />
      ) : !query.data?.results.length ? (
        <EmptyState title="No API tokens yet" />
      ) : (
        <div className="card overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Prefix</th>
                <th>Last used</th>
                <th>Expires</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {query.data.results.map((token) => (
                <tr key={token.uuid}>
                  <td className="font-medium text-surface-100">{token.name}</td>
                  <td className="font-mono text-xs">{token.prefix}...</td>
                  <td className="text-xs text-surface-400">{formatRelativeTime(token.last_used_at)}</td>
                  <td className="text-xs text-surface-400">{token.expires_at ? formatDateTime(token.expires_at) : "never"}</td>
                  <td className="text-xs">{token.revoked ? "revoked" : "active"}</td>
                  <td className="text-right">
                    {!token.revoked && (
                      <ConfirmButton className="btn-ghost !py-1 !px-2 text-xs text-status-error" onConfirm={() => revokeMutation.mutate(token.uuid)}>
                        Revoke
                      </ConfirmButton>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && <CreateTokenModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

function CreateTokenModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [createdToken, setCreatedToken] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => apiTokens.create({ name }),
    onSuccess: (data) => {
      setCreatedToken(data.token ?? null);
      queryClient.invalidateQueries({ queryKey: ["tokens"] });
    },
  });

  if (createdToken) {
    return (
      <Modal title="Token created" onClose={onClose}>
        <div className="space-y-3">
          <p className="text-sm text-status-warning">Shown once, copy it now</p>
          <code className="block break-all rounded-md bg-surface-950 p-2 text-xs text-surface-200">{createdToken}</code>
          <p className="text-xs text-surface-500">
            Use it as <code>Authorization: Token {createdToken.slice(0, 12)}...</code>, or run{" "}
            <code>nodepilot login</code> with the CLI and paste it in.
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
    <Modal title="New API token" onClose={onClose}>
      <form
        className="space-y-3"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <div>
          <label className="label">Name</label>
          <input className="input" required value={name} onChange={(e) => setName(e.target.value)} placeholder="ci-pipeline" />
        </div>
        <p className="text-xs text-surface-500">The token inherits your own permissions -- scope restriction is available via the API's `scopes` field.</p>
        <ErrorBanner error={mutation.error} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending || !name}>
            Create
          </button>
        </div>
      </form>
    </Modal>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import EmptyState from "@/components/EmptyState";
import ErrorBanner from "@/components/ErrorBanner";
import Modal from "@/components/Modal";
import { OrganizationSelect } from "@/components/pickers";
import PageHeader from "@/components/PageHeader";
import { FullPageSpinner } from "@/components/Spinner";
import StatusBadge from "@/components/StatusBadge";
import { organizations, projects } from "@/lib/resources";

const SUBTABS = ["Organizations", "Projects"] as const;

export default function OrganizationsPage() {
  const [tab, setTab] = useState<(typeof SUBTABS)[number]>("Organizations");
  const [showCreate, setShowCreate] = useState(false);

  return (
    <div>
      <PageHeader
        title="Organizations"
        actions={
          <button className="btn-primary" onClick={() => setShowCreate(true)}>
            + New {tab === "Organizations" ? "organization" : "project"}
          </button>
        }
      />

      <div className="mb-4 flex gap-1">
        {SUBTABS.map((t) => (
          <button key={t} className={`rounded-md px-2.5 py-1 text-xs font-medium ${tab === t ? "bg-accent-500/15 text-accent-400" : "text-surface-400 hover:bg-surface-800"}`} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      {tab === "Organizations" && <OrganizationsList />}
      {tab === "Projects" && <ProjectsList />}

      {showCreate && tab === "Organizations" && <CreateOrgModal onClose={() => setShowCreate(false)} />}
      {showCreate && tab === "Projects" && <CreateProjectModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

function OrganizationsList() {
  const query = useQuery({ queryKey: ["organizations"], queryFn: () => organizations.list({ page_size: 100 }) });
  if (query.isLoading) return <FullPageSpinner />;
  if (!query.data?.results.length) return <EmptyState title="No organizations" />;

  return (
    <div className="card overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Slug</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {query.data.results.map((org) => (
            <tr key={org.uuid}>
              <td className="font-medium text-surface-100">{org.name}</td>
              <td className="font-mono text-xs text-surface-400">{org.slug}</td>
              <td>
                <StatusBadge status={org.is_active ? "ACTIVE" : "DISABLED"} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProjectsList() {
  const query = useQuery({ queryKey: ["projects", "all"], queryFn: () => projects.list({ page_size: 100 }) });
  if (query.isLoading) return <FullPageSpinner />;
  if (!query.data?.results.length) return <EmptyState title="No projects" />;

  return (
    <div className="card overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Slug</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {query.data.results.map((project) => (
            <tr key={project.uuid}>
              <td className="font-medium text-surface-100">{project.name}</td>
              <td className="font-mono text-xs text-surface-400">{project.slug}</td>
              <td>
                <StatusBadge status={project.is_active ? "ACTIVE" : "DISABLED"} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CreateOrgModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");

  const mutation = useMutation({
    mutationFn: () => organizations.create({ name, slug }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
      onClose();
    },
  });

  return (
    <Modal title="New organization" onClose={onClose}>
      <form
        className="space-y-3"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <div>
          <label className="label">Name</label>
          <input
            className="input"
            required
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (!slug) setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, ""));
            }}
          />
        </div>
        <div>
          <label className="label">Slug</label>
          <input className="input" required value={slug} onChange={(e) => setSlug(e.target.value)} />
        </div>
        <ErrorBanner error={mutation.error} />
        <p className="text-xs text-surface-500">Creating a new organization requires platform-superuser access.</p>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending || !name || !slug}>
            Create
          </button>
        </div>
      </form>
    </Modal>
  );
}

function CreateProjectModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [organization, setOrganization] = useState("");
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");

  const mutation = useMutation({
    mutationFn: () => projects.create({ organization, name, slug }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects", "all"] });
      onClose();
    },
  });

  return (
    <Modal title="New project" onClose={onClose}>
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
          <input
            className="input"
            required
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (!slug) setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, ""));
            }}
          />
        </div>
        <div>
          <label className="label">Slug</label>
          <input className="input" required value={slug} onChange={(e) => setSlug(e.target.value)} />
        </div>
        <ErrorBanner error={mutation.error} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending || !organization || !name || !slug}>
            Create
          </button>
        </div>
      </form>
    </Modal>
  );
}

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import EmptyState from "@/components/EmptyState";
import ErrorBanner from "@/components/ErrorBanner";
import JobTracker from "@/components/JobTracker";
import Modal from "@/components/Modal";
import PageHeader from "@/components/PageHeader";
import { NodeSelect, ProjectSelect, OrganizationSelect, StorageSelect } from "@/components/pickers";
import { FullPageSpinner } from "@/components/Spinner";
import { networks, templates } from "@/lib/resources";
import type { Template } from "@/types/api";

export default function TemplatesPage() {
  const [deployTarget, setDeployTarget] = useState<Template | null>(null);
  const query = useQuery({ queryKey: ["templates"], queryFn: () => templates.list({ page_size: 100 }) });

  return (
    <div>
      <PageHeader title="Templates" description="Reusable VM blueprints." />
      <ErrorBanner error={query.error} />

      {query.isLoading ? (
        <FullPageSpinner />
      ) : !query.data?.results.length ? (
        <EmptyState title="No templates yet" description="Templates are created from the API/admin for now; deploying one is available here." />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {query.data.results.map((t) => (
            <div key={t.uuid} className="card p-4">
              <h3 className="font-medium text-surface-100">{t.name}</h3>
              <p className="mt-0.5 text-xs text-surface-500">{t.description || "No description"}</p>
              <dl className="mt-3 grid grid-cols-2 gap-1 text-xs text-surface-400">
                <span>{t.default_cpu_count} vCPU</span>
                <span>{(t.default_memory_mb / 1024).toFixed(1)} GB RAM</span>
                <span>{t.default_disk_gb} GB disk</span>
                <span>{t.default_firmware}</span>
              </dl>
              <button className="btn-primary mt-3 w-full justify-center" onClick={() => setDeployTarget(t)}>
                Deploy
              </button>
            </div>
          ))}
        </div>
      )}

      {deployTarget && <DeployModal template={deployTarget} onClose={() => setDeployTarget(null)} />}
    </div>
  );
}

function DeployModal({ template, onClose }: { template: Template; onClose: () => void }) {
  const navigate = useNavigate();
  const [organization, setOrganization] = useState(template.organization);
  const [project, setProject] = useState("");
  const [node, setNode] = useState("");
  const [storage, setStorage] = useState("");
  const [network, setNetwork] = useState("");
  const [name, setName] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);

  const networksQuery = useQuery({ queryKey: ["networks", "picker", node], queryFn: () => networks.list({ node, page_size: 100 }), enabled: !!node });

  const mutation = useMutation({
    mutationFn: () =>
      templates.deploy(template.uuid, { name, project, node: node || undefined, storage, network }, crypto.randomUUID()),
    onSuccess: (data) => data.job_id && setJobId(data.job_id),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    mutation.mutate();
  }

  return (
    <Modal title={`Deploy from "${template.name}"`} onClose={onClose}>
      {jobId ? (
        <JobTracker jobId={jobId} onSettled={(job) => job.status === "SUCCESS" && setTimeout(() => navigate(`/vms/${job.resource_id}`), 800)} />
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="label">Organization</label>
            <OrganizationSelect value={organization} onChange={setOrganization} required />
          </div>
          <div>
            <label className="label">Project</label>
            <ProjectSelect organization={organization} value={project} onChange={setProject} required />
          </div>
          <div>
            <label className="label">Name</label>
            <input className="input" required value={name} onChange={(e) => setName(e.target.value)} placeholder="web-01" />
          </div>
          <div>
            <label className="label">Node</label>
            <NodeSelect organization={organization} value={node} onChange={setNode} />
          </div>
          <div>
            <label className="label">Storage pool</label>
            <StorageSelect node={node || undefined} value={storage} onChange={setStorage} required />
          </div>
          <div>
            <label className="label">Network</label>
            <select className="input" required value={network} onChange={(e) => setNetwork(e.target.value)} disabled={!node}>
              <option value="">{node ? "Select a network..." : "Select a node first"}</option>
              {networksQuery.data?.results.map((n) => (
                <option key={n.uuid} value={n.uuid}>
                  {n.name}
                </option>
              ))}
            </select>
          </div>
          <ErrorBanner error={mutation.error} />
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={mutation.isPending || !project || !storage || !network}>
              {mutation.isPending ? "Deploying..." : "Deploy"}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

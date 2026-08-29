import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import ConfirmButton from "@/components/ConfirmButton";
import EmptyState from "@/components/EmptyState";
import ErrorBanner from "@/components/ErrorBanner";
import Modal from "@/components/Modal";
import { OrganizationSelect, ProjectSelect } from "@/components/pickers";
import { FullPageSpinner } from "@/components/Spinner";
import { memberships, organizations, roleAssignments, roles, users } from "@/lib/resources";

/**
 * Org membership + role-assignment administration (section 7). Both
 * viewsets are org-scoped, so this queries across every org the current
 * user can see rather than requiring one to be picked first; the
 * organization name is resolved client-side from a single fetch of
 * /organizations/ rather than showing raw UUIDs in every row.
 */
export default function AccessTab() {
  const [showAddMember, setShowAddMember] = useState(false);
  const [showAddRole, setShowAddRole] = useState(false);

  const orgsQuery = useQuery({ queryKey: ["organizations", "access-tab"], queryFn: () => organizations.list({ page_size: 100 }) });
  const orgName = (uuid: string) => orgsQuery.data?.results.find((o) => o.uuid === uuid)?.name ?? uuid.slice(0, 8);

  return (
    <div className="space-y-6">
      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-surface-100">Members</h2>
          <button className="btn-secondary" onClick={() => setShowAddMember(true)}>
            + Add member
          </button>
        </div>
        <MembersList orgName={orgName} />
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-surface-100">Role Assignments</h2>
          <button className="btn-secondary" onClick={() => setShowAddRole(true)}>
            + Grant role
          </button>
        </div>
        <RoleAssignmentsList orgName={orgName} />
      </section>

      {showAddMember && <AddMemberModal onClose={() => setShowAddMember(false)} />}
      {showAddRole && <AddRoleAssignmentModal onClose={() => setShowAddRole(false)} />}
    </div>
  );
}

function MembersList({ orgName }: { orgName: (uuid: string) => string }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["memberships"], queryFn: () => memberships.list({ page_size: 200 }) });
  const removeMutation = useMutation({ mutationFn: memberships.remove, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["memberships"] }) });

  if (query.isLoading) return <FullPageSpinner />;
  if (!query.data?.results.length) return <EmptyState title="No members yet" />;

  return (
    <div className="card overflow-x-auto">
      <ErrorBanner error={removeMutation.error} />
      <table>
        <thead>
          <tr>
            <th>Organization</th>
            <th>User</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {query.data.results.map((m) => (
            <tr key={m.uuid}>
              <td>{orgName(m.organization)}</td>
              <td className="font-mono text-xs">{m.user.slice(0, 8)}</td>
              <td className="text-right">
                <ConfirmButton className="btn-ghost !py-1 !px-2 text-xs text-status-error" onConfirm={() => removeMutation.mutate(m.uuid)}>
                  Remove
                </ConfirmButton>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RoleAssignmentsList({ orgName }: { orgName: (uuid: string) => string }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["role-assignments"], queryFn: () => roleAssignments.list({ page_size: 200 }) });
  const rolesQuery = useQuery({ queryKey: ["roles", "access-tab"], queryFn: () => roles.list({ page_size: 200 }) });
  const roleName = (uuid: string) => rolesQuery.data?.results.find((r) => r.uuid === uuid)?.name ?? uuid.slice(0, 8);
  const removeMutation = useMutation({ mutationFn: roleAssignments.remove, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["role-assignments"] }) });

  if (query.isLoading) return <FullPageSpinner />;
  if (!query.data?.results.length) return <EmptyState title="No role assignments yet" description="Members without a role assignment can't do anything beyond what an unauthenticated view allows." />;

  return (
    <div className="card overflow-x-auto">
      <ErrorBanner error={removeMutation.error} />
      <table>
        <thead>
          <tr>
            <th>Organization</th>
            <th>Scope</th>
            <th>User</th>
            <th>Role</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {query.data.results.map((ra) => (
            <tr key={ra.uuid}>
              <td>{orgName(ra.organization)}</td>
              <td className="text-xs text-surface-400">{ra.project ? "Project" : "Organization-wide"}</td>
              <td className="font-mono text-xs">{ra.user.slice(0, 8)}</td>
              <td>{roleName(ra.role)}</td>
              <td className="text-right">
                <ConfirmButton className="btn-ghost !py-1 !px-2 text-xs text-status-error" onConfirm={() => removeMutation.mutate(ra.uuid)}>
                  Revoke
                </ConfirmButton>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AddMemberModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [organization, setOrganization] = useState("");
  const [username, setUsername] = useState("");

  const mutation = useMutation({
    mutationFn: async () => {
      const found = await users.lookup(username);
      return memberships.create({ organization, user: found.uuid });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["memberships"] });
      onClose();
    },
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    mutation.mutate();
  }

  return (
    <Modal title="Add member" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="label">Organization</label>
          <OrganizationSelect value={organization} onChange={setOrganization} required />
        </div>
        <div>
          <label className="label">Username</label>
          <input className="input" required value={username} onChange={(e) => setUsername(e.target.value)} placeholder="exact username" />
        </div>
        <ErrorBanner error={mutation.error} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending || !organization || !username}>
            {mutation.isPending ? "Adding..." : "Add"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function AddRoleAssignmentModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [organization, setOrganization] = useState("");
  const [project, setProject] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("");

  const rolesQuery = useQuery({ queryKey: ["roles", "grant-modal", organization], queryFn: () => roles.list({ organization, page_size: 200 }), enabled: !!organization });

  const mutation = useMutation({
    mutationFn: async () => {
      const found = await users.lookup(username);
      return roleAssignments.create({ organization, project: project || null, user: found.uuid, role });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["role-assignments"] });
      onClose();
    },
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    mutation.mutate();
  }

  return (
    <Modal title="Grant role" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="label">Organization</label>
          <OrganizationSelect
            value={organization}
            onChange={(v) => {
              setOrganization(v);
              setRole("");
            }}
            required
          />
        </div>
        <div>
          <label className="label">Project (optional -- leave unset for organization-wide)</label>
          <ProjectSelect organization={organization} value={project} onChange={setProject} />
        </div>
        <div>
          <label className="label">Username</label>
          <input className="input" required value={username} onChange={(e) => setUsername(e.target.value)} placeholder="exact username" />
        </div>
        <div>
          <label className="label">Role</label>
          <select className="input" required value={role} onChange={(e) => setRole(e.target.value)} disabled={!organization}>
            <option value="">{organization ? "Select a role..." : "Select an organization first"}</option>
            {rolesQuery.data?.results.map((r) => (
              <option key={r.uuid} value={r.uuid}>
                {r.name}
                {r.is_system ? " (system)" : ""}
              </option>
            ))}
          </select>
        </div>
        <ErrorBanner error={mutation.error} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={mutation.isPending || !organization || !username || !role}>
            {mutation.isPending ? "Granting..." : "Grant"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

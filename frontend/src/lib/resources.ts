import { api } from "@/lib/api";
import type {
  APIToken,
  AuditLog,
  Backup,
  BackupSchedule,
  BackupTarget,
  Image,
  IPAddress,
  Job,
  Membership,
  Node,
  NodePilotEvent,
  NodePilotNetwork,
  Organization,
  Paginated,
  Project,
  Quota,
  Role,
  RoleAssignment,
  Snapshot,
  StoragePool,
  Subnet,
  Template,
  User,
  UserLookupResult,
  VirtualMachine,
  Webhook,
} from "@/types/api";

type Params = Record<string, string | number | boolean | undefined | null>;
interface JobRef {
  job_id: string | null;
  status: string;
}

export const organizations = {
  list: (params?: Params) => api.get<Paginated<Organization>>("organizations/", params),
  get: (uuid: string) => api.get<Organization>(`organizations/${uuid}/`),
  create: (body: { name: string; slug: string }) => api.post<Organization>("organizations/", body),
};

export const projects = {
  list: (params?: Params) => api.get<Paginated<Project>>("projects/", params),
  create: (body: Partial<Project>) => api.post<Project>("projects/", body),
};

export const quotas = {
  list: (params?: Params) => api.get<Paginated<Quota>>("quotas/", params),
};

export const users = {
  me: () => api.get<User>("users/me/"),
  list: (params?: Params) => api.get<Paginated<User>>("users/", params),
  lookup: (username: string) => api.get<UserLookupResult>("users/lookup/", { username }),
};

export const apiTokens = {
  list: () => api.get<Paginated<APIToken>>("auth/tokens/"),
  create: (body: { name: string; scopes?: string[]; expires_at?: string | null }) => api.post<APIToken>("auth/tokens/", body),
  revoke: (uuid: string) => api.delete(`auth/tokens/${uuid}/`),
};

export const roles = {
  list: (params?: Params) => api.get<Paginated<Role>>("roles/", params),
};

export const memberships = {
  list: (params?: Params) => api.get<Paginated<Membership>>("memberships/", params),
  create: (body: { organization: string; user: string }) => api.post<Membership>("memberships/", body),
  remove: (uuid: string) => api.delete(`memberships/${uuid}/`),
};

export const roleAssignments = {
  list: (params?: Params) => api.get<Paginated<RoleAssignment>>("role-assignments/", params),
  create: (body: { organization: string; project?: string | null; user: string; role: string }) => api.post<RoleAssignment>("role-assignments/", body),
  remove: (uuid: string) => api.delete(`role-assignments/${uuid}/`),
};

export const nodes = {
  list: (params?: Params) => api.get<Paginated<Node>>("nodes/", params),
  get: (uuid: string) => api.get<Node>(`nodes/${uuid}/`),
  create: (body: { organization: string; name: string; hostname: string; fqdn?: string }) => api.post<Node>("nodes/", body),
  setMaintenance: (uuid: string, enabled: boolean) => api.post<Node>(`nodes/${uuid}/maintenance/`, { enabled }),
  registerAgent: (uuid: string) => api.post<{ node_id: string; agent_id: string; token: string; controller_version: string }>(`nodes/${uuid}/register-agent/`),
  revokeAgent: (uuid: string) => api.post<Node>(`nodes/${uuid}/revoke-agent/`),
};

export const vms = {
  list: (params?: Params) => api.get<Paginated<VirtualMachine>>("vms/", params),
  get: (uuid: string) => api.get<VirtualMachine>(`vms/${uuid}/`),
  create: (body: Record<string, unknown>, idempotencyKey: string) => api.post<{ id: string; status: string; job_id: string | null }>("vms/", body, idempotencyKey),
  start: (uuid: string) => api.post<JobRef>(`vms/${uuid}/start/`),
  stop: (uuid: string, force = false) => api.post<JobRef>(`vms/${uuid}/stop/`, { force }),
  reboot: (uuid: string, force = false) => api.post<JobRef>(`vms/${uuid}/reboot/`, { force }),
  pause: (uuid: string) => api.post<JobRef>(`vms/${uuid}/pause/`),
  resume: (uuid: string) => api.post<JobRef>(`vms/${uuid}/resume/`),
  clone: (uuid: string, name: string, linked: boolean) => api.post<JobRef>(`vms/${uuid}/clone/`, { name, linked }),
  remove: (uuid: string) => api.delete<JobRef>(`vms/${uuid}/`),
  console: (uuid: string) => api.get<{ websocket_url: string; protocol: string; note: string }>(`vms/${uuid}/console/`),
  attachDisk: (uuid: string, body: { storage: string; size_gb: number; bus: string }) => api.post<{ disk_id: string; job_id: string; status: string }>(`vms/${uuid}/disks/`, body),
  resizeDisk: (uuid: string, diskUuid: string, sizeGb: number) => api.post<JobRef>(`vms/${uuid}/disks/${diskUuid}/resize/`, { size_gb: sizeGb }),
  removeDisk: (uuid: string, diskUuid: string) => api.delete<JobRef>(`vms/${uuid}/disks/${diskUuid}/`),
  attachNic: (uuid: string, body: { network: string; model?: string; vlan?: number }) => api.post<{ nic_id: string; job_id: string; status: string }>(`vms/${uuid}/nics/`, body),
  removeNic: (uuid: string, nicUuid: string) => api.delete<JobRef>(`vms/${uuid}/nics/${nicUuid}/`),
};

export const jobs = {
  list: (params?: Params) => api.get<Paginated<Job>>("jobs/", params),
  get: (uuid: string) => api.get<Job>(`jobs/${uuid}/`),
  cancel: (uuid: string) => api.post<Job>(`jobs/${uuid}/cancel/`),
};

export const storagePools = {
  list: (params?: Params) => api.get<Paginated<StoragePool>>("storages/", params),
  get: (uuid: string) => api.get<StoragePool>(`storages/${uuid}/`),
  create: (body: Partial<StoragePool>) => api.post<StoragePool>("storages/", body),
};

export const networks = {
  list: (params?: Params) => api.get<Paginated<NodePilotNetwork>>("networks/", params),
  create: (body: Partial<NodePilotNetwork>) => api.post<NodePilotNetwork>("networks/", body),
};

export const subnets = {
  list: (params?: Params) => api.get<Paginated<Subnet>>("subnets/", params),
  create: (body: { network: string; cidr: string; gateway?: string | null }) => api.post<Subnet>("subnets/", body),
  allocateIp: (uuid: string, note?: string) => api.post<IPAddress>(`subnets/${uuid}/allocate/`, { note }),
  reserveIp: (uuid: string, address: string, note?: string) => api.post<IPAddress>(`subnets/${uuid}/reserve/`, { address, note }),
};

export const ipAddresses = {
  list: (params?: Params) => api.get<Paginated<IPAddress>>("ips/", params),
  release: (uuid: string) => api.post<IPAddress>(`ips/${uuid}/release/`),
};

export const images = {
  list: (params?: Params) => api.get<Paginated<Image>>("images/", params),
  remove: (uuid: string) => api.delete(`images/${uuid}/`),
  initiateUpload: (body: { name: string; version?: string; type: string; format?: string; storage: string; total_size_bytes: number; expected_sha256?: string }) =>
    api.post<{ uuid: string; image: Image; total_size_bytes: number; received_bytes: number; next_chunk_index: number; status: string }>("images/uploads/", body),
  finalizeUpload: (sessionUuid: string) => api.post<Image>(`images/uploads/${sessionUuid}/finalize/`),
};

export const templates = {
  list: (params?: Params) => api.get<Paginated<Template>>("templates/", params),
  deploy: (uuid: string, body: Record<string, unknown>, idempotencyKey: string) =>
    api.post<{ id: string; status: string; job_id: string | null }>(`templates/${uuid}/deploy/`, body, idempotencyKey),
};

export const snapshots = {
  list: (params?: Params) => api.get<Paginated<Snapshot>>("snapshots/", params),
  create: (vm: string, name: string, description = "") => api.post<JobRef>("snapshots/", { vm, name, description }),
  rollback: (uuid: string) => api.post<JobRef>(`snapshots/${uuid}/rollback/`),
  remove: (uuid: string) => api.delete<JobRef>(`snapshots/${uuid}/`),
};

export const backupTargets = {
  list: (params?: Params) => api.get<Paginated<BackupTarget>>("backup-targets/", params),
  create: (body: Partial<BackupTarget>) => api.post<BackupTarget>("backup-targets/", body),
};

export const backups = {
  list: (params?: Params) => api.get<Paginated<Backup>>("backups/", params),
  create: (vm: string, target: string, type: string) => api.post<JobRef>("backups/", { vm, target, type }),
  restore: (uuid: string) => api.post<JobRef>(`backups/${uuid}/restore/`),
  remove: (uuid: string) => api.delete(`backups/${uuid}/`),
};

export const backupSchedules = {
  list: (params?: Params) => api.get<Paginated<BackupSchedule>>("backup-schedules/", params),
  create: (body: { organization: string; vm: string; target: string; backup_type: string; cron_expression: string; timezone?: string; retention_days?: number }) =>
    api.post<BackupSchedule>("backup-schedules/", body),
  remove: (uuid: string) => api.delete(`backup-schedules/${uuid}/`),
};

export const events = {
  list: (params?: Params) => api.get<Paginated<NodePilotEvent>>("events/", params),
};

export const webhooks = {
  list: (params?: Params) => api.get<Paginated<Webhook>>("webhooks/", params),
  create: (body: { organization: string; name: string; url: string; events: string[] }) => api.post<Webhook>("webhooks/", body),
  remove: (uuid: string) => api.delete(`webhooks/${uuid}/`),
};

export const auditLogs = {
  list: (params?: Params) => api.get<Paginated<AuditLog>>("audit/", params),
};

export const metrics = {
  node: (uuid: string, sinceSeconds?: number) => api.get<{ node: string; samples: Record<string, unknown>[] }>(`metrics/nodes/${uuid}/`, { since_seconds: sinceSeconds }),
  vm: (uuid: string, sinceSeconds?: number) => api.get<{ vm: string; samples: Record<string, unknown>[] }>(`metrics/vms/${uuid}/`, { since_seconds: sinceSeconds }),
};

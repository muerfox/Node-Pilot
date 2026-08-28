// Mirrors backend/apps/*/serializers.py. Kept hand-written (not
// codegen'd from /api/schema/) for this pass -- see frontend/README.md
// for the suggested `openapi-typescript` upgrade path.

export interface Paginated<T> {
  count: number;
  page: number;
  num_pages: number;
  page_size: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> };
}

export interface Organization {
  uuid: string;
  name: string;
  slug: string;
  description: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Project {
  uuid: string;
  organization: string;
  name: string;
  slug: string;
  description: string;
  is_active: boolean;
  created_at: string;
}

export interface Quota {
  uuid: string;
  organization: string;
  project: string | null;
  max_vms: number;
  max_vcpu: number;
  max_memory_mb: number;
  max_storage_gb: number;
  max_snapshots: number;
}

export interface User {
  uuid: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  is_service_account: boolean;
  date_joined: string;
  last_login: string | null;
}

export interface APIToken {
  uuid: string;
  name: string;
  prefix: string;
  scopes: string[];
  expires_at: string | null;
  last_used_at: string | null;
  revoked: boolean;
  created_at: string;
  token?: string; // present only in the create response
}

export type NodeStatus = "ONLINE" | "OFFLINE" | "WARNING" | "MAINTENANCE" | "DISABLED";
export type NodeAdminState = "ACTIVE" | "MAINTENANCE" | "DISABLED";

export interface Agent {
  uuid: string;
  agent_id: string | null;
  status: "ACTIVE" | "DISABLED" | "REVOKED" | "OFFLINE";
  token_prefix: string;
  protocol_version: string;
  mtls_enabled: boolean;
  last_heartbeat_at: string | null;
  registered_at: string;
}

export interface Node {
  uuid: string;
  organization: string;
  name: string;
  hostname: string;
  fqdn: string;
  admin_state: NodeAdminState;
  status: NodeStatus;
  agent_version: string;
  kernel: string;
  architecture: string;
  cpu_model: string;
  cpu_threads: number;
  cpu_cores: number;
  cpu_sockets: number;
  memory_total_mb: number;
  memory_available_mb: number;
  storage_total_gb: number;
  storage_available_gb: number;
  reported_vm_count: number;
  last_seen: string | null;
  agent: Agent | null;
  created_at: string;
  updated_at: string;
}

export type VMStatus = "CREATING" | "STOPPED" | "RUNNING" | "PAUSED" | "SUSPENDED" | "MIGRATING" | "ERROR" | "DELETING" | "UNKNOWN";
export type ProvisioningState =
  | "REQUESTED"
  | "ALLOCATING"
  | "DISK_CREATED"
  | "NETWORK_CREATED"
  | "DOMAIN_CREATED"
  | "CLOUD_INIT_ATTACHED"
  | "STARTED"
  | "READY"
  | "ERROR";

export interface VMDisk {
  uuid: string;
  storage: string;
  name: string;
  volume_id: string;
  bus: "VIRTIO" | "VIRTIO_SCSI" | "SATA" | "IDE";
  device: string;
  size_bytes: number;
  format: string;
  bootable: boolean;
  readonly: boolean;
  discard: boolean;
  iothread: boolean;
  boot_index: number;
}

export interface VMNic {
  uuid: string;
  network: string;
  mac_address: string;
  model: "VIRTIO" | "E1000";
  vlan: number | null;
  rate_limit_mbps: number | null;
  bootable: boolean;
  boot_index: number;
  ip_address: string | null;
}

export interface VirtualMachine {
  uuid: string;
  name: string;
  hostname: string;
  description: string;
  organization: string;
  project: string;
  node: string | null;
  status: VMStatus;
  provisioning_state: ProvisioningState;
  os_type: string;
  firmware: "BIOS" | "UEFI";
  machine_type: string;
  cpu_count: number;
  cpu_sockets: number;
  cpu_cores: number;
  cpu_threads: number;
  cpu_model: string;
  memory_mb: number;
  min_memory_mb: number | null;
  max_memory_mb: number | null;
  ballooning_enabled: boolean;
  boot_order: string[];
  autostart: boolean;
  cloud_init_enabled: boolean;
  disks: VMDisk[];
  nics: VMNic[];
  last_error: string;
  created_at: string;
  updated_at: string;
}

export type JobStatus = "QUEUED" | "RUNNING" | "SUCCESS" | "FAILED" | "CANCELING" | "CANCELED";

export interface Job {
  uuid: string;
  type: string;
  status: JobStatus;
  organization: string;
  resource_type: string;
  resource_id: string;
  node: string | null;
  created_by: string | null;
  progress: number;
  message: string;
  error: string;
  logs: { at: string; line: string }[];
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export type StorageType = "DIRECTORY" | "LVM" | "LVM_THIN" | "ZFS" | "NFS" | "CEPH_RBD";
export type StorageCapability = "VM_DISK" | "ISO" | "BACKUP" | "SNAPSHOT" | "TEMPLATE";

export interface StoragePool {
  uuid: string;
  node: string;
  name: string;
  type: StorageType;
  path: string;
  capacity_bytes: number;
  used_bytes: number;
  available_bytes: number;
  status: "ONLINE" | "OFFLINE" | "WARNING" | "ERROR";
  shared: boolean;
  enabled: boolean;
  capabilities: StorageCapability[];
  created_at: string;
}

export interface NodePilotNetwork {
  uuid: string;
  node: string;
  name: string;
  type: "BRIDGE" | "VLAN" | "NAT" | "ROUTED" | "ISOLATED";
  bridge: string;
  vlan_id: number | null;
  dhcp_enabled: boolean;
  status: "ACTIVE" | "INACTIVE" | "ERROR";
  created_at: string;
}

export interface Subnet {
  uuid: string;
  network: string;
  cidr: string;
  gateway: string | null;
  dns_servers: string[];
  created_at: string;
}

export interface IPAddress {
  uuid: string;
  subnet: string;
  address: string;
  state: "AVAILABLE" | "ALLOCATED" | "RESERVED" | "BLOCKED";
  note: string;
  created_at: string;
}

export type ImageType = "ISO" | "QCOW2" | "RAW" | "VMDK";
export type ImageStatus = "PENDING" | "UPLOADING" | "VERIFYING" | "READY" | "FAILED";

export interface Image {
  uuid: string;
  name: string;
  version: string;
  type: ImageType;
  format: string;
  size_bytes: number;
  checksum_algorithm: string;
  sha256: string;
  source: string;
  status: ImageStatus;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Template {
  uuid: string;
  organization: string;
  image: string;
  name: string;
  description: string;
  default_cpu_count: number;
  default_memory_mb: number;
  default_disk_gb: number;
  default_firmware: "BIOS" | "UEFI";
  default_os_type: string;
  network_defaults: Record<string, unknown>;
  cloud_init_defaults: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
}

export type SnapshotStatus = "CREATING" | "READY" | "DELETING" | "ROLLING_BACK" | "ERROR";

export interface Snapshot {
  uuid: string;
  vm: string;
  name: string;
  description: string;
  status: SnapshotStatus;
  size_bytes: number;
  created_at: string;
}

export type BackupStatus = "PENDING" | "RUNNING" | "VERIFYING" | "COMPLETED" | "FAILED" | "RESTORING" | "DELETED";

export interface BackupTarget {
  uuid: string;
  organization: string;
  name: string;
  type: "LOCAL" | "NFS" | "S3" | "MINIO" | "CEPH";
  config: Record<string, unknown>;
  encryption_key_id: string;
  enabled: boolean;
  created_at: string;
}

export interface BackupSchedule {
  uuid: string;
  organization: string;
  vm: string;
  target: string;
  backup_type: "FULL" | "INCREMENTAL" | "SNAPSHOT";
  cron_expression: string;
  timezone: string;
  retention_days: number;
  enabled: boolean;
  created_at: string;
}

export interface Backup {
  uuid: string;
  vm: string;
  target: string;
  type: "FULL" | "INCREMENTAL" | "SNAPSHOT";
  status: BackupStatus;
  size_bytes: number;
  checksum: string;
  encrypted: boolean;
  started_at: string | null;
  finished_at: string | null;
  retention_expires_at: string | null;
  created_at: string;
}

export interface NodePilotEvent {
  uuid: string;
  type: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  resource_type: string;
  resource_id: string;
  organization: string;
  actor: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Webhook {
  uuid: string;
  organization: string;
  name: string;
  url: string;
  /** Masked (`********1234`) on list/retrieve; only the create response carries the full secret. */
  secret: string;
  events: string[];
  enabled: boolean;
  created_at: string;
}

export interface AuditLog {
  uuid: string;
  actor: string | null;
  actor_label: string;
  action: string;
  resource_type: string;
  resource_id: string;
  organization: string | null;
  ip_address: string | null;
  result: "SUCCESS" | "FAILURE";
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Role {
  uuid: string;
  name: string;
  organization: string | null;
  permissions: string[];
  is_system: boolean;
}

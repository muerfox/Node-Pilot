# NodePilot Architecture

NodePilot is split into two independently deployed, independently
versioned projects that agree on one contract -- the **Agent Protocol**
(`backend/apps/nodes/protocol.py` / `agent/nodepilot_agent/protocol.py`):

```
                    +------------------------------+
                    |          NodePilot            |
                    |                              |
                    | Web UI (React/TypeScript,     |
                    |  frontend/, talks only to     |
                    |  the REST/WebSocket API)      |
                    | REST API  (Django + DRF)      |
                    | Auth / RBAC                    |
                    | Scheduler / Job System (Celery) |
                    | WebSocket Gateway (Channels)  |
                    +--------------+----------------+
                                   |
                         Secure Agent Protocol
                     (agent-initiated WebSocket +
                      authenticated HTTP heartbeat)
                                   |
               +-------------------+-------------------+
               |                   |                   |
        +------+------+     +------+------+     +------+------+
        | NodePilot   |     | NodePilot   |     | NodePilot   |
        | Agent       |     | Agent       |     | Agent       |
        | node-01     |     | node-02     |     | node-03     |
        +------+------+     +------+------+     +------+------+
               |                   |                   |
          KVM/QEMU             KVM/QEMU             KVM/QEMU
          libvirt              libvirt              libvirt
```

## Controller owns desired state; agent owns actual state

The controller (`backend/`) never touches libvirt, QEMU, or a
hypervisor's disks/network directly. It owns:

- Users, Organizations, Projects, RBAC (`apps.users`, `apps.organizations`, `apps.permissions`)
- The Job system and its state machine (`apps.jobs`)
- Desired configuration for VMs/disks/networks/storage pools (`apps.virtual_machines`, `apps.storage`, `apps.networks`)
- Scheduling (`apps.virtual_machines.scheduler`)
- Audit (`apps.audit`) and events (`apps.events`)
- The REST/WebSocket API (`apps.api`)

The agent (`agent/`) owns:

- libvirt domain lifecycle (`nodepilot_agent.libvirt_client`)
- Storage backends: directory/qcow2, LVM, LVM-thin, ZFS, NFS (`nodepilot_agent.storage`)
- Host networking: Linux bridges/VLANs (`nodepilot_agent.network`)
- Host + VM metrics (`nodepilot_agent.metrics`)
- Cloud-init generation (`nodepilot_agent.cloud_init`)

**The controller's database is never assumed to be the same as the
hypervisor's actual state.** `apps.nodes.reconciliation` periodically
compares the VM count the database believes it manages against what the
agent last reported and emits a `RECONCILIATION_MISMATCH` event on
drift -- it never silently "fixes" the database.

## Every privileged operation is a typed message, never shell

There is no `POST /api/execute-shell` and there never will be. The full
set of operations the agent will perform is the closed enum
`OperationType` (`CREATE_VM`, `DELETE_DISK`, `ATTACH_NIC`, ...). Every
subprocess call inside the agent uses an argument list
(`subprocess.run([...])`), never `shell=True` with interpolated strings.

## Request flow for a mutating VM operation

1. `POST /api/v1/vms/{id}/start/` hits `VirtualMachineViewSet.start`.
2. The view calls `apps.virtual_machines.services.start_vm`, which does a
   fast optimistic Redis-lock check, creates a `Job` row (`QUEUED`), and
   returns `{"job_id", "status": "queued"}` immediately -- **the HTTP
   handler never blocks on the actual operation** (rule 4/5).
3. A Celery task (`apps.virtual_machines.tasks.start_vm_task`) picks up
   the job, acquires `vm:{uuid}:lifecycle` in Redis (section 20), and
   calls `apps.nodes.agent_client.send_operation(...)`.
4. `agent_client` publishes the typed request onto the node's
   `agent.{node_id}` Channels group; `AgentConsumer` (running in the ASGI
   process, holding the agent's live WebSocket) relays it out over the
   wire.
5. The agent's `Dispatcher` runs the matching handler (`vm_ops.start_vm`)
   in a thread executor (libvirt calls are blocking) and sends an
   `AgentResponse` back over the same WebSocket.
6. `AgentConsumer.receive` writes the correlated response into a
   short-lived Redis key; `agent_client.send_operation` (still blocked in
   the Celery worker) polls it, returns, and the task transitions the Job
   to `SUCCESS`/`FAILED` and broadcasts progress over `/ws/jobs/{id}`.

## What's implemented vs. scaffolded vs. explicitly deferred

**Fully implemented, with passing tests:** RBAC/policy engine, JWT +
API-token auth, organizations/projects/quotas, the Job state machine,
node registration + heartbeat + computed online/offline status, the
agent protocol + WebSocket transport + Redis-correlated RPC, the full VM
provisioning/lifecycle/clone state machine with rollback-on-failure
cleanup, network create/delete provisioning with real per-VLAN traffic
isolation (a dedicated bridge per VLAN, never a shared/untagged one),
IPAM allocation and reservation, storage-capability-aware snapshots, chunked
image upload with streaming checksum verification, webhook delivery with
HMAC signing + exponential backoff, Redis-backed short-term metrics for
both hosts and individual VMs (the agent's `vm_metrics_loop` computes
real CPU% from libvirt `cpu_time` deltas and pushes it alongside memory
RSS every heartbeat interval, scoped server-side so an agent can only
report metrics for VMs actually scheduled on its own node), a working
graphical console (noVNC's RFB client in the browser, talking straight
through the existing WebSocket relay to the agent's proxy onto QEMU's
VNC socket -- no extra framing needed since that relay already carries
raw binary both ways), the CLI, and the agent's libvirt/storage/network/
cloud-init abstractions. The web UI (`frontend/`, React/TypeScript)
covers every resource in the nav -- dashboard, nodes, VMs (list/wizard/
10-tab detail, console included), networks/IPAM, storage, images (real
chunked upload), templates, jobs, backups, and the admin pages -- against
the real API, with live job/status updates over WebSockets; see
`frontend/README.md`.

**Present but intentionally limited (documented, not faked):**

- **Live migration** (section 44): the API endpoint performs real
  compatibility checks (target node online, shared storage) and then
  returns `501 MIGRATION_NOT_IMPLEMENTED` rather than claiming success --
  actual live-migration execution is Phase 9 per the project's own phased
  rollout (section 70).
- **HA** (section 45): explicitly out of scope for this pass, per the
  same phased rollout ("do not implement unsafe automatic failover until
  fencing/split-brain protection is properly designed").
- **Backup targets**: LOCAL/NFS and S3/MinIO/Ceph (RGW) are all
  implemented end-to-end -- the S3-compatible path uploads/downloads via
  `boto3` with server-side encryption and a sha256 checksum verified
  against the object, and `endpoint_url` is how MinIO/Ceph RGW targets
  are distinguished from real AWS S3. Any other target type still raises
  a clear `NotImplementedError` rather than a fake success.

Nothing in the implemented paths pretends to succeed when it didn't --
provisioning failures roll back and clean up partially created resources
and surface through the Job's `error` field; disabled backend types raise
instead of silently no-op'ing.

## Security review findings and fixes

A four-way security review (backend auth/RBAC, the agent's subprocess/
file handling, upload/webhook/SSRF surfaces, and frontend token
handling) found and fixed four real issues, each with a regression test:

- **Cross-tenant IDOR** (`apps/common/permissions.py`): object-level
  permission checks used to fall back to a client-supplied
  `?organization=` query parameter whenever the target object had no
  *direct* `organization` field (true of StoragePool, Network, Subnet,
  IPAddress, IPPool, Snapshot, Backup). A user who was merely a Member of
  org A -- with no write permission there -- could act on an org-A
  object by passing `?organization=<org-B-uuid>` for an unrelated org B
  where they *did* hold the permission. Fixed by deriving the
  organization strictly from the object itself
  (`_resolve_organization_from_object`), never from the request.
  `tests/test_cross_tenant_authorization.py`.
- **Webhook SSRF via redirect** (`apps/webhooks/tasks.py`): the
  private/loopback/link-local host check on a webhook URL
  (`_is_private_host`) only ran at creation time; `requests.post`
  follows redirects by default, so a webhook target that later responded
  with a 3xx to an internal address (cloud metadata, localhost services)
  made that check purely cosmetic. Fixed with `allow_redirects=False`.
  `tests/test_webhook_delivery.py`. DNS rebinding between validation and
  delivery -- flagged in that same review as a related, unclosed gap --
  is now also closed: `apps/webhooks/tasks.py` re-resolves and
  re-validates the host at delivery time (`security.resolve_safe_ip`)
  and pins the HTTP client's connection to that exact validated address
  (`security.pinned_dns`, a scoped `socket.getaddrinfo` override for the
  duration of the request) so the client's own separate DNS lookup can't
  be steered to a different address in the gap between the check and the
  connect. That monkeypatch is process-global, so `pinned_dns` serializes
  on a lock (`_dns_patch_lock`) -- harmless under Celery's default
  prefork pool (one task per process at a time) but load-bearing under a
  threaded/gevent/eventlet pool, where two deliveries running
  concurrently in the same process could otherwise clobber each other's
  patch or restore. `tests/test_webhook_dns_rebinding.py`.
- **XML attribute injection** (`agent/nodepilot_agent/domain_xml.py`):
  `xml.sax.saxutils.escape()`'s default entity set covers `&`/`<`/`>`
  only, not quotes -- every value here lands inside a double-quoted XML
  attribute, so a `StoragePool.path` or `Network.bridge` containing a
  literal `"` (both settable by an authenticated user with
  `storage.manage`/`network.manage`, no controller compromise needed)
  could break out and inject an arbitrary sibling element into the
  domain XML libvirt goes on to define -- e.g. a second `<disk>` exposing
  an arbitrary host path to the guest. Fixed by escaping quotes too.
  `agent/tests/test_domain_xml.py`.
- **Missing pool-scope check on LVM/LVM-thin/ZFS volume operations**
  (`agent/nodepilot_agent/storage/{lvm,lvm_thin,zfs}.py`):
  `DirectoryBackend` already refuses to delete/resize a path outside its
  own pool; the block-storage backends had no equivalent guard before
  calling `lvremove`/`lvextend`/`zfs destroy -r`/`zfs set`. Requires a
  bug elsewhere or a compromised controller (a `VMDisk.volume_id` is
  otherwise only ever set from the agent's own CREATE_DISK response, not
  directly by a platform user) but is a real defense-in-depth gap,
  particularly for ZFS's recursive `destroy -r`. Fixed with the same
  `_assert_within_*` pattern DirectoryBackend already uses.
  `agent/tests/test_storage_scope_checks.py`.

A fifth item was investigated as a lower-severity concern in that same
review and has since been closed: the frontend used to carry the raw JWT
access token as a `?token=` query parameter on WebSocket URLs (browsers
can't attach custom headers to a WS handshake), which risked the token
appearing in server/proxy access logs on the WS upgrade request. Fixed
by exchanging the JWT for a short-lived (30s), single-use ticket over an
ordinary authenticated HTTPS POST first
(`apps/authentication/ws_ticket.py`,
`POST /api/v1/auth/ws-ticket/`) and putting *that* in the WS URL instead
-- `apps/authentication/ws_auth.py`'s Channels middleware redeems it
atomically (a Lua GET-then-DELETE), so even a leaked ticket is useless
after the one legitimate connection it was issued for.
`tests/test_ws_ticket.py`.

## Post-review correctness fixes

Tracing the storage and backup paths end-to-end after the security review
surfaced three functional bugs, none of them security issues but each
one that would have broken real deployments:

- **Disk format never tracked past creation** (`apps/virtual_machines/
  tasks.py`, `agent/nodepilot_agent/domain_xml.py`): `VMDisk.format`
  wasn't persisted from the agent's CREATE_DISK response, and the domain
  XML generator hardcoded `type="qcow2"`/`type="file"` for every disk.
  Any VM whose boot disk lived on LVM, LVM-thin, ZFS, or Ceph RBD --
  which are always raw block devices, never files -- would get a domain
  definition libvirt can't actually boot. Fixed by propagating the
  agent-reported format/storage type through create, attach, and detach,
  and deriving the XML's disk `type`/driver `format` from
  `storage_type` (`_disk_source()` in `domain_xml.py`).
  `backend/tests/test_disk_format_propagation.py`,
  `agent/tests/test_domain_xml.py`.
- **Backup create/restore never sent which disk to operate on**
  (`apps/backups/tasks.py`, `agent/nodepilot_agent/operations/
  backup_ops.py`): the CREATE_BACKUP/RESTORE_BACKUP payloads carried the
  VM and target but no `volume_id`, so the agent had nothing to read
  from or write to -- despite prior documentation in this file claiming
  LOCAL/NFS backups worked end-to-end, they did not. Fixed by resolving
  the VM's boot disk (falling back to its lowest-boot-index disk) and
  including its `volume_id`/`format` in both payloads; a VM with no
  disks now fails the job cleanly (`VM_HAS_NO_DISKS`) instead of the
  agent receiving an unusable request. `backend/tests/
  test_backup_payloads.py`.
- **`BackupTarget.config` returned raw credentials on every list/
  retrieve** (`apps/backups/serializers.py`): once S3/MinIO/Ceph support
  landed, `config` routinely carries `access_key_id`/`secret_access_key`
  -- the same class of leak the security review closed for
  `Webhook.secret`. Fixed with the same pattern: a masked
  `SerializerMethodField` for list/retrieve (last 4 characters kept for
  identification) and a separate `BackupTargetCreateSerializer` that
  returns the full value only in the create/update response.
  `backend/tests/test_backup_target_secrets.py`.
- **Backup schedules could silently drift from what Celery Beat actually
  runs** (`apps/backups/serializers.py`, `apps/backups/services.py`,
  `apps/backups/views.py`): had no test coverage at all until this was
  found. Two compounding gaps -- `validate_cron_expression` only checked
  for 5 whitespace-separated fields, never that each was a valid cron
  value, and `_sync_periodic_task` feeds those fields straight into
  `CrontabSchedule.objects.get_or_create(...)`, which (unlike
  `full_clean()`) skips the model's own field validators, so e.g.
  `"99 25 abc def ghi"` was accepted with a 201 and produced a
  CrontabSchedule Beat could never evaluate. Separately,
  `update_schedule_enabled` -- written specifically to keep a schedule's
  linked `PeriodicTask` in sync -- was never actually called from
  anywhere; `BackupScheduleViewSet` had no `perform_update` override, so
  PATCH/PUT fell through to DRF's default `serializer.save()`, which
  updates the `BackupSchedule` row and never touches the `PeriodicTask`.
  `PATCH {"enabled": false}` looked like it worked (the row said so)
  while Beat kept firing the schedule on its original crontab forever;
  changing `cron_expression` had the same silent-drift problem. Fixed by
  validating each cron field against `django_celery_beat`'s own
  validators (`minute_validator`, `hour_validator`, ...) -- the same
  ones `CrontabSchedule` itself uses, so nothing accepted here can go on
  to silently fail at the model level -- and replacing
  `update_schedule_enabled` with a general `update_schedule` that
  re-syncs the linked `CrontabSchedule`/`PeriodicTask` for whichever
  fields actually affect it, wired in via `perform_update`.
  `backend/tests/test_backup_schedules.py`.
- **IP reservation was unreachable, and unsafe once reachable**
  (`apps/networks/services.py`): `IPAddressState.RESERVED` has been a
  first-class model state since section 23, and `reserve_ip` fully
  implemented it -- but nothing in the codebase ever called it: no view
  action, no CLI command, nothing. Once wired up it also turned out to
  be unsafe as written -- it used `update_or_create` unconditionally, so
  reserving an address currently `ALLOCATED` to a live VM NIC would have
  silently reassigned that NIC's address out from under it. Fixed by
  rejecting a reservation against an already-allocated address, adding
  a same-subnet-CIDR check, and exposing it as `POST
  /subnets/{uuid}/reserve/` (`SubnetViewSet.reserve`, alongside the
  existing `allocate` action) with a matching "Reserve IP" button on the
  Networks page. `backend/tests/test_ipam.py`.

Not every "no test coverage" lead panned out into a bug: `apps.nodes.tasks.sweep_offline_nodes`/`reconcile_nodes` (node offline detection and the drift-reconciliation sweep, both correctly registered in `CELERY_BEAT_SCHEDULE`) had zero test coverage but turned out to already be correct, including the trickier case of a node flapping offline, recovering, then going offline again without double-firing or dropping the second `NODE_OFFLINE` event. `backend/tests/test_node_health.py` now locks that in.

## Network provisioning was never wired up, and VLAN isolation didn't work at all

The single largest gap found this way: `NetworkViewSet` was a plain
`ModelViewSet` with no `perform_create`/`destroy` override, so creating
or deleting a `Network` through the API was a database-only operation.
`CREATE_NETWORK`/`DELETE_NETWORK` were defined in the Agent Protocol and
fully implemented on the agent side
(`nodepilot_agent.operations.network_ops`, using `nodepilot_agent.network`'s
`create_bridge`/`create_vlan_interface`/`attach_to_bridge` primitives) --
but the controller never dispatched them, so the bridge a Network row
claimed to represent was never actually created (or torn down) on the
hypervisor. `attach_to_bridge` in particular had zero callers anywhere.

Separately, and independently of that wiring gap: the per-NIC `vlan`
field the controller has always computed and sent on `CREATE_VM`'s NIC
payloads (`nic.vlan or nic.network.vlan_id`) was read nowhere on the
agent side -- `build_domain_xml`'s NIC loop never looked at it, and
`ATTACH_NIC`/`DETACH_NIC`'s payloads didn't even include it. Two VM NICs
on networks that only differed by `vlan_id` but happened to share the
same base bridge string ended up on the exact same untagged L2 segment --
no isolation at all, despite the platform presenting VLANs as configured
and enforced.

Fixed with real per-VLAN isolation rather than a `<vlan>` XML tag (which
libvirt only honors for standard Linux bridges under specific
vlan-filtering configurations that aren't guaranteed here): every VLAN
network gets a **dedicated bridge**, distinct from its parent/uplink
bridge, uplinked through a tagged 802.1Q sub-interface --
`network.ensure_vlan_network`/`teardown_vlan_network` orchestrate the
existing (previously unused) `create_vlan_interface` + `attach_to_bridge`
primitives to build and tear this down, and
`domain_xml._resolve_nic_bridge` / `network_ops._nic_target_bridge`
route NIC attachment to that dedicated bridge (named
`network.vlan_bridge_name`) instead of the raw parent, both for
`CREATE_VM` and for hot-attach/detach. Two networks that only differ by
`vlan_id` now always resolve to different bridges -- there is no L2 path
between them without going out through the tagged uplink. Attaching a
NIC to a `vlan` that was never provisioned via `CREATE_NETWORK` fails
with a clear libvirt "no such device" error rather than silently landing
on the wrong (untagged) segment.

Also fixed along the way: `create_vlan_interface` wasn't actually
idempotent (a retried `CREATE_NETWORK` would hit a raw `ip link add`
"File exists" failure), `NetworkSerializer.vlan_id` was spuriously
`required=True` at the API layer despite the model declaring
`null=True, blank=True` -- caused by `unique_together`'s
`UniqueTogetherValidator` requiring an explicit `default=None`, not just
`allow_null=True`, to treat a participating field as optional -- and
bridge/vlan_id are now validated against the same Linux interface-name
and length rules the agent enforces (`IFNAMSIZ` = 15 usable characters,
tighter still once a VLAN's dedicated-bridge suffix is appended), so a
bad value is rejected with a clear 400 instead of only failing once the
job reaches the agent. `Network` update (`PATCH`/`PUT`) is now disallowed
entirely (`405`, same rule `BackupViewSet` applies to backups) --
`bridge`/`vlan_id`/`type` are baked into what actually got provisioned at
create time, and allowing an edit would let the DB row silently diverge
from the real bridge/VLAN setup with no re-provisioning step to
reconcile them.

`backend/tests/test_network_provisioning.py`,
`backend/tests/test_vm_disk_nic_ops.py`,
`agent/tests/test_vlan_networks.py`, `agent/tests/test_network_ops.py`.

## Scheduler storage-overcommit race

`apps.virtual_machines.scheduler` (which node a VM lands on when none is
specified) had zero test coverage. Its CPU headroom check was already
careful -- it sums the vCPU count of only *running* VMs against a
node's static, overcommit-adjusted ceiling, so provisioned-but-stopped
VMs correctly don't count against it. Its storage headroom check wasn't:
it compared the request directly against `node.storage_available_gb`,
a value that's only as fresh as the node's last heartbeat. Unlike
memory/CPU, a VM's disk consumes real host storage the moment it's
created, regardless of whether the VM has ever started -- so two VMs
scheduled to the same node within one heartbeat interval could each
individually pass the capacity check and, together, overcommit real
storage. Fixed by subtracting disks created since the node's last
heartbeat (`scheduler._pending_storage_gb`) from its reported free
space -- the same "local DB is more current than the last heartbeat"
adjustment the CPU check already made, applied to the one resource
(disk space) that's actually consumed immediately. Also caught while
writing the tests: an early draft of the regression test for this exact
race passed even before the fix, because it left `memory_available_mb`
at the `Node` model's zero default -- the assertion was accidentally
exercising the memory check, not the storage one it claimed to.
`backend/tests/test_scheduler.py`.

## A failed snapshot rollback/delete attempt used to permanently brick the snapshot

`apps.snapshots` (services.py + tasks.py, real business logic behind a
destructive, dual-locked rollback path) had zero test coverage. Both
`rollback_snapshot_task` and `delete_snapshot_task` marked the snapshot
`ERROR` on any failure -- but `delete_snapshot`/`rollback_snapshot` both
require `status == READY` to even start, so `ERROR` was a dead end: a
single transient failure (an agent timeout, a momentary lock conflict)
left an otherwise-perfectly-good snapshot impossible to retry, roll back
to, or even delete, ever again, short of direct database access. This is
the same class of bug already fixed once in `apps.backups.tasks
.restore_backup_task` -- the snapshot/backup *artifact* is unaffected by
a failed *attempt* to use it -- just not applied here. Fixed by reverting
to `READY` (rollback: it can only ever have started from `READY` anyway;
delete: restores whatever status let the attempt start, so a delete
retry doesn't relabel a snapshot that was already broken for some other
reason). Also broadened `delete_snapshot` to allow deleting from `ERROR`
too (mirroring `VMStatus`'s own `_ALLOWED_FROM[VM_DELETE]`, which already
permits deleting an `ERROR` VM) so a snapshot that failed mid-*create* --
which correctly stays `ERROR`, since it never became a real artifact --
still has a way to be cleaned up. `backend/tests/test_snapshots.py`.

## Deploying a VM from a Template produced a completely blank disk

The largest gap found this way: `Template.image` -- a required FK, e.g.
"Ubuntu 24.04" -- was never referenced anywhere in VM provisioning.
`apps.vm_templates.services.create_vm_from_template`'s disk spec had no
mention of it, and the agent's `create_disk` always made a fresh blank
volume; there was no image-to-disk copy mechanism anywhere on either
side. Deploying "from a template" produced a VM with an empty,
unformatted disk -- nothing bootable, regardless of which image the
template named.

Closed end to end:

- **`VMDisk.source_image`** (new FK to `images.Image`, nullable):
  provenance -- which image, if any, this disk was seeded from at
  creation time. `create_vm_from_template` sets it on the template's
  boot disk; `create_vm` persists whatever `create_vm_from_template`
  passes through.
- **`apps.images.views.AgentImageDownloadView`** (new,
  `GET /api/v1/agent/images/{uuid}/download/`): images live centrally on
  the controller's own storage, never per-node
  (`apps.images.storage_backend`'s own docstring already said as much),
  so any node's agent can fetch any of its own organization's images
  over the same agent-token-authenticated HTTP channel already used for
  heartbeats -- this works identically regardless of which node's
  storage pool the new disk lands on, no agent-to-agent transfer needed.
  Agent-token authenticated only, and scoped to the requesting agent's
  own organization (404, not 403, on a cross-tenant hit, so existence
  isn't leaked either) -- images are never public.
  `IsAgentOrHasImageView` had apparently been scaffolded for exactly
  this and then never wired to anything; this is a fresh view, not a
  reuse of it.
- **`provision_vm`'s CREATE_DISK step** now includes `image_uuid`/
  `image_sha256`/`image_format` in the payload when `disk.source_image_id`
  is set, and raises the RPC timeout to 3600s for that case -- the
  default `AGENT_RPC_TIMEOUT_SECONDS` (30s) is nowhere near enough to
  download and convert a multi-GB OS image (same reasoning as backups'
  `CREATE_BACKUP`/`RESTORE_BACKUP` timeout).
- **`nodepilot_agent.image_fetch.download_image`**: streams the image to
  a local temp file over `httpx`, verifying its sha256 before it's ever
  handed to `qemu-img`.
- **`disk_ops.create_disk`**: after creating the (correctly sized/typed)
  blank volume as before, if an image was specified it runs
  `qemu-img convert -n -O <target_format> <downloaded_image> <volume_id>`
  to seed it -- `-n` writes into the volume already created instead of
  letting qemu-img create/resize a target to match the image's own size,
  since the requested disk can legitimately be larger than the base
  image (the guest just sees extra free space). This works unmodified
  for block-backed targets (LVM/LVM-thin/ZFS/Ceph RBD) too, since
  `qemu-img convert` can write directly to a block device -- no new
  `StorageBackend` method needed.
- `create_vm_from_template` also now rejects deploying from a template
  whose image isn't `READY` (`TemplateImageNotReady`, 409) instead of
  discovering that failure deep inside the async provisioning job.

`backend/tests/test_vm_templates.py`,
`backend/tests/test_agent_image_download.py`,
`agent/tests/test_image_fetch.py`, `agent/tests/test_disk_ops.py`.

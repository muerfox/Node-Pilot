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
cleanup, IPAM allocation, storage-capability-aware snapshots, chunked
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
- **Backup targets**: LOCAL/NFS are implemented end-to-end; S3/MinIO/Ceph
  raise a clear `NotImplementedError` rather than a fake success, since
  they need an object-storage client this pass doesn't ship.

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
  `tests/test_webhook_delivery.py`. (DNS rebinding between validation and
  delivery is a related, lower-severity gap that isn't closed yet --
  would need re-resolving and re-validating the host immediately before
  each delivery attempt.)
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

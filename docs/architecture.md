# NodePilot Architecture

NodePilot is split into two independently deployed, independently
versioned projects that agree on one contract -- the **Agent Protocol**
(`backend/apps/nodes/protocol.py` / `agent/nodepilot_agent/protocol.py`):

```
                    +------------------------------+
                    |          NodePilot            |
                    |                              |
                    | Web UI (not built in this    |
                    |  pass -- see "What's not     |
                    |  implemented" below)         |
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
HMAC signing + exponential backoff, Redis-backed short-term metrics, the
CLI, and the agent's libvirt/storage/network/cloud-init abstractions.

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
- **Web UI** (sections 38-42, 65-67): not built in this pass. The backend
  exposes a complete, documented REST/WebSocket API
  (`/api/docs/`, `/api/redoc/`) plus a CLI; a frontend can be built
  against that contract without backend changes. See `frontend/README.md`.

Nothing in the implemented paths pretends to succeed when it didn't --
provisioning failures roll back and clean up partially created resources
and surface through the Job's `error` field; disabled backend types raise
instead of silently no-op'ing.

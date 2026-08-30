# NodePilot

**NodePilot -- KVM Infrastructure, Simplified.**

NodePilot is a centralized control plane for managing Linux KVM/QEMU
virtualization hosts: VMs, storage, networks, snapshots, templates,
backups, users, permissions, metrics, and infrastructure automation. It
is built as a real multi-host virtualization platform -- a controller +
agent architecture, typed operation protocol, background job system with
progress tracking, RBAC, and reconciliation -- not a web wrapper around
`virsh`.

See `docs/architecture.md` for the full design (desired-state vs.
actual-state, the request/response flow for a mutating VM operation, and
an honest breakdown of what's fully implemented vs. intentionally
deferred in this codebase).

## Repository layout

```
backend/     Django/DRF/Channels/Celery controller -- the API, RBAC,
             and job system
agent/       nodepilot-agent -- runs on every KVM hypervisor; libvirt,
             storage, network, cloud-init, metrics
cli/         nodepilot -- CLI client for the REST API
frontend/    React/TypeScript web UI -- see frontend/README.md
deployment/  Dockerfiles, systemd units, nginx config
docs/        Architecture and installation docs
scripts/     Convenience installer for the agent
```

## Quickstart (development)

```bash
cp .env.example .env
docker compose up --build
```

This brings up PostgreSQL, Redis, the ASGI controller, a Celery worker,
and Celery Beat, running migrations and seeding the RBAC catalog
automatically. Then, in a second terminal:

```bash
cd frontend && npm install && npm run dev
```

- Web UI: http://localhost:5173/
- API docs: http://localhost:8000/api/docs/
- Admin: http://localhost:8000/admin/ (create a superuser first: `docker
  compose exec nodepilot-web python manage.py createsuperuser`)
- Health: http://localhost:8000/health/ready/

Register a hypervisor node and its agent via the UI, API, or CLI, then
run the agent on that host -- see `docs/installation.md` section 2. The
production controller install (no Docker required) is documented in
`docs/installation.md` section 1.

## Running the test suites

```bash
make test           # backend + agent + cli
# or individually:
make backend-test
make agent-test
make cli-test
```

The backend suite (81 tests) runs against SQLite with a faked Redis (no
external services required); it covers the RBAC policy engine
(including a cross-tenant authorization regression and the WebSocket
ticket auth flow -- see `docs/architecture.md`'s security review
section), quota enforcement, IPAM allocation, distributed locking, the
Job state machine, a full VM-provisioning run, disk/NIC hot-plug, per-VM
metrics ingest, webhook delivery's SSRF-redirect and DNS-rebinding
protection, disk-format propagation onto the domain XML, backup
create/restore payload correctness, and backup-target credential
masking, all with the agent
RPC layer mocked. The agent suite (48 tests, +3 skipped when `qemu-img`
isn't installed) covers protocol framing, domain-XML generation
(including XML-attribute-injection safety and block- vs. file-backed
disk format selection), the storage backends' path-traversal and
pool-scope protection, operation dispatch, the real CPU% delta
computation behind per-VM metrics, and a real S3 upload/download round
trip (via `moto`) for the S3/MinIO/Ceph-RGW backup target. The CLI suite
(8 tests) covers the HTTP client and command wiring. The frontend (`npm
run typecheck && npm run lint && npm run build`) type-checks, lints
clean, and builds to a 146 KB gzipped bundle (noVNC accounts for most of
that). 137 automated tests pass as of this build.

## CLI

```bash
pip install ./cli
nodepilot login
nodepilot doctor
nodepilot node list
nodepilot vm list
nodepilot vm start <uuid>
```

## Security posture

No unrestricted shell execution is exposed anywhere in this codebase --
the agent protocol is a closed set of typed operations
(`agent/nodepilot_agent/protocol.py`), and every subprocess call in the
agent uses an argument list, never `shell=True` on interpolated input.
See `docs/architecture.md` for the full list of security properties
(RBAC, audit logging, distributed locking, SSRF mitigation on webhook
URLs, path-traversal-safe storage volume naming, never-store-raw-tokens
credential handling).

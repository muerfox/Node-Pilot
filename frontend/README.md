# NodePilot Web UI

React + TypeScript + Vite, talking to the controller's REST/WebSocket API
(`../backend/`) only -- no direct database access, matching the same
rule the CLI follows.

## Running it

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api and /ws to :8000 (see vite.config.ts)
```

Against the Docker dev stack: `docker compose up` first (controller on
`:8000`), then `npm run dev` here.

```bash
npm run typecheck   # tsc -b, no emit errors
npm run lint         # eslint
npm run build        # production build to dist/
```

## What's implemented

Every page in the nav (Dashboard; Nodes; Virtual Machines incl. the
create wizard and a 10-tab detail page -- Overview/Console/Hardware/
Disks/Network/Snapshots/Backups/Metrics/Events/Tasks; Networks/IPAM;
Storage; Images with real chunked upload; Templates; Jobs; Backups incl.
schedules and targets; Users/Organizations/API Tokens/Webhooks/Audit
Logs; global Search) is wired to real backend endpoints -- there is no
mocked or placeholder data anywhere. Job-driven mutations (start/stop/
create/clone/snapshot/backup/...) show live progress via
`/ws/jobs/{id}`; Node and VM status update live via their own channels.

The Console tab renders a real graphical console: `@novnc/novnc`'s RFB
client talks straight through the WebSocket relay to the agent's proxy
onto QEMU's VNC socket (`agent/nodepilot_agent/console.py`) -- no extra
framing needed, since that relay already carries raw binary frames both
ways. The Metrics tab reads real per-VM CPU%/memory samples pushed by
the agent's `vm_metrics_loop` (computed from actual libvirt `cpu_time`
deltas, never fabricated) via `/api/v1/agent/vm-metrics/`.

## Key files

- `src/lib/api.ts` -- fetch wrapper, JWT (access in memory, refresh in
  localStorage), auto-refresh-and-retry on 401, standard error envelope.
- `src/lib/resources.ts` -- one typed function per backend endpoint.
- `src/lib/ws.ts` -- reconnecting WebSocket subscription hook.
- `src/lib/auth.tsx` -- auth context/provider.
- `src/components/` -- shared UI primitives (StatusBadge, JobTracker,
  ConfirmButton for destructive actions, Modal, pickers, ...).
- `src/pages/` -- one file per route; `src/pages/vm-tabs/` holds the VM
  detail page's ten tabs as separate components.

## Auth notes

- JWT access/refresh via `/api/v1/auth/login/` and `/api/v1/auth/refresh/`.
  Access token lives in memory only; refresh token in `localStorage`
  (the backend has no httpOnly-cookie delivery path for it).
- WebSocket connections authenticate via a `?ticket=` query parameter --
  never the JWT itself, to keep it out of proxy/server access logs.
  `authenticatedWsUrl()` (`src/lib/api.ts`) exchanges the access token
  for a short-lived, single-use ticket over an ordinary authenticated
  HTTPS POST first; see `../backend/apps/authentication/ws_ticket.py`
  and `ws_auth.py`.

## Design

A dense, professional infrastructure-management look (section 65) --
deliberately not a Proxmox clone: a dark slate/blue "control plane"
palette (`tailwind.config.js`), status-colored badges, destructive
actions requiring a second confirming click (`ConfirmButton`), and no
unnecessary animation.

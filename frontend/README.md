# NodePilot Web UI

Not implemented in this pass. The backend (`../backend/`) exposes a
complete, documented REST API (`/api/docs/`, `/api/redoc/`,
`/api/schema/`) and WebSocket channels for jobs, VM status, node status,
events, and the interactive console (see `../docs/architecture.md` and
spec sections 36-42/65-67) -- a frontend can be built against that
contract without any backend changes.

## Suggested approach

- **Framework**: React or Vue + TypeScript, generating an API client from
  `/api/schema/` (e.g. `openapi-typescript` + a thin fetch wrapper, or
  `orval`).
- **Auth**: JWT access/refresh via `/api/v1/auth/login/` and
  `/api/v1/auth/refresh/`; store the access token in memory, not
  `localStorage`, and use the same session for WebSocket auth (Channels'
  `AuthMiddlewareStack` reads the session cookie -- see the note in
  `../backend/apps/virtual_machines/views.py`'s `console` action).
- **Console**: connect to `wss://.../ws/console/{vm_uuid}` and feed
  received binary frames into a noVNC (or xterm.js, for serial) client;
  see `../agent/nodepilot_agent/console.py` for the wire framing.
- **Real-time updates**: `/ws/jobs/{id}`, `/ws/vms/{id}`, `/ws/nodes/{id}`,
  `/ws/events` for the dashboard/detail-page live updates described in
  spec sections 39-40.
- **Design**: sections 65-67 call for a dense, professional
  infrastructure-management aesthetic (not a Proxmox clone) with clear
  status indicators, destructive-action confirmation, and live operation
  progress -- the Job model's `progress`/`message`/`logs` fields plus the
  `/ws/jobs/{id}` stream are built to drive exactly that kind of UI.

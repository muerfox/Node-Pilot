# Installing NodePilot

NodePilot has two halves that are installed differently:

- **Controller** -- a Django app, runs anywhere (VM, container, bare
  metal) that can reach PostgreSQL and Redis. Docker is fine here.
- **Agent** -- runs directly on every KVM hypervisor, as a systemd
  service, with access to `/var/run/libvirt/libvirt-sock`. **Never**
  run the agent in a container in production -- it needs to manage the
  host's real storage/network/libvirt, and containerizing that away
  defeats the point.

## 1. Controller installation

### 1a. Dependencies

- Python 3.11+
- PostgreSQL 14+
- Redis 6+
- A reverse proxy that supports WebSocket upgrades (nginx example in
  `deployment/nginx/nodepilot.conf`)

### 1b. Manual / package-based install (recommended for production)

```bash
sudo useradd --system --home /opt/nodepilot --shell /usr/sbin/nologin nodepilot
sudo mkdir -p /opt/nodepilot /var/lib/nodepilot/media /var/lib/nodepilot/media/uploads/chunks
sudo chown -R nodepilot:nodepilot /opt/nodepilot /var/lib/nodepilot

sudo -u nodepilot git clone https://github.com/muerfox/Node-Pilot.git /opt/nodepilot/src
cd /opt/nodepilot/src/backend

sudo -u nodepilot python3 -m venv /opt/nodepilot/backend/.venv
sudo -u nodepilot /opt/nodepilot/backend/.venv/bin/pip install -r requirements/production.txt

sudo cp .env.example /opt/nodepilot/backend/.env
sudo $EDITOR /opt/nodepilot/backend/.env   # set SECRET_KEY, JWT_SIGNING_KEY, POSTGRES_*, REDIS_URL, ALLOWED_HOSTS, CORS_*

# Create the database
sudo -u postgres createuser nodepilot
sudo -u postgres createdb -O nodepilot nodepilot

cd /opt/nodepilot/backend
sudo -u nodepilot DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/python manage.py migrate
sudo -u nodepilot DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/python manage.py seed_rbac
sudo -u nodepilot DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/python manage.py createsuperuser
sudo -u nodepilot DJANGO_SETTINGS_MODULE=config.settings.production .venv/bin/python manage.py collectstatic --noinput

sudo cp ../deployment/systemd/nodepilot-web.service \
        ../deployment/systemd/nodepilot-worker.service \
        ../deployment/systemd/nodepilot-beat.service \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nodepilot-web nodepilot-worker nodepilot-beat

sudo cp ../deployment/nginx/nodepilot.conf /etc/nginx/sites-available/nodepilot.conf
sudo ln -s /etc/nginx/sites-available/nodepilot.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 1c. Docker-based development (not for production)

```bash
cp .env.example .env
docker compose up --build
```

This starts PostgreSQL, Redis, the ASGI web process, a Celery worker, and
Celery Beat. It runs migrations and seeds RBAC automatically. The
controller is then reachable at `http://localhost:8000`, with API docs
at `http://localhost:8000/api/docs/`.

## 2. Agent installation (on each hypervisor)

### 2a. Register the node and obtain a token

From a machine with the CLI installed and authenticated
(`pip install ./cli && nodepilot login`):

```bash
nodepilot node list --organization <org-uuid>   # or create one via the API/admin first
nodepilot agent register <node-uuid>
# prints: node_id, agent_id, token -- copy the token now, it is shown once
```

### 2b. Install the agent (package/manual method)

```bash
sudo useradd --system --home /var/lib/nodepilot --shell /usr/sbin/nologin nodepilot
sudo usermod -aG libvirt,kvm,disk nodepilot
sudo mkdir -p /etc/nodepilot /var/lib/nodepilot/pools /var/lib/nodepilot/cloud-init
sudo chown -R nodepilot:nodepilot /var/lib/nodepilot

python3 -m venv /opt/nodepilot-agent/.venv
/opt/nodepilot-agent/.venv/bin/pip install -e ./agent[libvirt]   # from a checkout of this repo
sudo ln -s /opt/nodepilot-agent/.venv/bin/nodepilot-agent /usr/local/bin/nodepilot-agent

sudo tee /etc/nodepilot/agent.yaml <<'EOF'
controller_url: https://nodepilot.example.com
node_id: <node-uuid-from-step-2a>
agent_token: <token-from-step-2a>
EOF
sudo chmod 600 /etc/nodepilot/agent.yaml

sudo cp agent/systemd/nodepilot-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nodepilot-agent
sudo systemctl status nodepilot-agent
```

### 2c. Scripted install (convenience wrapper around 2b)

`scripts/install-agent.sh` automates the steps above for a standard
Debian/Ubuntu host. It is **one of two supported installation paths, not
the only one** (section 59) -- read it before running it:

```bash
curl -fsSL https://raw.githubusercontent.com/muerfox/Node-Pilot/main/scripts/install-agent.sh -o install-agent.sh
less install-agent.sh   # review before running anything as root
sudo NODEPILOT_CONTROLLER_URL=https://nodepilot.example.com \
     NODEPILOT_NODE_ID=<node-uuid> \
     NODEPILOT_AGENT_TOKEN=<token> \
     bash install-agent.sh
```

Verify with `nodepilot agent status <node-uuid>` from the CLI, or check
the node's status in `GET /api/v1/nodes/{uuid}/`.

## 3. Database migrations / upgrades / rollback

- **Migrate**: `python manage.py migrate` (run automatically by the
  Docker dev stack; run manually as part of your deploy for production --
  never auto-migrate on every controller restart in prod, so a bad
  release can't half-apply a migration under load).
- **Upgrade**: stop `nodepilot-worker`/`nodepilot-beat` (in-flight jobs
  finish or fail cleanly -- see the Job state machine), deploy the new
  code, run `migrate`, restart all three services in the order
  web -> worker -> beat.
- **Rollback**: NodePilot's migrations are standard Django migrations;
  roll back with `python manage.py migrate <app> <previous_migration>`
  before redeploying the previous release's code. Because the API is
  versioned and kept backwards-compatible within `v1` (rule 20), a
  controller rollback does not require an agent rollback -- agents report
  their version on every heartbeat, and the controller rejects
  potentially destructive operations against an incompatible agent
  (`AGENT_VERSION_UNSUPPORTED`, section 54).

## 4. Backups (of NodePilot itself)

Back up the PostgreSQL database (`pg_dump`) and `/var/lib/nodepilot/media`
(the image/ISO library) on a schedule -- this is separate from, and in
addition to, the VM backup feature (section 26) NodePilot exposes to its
users for their own VMs.

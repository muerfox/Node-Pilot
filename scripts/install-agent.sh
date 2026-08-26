#!/usr/bin/env bash
#
# Convenience installer for the NodePilot Agent on a Debian/Ubuntu KVM
# host. This is ONE of two supported installation paths (see
# docs/installation.md section 2) -- the manual/package-based steps are
# documented there and work identically without this script.
#
# Required environment variables:
#   NODEPILOT_CONTROLLER_URL   e.g. https://nodepilot.example.com
#   NODEPILOT_NODE_ID          UUID from `nodepilot agent register`
#   NODEPILOT_AGENT_TOKEN      token from `nodepilot agent register`
#
# Must be run as root (it creates a system user, installs packages, and
# writes a systemd unit).

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (it creates the 'nodepilot' system user and a systemd unit)." >&2
    exit 1
fi

: "${NODEPILOT_CONTROLLER_URL:?Set NODEPILOT_CONTROLLER_URL}"
: "${NODEPILOT_NODE_ID:?Set NODEPILOT_NODE_ID}"
: "${NODEPILOT_AGENT_TOKEN:?Set NODEPILOT_AGENT_TOKEN}"

REPO_URL="${NODEPILOT_REPO_URL:-https://github.com/muerfox/Node-Pilot.git}"
INSTALL_DIR="/opt/nodepilot-agent"

echo "==> Installing system packages"
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip git \
    libvirt-dev pkg-config gcc \
    qemu-utils genisoimage lvm2

echo "==> Creating the nodepilot system user"
if ! id nodepilot >/dev/null 2>&1; then
    useradd --system --home /var/lib/nodepilot --shell /usr/sbin/nologin nodepilot
fi
usermod -aG libvirt,kvm,disk nodepilot

echo "==> Fetching NodePilot"
mkdir -p "$INSTALL_DIR"
if [[ -d "$INSTALL_DIR/src/.git" ]]; then
    git -C "$INSTALL_DIR/src" pull --ff-only
else
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR/src"
fi

echo "==> Installing the agent into a virtualenv"
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/.venv/bin/pip" install -e "$INSTALL_DIR/src/agent[libvirt]" -q
ln -sf "$INSTALL_DIR/.venv/bin/nodepilot-agent" /usr/local/bin/nodepilot-agent

echo "==> Writing configuration"
mkdir -p /etc/nodepilot /var/lib/nodepilot/pools /var/lib/nodepilot/cloud-init
chown -R nodepilot:nodepilot /var/lib/nodepilot

cat > /etc/nodepilot/agent.yaml <<EOF
controller_url: ${NODEPILOT_CONTROLLER_URL}
node_id: ${NODEPILOT_NODE_ID}
agent_token: ${NODEPILOT_AGENT_TOKEN}
EOF
chmod 600 /etc/nodepilot/agent.yaml
chown nodepilot:nodepilot /etc/nodepilot/agent.yaml

echo "==> Installing the systemd unit"
cp "$INSTALL_DIR/src/agent/systemd/nodepilot-agent.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now nodepilot-agent

echo "==> Done. Check status with: systemctl status nodepilot-agent"

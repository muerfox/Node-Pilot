# Development-only agent container. Runs the transport/heartbeat loop
# against nodepilot-web for integration testing WITHOUT libvirt-python
# installed -- libvirt-dependent operations (CREATE_VM, START_VM, ...)
# will fail with a clear LibvirtUnavailable error, which is expected: a
# real deployment installs this package directly on a KVM hypervisor
# (see agent/systemd/nodepilot-agent.service), never in a container.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    qemu-utils \
    genisoimage \
    iproute2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/agent

COPY agent/requirements.txt .
RUN pip install -r requirements.txt

COPY agent/ .
RUN pip install -e .

CMD ["nodepilot-agent"]

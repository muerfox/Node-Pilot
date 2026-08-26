"""
NFS-backed storage. Mount lifecycle (mounting the export at pool_path) is
a node provisioning concern handled outside the agent's hot path (via
/etc/fstab or a systemd .mount unit set up when the pool is registered) --
once mounted, an NFS pool behaves exactly like a directory pool.
"""
from __future__ import annotations

from nodepilot_agent.storage.directory import DirectoryBackend


class NFSBackend(DirectoryBackend):
    pass

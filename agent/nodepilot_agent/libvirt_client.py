"""
Thin, typed wrapper around libvirt-python. Nothing outside this module
(and nodepilot_agent.metrics, for read-only stats) touches the `libvirt`
package directly -- that keeps the rest of the agent testable without a
real hypervisor and gives us one place to translate libvirt's exceptions
into something the operation handlers can reason about.

The import is guarded: the agent can start and answer non-libvirt
operations (e.g. a plain host-info probe of a non-KVM box during initial
bring-up) without libvirt-python installed. Any call that actually needs
it raises a clear LibvirtUnavailable error instead of an ImportError deep
in a stack trace.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from xml.sax.saxutils import escape as _escape

logger = logging.getLogger("nodepilot_agent.libvirt")

try:
    import libvirt  # type: ignore

    LIBVIRT_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only on hosts without libvirt-python
    libvirt = None
    LIBVIRT_AVAILABLE = False


class LibvirtUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("libvirt-python is not installed on this host; install the 'libvirt' extra to manage VMs.")


class LibvirtOperationError(RuntimeError):
    pass


def _require_libvirt() -> None:
    if not LIBVIRT_AVAILABLE:
        raise LibvirtUnavailable()


class LibvirtClient:
    """One instance per agent process, holding a single libvirt
    connection (libvirt handles internal thread-safety for us)."""

    def __init__(self, uri: str = "qemu:///system"):
        self.uri = uri
        self._conn = None

    def connect(self):
        _require_libvirt()
        if self._conn is None or not self._conn.isAlive():
            try:
                self._conn = libvirt.open(self.uri)
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"Failed to connect to libvirt at {self.uri}: {exc}") from exc
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @contextmanager
    def domain(self, domain_uuid: str):
        conn = self.connect()
        try:
            dom = conn.lookupByUUIDString(domain_uuid)
        except libvirt.libvirtError as exc:
            raise LibvirtOperationError(f"No domain with uuid {domain_uuid}: {exc}") from exc
        yield dom

    # -- Domain lifecycle -----------------------------------------------

    def define_domain(self, domain_xml: str) -> str:
        conn = self.connect()
        try:
            dom = conn.defineXML(domain_xml)
        except libvirt.libvirtError as exc:
            raise LibvirtOperationError(f"defineXML failed: {exc}") from exc
        return dom.UUIDString()

    def undefine_domain(self, domain_uuid: str, *, remove_storage: bool = False) -> None:
        with self.domain(domain_uuid) as dom:
            try:
                if dom.isActive():
                    dom.destroy()
                flags = 0
                if remove_storage and hasattr(libvirt, "VIR_DOMAIN_UNDEFINE_MANAGED_SAVE"):
                    flags |= libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE
                    flags |= getattr(libvirt, "VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA", 0)
                dom.undefineFlags(flags) if flags else dom.undefine()
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"undefine failed: {exc}") from exc

    def start_domain(self, domain_uuid: str) -> None:
        with self.domain(domain_uuid) as dom:
            try:
                if not dom.isActive():
                    dom.create()
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"start failed: {exc}") from exc

    def graceful_shutdown(self, domain_uuid: str) -> None:
        with self.domain(domain_uuid) as dom:
            try:
                if dom.isActive():
                    dom.shutdown()
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"shutdown failed: {exc}") from exc

    def force_stop(self, domain_uuid: str) -> None:
        with self.domain(domain_uuid) as dom:
            try:
                if dom.isActive():
                    dom.destroy()
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"destroy failed: {exc}") from exc

    def reboot(self, domain_uuid: str) -> None:
        with self.domain(domain_uuid) as dom:
            try:
                dom.reboot()
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"reboot failed: {exc}") from exc

    def reset(self, domain_uuid: str) -> None:
        with self.domain(domain_uuid) as dom:
            try:
                dom.reset()
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"reset failed: {exc}") from exc

    def suspend(self, domain_uuid: str) -> None:
        with self.domain(domain_uuid) as dom:
            try:
                dom.suspend()
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"pause failed: {exc}") from exc

    def resume(self, domain_uuid: str) -> None:
        with self.domain(domain_uuid) as dom:
            try:
                dom.resume()
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"resume failed: {exc}") from exc

    def domain_info(self, domain_uuid: str) -> dict:
        with self.domain(domain_uuid) as dom:
            state, max_mem, mem, cpus, cpu_time = dom.info()
            return {
                "state": _DOMAIN_STATE_NAMES.get(state, "UNKNOWN"),
                "max_memory_kb": max_mem,
                "memory_kb": mem,
                "cpu_count": cpus,
                "cpu_time_ns": cpu_time,
            }

    def attach_device(self, domain_uuid: str, device_xml: str, *, live: bool = True, persistent: bool = True) -> None:
        with self.domain(domain_uuid) as dom:
            flags = 0
            if persistent:
                flags |= libvirt.VIR_DOMAIN_AFFECT_CONFIG
            if live and dom.isActive():
                flags |= libvirt.VIR_DOMAIN_AFFECT_LIVE
            try:
                dom.attachDeviceFlags(device_xml, flags)
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"attach device failed: {exc}") from exc

    def detach_device(self, domain_uuid: str, device_xml: str, *, live: bool = True, persistent: bool = True) -> None:
        with self.domain(domain_uuid) as dom:
            flags = 0
            if persistent:
                flags |= libvirt.VIR_DOMAIN_AFFECT_CONFIG
            if live and dom.isActive():
                flags |= libvirt.VIR_DOMAIN_AFFECT_LIVE
            try:
                dom.detachDeviceFlags(device_xml, flags)
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"detach device failed: {exc}") from exc

    # -- Snapshots --------------------------------------------------------

    def create_snapshot(self, domain_uuid: str, name: str, description: str = "") -> str:
        with self.domain(domain_uuid) as dom:
            xml = f"<domainsnapshot><name>{_escape(name)}</name><description>{_escape(description)}</description></domainsnapshot>"
            try:
                snap = dom.snapshotCreateXML(xml, 0)
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"snapshot create failed: {exc}") from exc
            return snap.getName()

    def delete_snapshot(self, domain_uuid: str, name: str) -> None:
        with self.domain(domain_uuid) as dom:
            try:
                snap = dom.snapshotLookupByName(name, 0)
                snap.delete(0)
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"snapshot delete failed: {exc}") from exc

    def rollback_snapshot(self, domain_uuid: str, name: str) -> None:
        with self.domain(domain_uuid) as dom:
            try:
                snap = dom.snapshotLookupByName(name, 0)
                dom.revertToSnapshot(snap, 0)
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"snapshot rollback failed: {exc}") from exc

    # -- Host info --------------------------------------------------------

    def host_info(self) -> dict:
        conn = self.connect()
        model, memory_mb, cpus, mhz, nodes, sockets, cores, threads = conn.getInfo()
        return {
            "cpu_model": model,
            "memory_total_mb": memory_mb,
            "cpu_count": cpus,
            "cpu_mhz": mhz,
            "cpu_sockets": sockets,
            "cpu_cores": cores,
            "cpu_threads": threads,
            "hypervisor_type": conn.getType(),
            "libvirt_version": conn.getLibVersion(),
        }

    def domain_stats(self, domain_uuid: str) -> dict:
        """CPU/memory/disk/network stats for a single running domain,
        used by nodepilot_agent.metrics -- never fabricated (rule 2)."""
        with self.domain(domain_uuid) as dom:
            if not dom.isActive():
                return {}
            try:
                cpu_stats = dom.getCPUStats(True)
                mem_stats = dom.memoryStats()
            except libvirt.libvirtError as exc:
                raise LibvirtOperationError(f"stats failed: {exc}") from exc
            return {"cpu": cpu_stats, "memory": mem_stats}


_DOMAIN_STATE_NAMES = {
    0: "NOSTATE",
    1: "RUNNING",
    2: "BLOCKED",
    3: "PAUSED",
    4: "SHUTDOWN",
    5: "SHUTOFF",
    6: "CRASHED",
    7: "PMSUSPENDED",
}
